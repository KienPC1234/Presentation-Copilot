"""Exercise orchestration without installing or contacting model providers."""
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from services.context_manager import SessionContext


def load_agent():
    modules = {}
    for name, exports in {
        "langchain.agents": {"AgentExecutor": Mock(), "create_react_agent": Mock()},
        "langchain_core.prompts": {"PromptTemplate": Mock()},
        "langchain_core.tools": {"tool": lambda function: function},
        "langchain_ollama": {"ChatOllama": Mock()},
        "config": {"settings": SimpleNamespace(response_style="technical")},
        "services.react_parser": {"StructuredReActParser": Mock()},
        "langchain_core.messages": {"HumanMessage": Mock(), "SystemMessage": Mock()},
    }.items():
        module = ModuleType(name)
        module.__dict__.update(exports)
        modules[name] = module
    spec = importlib.util.spec_from_file_location("agent_under_test", Path(__file__).parents[1] / "services/agent_service.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class AgentContractTests(unittest.TestCase):
    def setUp(self):
        self.module = load_agent()
        self.agent = self.module.AgentService.__new__(self.module.AgentService)
        self.agent._rag = Mock()
        self.agent._rag.query.return_value = ["[actual.md] evidence"]
        self.agent._executor = Mock()
        self.ctx = SessionContext("test")

    def test_evidence_supplied_before_generation(self):
        self.agent._executor.invoke.return_value = {"output": json.dumps({
            "key_point": "Answer", "keywords": [], "framework_steps": [],
            "retrieved_sources": ["forged.md"]}), "intermediate_steps": []}
        result = self.agent.run("question", self.ctx)
        self.assertIn("[actual.md]", self.agent._executor.invoke.call_args.args[0]["evidence"])
        self.assertEqual(result["retrieved_sources"], ["[actual.md]"])
        self.assertEqual(len(self.ctx.get_history()), 2)

    def test_invalid_answer_not_remembered(self):
        self.agent._executor.invoke.return_value = {"output": "Agent stopped due to iteration limit."}
        with self.assertLogs(self.module.logger, level="ERROR"):
            result = self.agent.run("question", self.ctx)
        self.assertIn("error", result)
        self.assertEqual(self.ctx.get_history(), [])

    def test_retrieval_failure_prevents_generation(self):
        self.agent._rag.query.side_effect = RuntimeError("offline")
        with self.assertLogs(self.module.logger, level="ERROR"):
            result = self.agent.run("question", self.ctx)
        self.agent._executor.invoke.assert_not_called()
        self.assertIn("error", result)

    def test_plain_style_applies_to_technical_persona(self):
        self.module.settings.response_style = "plain"
        self.agent._current_persona_key = "tech_hackathon"
        self.agent._custom_persona_text = ""
        self.agent._tools = []
        self.agent._llm = Mock()
        self.agent._rebuild_executor()
        values = self.module.PromptTemplate.from_template.return_value.partial.call_args.kwargs
        self.assertEqual(values["response_style"], self.module.RESPONSE_STYLES["plain"])
        self.assertIn("ADULT", values["response_style"])

    def test_technical_style_is_explicitly_available(self):
        self.module.settings.response_style = "technical"
        self.agent._current_persona_key = "general"
        self.agent._tools = []
        self.agent._llm = Mock()
        self.agent._rebuild_executor()
        values = self.module.PromptTemplate.from_template.return_value.partial.call_args.kwargs
        self.assertEqual(values["response_style"], self.module.RESPONSE_STYLES["technical"])

    def test_plain_pass_uses_evidence_and_recovers_iteration_stop(self):
        self.module.settings.response_style = "plain"
        self.agent._executor.invoke.return_value = {"output": "Agent stopped due to iteration limit.", "intermediate_steps": []}
        self.agent._plain_llm = Mock()
        self.agent._plain_llm.invoke.return_value.content = json.dumps({
            "key_point": "Chưa có thông tin này.", "keywords": [], "framework_steps": []})
        result = self.agent.run("question", self.ctx)
        self.assertNotIn("error", result)
        payload = self.module.HumanMessage.call_args.kwargs["content"]
        self.assertEqual(json.loads(payload)["evidence"], ["[actual.md] evidence"])
        self.assertNotIn("Agent stopped", payload)

    def test_plain_pass_malformed_json_is_not_remembered(self):
        self.module.settings.response_style = "plain"
        self.agent._executor.invoke.return_value = {"output": "irrelevant draft", "intermediate_steps": []}
        self.agent._plain_llm = Mock()
        self.agent._plain_llm.invoke.return_value.content = '{"key_point":'
        with self.assertLogs(self.module.logger, level="ERROR"):
            result = self.agent.run("question", self.ctx)
        self.assertIn("error", result)
        self.assertEqual(self.ctx.get_history(), [])

    def test_plain_pass_can_recover_planner_failure(self):
        self.module.settings.response_style = "plain"
        self.agent._executor.invoke.side_effect = RuntimeError("transient provider error")
        self.agent._plain_llm = Mock()
        self.agent._plain_llm.invoke.return_value.content = json.dumps({
            "key_point": "Chưa biết.", "keywords": [], "framework_steps": []})
        with self.assertLogs(self.module.logger, level="WARNING"):
            result = self.agent.run("question", self.ctx)
        self.assertNotIn("error", result)

    def test_requested_example_is_repaired_once(self):
        self.module.settings.response_style = "plain"
        self.agent._executor.invoke.return_value = {"intermediate_steps": []}
        self.agent._plain_llm = Mock()
        definition = {"key_point": "Dữ liệu đang chờ xử lý.", "keywords": [], "framework_steps": []}
        example = {**definition, "framework_steps": ["Ví dụ, người xếp hàng chờ đến lượt."]}
        self.agent._plain_llm.invoke.side_effect = [SimpleNamespace(content=json.dumps(x)) for x in [definition, example]]
        result = self.agent.run("Cho một ví dụ", self.ctx)
        self.assertEqual(self.agent._plain_llm.invoke.call_count, 2)
        self.assertNotIn("quality_warnings", result)

    def test_example_repair_is_bounded_and_marks_incomplete_answer(self):
        self.module.settings.response_style = "plain"
        self.agent._executor.invoke.return_value = {"intermediate_steps": []}
        self.agent._plain_llm = Mock()
        self.agent._plain_llm.invoke.return_value.content = json.dumps({"key_point": "Định nghĩa.", "keywords": [], "framework_steps": []})
        result = self.agent.run("Cho ví dụ", self.ctx)
        self.assertEqual(self.agent._plain_llm.invoke.call_count, 2)
        self.assertEqual(result["quality_warnings"], ["missing_requested_example"])
