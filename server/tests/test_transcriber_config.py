from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from services.transcriber import TranscriberService


class TranscriberConfigTests(unittest.TestCase):
    def setUp(self):
        self.service = TranscriberService.__new__(TranscriberService)
        self.service._config_lock = RLock()
        self.service._model = Mock(supported_languages=["vi", "en"])
        self.service.model_size = "actually-loaded-model"
        self.service.set_language("vi", "first prompt")

    def test_invalid_config_does_not_replace_working_config(self):
        for language, prompt in [("invalid", "x"), ("en", "x" * 2001)]:
            with self.assertRaises(ValueError):
                self.service.set_language(language, prompt)
        self.assertEqual(self.service.get_config()["language"], "vi")
        self.assertEqual(self.service.get_config()["initial_prompt"], "first prompt")

    def test_auto_and_prompt_clearing(self):
        self.service.set_language(" AUTO ", "")
        self.assertIsNone(self.service.language)
        self.assertEqual(self.service.get_config()["initial_prompt"], "")
        self.assertEqual(self.service.get_config()["model_size"], "actually-loaded-model")

    def test_request_uses_snapshot_when_config_changes(self):
        def transcribe(path, **kwargs):
            self.service.set_language("en", "next prompt")
            self.assertEqual(kwargs["language"], "vi")
            self.assertEqual(kwargs["initial_prompt"], "first prompt")
            return iter([SimpleNamespace(text=" câu hỏi ")]), SimpleNamespace(language="vi", language_probability=1.0)

        self.service._model.transcribe.side_effect = transcribe
        self.assertEqual(self.service.transcribe("public-fixture.wav"), "câu hỏi")
        self.assertEqual(self.service.get_config()["language"], "en")
