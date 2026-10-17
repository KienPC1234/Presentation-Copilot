import os
import time
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from services import maintenance


def make_settings(tmp: str):
    root = Path(tmp)
    return SimpleNamespace(
        data_dir=str(root),
        export_dir=str(root / "exports"),
        tmp_dir=str(root / "tmp"),
        chroma_persist_dir=str(root / "chroma"),
    )


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.settings = make_settings(self._tmp.name)
        for name in ("exports", "tmp", "chroma"):
            (Path(self._tmp.name) / name).mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_runtime_cleanup_removes_only_temp_files(self):
        (Path(self.settings.tmp_dir) / "clip.wav").write_bytes(b"x" * 10)
        marker = Path(self.settings.chroma_persist_dir) / ".index-write-pending"
        marker.write_text("keep me", encoding="utf-8")
        result = maintenance.cleanup_runtime(self.settings)
        self.assertEqual(result["removed"], 1)
        self.assertFalse((Path(self.settings.tmp_dir) / "clip.wav").exists())
        self.assertTrue(marker.exists(), "the recovery marker must survive cleanup")

    def test_exports_retention_keeps_fresh_and_drops_old(self):
        old = Path(self.settings.export_dir) / "old-bundle"
        new = Path(self.settings.export_dir) / "new-bundle"
        old.mkdir()
        new.mkdir()
        (old / "defense-pack.md").write_text("old", encoding="utf-8")
        stale = time.time() - 40 * 86400
        os.utime(old, (stale, stale))

        result = maintenance.cleanup_exports(self.settings.export_dir, 14)
        self.assertEqual(result["removed"], 1)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def test_retention_zero_disables_age_deletion(self):
        bundle = Path(self.settings.export_dir) / "keep"
        bundle.mkdir()
        stale = time.time() - 400 * 86400
        os.utime(bundle, (stale, stale))
        result = maintenance.cleanup_exports(self.settings.export_dir, 0)
        self.assertEqual(result["removed"], 0)
        self.assertTrue(bundle.exists())

    def test_purge_removes_every_bundle(self):
        for name in ("a", "b"):
            (Path(self.settings.export_dir) / name).mkdir()
        result = maintenance.purge_exports(self.settings.export_dir)
        self.assertEqual(result["removed"], 2)
        self.assertEqual(list(Path(self.settings.export_dir).iterdir()), [])

    def test_storage_report_counts_bytes(self):
        (Path(self.settings.tmp_dir) / "a.bin").write_bytes(b"12345")
        report = maintenance.storage_report(self.settings)
        self.assertEqual(report["tmp"]["files"], 1)
        self.assertEqual(report["tmp"]["bytes"], 5)


if __name__ == "__main__":
    unittest.main()
