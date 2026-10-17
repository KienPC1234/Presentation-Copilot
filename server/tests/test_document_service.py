"""Exercise document rendering and caching without model or vector providers."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


class _Msg:
    def __init__(self, content):
        self.content = content


def load_document_module(export_dir: str):
    stub_settings = SimpleNamespace(export_dir=export_dir, ollama_answer_model="",
                                    ollama_model="test-model")
    exports = {
        "config": {"settings": stub_settings},
        "langchain_core.messages": {"HumanMessage": _Msg, "SystemMessage": _Msg},
    }
    modules = {}
    for name, values in exports.items():
        stub = ModuleType(name)
        stub.__dict__.update(values)
        modules[name] = stub
    spec = importlib.util.spec_from_file_location(
        "document_under_test", Path(__file__).parents[1] / "services/document_service.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class FakeRAG:
    def __init__(self, chunks):
        self._chunks = chunks
        self.ingested = []

    def query(self, question, top_k=4):
        return list(self._chunks)

    def get_stats(self):
        return {"total_chunks": 5, "index_state": "ready"}


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return SimpleNamespace(content=json.dumps(self.payload))


class FakeDefense:
    def __init__(self):
        self.calls = 0

    def prepare(self, topic, focus, count, language):
        self.calls += 1
        return {
            "topic": topic, "language": language,
            "questions": [{
                "id": "q1", "category": "product", "question": "Who is it for?",
                "purpose": "Explain user value", "follow_up": "What proof exists?",
                "answer_outline": ["Check the documented user task"],
                "evidence_ids": ["e1"], "evidence_status": "cited",
                "proof_needed": ["Prepare the 88-sample precision/recall figure"],
                "pitfall": "Đừng khẳng định chặn mọi cuộc gọi lừa đảo.",
                "follow_ups": ["Bộ mẫu được dán nhãn thế nào?"],
            }],
            "evidence": [{"id": "e1", "excerpt": "[readme.md] Project fact"}],
        }


def pack_payload(evidence_ids=("e1",)):
    return {
        "rebuttal": [{"question_id": "q1", "objection": "Cost",
                      "answer_points": ["Cite the measured cost"],
                      "evidence_ids": list(evidence_ids), "fallback": "Say it is not measured",
                      "closing": "Số liệu nằm trong tài liệu, tôi kiểm tra lại sau.",
                      "second_followup": "Nếu hỏi tiếp về thời điểm đo, nói rõ chưa đo lúc tải cao."}],
        "outline": [{"title": "Demo", "points": ["Show the login flow"],
                     "evidence_ids": list(evidence_ids), "timing": "2 phút"}],
        "cheatsheet": {"key_numbers": ["5 chunks"], "key_terms": ["latency"],
                       "one_liners": [{"question": "Who?", "answer": "Students",
                                       "evidence_ids": list(evidence_ids)}]},
        "rehearsal": {"timeline": [{"minutes": 2, "focus": "Mở đầu và vấn đề"}],
                      "risky_claims": ["Đừng khẳng định chặn 100% lừa đảo"],
                      "checklist": ["Chuẩn bị bộ 88 mẫu trước khi lên"]},
    }


class FlakyFakeLLM:
    """Fails the combined call (like a truncated response) but succeeds per section."""

    def __init__(self):
        self.calls = []

    def invoke(self, messages):
        human = json.loads(messages[-1].content)
        sections = human["sections"]
        self.calls.append(sections)
        if len(sections) > 1:
            raise ValueError("Incomplete JSON provider response")
        payload = pack_payload()
        return SimpleNamespace(content=json.dumps({key: payload[key] for key in sections}))


class DocumentServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.module = load_document_module(self._tmp.name)
        self.rag = FakeRAG(["[readme.md] Project fact"])

    def tearDown(self):
        self._tmp.cleanup()

    def make_service(self, payload=None):
        llm = FakeLLM(payload if payload is not None else pack_payload())
        service = self.module.DocumentService(self.rag, llm=llm,
                                              defense_factory=lambda: FakeDefense())
        return service, llm

    def test_generates_bundle_and_manifest_for_requested_kinds(self):
        service, _ = self.make_service()
        result = service.generate("Online learning platform", kinds=["qa", "rebuttal", "evidence"])
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["cached"])
        self.assertIn("Who is it for?", result["markdown"])
        bundle = Path(result["bundle_dir"])
        self.assertTrue((bundle / "defense-pack.md").exists())
        self.assertTrue((bundle / "manifest.json").exists())
        self.assertEqual(result["document_origin"], "ai_generated_preparation")
        self.assertEqual({f["kind"] for f in result["files"]}, {"qa", "rebuttal", "evidence"})

    def test_second_request_is_served_from_cache_without_calling_the_model(self):
        service, llm = self.make_service()
        first = service.generate("Online learning platform", kinds=["qa", "rebuttal"])
        calls_after_first = llm.calls
        second = service.generate("Online learning platform", kinds=["qa", "rebuttal"])
        self.assertTrue(second["cached"])
        self.assertEqual(second["cache_key"], first["cache_key"])
        self.assertEqual(llm.calls, calls_after_first)

    def test_force_bypasses_the_cache(self):
        service, _ = self.make_service()
        service.generate("Online learning platform", kinds=["qa", "rebuttal"])
        forced = service.generate("Online learning platform", kinds=["qa", "rebuttal"], force=True)
        self.assertFalse(forced["cached"])

    def test_forged_evidence_marks_the_section_partial(self):
        service, _ = self.make_service(pack_payload(evidence_ids=("forged",)))
        result = service.generate("Online learning platform", kinds=["qa", "rebuttal"])
        self.assertEqual(result["status"], "partial")
        self.assertIn("rebuttal", result["missing_sections"])
        self.assertIn(self.module._LABELS["vi"]["section_failed"], result["markdown"])

    def test_evidence_only_request_skips_the_model(self):
        service, llm = self.make_service()
        result = service.generate("Online learning platform", kinds=["evidence"])
        self.assertEqual(result["status"], "success")
        self.assertEqual(llm.calls, 0)

    def test_rebuttal_without_qa_still_prepares_questions(self):
        service, llm = self.make_service()
        result = service.generate("Online learning platform", kinds=["rebuttal"])
        self.assertEqual(result["status"], "success")
        self.assertEqual({f["kind"] for f in result["files"]}, {"rebuttal"})
        self.assertEqual(result["questions_count"], 1)
        self.assertEqual(llm.calls, 1)

    def test_kind_order_does_not_change_the_cache_key(self):
        service, _ = self.make_service()
        first = service.generate("Online learning platform", kinds=["evidence", "qa"])
        second = service.generate("Online learning platform", kinds=["qa", "evidence"])
        self.assertTrue(second["cached"])
        self.assertEqual(first["cache_key"], second["cache_key"])

    def test_full_pack_renders_the_deeper_sections(self):
        service, _ = self.make_service()
        result = service.generate("Online learning platform",
                                  kinds=["qa", "rebuttal", "outline", "cheatsheet", "rehearsal"])
        self.assertEqual(result["status"], "success")
        self.assertEqual({f["kind"] for f in result["files"]},
                         {"qa", "rebuttal", "outline", "cheatsheet", "rehearsal"})
        markdown = result["markdown"]
        for marker in (self.module._LABELS["vi"]["proof"],
                       self.module._LABELS["vi"]["pitfall"],
                       self.module._LABELS["vi"]["followups"],
                       self.module._LABELS["vi"]["closing"],
                       self.module._LABELS["vi"]["rehearsal"],
                       self.module._LABELS["vi"]["risky"]):
            self.assertIn(marker, markdown)
        self.assertIn("88 mẫu", markdown)

    def test_missing_sections_are_retried_with_focused_calls(self):
        llm = FlakyFakeLLM()
        service = self.module.DocumentService(self.rag, llm=llm,
                                              defense_factory=lambda: FakeDefense())
        result = service.generate("Online learning platform",
                                  kinds=["qa", "rebuttal", "outline", "cheatsheet"])
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["missing_sections"], [])
        self.assertEqual(llm.calls[0], ["rebuttal", "outline", "cheatsheet"])
        self.assertEqual({tuple(call) for call in llm.calls[1:]},
                         {("rebuttal",), ("outline",), ("cheatsheet",)})

    def test_list_read_and_delete(self):
        service, _ = self.make_service()
        result = service.generate("Online learning platform", kinds=["qa"])
        listed = service.list_documents()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["cache_key"], result["cache_key"])
        self.assertIn("Who is it for?", service.read_document(result["cache_key"]))
        self.assertTrue(service.delete_document(result["cache_key"]))
        self.assertEqual(service.list_documents(), [])

    def test_invalid_kind_and_short_topic_are_rejected(self):
        service, _ = self.make_service()
        with self.assertRaises(ValueError):
            service.generate("ab", kinds=["qa"])
        with self.assertRaises(ValueError):
            service.generate("Online learning platform", kinds=["nonsense"])
        with self.assertRaises(ValueError):
            service.generate("Online learning platform", kinds=[])


if __name__ == "__main__":
    unittest.main()
