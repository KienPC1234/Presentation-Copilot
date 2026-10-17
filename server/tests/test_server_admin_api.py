"""HTTP contract for the remote admin panel, token, documents and cleanup."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

try:
    import main as server
    from fastapi.testclient import TestClient
except ImportError:
    server = None


@unittest.skipIf(server is None, "Requires installed server dependencies")
class AdminApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app, base_url="http://localhost:8765")
        # Isolate from any real token file: rotate() writes to disk when no env
        # token is set, and the data dir is a shared bind mount.
        self._tmp = tempfile.TemporaryDirectory()
        self._original_path = server._token_store._path
        self._original_file_token = server._token_store._file_token
        self._original_rotation = server._token_store._rotated
        server._token_store._path = Path(self._tmp.name) / ".api-token"
        server._token_store._file_token = ""

    def tearDown(self):
        server._token_store._path = self._original_path
        server._token_store._rotated = self._original_rotation
        server._token_store._file_token = self._original_file_token
        self._tmp.cleanup()

    def test_new_endpoints_require_authorization_for_remote_clients(self):
        with patch.object(server.settings, "api_token", "test-secret"):
            for method, path in (("get", "/api/fs/roots"), ("get", "/api/admin/settings"),
                                 ("get", "/api/documents"), ("get", "/api/maintenance/report"),
                                 ("post", "/api/documents/prebuild")):
                with self.subTest(path=path):
                    response = getattr(self.client, method)(path)
                    self.assertEqual(response.status_code, 401)

    def test_documents_generate_delegates_to_the_service(self):
        fake = Mock()
        fake.generate.return_value = {"status": "success", "cache_key": "k",
                                      "cached": False, "markdown": "# doc"}
        admin = Mock()
        admin.get.return_value = {"default_kinds": ["qa"]}
        with patch.object(server.settings, "api_token", ""), \
                patch.object(server, "_documents", fake), patch.object(server, "_admin_settings", admin):
            response = self.client.post("/api/documents/generate", json={"topic": "Product demo"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cache_key"], "k")
        fake.generate.assert_called_once()
        self.assertEqual(fake.generate.call_args.args[0], "Product demo")

    def test_documents_generate_rejects_invalid_payload(self):
        with patch.object(server.settings, "api_token", ""), patch.object(server, "_documents", Mock()):
            self.assertEqual(
                self.client.post("/api/documents/generate", json={"topic": "x", "count": 99}).status_code, 422)

    def test_fs_list_refuses_paths_outside_the_configured_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(server.settings, "api_token", ""), \
                    patch.object(server.settings, "host_mount_root", tmp), \
                    patch.object(server.settings, "docs_dir", str(Path(tmp) / "docs")), \
                    patch.object(server.settings, "export_dir", str(Path(tmp) / "exports")):
                Path(tmp, "docs").mkdir()
                Path(tmp, "exports").mkdir()
                inside = self.client.get("/api/fs/list", params={"path": tmp})
                outside = self.client.get("/api/fs/list", params={"path": "/etc"})
        self.assertTrue(inside.json()["ok"])
        self.assertFalse(outside.json()["ok"])

    def test_cleanup_purge_removes_export_bundles(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp, "bundle")
            bundle.mkdir()
            with patch.object(server.settings, "api_token", ""), \
                    patch.object(server.settings, "export_dir", tmp), \
                    patch.object(server.settings, "tmp_dir", str(Path(tmp) / "tmp")), \
                    patch.object(server.settings, "data_dir", tmp), \
                    patch.object(server, "_admin_settings", Mock(**{"get.return_value": {"export_retention_days": 0}})):
                response = self.client.post("/api/maintenance/cleanup",
                                            json={"targets": ["exports"], "purge_exports": True})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(bundle.exists())

    def test_agent_tool_policy_is_validated_and_applied(self):
        agent = Mock()
        agent.get_tool_policy.return_value = {"tools": ["rag_search", "bash"]}
        admin = Mock()
        with patch.object(server.settings, "api_token", ""), \
                patch.object(server, "_agent", agent), patch.object(server, "_admin_settings", admin), \
                patch.object(server, "_apply_agent_policy") as apply_policy:
            response = self.client.post("/api/agent/tools", json={"bash_enabled": True, "max_iterations": 5})
        self.assertEqual(response.status_code, 200)
        apply_policy.assert_called_once()
        updates = admin.update.call_args.args[0]
        self.assertEqual(updates["agent_bash_enabled"], True)
        self.assertEqual(updates["agent_max_iterations"], 5)

    def test_token_rotation_returns_a_new_secret(self):
        with patch.object(server.settings, "api_token", ""):
            response = self.client.post("/api/admin/token/rotate")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()["token"]), 16)


if __name__ == "__main__":
    unittest.main()
