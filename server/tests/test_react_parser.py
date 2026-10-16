import unittest

try:
    from services.react_parser import StructuredReActParser
    from langchain_core.agents import AgentFinish, AgentAction
except ImportError:
    StructuredReActParser = None


@unittest.skipIf(StructuredReActParser is None, "Requires installed LangChain runtime")
class ReActParserTests(unittest.TestCase):
    def test_direct_valid_json_finishes(self):
        result = StructuredReActParser().parse('{"key_point":"17 minutes","keywords":[],"framework_steps":[]}')
        self.assertIsInstance(result, AgentFinish)

    def test_standard_tool_action_still_parses(self):
        result = StructuredReActParser().parse('Thought: lookup\nAction: rag_search\nAction Input: tokens')
        self.assertIsInstance(result, AgentAction)
        self.assertEqual(result.tool, "rag_search")

    def test_invalid_bare_json_is_not_finished(self):
        with self.assertRaises(ValueError):
            StructuredReActParser().parse('{"key_point": 17}')
