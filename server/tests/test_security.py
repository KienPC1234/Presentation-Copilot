import unittest

from security import authorized, same_origin


class SecurityTests(unittest.TestCase):
    def test_local_without_token(self):
        self.assertTrue(authorized("127.0.0.1", None, "", "localhost:8765"))
        self.assertTrue(authorized("::1", None, "", "[::1]:8765"))
        self.assertFalse(authorized("192.168.1.2", None, "", "localhost:8765"))
        self.assertFalse(authorized("127.0.0.1", None, "", "evil.example"))

    def test_remote_requires_matching_bearer_token(self):
        self.assertTrue(authorized("192.168.1.2", "Bearer secret", "secret"))
        self.assertFalse(authorized("127.0.0.1", None, "secret"))
        self.assertFalse(authorized("192.168.1.2", "Bearer wrong", "secret"))

    def test_browser_origin_must_match_host(self):
        self.assertTrue(same_origin(None, "localhost:8765"))
        self.assertTrue(same_origin("http://localhost:8765", "localhost:8765"))
        self.assertFalse(same_origin("https://evil.example", "localhost:8765"))
        self.assertFalse(same_origin("file:///app", "localhost:8765"))

    def test_malformed_origin_is_rejected_without_server_exception(self):
        self.assertFalse(same_origin("http://[invalid", "localhost:8765"))

    def test_unicode_bearer_does_not_crash_constant_time_comparison(self):
        self.assertFalse(authorized("192.168.1.2", "Bearer tiếng Việt", "secret"))
        self.assertTrue(authorized("192.168.1.2", "Bearer tiếng Việt", "tiếng Việt"))


if __name__ == "__main__":
    unittest.main()
