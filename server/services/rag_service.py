import logging
import os
import hashlib
from functools import wraps
from threading import RLock
from pathlib import Path
from typing import Any, List

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from chromadb.config import Settings as ChromaSettings

from config import settings
from services.vocab_bias import extract_terms, store_vocab

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "project_docs"
_CHUNK_SIZE = 1000
_CHUNK_OVERLAP = 150

# Supported code and document file extensions for tech hackathons / project competitions
_SUPPORTED_TEXT_EXTS = {
    ".md", ".txt", ".rst",
    ".cs", ".py", ".ts", ".js", ".json", ".sql", ".yaml", ".yml",
    ".html", ".css", ".sh", ".ps1", ".env.example"
}

# Directories to skip when scanning a codebase
_IGNORE_DIRS = {
    "node_modules", ".git", ".vs", ".vscode", "bin", "obj",
    "__pycache__", ".venv", "venv", "dist", "build", "data"
}


def _serialized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


class RAGService:
    """Manages document ingestion, codebase indexing, and retrieval via ChromaDB."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._embeddings = OllamaEmbeddings(
            base_url=settings.ollama_embedding_base_url or settings.ollama_base_url,
            model="nomic-embed-text",
        )
        self._persist_dir = settings.chroma_persist_dir
        os.makedirs(self._persist_dir, exist_ok=True)
        self._pending_write = Path(self._persist_dir) / ".index-write-pending"
        self._vectorstore: Chroma | None = None
        self._indexed_files: set[str] = set()
        self._load_existing_store()

    def _load_existing_store(self) -> None:
        """Attempt to load an existing ChromaDB collection from disk."""
        try:
            self._vectorstore = Chroma(
                collection_name=_COLLECTION_NAME,
                embedding_function=self._embeddings,
                persist_directory=self._persist_dir,
                # ChromaDB phones home by default. Disable it explicitly here so it
                # does not depend on the environment of the wrapper. is_persistent
                # must be set too, otherwise the wrapper builds an in-memory client.
                client_settings=ChromaSettings(is_persistent=True, anonymized_telemetry=False),
            )
            count = self._vectorstore._collection.count()
            self._indexed_files = {metadata.get("source_path", "") for metadata in
                                   self._vectorstore._collection.get(include=["metadatas"])["metadatas"]
                                   if metadata}
            self._indexed_files.discard("")
            logger.info("Loaded ChromaDB collection '%s' with %d chunks", _COLLECTION_NAME, count)
        except Exception:
            logger.warning("Could not load ChromaDB store, will create on first ingest")
            self._vectorstore = None

    def verify_path(self, target_path: str) -> dict[str, Any]:
        """Validates existence, read permissions, and counts indexable files."""
        p = Path(target_path).resolve()
        if not p.exists():
            return {"valid": False, "error": f"Path does not exist: {p}"}

        if not os.access(str(p), os.R_OK):
            return {"valid": False, "error": f"Permission denied (no read access): {p}"}

        candidate_files: list[str] = []
        if p.is_file():
            if p.suffix.lower() == ".pdf" or p.suffix.lower() in _SUPPORTED_TEXT_EXTS:
                candidate_files.append(str(p))
        else:
            for root, dirs, files in os.walk(str(p)):
                dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS and not d.startswith(".")]
                for file in files:
                    ext = Path(file).suffix.lower()
                    if ext == ".pdf" or ext in _SUPPORTED_TEXT_EXTS:
                        candidate_files.append(os.path.join(root, file))

        return {
            "valid": True,
            "resolved_path": str(p),
            "is_dir": p.is_dir(),
            "total_files": len(candidate_files),
            "sample_files": [Path(f).name for f in candidate_files[:8]],
        }

    def _load_documents_from_path(self, target_path: str) -> tuple[list, set[str]]:
        """Loads all supported files from path with robust exception handling."""
        p = Path(target_path).resolve()
        all_docs: list = []
        indexed_files: set[str] = set()

        def _try_load_file(fpath: Path) -> None:
            if fpath.is_symlink():
                return
            ext = fpath.suffix.lower()
            try:
                if ext == ".pdf":
                    loader = PyPDFLoader(str(fpath))
                    docs = loader.load()
                elif ext in _SUPPORTED_TEXT_EXTS:
                    loader = TextLoader(str(fpath), encoding="utf-8", autodetect_encoding=True)
                    docs = loader.load()
                else:
                    return

                for doc in docs:
                    doc.metadata["source_name"] = fpath.name
                    doc.metadata["source_path"] = str(fpath)
                all_docs.extend(docs)
                indexed_files.add(str(fpath))
            except Exception as exc:
                # A failed scan must not delete last-known content as if the
                # unreadable file had been intentionally removed.
                raise RuntimeError(f"Could not read indexed file: {fpath.name}") from exc

        if p.is_file():
            _try_load_file(p)
        elif p.is_dir():
            def scan_error(error):
                raise error
            for root, dirs, files in os.walk(str(p), onerror=scan_error):
                dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS and not d.startswith(".")]
                for file in files:
                    fpath = Path(root) / file
                    if fpath.suffix.lower() == ".pdf" or fpath.suffix.lower() in _SUPPORTED_TEXT_EXTS:
                        _try_load_file(fpath)

        return all_docs, indexed_files

    @_serialized
    def ingest_documents(self, target_path: str) -> dict[str, Any]:
        """Loads, splits, embeds, and stores documents from target_path into ChromaDB."""
        logger.info("Ingesting documents from: %s", target_path)
        target = Path(target_path).resolve()
        if not target.exists():
            raise ValueError("Ingestion path does not exist")
        if self._pending_write.exists():
            raise RuntimeError("Index update was interrupted; clear and rebuild the index")
        raw_docs, indexed_files = self._load_documents_from_path(target_path)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=_CHUNK_SIZE,
            chunk_overlap=_CHUNK_OVERLAP,
            separators=["\n\n", "\n", ";", ".", " ", ""],
        )
        chunks = splitter.split_documents(raw_docs)
        logger.info("Split %d documents into %d chunks", len(raw_docs), len(chunks))
        if self._vectorstore is None:
            self._load_existing_store()
        if self._vectorstore is None:
            raise RuntimeError("Chroma collection is unavailable")

        # Replace each indexed file instead of appending duplicate chunks on every run.
        # Stable IDs allow Chroma to keep unchanged chunks across repeated ingestion.
        ids: list[str] = []
        for chunk in chunks:
            source = chunk.metadata["source_path"]
            page = chunk.metadata.get("page", 0)
            content_hash = hashlib.sha256(chunk.page_content.encode("utf-8")).hexdigest()
            chunk.metadata["citation"] = f"{chunk.metadata['source_name']}:{int(page) + 1}" if "page" in chunk.metadata else chunk.metadata["source_name"]
            ids.append(hashlib.sha256(f"{source}:{page}:{content_hash}".encode("utf-8")).hexdigest())

        existing = self._vectorstore._collection.get(include=["metadatas"])
        def belongs_to_scope(metadata):
            if not metadata or not metadata.get("source_path"):
                return False
            source = Path(metadata["source_path"])
            return source.is_relative_to(target) if target.is_dir() else source == target

        old_ids = [doc_id for doc_id, metadata in zip(existing["ids"], existing["metadatas"])
                   if belongs_to_scope(metadata)]
        # Duplicate content within a file is represented once per source and page.
        unique = {doc_id: chunk for doc_id, chunk in zip(ids, chunks)}
        stale_ids = list(set(old_ids) - set(unique))
        if unique or stale_ids:
            # Durable marker: after an interrupted or failed mutation, refuse
            # retrieval even after restart rather than expose mixed versions.
            self._pending_write.write_text("Index mutation in progress; clear and rebuild after interruption.", encoding="utf-8")
            if unique:
                self._vectorstore.add_documents(list(unique.values()), ids=list(unique))
            if stale_ids:
                self._vectorstore._collection.delete(ids=stale_ids)
            refreshed = self._vectorstore._collection.get(include=["metadatas"])
            self._indexed_files = {m["source_path"] for m in refreshed["metadatas"] if m and m.get("source_path")}
            self._pending_write.unlink()

        self.rebuild_vocab()

        return {
            "status": "success",
            "chunks_ingested": len(unique),
            "files_indexed": len(indexed_files),
            "chunks_removed": len(stale_ids),
            "target_path": target_path
        }

    @_serialized
    def rebuild_vocab(self) -> dict[str, Any]:
        """Mine technical terms from the indexed chunks for Whisper biasing.

        Prose documents (markdown/text) give far better spoken terms than source
        code, so they are preferred when there are enough of them.
        """
        if settings.vocab_bias_terms <= 0:
            return {"terms": 0}
        if self._vectorstore is None:
            self._load_existing_store()
        if self._vectorstore is None:
            return {"terms": 0}
        try:
            payload = self._vectorstore._collection.get(include=["documents", "metadatas"])
        except Exception:
            logger.exception("Could not read chunks for the vocabulary")
            return {"terms": 0}
        documents = payload.get("documents") or []
        metadatas = payload.get("metadatas") or []
        doc_suffixes = (".md", ".txt", ".rst")
        prose = [text for text, meta in zip(documents, metadatas)
                 if isinstance(meta, dict) and str(meta.get("source_name", "")).lower().endswith(doc_suffixes)]
        source = prose if len(prose) >= 20 else documents
        terms = extract_terms(source, limit=settings.vocab_bias_terms)
        store_vocab(settings.vocab_file, terms)
        logger.info("Vocabulary bias: %d terms mined from %d/%d chunks",
                    len(terms), len(source), len(documents))
        return {"terms": len(terms)}

    @_serialized
    def clear_store(self) -> bool:
        """Clears the collection so new documents can be ingested fresh."""
        try:
            if self._pending_write.exists() and self._vectorstore is None:
                self._load_existing_store()
                if self._vectorstore is None:
                    return False
            if self._vectorstore is not None:
                self._vectorstore.delete_collection()
                self._vectorstore = None
                self._indexed_files.clear()
                logger.info("ChromaDB collection cleared")
            self._pending_write.unlink(missing_ok=True)
            return True
        except Exception as exc:
            logger.exception("Failed to clear vector store: %s", exc)
            return False

    @_serialized
    def get_stats(self) -> dict[str, Any]:
        """Returns statistics about the current vector collection."""
        count = 0
        if self._vectorstore is not None:
            try:
                count = self._vectorstore._collection.count()
            except Exception:
                count = 0

        return {
            "collection_name": _COLLECTION_NAME,
            "total_chunks": count,
            "indexed_files_count": len(self._indexed_files),
            "persist_directory": self._persist_dir,
            "index_state": "needs_rebuild" if self._pending_write.exists() else "ready",
        }

    @_serialized
    def query(self, question: str, top_k: int = 4) -> List[str]:
        """Retrieve the top-k relevant document chunks for question."""
        if self._pending_write.exists():
            raise RuntimeError("Index update incomplete; clear and rebuild before answering")
        if self._vectorstore is None:
            raise RuntimeError("Retrieval store unavailable")

        try:
            results = self._vectorstore.similarity_search(question, k=top_k)
            chunks = []
            for doc in results:
                citation = doc.metadata.get("citation", doc.metadata.get("source_name", ""))
                header = f"[{citation}] " if citation else ""
                chunks.append(f"{header}{doc.page_content}")
            return chunks
        except Exception:
            logger.exception("RAG query failed")
            raise RuntimeError("Document retrieval failed") from None
