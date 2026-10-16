import json
from types import SimpleNamespace
from urllib.error import HTTPError
import unittest
from unittest.mock import MagicMock, patch

from services import ollama_json as module


class OllamaJSONTests(unittest.TestCase):
    def call(self, payload):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        with patch.object(module, "urlopen", return_value=response) as request:
            result = module.OllamaJSONClient("test-model").invoke([SimpleNamespace(type="human", content="Câu hỏi")])
            body = json.loads(request.call_args.args[0].data)
            self.assertFalse(body["stream"])
            self.assertFalse(body["think"])
            self.assertEqual(body["messages"], [{"role": "user", "content": "Câu hỏi"}])
            self.assertGreater(request.call_args.kwargs["timeout"], 0)
            return result

    def test_returns_only_final_content(self):
        result = self.call({"done": True, "done_reason": "stop", "message": {"content": '{"issues": []}', "thinking": "private"}})
        self.assertEqual(result.content, '{"issues": []}')

    def test_truncated_or_reasoning_only_is_not_an_answer(self):
        for payload in [{"done": True, "done_reason": "length", "message": {"content": "{}"}},
                        {"done": True, "message": {"thinking": "private", "content": ""}},
                        {"done": False, "message": {"content": "{}"}}, []]:
            with self.assertRaises(ValueError):
                self.call(payload)

    def test_provider_body_and_credentials_not_in_error(self):
        with patch.object(module, "urlopen", side_effect=HTTPError("https://secret:token@host", 503, "private payload", {}, None)):
            with self.assertRaisesRegex(RuntimeError, "^JSON provider HTTP status 503$"):
                module.OllamaJSONClient().invoke([])
