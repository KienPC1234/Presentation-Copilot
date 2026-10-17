import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from services import path_browser


class PathBrowserTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "sub").mkdir()
        (self.root / "sub" / "file.md").write_text("hi", encoding="utf-8")
        (self.root / ".hidden").write_text("x", encoding="utf-8")
        self.settings = SimpleNamespace(
            host_mount_root=str(self.root),
            docs_dir=str(self.root / "docs"),
            export_dir=str(self.root / "exports"),
        )
        (self.root / "docs").mkdir()
        (self.root / "exports").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_roots_include_host_and_skip_missing(self):
        roots = path_browser.allowed_roots(self.settings)
        paths = {root["path"] for root in roots}
        self.assertIn(str(self.root), paths)
        self.assertIn(str(self.root / "docs"), paths)

    def test_listing_is_sorted_directories_first_and_hides_dotfiles(self):
        roots = path_browser.allowed_roots(self.settings)
        result = path_browser.list_directory(str(self.root), roots)
        self.assertTrue(result["ok"])
        names = [entry["name"] for entry in result["entries"]]
        self.assertEqual(names[0], "docs")
        self.assertNotIn(".hidden", names)
        self.assertIsNone(result["parent"])

    def test_show_hidden_reveals_dotfiles(self):
        roots = path_browser.allowed_roots(self.settings)
        result = path_browser.list_directory(str(self.root), roots, show_hidden=True)
        self.assertIn(".hidden", [entry["name"] for entry in result["entries"]])

    def test_paths_outside_roots_are_refused(self):
        roots = path_browser.allowed_roots(self.settings)
        result = path_browser.list_directory("/etc", roots)
        self.assertFalse(result["ok"])
        self.assertIn("outside", result["error"])

    def test_symlink_escape_is_refused(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        link = self.root / "escape"
        try:
            os.symlink(outside.name, link)
        except OSError:
            self.skipTest("symlinks not supported here")
        roots = path_browser.allowed_roots(self.settings)
        with self.assertRaises(path_browser.PathAccessError):
            path_browser.resolve_within_roots(str(link), roots)

    def test_missing_path_reports_error_not_exception(self):
        roots = path_browser.allowed_roots(self.settings)
        result = path_browser.list_directory(str(self.root / "nope"), roots)
        self.assertFalse(result["ok"])
        self.assertIn("does not exist", result["error"])


if __name__ == "__main__":
    unittest.main()
