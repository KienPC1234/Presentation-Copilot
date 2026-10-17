"""Exercise orchestration without installing or contacting model providers."""
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from services.context_manager import SessionContext
from services.answer_review import parse_review


def mocked_grounding_review(llm, *args, **kwargs):
    """Orchestration-only double; quote/coverage semantics are tested separately."""
    return parse_review(llm.invoke([]).content)


def load_agent():
    modules = {}
    for name, exports in {
        "langchain.agents": {"AgentExecutor": Mock(), "create_react_agent": Mock()},
        "langchain_core.prompts": {"PromptTemplate": Mock()},
        "langchain_core.tools": {"tool": lambda function: function},
        "langchain_ollama": {"ChatOllama": Mock()},
        "config": {"settings": SimpleNamespace(response_style="technical")},
        "services.react_parser": {"StructuredReActParser": Mock()},
        "services.ollama_json": {"OllamaJSONClient": Mock()},
        "services.grounding_review": {"review_grounding": mocked_grounding_review},
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
        self.agent._current_persona_key = "tech_hackathon"
        self.agent._custom_persona_text = ""
        self.agent._rag = Mock()
        self.agent._rag.query.return_value = ["[actual.md] evidence"]
        self.agent._executor = Mock()
        self.agent._plain_llm = Mock()
        self.agent._review_llm = Mock()
        self.agent._plan_llm = Mock()
        self.agent._plan_llm.invoke.return_value.content = '{"requirements": ["Answer the question"], "tools": []}'
        self.agent._review_llm.invoke.return_value.content = '{"issues": []}'
        self.agent._plain_llm.invoke.return_value.content = json.dumps({
            "key_point": "Answer", "keywords": [], "framework_steps": [],
            "retrieved_sources": ["forged.md"]})
        self.ctx = SessionContext("test")

    def test_evidence_supplied_before_generation(self):
        self.agent._executor.invoke.return_value = {"output": json.dumps({
            "key_point": "Answer", "keywords": [], "framework_steps": [],
            "retrieved_sources": ["forged.md"]}), "intermediate_steps": []}
        result = self.agent.run("question", self.ctx)
        payload = json.loads(self.module.HumanMessage.call_args.kwargs["content"])
        self.assertIn("[actual.md] evidence", payload["evidence"])
        self.agent._executor.invoke.assert_not_called()
        self.assertEqual(result["retrieved_sources"], ["[actual.md]"])
        self.assertEqual(len(self.ctx.get_history()), 2)

    def test_technical_question_parts_are_passed_to_composer(self):
        self.agent._executor.invoke.return_value = {"intermediate_steps": []}
        self.agent._plan_llm.invoke.return_value.content = '{"requirements":["Test ownership", "Test changed ID"], "tools":[]}'
        self.agent.run("Test both", self.ctx)
        payload = json.loads(self.module.HumanMessage.call_args.kwargs["content"])
        self.assertEqual([p["id"] for p in payload["requirements"]], ["r1", "r2"])
        self.assertEqual(payload["requirements"][1]["request"], "Test changed ID")

    def test_persona_is_preserved_without_requiring_react_round_trip(self):
        self.agent._current_persona_key = "startup_pitch"
        self.agent.run("What should I say?", self.ctx)
        payload = json.loads(self.module.HumanMessage.call_args.kwargs["content"])
        self.assertIn("investors", payload["presentation_persona"])
        self.agent._executor.invoke.assert_not_called()

    def test_evidence_for_last_of_eight_parts_reaches_composer_and_reviewer(self):
        parts = [f"Requirement {i}" for i in range(1, 9)]
        self.agent._plan_llm.invoke.return_value.content = json.dumps({"requirements": parts, "tools": []})
        self.agent._rag.query.side_effect = lambda query, **kw: ["[last.md] unique final requirement evidence"] if query == parts[-1] else []
        with patch.object(self.module, "review_grounding", return_value=[]) as reviewer:
            result = self.agent.run("Answer all eight parts", self.ctx, include_evidence=True)
        self.assertNotIn("error", result)
        queries = [call.args[0] for call in self.agent._rag.query.call_args_list]
        self.assertEqual(queries[1:], parts)
        payload = json.loads(self.module.HumanMessage.call_args.kwargs["content"])
        self.assertEqual(payload["evidence"], ["[last.md] unique final requirement evidence"])
        self.assertEqual(reviewer.call_args.args[3], payload["evidence"])
        self.assertEqual(result["retrieved_chunks"], payload["evidence"])

    def test_retrieval_failure_in_last_part_prevents_partial_answer_and_memory(self):
        parts = [f"Requirement {i}" for i in range(1, 9)]
        self.agent._plan_llm.invoke.return_value.content = json.dumps({"requirements": parts, "tools": []})
        def query(value, **kwargs):
            if value == parts[-1]:
                raise RuntimeError("RAG unavailable")
            return ["[partial.md] earlier evidence"]
        self.agent._rag.query.side_effect = query
        with self.assertLogs(self.module.logger, level="ERROR"):
            result = self.agent.run("Answer all eight parts", self.ctx)
        self.assertIn("error", result)
        self.agent._plain_llm.invoke.assert_not_called()
        self.assertEqual(self.ctx.get_history(), [])

    def test_invalid_question_plan_prevents_generation_and_memory(self):
        self.agent._plan_llm.invoke.return_value.content = '{"requirements":[]}'
        with self.assertLogs(self.module.logger, level="ERROR"):
            result = self.agent.run("question", self.ctx)
        self.assertIn("error", result)
        self.agent._executor.invoke.assert_not_called()
        self.agent._plain_llm.invoke.assert_not_called()
        self.assertEqual(self.ctx.get_history(), [])

    def test_rehearsal_topic_anchors_retrieval_without_replacing_question(self):
        self.ctx.set_fact("presentation_topic", "My real product")
        self.agent._executor.invoke.return_value = {"output": json.dumps({
            "key_point": "Answer", "keywords": [], "framework_steps": []}), "intermediate_steps": []}
        self.agent.run("How reliable is it?", self.ctx)
        self.assertEqual(self.agent._rag.query.call_args_list[0].args[0], "My real product: How reliable is it?")
        self.assertTrue(all(call.args[0].startswith("My real product:") for call in self.agent._rag.query.call_args_list))

    def test_invalid_answer_not_remembered(self):
        self.agent._plain_llm.invoke.return_value.content = "invalid JSON"
        self.agent._executor.invoke.return_value = {"output": "Agent stopped due to iteration limit."}
        with self.assertLogs(self.module.logger, level="ERROR"):
            result = self.agent.run("question", self.ctx)
        self.assertIn("error", result)
        self.assertEqual(self.ctx.get_history(), [])

    def test_technical_planner_failure_recovers_from_original_evidence(self):
        self.agent._plan_llm.invoke.return_value.content = '{"requirements":["Calculate a value"], "tools":["calculator"]}'
        self.agent._executor.invoke.side_effect = ValueError("invalid planner output")
        with self.assertLogs(self.module.logger, level="WARNING"):
            result = self.agent.run("question", self.ctx)
        self.assertNotIn("error", result)
        self.agent._plain_llm.invoke.assert_called_once()
        self.assertEqual(result["retrieved_sources"], ["[actual.md]"])

    def test_technical_calculator_plan_still_runs_real_tool_executor(self):
        self.agent._plan_llm.invoke.return_value.content = '{"requirements":["Calculate 17 * 60"], "tools":["calculator"]}'
        action = SimpleNamespace(tool="calculator", tool_input="17 * 60")
        self.agent._executor.invoke.return_value = {"intermediate_steps": [(action, "1020")]}
        self.agent.run("17 phút bằng mấy giây?", self.ctx)
        self.agent._executor.invoke.assert_called_once()
        payload = json.loads(self.module.HumanMessage.call_args.kwargs["content"])
        self.assertEqual(payload["tool_observations"][0]["result"], "1020")

    def test_review_rejects_twice_without_remembering_answer(self):
        self.agent._executor.invoke.return_value = {"intermediate_steps": []}
        self.agent._review_llm.invoke.return_value.content = json.dumps({"issues": [
            {"code": "unsupported_claim", "detail": "The endpoint is invented."}]})
        with self.assertLogs(self.module.logger, level="ERROR"):
            result = self.agent.run("question", self.ctx)
        self.assertIn("error", result)
        self.assertEqual(self.agent._plain_llm.invoke.call_count, 2)
        self.assertEqual(self.agent._review_llm.invoke.call_count, 2)
        self.assertEqual(self.ctx.get_history(), [])

    def test_review_repairs_once_and_rechecks(self):
        self.agent._executor.invoke.return_value = {"intermediate_steps": []}
        self.agent._review_llm.invoke.side_effect = [
            SimpleNamespace(content=json.dumps({"issues": [{"code": "unsupported_claim", "detail": "Unmeasured capacity."}]})),
            SimpleNamespace(content='{"issues": []}')]
        result = self.agent.run("question", self.ctx)
        self.assertNotIn("error", result)
        self.assertEqual(result["review_status"], "model_reviewed")
        self.assertEqual(self.agent._review_llm.invoke.call_count, 2)

    def test_optional_evidence_is_the_actual_observed_evidence_and_steps_are_remembered(self):
        self.agent._executor.invoke.return_value = {"intermediate_steps": []}
        self.agent._plain_llm.invoke.return_value.content = json.dumps({
            "key_point": "Chưa có số đo.", "keywords": [], "framework_steps": ["Đề xuất thử quyền sở hữu."]})
        result = self.agent.run("question", self.ctx, include_evidence=True)
        self.assertEqual(result["retrieved_chunks"], ["[actual.md] evidence"])
        self.assertIn("quyền sở hữu", self.ctx.get_history()[-1].content)

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
