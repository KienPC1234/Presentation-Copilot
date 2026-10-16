"""Real local Chroma lifecycle with deterministic embeddings; no model/network."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

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
