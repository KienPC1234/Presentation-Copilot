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
        "config": {"settings": SimpleNamespace()},
        "services.react_parser": {"StructuredReActParser": Mock()},
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
