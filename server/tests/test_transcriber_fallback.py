"""Loading the speech model must never leave the server unable to transcribe."""
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


class _FakeModel:
    supported_languages = ["vi", "en"]

    def __init__(self, size, device="cpu", compute_type="int8"):
        if device != "cpu":
            raise RuntimeError("CUDA failed with error no CUDA-capable device is detected")
        self.device = device
        self.compute_type = compute_type

    def transcribe(self, path, **kwargs):  # pragma: no cover - not exercised here
        raise AssertionError("not used")


def load_transcriber(settings):
    modules = {}
    for name, values in {
        "faster_whisper": {"WhisperModel": _FakeModel},
        "config": {"settings": settings},
    }.items():
        stub = ModuleType(name)
        stub.__dict__.update(values)
        modules[name] = stub
    spec = importlib.util.spec_from_file_location(
        "transcriber_under_test", Path(__file__).parents[1] / "services/transcriber.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


def make_settings(device):
    return SimpleNamespace(whisper_model_size="tiny", whisper_device=device,
                           whisper_compute_type="float16", whisper_language="vi",
                           whisper_initial_prompt="")


class TranscriberFallbackTests(unittest.TestCase):
    def test_cuda_failure_falls_back_to_cpu(self):
        module = load_transcriber(make_settings("cuda"))
        service = module.TranscriberService()
        with self.assertLogs(module.logger, level="WARNING"):
            service.ensure_loaded()
        self.assertTrue(service.is_model_loaded())
        self.assertEqual(service.active_device(), "cpu")

    def test_cpu_configuration_loads_directly(self):
        module = load_transcriber(make_settings("cpu"))
        service = module.TranscriberService()
        service.ensure_loaded()
        self.assertEqual(service.active_device(), "cpu")

    def test_model_is_not_loaded_until_first_use(self):
        module = load_transcriber(make_settings("cuda"))
        service = module.TranscriberService()
        self.assertFalse(service.is_model_loaded())

    def test_idle_unload_frees_the_model(self):
        module = load_transcriber(make_settings("cpu"))
        service = module.TranscriberService()
        service.ensure_loaded()
        self.assertTrue(service.is_model_loaded())
        self.assertFalse(service.unload_if_idle(0), "0 disables unloading")
        self.assertFalse(service.unload_if_idle(3600), "recently used stays loaded")
        service._last_used -= 100
        self.assertTrue(service.unload_if_idle(50))
        self.assertFalse(service.is_model_loaded())

    def test_model_reloads_after_unload(self):
        module = load_transcriber(make_settings("cpu"))
        service = module.TranscriberService()
        service.ensure_loaded()
        service.unload()
        self.assertFalse(service.is_model_loaded())
        service.ensure_loaded()
        self.assertTrue(service.is_model_loaded())

    def test_prompt_echo_is_detected(self):
        module = load_transcriber(make_settings("cuda"))
        prompt = "Thuyết trình bảo vệ dự án, phần mềm, công nghệ, kiến trúc, API, microservices, database, latency."
        self.assertTrue(module._echoes_prompt(
            "Thuyết bảo vệ dự án, phần mềm, công nghệ, kiến trúc, API, micro", prompt))
        self.assertFalse(module._echoes_prompt(
            "Vì sao dự án chọn FAISS thay vì pgvector cho phần RAG?", prompt))
        self.assertFalse(module._echoes_prompt("Ừm.", prompt))


if __name__ == "__main__":
    unittest.main()
