"""Real local Chroma lifecycle with deterministic embeddings; no model/network."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from langchain_core.documents import Document

from services import rag_service as module


class LocalEmbeddings:
    def embed_documents(self, texts):
        return [[float(len(text) % 17 + 1), 1.0, 0.5] for text in texts]

    def embed_query(self, text):
        return self.embed_documents([text])[0]


class RagLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rag-lifecycle-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.corpus = self.root / "docs"
        self.corpus.mkdir()
        self.file = self.corpus / "first.md"
        self.file.write_text("Original project evidence.", encoding="utf-8")
        self.config = patch.object(module.settings, "chroma_persist_dir", str(self.root / "vectors"))
        self.config.start()
        self.addCleanup(self.config.stop)
        self.embedding = patch.object(module, "OllamaEmbeddings", return_value=LocalEmbeddings())
        self.embedding.start()
        self.addCleanup(self.embedding.stop)
        self.rag = module.RAGService()
        self.rag.ingest_documents(str(self.corpus))

    def test_deleted_files_removed_only_inside_requested_scope(self):
        outside = self.root / "docs-other.md"
        outside.write_text("Unrelated scope retained.", encoding="utf-8")
        self.rag.ingest_documents(str(outside))
        self.file.unlink()
        result = self.rag.ingest_documents(str(self.corpus))
        self.assertEqual(result["chunks_removed"], 1)
        self.assertEqual(self.rag.get_stats()["indexed_files_count"], 1)
        self.assertEqual(len(self.rag.query("project", top_k=4)), 1)
        self.assertIn("Unrelated", self.rag.query("project")[0])

    def test_empty_file_removes_previous_content(self):
        self.file.write_text("", encoding="utf-8")
        result = self.rag.ingest_documents(str(self.file))
        self.assertEqual(result["chunks_ingested"], 0)
        self.assertEqual(result["chunks_removed"], 1)
        self.assertEqual(self.rag.query("project"), [])

    def test_failed_scan_keeps_previous_index_without_mutation(self):
        with patch.object(self.rag, "_load_documents_from_path", side_effect=RuntimeError("unreadable")):
            with self.assertRaises(RuntimeError):
                self.rag.ingest_documents(str(self.corpus))
        self.assertIn("Original", self.rag.query("project")[0])
        self.assertFalse(self.rag._pending_write.exists())

    def test_partial_write_blocks_retrieval_across_restart_until_rebuild(self):
        with patch.object(self.rag._vectorstore, "add_documents", side_effect=RuntimeError("disk failure")):
            with self.assertRaises(RuntimeError):
                self.rag.ingest_documents(str(self.corpus))
        restarted = module.RAGService()
        self.assertEqual(restarted.get_stats()["index_state"], "needs_rebuild")
        with self.assertRaises(RuntimeError):
            restarted.query("project")
        self.assertTrue(restarted.clear_store())
        restarted.ingest_documents(str(self.corpus))
        self.assertIn("Original", restarted.query("project")[0])

    def test_query_waits_until_update_completes(self):
        writing, release, query_started = Event(), Event(), Event()
        original = self.rag._vectorstore.add_documents

        def slow_write(*args, **kwargs):
            writing.set()
            if not release.wait(5):
                raise RuntimeError("Test update timed out")
            return original(*args, **kwargs)

        def query():
            query_started.set()
            return self.rag.query("project")

        with patch.object(self.rag._vectorstore, "add_documents", side_effect=slow_write):
            with ThreadPoolExecutor(max_workers=2) as pool:
                update = pool.submit(self.rag.ingest_documents, str(self.corpus))
                try:
                    self.assertTrue(writing.wait(5))
                    read = pool.submit(query)
                    self.assertTrue(query_started.wait(5))
                    self.assertFalse(read.done())
                finally:
                    release.set()
                update.result(timeout=5)
                self.assertIn("Original", read.result(timeout=5)[0])

    def test_every_split_code_chunk_keeps_its_branch_hint(self):
        self.file.write_text("case 'status':\n" + "\n".join(f"// status detail {i}" for i in range(120))
                             + "\nreturn completed;\ncase 'commit':\nreturn replayed;", encoding="utf-8")
        self.rag.ingest_documents(str(self.corpus))
        stored = self.rag._vectorstore._collection.get(include=["documents", "metadatas"])
        self.assertGreater(len(stored["documents"]), 2)
        for content, metadata in zip(stored["documents"], stored["metadatas"]):
            self.assertIn("[Lexical scope hint: " + metadata["scope_hint"] + "]", content)
            if "return replayed" in content:
                self.assertEqual(metadata["scope_hint"], "switch case commit")
            if metadata["scope_hint"] == "switch case status":
                self.assertNotIn("return replayed", content)

    def test_identifier_route_recovers_formula_when_dense_route_returns_only_calls(self):
        self.file.write_text("function deadline_window() { started_at + duration; min(ends_at); }\n" +
                             "\n".join(f"case 'action_{i}': deadline_window(); ends_at;" for i in range(8)), encoding="utf-8")
        self.rag.ingest_documents(str(self.corpus))
        stored = self.rag._vectorstore._collection.get(include=["documents", "metadatas"])
        calls = [Document(page_content=text, metadata=metadata) for text, metadata in zip(stored["documents"], stored["metadatas"])
                 if metadata.get("scope_hint")]
        with patch.object(self.rag._vectorstore, "similarity_search", return_value=calls[:4]):
            results = self.rag.query("deadline_window started_at duration ends_at", top_k=4)
        self.assertTrue(any("started_at + duration" in result for result in results))
        self.assertTrue(any("Lexical scope hint" in result for result in results))

    def test_intentional_clear_leaves_usable_empty_index(self):
        self.assertTrue(self.rag.clear_store())
        self.assertEqual(self.rag.get_stats()["index_state"], "ready")
        self.assertEqual(self.rag.query("project"), [])

    def test_unavailable_store_cannot_report_clear_success_or_ready(self):
        self.rag._vectorstore = None
        with patch.object(self.rag, "_load_existing_store", return_value=None):
            self.assertFalse(self.rag.clear_store())
        self.assertEqual(self.rag.get_stats()["index_state"], "unavailable")
