import json
import logging
import re
from typing import Any

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

from config import settings
from services.output_validation import parse_suggestion

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
    return parse_suggestion(text)


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
