import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from services.admin_settings import AdminSettingsStore
from services.document_kinds import DOCUMENT_KINDS


def make_settings(tmp: str):
    return SimpleNamespace(
        admin_settings_file=str(Path(tmp) / "admin-settings.json"),
        response_style="plain",
        export_retention_days=14,
        cleanup_on_startup=True,
        agent_bash_enabled=False,
        agent_ingest_enabled=False,
        agent_max_iterations=3,
    )


class AdminSettingsTests(unittest.TestCase):
    def test_defaults_follow_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AdminSettingsStore(make_settings(tmp))
            data = store.get()
            self.assertEqual(data["response_style"], "plain")
            self.assertEqual(data["default_kinds"], list(DOCUMENT_KINDS))
            self.assertFalse(data["agent_bash_enabled"])

    def test_valid_update_is_persisted_and_reloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AdminSettingsStore(make_settings(tmp))
            updated = store.update({
                "agent_bash_enabled": True,
                "agent_max_iterations": 5,
                "prebuild_topics": ["Nền tảng học tập trực tuyến"],
                "default_kinds": ["qa", "rebuttal"],
            })
            self.assertTrue(updated["agent_bash_enabled"])
            reloaded = AdminSettingsStore(make_settings(tmp))
            self.assertEqual(reloaded.get()["agent_max_iterations"], 5)
            self.assertEqual(reloaded.get()["default_kinds"], ["qa", "rebuttal"])

    def test_invalid_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AdminSettingsStore(make_settings(tmp))
            for payload in (
                {"response_style": "shouty"},
                {"default_language": "fr"},
                {"default_count": 99},
                {"default_kinds": ["unknown"]},
                {"cleanup_targets": ["everything"]},
                {"agent_bash_enabled": "yes"},
                {"agent_max_iterations": 0},
                {"prebuild_topics": ["ab"]},
            ):
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    store.update(payload)

    def test_corrupt_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "admin-settings.json"
            path.write_text("{not json", encoding="utf-8")
            store = AdminSettingsStore(make_settings(tmp))
            self.assertEqual(store.get()["default_count"], 6)


if __name__ == "__main__":
    unittest.main()
