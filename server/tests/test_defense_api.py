import unittest
from contextlib import ExitStack
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

    def test_eight_connections_with_same_peer_address_have_isolated_contexts(self):
        registry = server.ContextRegistry()
        with patch.object(server.settings, "api_token", ""), patch.object(server, "_ctx_registry", registry):
            with ExitStack() as stack:
                sockets = [stack.enter_context(self.client.websocket_connect("ws://localhost:8765/ws")) for _ in range(8)]
                for index, ws in enumerate(sockets):
                    ws.send_json({"type": "set_topic", "topic": f"Private topic {index}"})
                    self.assertEqual(ws.receive_json()["type"], "topic_set")
                self.assertEqual(registry.active_count(), 8)
                topics = {ctx.get_fact("presentation_topic") for ctx in registry._sessions.values()}
                self.assertEqual(topics, {f"Private topic {i}" for i in range(8)})
                sockets[0].send_json({"type": "clear"})
                self.assertEqual(sockets[0].receive_json()["type"], "cleared")
                topics = {ctx.get_fact("presentation_topic") for ctx in registry._sessions.values()}
                self.assertIn("Private topic 7", topics)
                self.assertNotIn("Private topic 0", topics)
            self.assertEqual(registry.active_count(), 0)

    def test_invalid_speech_configuration_returns_422(self):
        fake = Mock()
        fake.set_language.side_effect = ValueError("Unsupported language")
        with patch.object(server.settings, "api_token", ""), patch.object(server, "_transcriber", fake):
            result = self.client.post("/api/config", json={"whisper_language": "invalid"})
            self.assertEqual(result.status_code, 422)

    def test_simulation_returns_agent_evidence_without_second_retrieval(self):
        fake, rag = Mock(), Mock()
        fake.run.return_value = {"key_point": "Answer", "retrieved_chunks": ["actually used evidence"]}
        with patch.object(server.settings, "api_token", ""), patch.object(server, "_agent", fake), patch.object(server, "_rag", rag):
            result = self.client.post("/api/simulate", json={"question": "What?"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["retrieved_chunks"], ["actually used evidence"])
        rag.query.assert_not_called()
        self.assertTrue(fake.run.call_args.kwargs["include_evidence"])

    def test_simulation_failure_returns_non_success_status(self):
        fake = Mock()
        fake.run.return_value = {"error": "Answer failed review"}
        with patch.object(server.settings, "api_token", ""), patch.object(server, "_agent", fake), patch.object(server, "_rag", Mock()):
            result = self.client.post("/api/simulate", json={"question": "What?"})
        self.assertEqual(result.status_code, 502)
