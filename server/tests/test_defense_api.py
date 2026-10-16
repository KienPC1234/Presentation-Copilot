import unittest
from unittest.mock import Mock, patch

try:
    import main as server
    from fastapi.testclient import TestClient
except ImportError:
    server = None


@unittest.skipIf(server is None, "Requires installed server dependencies")
class DefenseApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app, base_url="http://localhost:8765")

    def test_prepare_requires_authorization(self):
        with patch.object(server.settings, "api_token", "test-secret"):
            self.assertEqual(self.client.post("/api/defense/prepare", json={"topic": "Product"}).status_code, 401)

    def test_invalid_topic_and_count_rejected(self):
        with patch.object(server.settings, "api_token", ""):
            for payload in ({"topic": "   "}, {"topic": "Product", "count": 99}):
                self.assertEqual(self.client.post("/api/defense/prepare", json=payload).status_code, 422)

    def test_prepare_returns_plan_without_calling_real_model(self):
        fake = Mock()
        fake.prepare.return_value = {"topic": "Product", "questions": [], "question_origin": "ai_generated_preparation"}
        with patch.object(server.settings, "api_token", ""), patch.object(server, "_rag", Mock()), patch.object(server, "DefenseService", return_value=fake):
            result = self.client.post("/api/defense/prepare", json={"topic": " Product "})
        self.assertEqual(result.status_code, 200)
        fake.prepare.assert_called_once_with("Product", "", 6, "vi")

    def test_malformed_provider_plan_returns_bad_gateway(self):
        fake = Mock()
        fake.prepare.side_effect = ValueError("forged source")
        with patch.object(server.settings, "api_token", ""), patch.object(server, "_rag", Mock()), patch.object(server, "DefenseService", return_value=fake):
            result = self.client.post("/api/defense/prepare", json={"topic": "Product"})
        self.assertEqual(result.status_code, 502)

    def test_websocket_topic_can_be_set_and_cleared(self):
        with patch.object(server.settings, "api_token", ""):
            with self.client.websocket_connect("ws://localhost:8765/ws") as ws:
                ws.send_json({"type": "set_topic", "topic": "Product demo"})
                self.assertEqual(ws.receive_json()["type"], "topic_set")
                ws.send_json({"type": "clear"})
                self.assertEqual(ws.receive_json()["type"], "cleared")
                ws.send_json([])
                self.assertEqual(ws.receive_json()["type"], "error")
