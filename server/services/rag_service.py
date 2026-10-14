import logging
import os
from pathlib import Path
from typing import Any, List

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma

from config import settings

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


class RAGService:
    """Manages document ingestion, codebase indexing, and retrieval via ChromaDB."""

    def __init__(self) -> None:
        self._embeddings = OllamaEmbeddings(
            base_url=settings.ollama_base_url,
            model="nomic-embed-text",
        )
        self._persist_dir = settings.chroma_persist_dir
        os.makedirs(self._persist_dir, exist_ok=True)
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
            )
            count = self._vectorstore._collection.count()
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
                logger.warning("Could not read file %s: %s", fpath, exc)

        if p.is_file():
            _try_load_file(p)
        elif p.is_dir():
            for root, dirs, files in os.walk(str(p)):
                dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS and not d.startswith(".")]
                for file in files:
                    fpath = Path(root) / file
                    if fpath.suffix.lower() == ".pdf" or fpath.suffix.lower() in _SUPPORTED_TEXT_EXTS:
                        _try_load_file(fpath)

        return all_docs, indexed_files

    def ingest_documents(self, target_path: str) -> dict[str, Any]:
        """Loads, splits, embeds, and stores documents from target_path into ChromaDB."""
        logger.info("Ingesting documents from: %s", target_path)
        raw_docs, indexed_files = self._load_documents_from_path(target_path)

        if not raw_docs:
            logger.warning("No readable documents found in %s", target_path)
            return {"chunks_ingested": 0, "files_indexed": 0, "status": "No documents found"}

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=_CHUNK_SIZE,
            chunk_overlap=_CHUNK_OVERLAP,
            separators=["\n\n", "\n", ";", ".", " ", ""],
        )
        chunks = splitter.split_documents(raw_docs)
        logger.info("Split %d documents into %d chunks", len(raw_docs), len(chunks))

        self._vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=self._embeddings,
            collection_name=_COLLECTION_NAME,
            persist_directory=self._persist_dir,
        )
        self._indexed_files = indexed_files

        return {
            "status": "success",
            "chunks_ingested": len(chunks),
            "files_indexed": len(indexed_files),
            "target_path": target_path
        }

    def clear_store(self) -> bool:
        """Clears the collection so new documents can be ingested fresh."""
        try:
            if self._vectorstore is not None:
                self._vectorstore.delete_collection()
                self._vectorstore = None
                self._indexed_files.clear()
                logger.info("ChromaDB collection cleared")
            return True
        except Exception as exc:
            logger.exception("Failed to clear vector store: %s", exc)
            return False

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
        }

    def query(self, question: str, top_k: int = 4) -> List[str]:
        """Retrieve the top-k relevant document chunks for question."""
        if self._vectorstore is None:
            return []

        try:
            results = self._vectorstore.similarity_search(question, k=top_k)
            chunks = []
            for doc in results:
                src = doc.metadata.get("source_name", "")
                header = f"[{src}] " if src else ""
                chunks.append(f"{header}{doc.page_content}")
            return chunks
        except Exception:
            logger.exception("RAG query failed")
            return []
