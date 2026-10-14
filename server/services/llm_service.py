import json
import logging
import re
from typing import Any

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

from config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a concise presentation assistant. "
    "Your ONLY output must be a single valid JSON object — no markdown, no explanation, no extra text.\n"
    "The JSON must have exactly these keys:\n"
    '  "key_point": a single sentence summarising the core idea,\n'
    '  "keywords": a list of 3 to 5 keyword strings,\n'
    '  "framework_steps": a list of 2 to 4 short action-oriented bullet points.\n'
    "Never include any text outside the JSON object."
)


def _extract_json(text: str) -> dict[str, Any]:
    """Attempt to parse JSON from LLM output with multiple fallback strategies."""
    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Extract first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # 3. Manual field extraction as last resort
    logger.warning("Could not parse LLM JSON, falling back to regex field extraction")
    key_point_match = re.search(r'"key_point"\s*:\s*"([^"]+)"', text)
    keywords_match = re.search(r'"keywords"\s*:\s*\[([^\]]+)\]', text)
    steps_match = re.search(r'"framework_steps"\s*:\s*\[([^\]]+)\]', text)

    def _parse_list(raw: str | None) -> list[str]:
        if not raw:
            return []
        return [item.strip().strip('"') for item in raw.split(",") if item.strip()]

    return {
        "key_point": key_point_match.group(1) if key_point_match else "",
        "keywords": _parse_list(keywords_match.group(1) if keywords_match else None),
        "framework_steps": _parse_list(steps_match.group(1) if steps_match else None),
    }


class LLMService:
    """Generates structured presentation suggestions via Ollama."""

    def __init__(self) -> None:
        self._llm = ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=0.3,
            format="json",
        )
        logger.info("LLMService initialised (model=%s)", settings.ollama_model)

    def generate_suggestion(self, question: str, context_chunks: list[str]) -> dict[str, Any]:
        """Build a prompt from the question and RAG context, call Ollama, return parsed JSON.

        Args:
            question: The transcribed user speech / query.
            context_chunks: Relevant document snippets from the RAG service.

        Returns:
            Dict with keys ``key_point`` (str), ``keywords`` (list[str]),
            ``framework_steps`` (list[str]).  On failure returns a dict with
            empty/fallback values and an ``error`` key.
        """
        context_block = "\n\n---\n\n".join(context_chunks) if context_chunks else "No context available."

        user_message = (
            f"Question / spoken input:\n{question}\n\n"
            f"Relevant project context:\n{context_block}\n\n"
            "Return the JSON object now."
        )

        logger.debug("Sending prompt to LLM (question=%s)", question[:80])
        try:
            response = self._llm.invoke(
                [
                    SystemMessage(content=_SYSTEM_PROMPT),
                    HumanMessage(content=user_message),
                ]
            )
            raw_text: str = response.content if hasattr(response, "content") else str(response)
            logger.debug("Raw LLM response: %s", raw_text[:300])
            result = _extract_json(raw_text)
            # Validate required keys exist
            result.setdefault("key_point", "")
            result.setdefault("keywords", [])
            result.setdefault("framework_steps", [])
            return result
        except Exception:
            logger.exception("LLM generation failed")
            return {
                "key_point": "",
                "keywords": [],
                "framework_steps": [],
                "error": "LLM generation failed — check server logs.",
            }

