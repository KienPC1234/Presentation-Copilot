"""Accept validated final JSON as well as the standard ReAct envelope."""
import json

from langchain.agents.output_parsers import ReActSingleInputOutputParser
from langchain_core.agents import AgentFinish

from services.output_validation import parse_suggestion


class StructuredReActParser(ReActSingleInputOutputParser):
    def parse(self, text):
        try:
            suggestion = parse_suggestion(text)
        except ValueError:
            return super().parse(text)
        return AgentFinish({"output": json.dumps(suggestion, ensure_ascii=False)}, text)
