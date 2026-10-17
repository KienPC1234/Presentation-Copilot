"""The question normalizer must improve the input or fall back, never break it."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


class _Msg:
    def __init__(self, content):
        self.content = content


def load_normalizer_module():
    stub_settings = SimpleNamespace(ollama_model="test", ollama_answer_model="",
                                    llm_max_output_tokens=4096, question_normalizer_model="")
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
        "normalizer_under_test", Path(__file__).parents[1] / "services/question_normalizer.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class QuestionNormalizerTests(unittest.TestCase):
    def setUp(self):
        self.module = load_normalizer_module()

    def test_rewrites_and_reports_change(self):
        llm = Mock()
        llm.invoke.return_value.content = json.dumps(
            {"question": "Vì sao chọn FAISS thay vì pgvector?", "language": "vi"})
        result = self.module.QuestionNormalizer(llm=llm).normalize(
            "vì sao chọn phai ét thay vì pgvector vì sao chọn phai ét thay vì pgvector", "RAG")
        self.assertEqual(result["question"], "Vì sao chọn FAISS thay vì pgvector?")
        self.assertTrue(result["changed"])
        self.assertEqual(result["language"], "vi")

    def test_provider_failure_keeps_the_raw_transcript(self):
        llm = Mock()
        llm.invoke.side_effect = RuntimeError("provider down")
        result = self.module.QuestionNormalizer(llm=llm).normalize("Hỏi gì đó?")
        self.assertEqual(result["question"], "Hỏi gì đó?")
        self.assertFalse(result["changed"])

    def test_empty_answer_is_rejected(self):
        llm = Mock()
        llm.invoke.return_value.content = json.dumps({"question": "   "})
        result = self.module.QuestionNormalizer(llm=llm).normalize("Vì sao?")
        self.assertEqual(result["question"], "Vì sao?")

    def test_blank_input(self):
        result = self.module.QuestionNormalizer(llm=Mock()).normalize("   ")
        self.assertEqual(result["question"], "")

    def test_language_guess(self):
        self.assertEqual(self.module.guess_language("Vì sao chọn FAISS?"), "vi")
        self.assertEqual(self.module.guess_language("Why did you choose FAISS?"), "en")


if __name__ == "__main__":
    unittest.main()
