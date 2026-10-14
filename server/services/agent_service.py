"""
Agent service: LangChain ReAct agent with tools for fast contextual answers.

Tools available to the agent:
  - rag_search   : Vector DB lookup against project documents & source code
  - bash_exec    : Run safe read-only shell commands (ls, cat, grep, find)
  - web_search   : DuckDuckGo search (market data, competitors, definitions)
  - calculator   : Safe eval of arithmetic expressions

The agent uses a tight 3-iteration cap and strict JSON output format so it
stays under the latency budget (<3 s on a modern CPU).
"""

from __future__ import annotations

import ast
import json
import logging
import operator
import re
import subprocess
from typing import TYPE_CHECKING, Any

from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import tool
from langchain_ollama import ChatOllama

from config import settings

if TYPE_CHECKING:
    from services.context_manager import SessionContext
    from services.rag_service import RAGService

logger = logging.getLogger(__name__)

# Allowed shell commands (read-only whitelist)
_ALLOWED_CMDS = frozenset({"ls", "cat", "grep", "find", "echo", "wc", "head", "tail", "dir"})

PERSONA_PRESETS: dict[str, str] = {
    "tech_hackathon": (
        "You are defending a technical project in a Hackathon / Tech Competition. "
        "Focus on system architecture, database performance, p99 latency, failover design, "
        "and concrete metrics from the codebase. Be precise, authoritative, and direct."
    ),
    "startup_pitch": (
        "You are pitching a startup to investors and judges. "
        "Focus on business model, unit economics, scaling cost per 1k users, market moat, "
        "and customer retention."
    ),
    "academic_defense": (
        "You are defending a thesis or academic research project. "
        "Focus on algorithmic complexity, benchmark data, methodology, and theoretical justification."
    ),
    "general": (
        "You are an expert technical presentation co-pilot. "
        "Provide immediate, high-density cues and bullet points for the speaker."
    ),
}

_BASE_TEMPLATE = """{persona}

Your task: Listen to the question / spoken context, retrieve necessary facts, and produce a sharp, structured suggestion in strict JSON.

TOOLS:
{tools}

TOOL NAMES: {tool_names}

CONVERSATION HISTORY (last turns):
{history}

INSTRUCTIONS:
- Retrieve context from project documents/code via rag_search.
- If calculation is needed (e.g. server costs, QPS, latency), use calculator.
- Stop after at most 3 tool calls.
- Output MUST be valid JSON with keys:
  "key_point": single punchy sentence to say immediately,
  "keywords": 3 to 5 vital technical terms or metrics,
  "framework_steps": 2 to 4 sequential bullet points outlining the response.
- NEVER include markdown code fences or conversational filler outside the JSON.

FORMAT:
Thought: <reasoning>
Action: <tool name>
Action Input: <tool input>
Observation: <tool output>
... (repeat up to 3 times)
Thought: I have enough information.
Final Answer: {{"key_point": "...", "keywords": ["..."], "framework_steps": ["..."]}}

BEGIN

Question: {input}
{agent_scratchpad}"""


def _make_tools(rag: "RAGService") -> list:
    """Build the tool list, closing over the RAG service."""

    @tool
    def rag_search(query: str) -> str:
        """Search project documents and source code for relevant context."""
        chunks = rag.query(query, top_k=3)
        return "\n---\n".join(chunks) if chunks else "No relevant documents found."

    @tool
    def bash_exec(command: str) -> str:
        """Run a safe read-only shell command (ls, cat, grep, find, echo, wc, head, tail)."""
        tokens = command.strip().split()
        if not tokens or tokens[0] not in _ALLOWED_CMDS:
            allowed = ", ".join(sorted(_ALLOWED_CMDS))
            return f"Denied. Allowed commands: {allowed}"
        try:
            result = subprocess.run(
                tokens,
                capture_output=True,
                text=True,
                timeout=5,
                cwd=".",
            )
            output = result.stdout or result.stderr
            return output[:2000] if output else "(no output)"
        except subprocess.TimeoutExpired:
            return "Command timed out (5s limit)."
        except Exception as exc:
            return f"Error: {exc}"

    @tool
    def web_search(query: str) -> str:
        """Search DuckDuckGo for external market data or definitions."""
        try:
            from langchain_community.tools import DuckDuckGoSearchRun
            searcher = DuckDuckGoSearchRun()
            result = searcher.run(query)
            return result[:1500] if result else "No results."
        except Exception as exc:
            logger.warning("Web search failed: %s", exc)
            return f"Web search unavailable: {exc}"

    @tool
    def calculator(expression: str) -> str:
        """Safely evaluate arithmetic expressions (e.g. '(1500 * 0.05) / 30')."""
        if not re.fullmatch(r"[\d\s\+\-\*\/\.\(\)]+", expression):
            return "Invalid expression."
        try:
            tree = ast.parse(expression, mode="eval")
            _SAFE_NODES = (
                ast.Expression, ast.BinOp, ast.UnaryOp,
                ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow,
                ast.USub, ast.UAdd,
            )
            for node in ast.walk(tree):
                if not isinstance(node, _SAFE_NODES):
                    return "Unsafe expression."

            _ops: dict[type, Any] = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Pow: operator.pow,
                ast.USub: operator.neg,
                ast.UAdd: operator.pos,
            }

            def _eval(node: ast.expr) -> float:
                if isinstance(node, ast.Constant):
                    return float(node.value)
                if isinstance(node, ast.BinOp):
                    return _ops[type(node.op)](_eval(node.left), _eval(node.right))
                if isinstance(node, ast.UnaryOp):
                    return _ops[type(node.op)](_eval(node.operand))
                raise ValueError("Unsupported node")

            result = _eval(tree.body)
            return str(round(result, 6))
        except Exception as exc:
            return f"Calculation error: {exc}"

    return [rag_search, bash_exec, web_search, calculator]


class AgentService:
    """LangChain ReAct agent with dynamic persona and live tools."""

    def __init__(self, rag: "RAGService") -> None:
        self._rag = rag
        self._current_persona_key: str = "tech_hackathon"
        self._custom_persona_text: str = ""
        self._tools = _make_tools(rag)
        self._llm = ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=0.2,
        )
        self._rebuild_executor()
        logger.info("AgentService ready with persona '%s'", self._current_persona_key)

    def _get_active_persona(self) -> str:
        if self._current_persona_key == "custom" and self._custom_persona_text:
            return self._custom_persona_text
        return PERSONA_PRESETS.get(self._current_persona_key, PERSONA_PRESETS["tech_hackathon"])

    def _rebuild_executor(self) -> None:
        persona = self._get_active_persona()
        prompt_text = _BASE_TEMPLATE.replace("{persona}", persona)
        prompt = PromptTemplate.from_template(prompt_text)
        agent = create_react_agent(self._llm, self._tools, prompt)
        self._executor = AgentExecutor(
            agent=agent,
            tools=self._tools,
            max_iterations=3,
            handle_parsing_errors=True,
            verbose=False,
            return_intermediate_steps=False,
        )

    def set_persona(self, key: str, custom_text: str = "") -> None:
        """Updates the active persona and rebuilds the ReAct executor."""
        self._current_persona_key = key
        if key == "custom":
            self._custom_persona_text = custom_text
        self._rebuild_executor()
        logger.info("Agent persona updated to '%s'", key)

    def get_persona_info(self) -> dict[str, Any]:
        return {
            "current_key": self._current_persona_key,
            "custom_text": self._custom_persona_text,
            "active_prompt": self._get_active_persona(),
            "presets": list(PERSONA_PRESETS.keys()),
        }

    def run(self, question: str, ctx: "SessionContext") -> dict[str, Any]:
        """Runs the agent on a user query and records turns into SessionContext."""
        history_text = ctx.format_for_prompt()

        try:
            result = self._executor.invoke({
                "input": question,
                "history": history_text or "(no previous turns)",
            })
            raw: str = result.get("output", "")
            parsed = _parse_agent_output(raw)
        except Exception:
            logger.exception("Agent execution failed")
            parsed = {
                "key_point": "System could not generate a response. Please check server logs.",
                "keywords": [],
                "framework_steps": [],
                "error": "Agent execution failed",
            }

        ctx.add_user(question)
        ctx.add_assistant(parsed.get("key_point", ""))
        return parsed


def _parse_agent_output(text: str) -> dict[str, Any]:
    """Robust 3-stage JSON parser for ReAct output."""
    try:
        return _validate(json.loads(text))
    except (json.JSONDecodeError, ValueError):
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return _validate(json.loads(match.group()))
        except (json.JSONDecodeError, ValueError):
            pass

    kp = re.search(r'"key_point"\s*:\s*"([^"]+)"', text)
    kw = re.search(r'"keywords"\s*:\s*\[([^\]]+)\]', text)
    fs = re.search(r'"framework_steps"\s*:\s*\[([^\]]+)\]', text)

    def _list(raw: str | None) -> list[str]:
        return [i.strip().strip('"') for i in raw.split(",") if i.strip()] if raw else []

    return {
        "key_point": kp.group(1) if kp else text[:120],
        "keywords": _list(kw.group(1) if kw else None),
        "framework_steps": _list(fs.group(1) if fs else None),
    }


def _validate(d: dict[str, Any]) -> dict[str, Any]:
    d.setdefault("key_point", "")
    d.setdefault("keywords", [])
    d.setdefault("framework_steps", [])
    return d
