import unittest

from langchain_core.documents import Document
from services.evidence_chunks import split_case_scopes


class EvidenceChunkTests(unittest.TestCase):
    def test_preserves_text_and_separates_status_commit_and_new_source_section(self):
        text = "Intro\ncase 'status':\n return completed;\ncase 'commit':\n return replayed;\n## Other source\nUnrelated facts.\n"
        parts = split_case_scopes([Document(page_content=text, metadata={"source_path": "/docs/sample.md"})])
        self.assertEqual("".join(p.page_content for p in parts), text)
        scopes = {p.metadata.get("scope_hint"): p.page_content for p in parts if p.metadata.get("scope_hint")}
        self.assertIn("completed", scopes["switch case status"])
        self.assertNotIn("replayed", scopes["switch case status"])
        self.assertNotIn("Unrelated", scopes["switch case commit"])
        self.assertTrue(all(p.metadata["source_path"] == "/docs/sample.md" for p in parts))

    def test_default_is_not_attributed_to_previous_named_case(self):
        text = 'case "read":\n return 1;\ndefault:\n return 0;'
        parts = split_case_scopes([Document(page_content=text)])
        self.assertEqual([p.metadata["scope_hint"] for p in parts], ["switch case read", "switch case default"])
        self.assertEqual("".join(p.page_content for p in parts), text)

    def test_plain_text_is_unchanged(self):
        original = Document(page_content="General discussion of case studies.")
        self.assertEqual(split_case_scopes([original]), [original])
