import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from token_store import TokenStore


def make_settings(tmp: str, *, api_token: str = "", auto: bool = False):
    return SimpleNamespace(
        api_token=api_token,
        auto_generate_token=auto,
        token_file=str(Path(tmp) / ".api-token"),
    )


class TokenStoreTests(unittest.TestCase):
    def test_loopback_only_when_nothing_is_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TokenStore(make_settings(tmp))
            self.assertEqual(store.current(), "")
            self.assertEqual(store.source(), "loopback-only")
            self.assertFalse((Path(tmp) / ".api-token").exists())

    def test_environment_token_wins_and_is_masked(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TokenStore(make_settings(tmp, api_token="a-very-secret-token"))
            self.assertEqual(store.current(), "a-very-secret-token")
            self.assertEqual(store.source(), "env")
            self.assertEqual(store.masked(), "a-ve…oken")

    def test_auto_generation_persists_and_reloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TokenStore(make_settings(tmp, auto=True))
            token = store.current()
            self.assertGreaterEqual(len(token), 16)
            self.assertEqual(store.source(), "generated")

            reloaded = TokenStore(make_settings(tmp, auto=True))
            self.assertEqual(reloaded.current(), token)
            self.assertEqual(reloaded.source(), "generated")

    def test_rotation_overrides_environment_until_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TokenStore(make_settings(tmp, api_token="env-token"))
            rotated = store.rotate()
            self.assertNotEqual(rotated, "env-token")
            self.assertEqual(store.current(), rotated)
            self.assertEqual(store.source(), "rotated")
            self.assertFalse((Path(tmp) / ".api-token").exists(),
                             "rotation must not write a file that disagrees with the env token")

    def test_environment_token_is_not_duplicated_to_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TokenStore(make_settings(tmp, api_token="env-only-token", auto=True))
            self.assertEqual(store.current(), "env-only-token")
            self.assertEqual(store.source(), "env")
            self.assertFalse((Path(tmp) / ".api-token").exists(),
                             "an env token must not also create a token file")

    def test_short_file_values_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".api-token").write_text("short", encoding="utf-8")
            store = TokenStore(make_settings(tmp, auto=True))
            self.assertGreaterEqual(len(store.current()), 16)
            self.assertNotEqual(store.current(), "short")


if __name__ == "__main__":
    unittest.main()
