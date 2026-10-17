import unittest

from langchain_core.documents import Document
from services.hybrid_retrieval import IdentifierIndex, merge_results


class IdentifierRetrievalTests(unittest.TestCase):
    def test_definition_and_multiple_field_matches_beat_repeated_call_sites(self):
        body = Document(page_content="function deadline_window() { started_at + duration; min(ends_at); }")
        calls = [Document(page_content=f"case action_{i}: deadline_window(); ends_at;", metadata={"source_path": str(i)}) for i in range(8)]
        index = IdentifierIndex([*calls, body])
        self.assertEqual(index.search("started_at duration ends_at deadline_window", 1), [body])
        merged = merge_results(calls[:4], index.search("started_at duration ends_at", 4), 4)
        self.assertIn(body, merged)
        self.assertIn(calls[0], merged)

    def test_no_ascii_identifier_matches_keeps_semantic_results(self):
        doc = Document(page_content="Học liệu cho học sinh.")
        index = IdentifierIndex([doc])
        self.assertEqual(index.search("Hiệu quả học tập?", 3), [])
        self.assertEqual(merge_results([doc], [], 3), [doc])

    def test_duplicate_results_are_not_returned_twice(self):
        doc = Document(page_content="unique_function", metadata={"source_path": "a.md"})
        self.assertEqual(merge_results([doc], [doc], 4), [doc])
