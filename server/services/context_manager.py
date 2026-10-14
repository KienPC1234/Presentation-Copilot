"""Per-session conversation context with a bounded sliding window."""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

Role = Literal["user", "assistant", "system"]


@dataclass(slots=True)
class Turn:
    role: Role
    content: str


class SessionContext:
    """
    Maintains a bounded chat history and extracted facts for one WebSocket
    session.  Older turns are dropped (FIFO) once ``max_turns`` is exceeded so
    the LLM prompt stays within token limits.
    """

    def __init__(self, session_id: str, max_turns: int = 10) -> None:
        self.session_id = session_id
        self._max_turns = max_turns
        self._history: deque[Turn] = deque(maxlen=max_turns)
        # Arbitrary key-value facts the agent can store between turns
        self._facts: dict[str, str] = {}

    # ------------------------------------------------------------------
    # History helpers
    # ------------------------------------------------------------------

    def add_user(self, text: str) -> None:
        self._history.append(Turn("user", text))

    def add_assistant(self, text: str) -> None:
        self._history.append(Turn("assistant", text))

    def add_system(self, text: str) -> None:
        self._history.append(Turn("system", text))

    def get_history(self) -> list[Turn]:
        return list(self._history)

    def format_for_prompt(self) -> str:
        """Return history as a compact multi-line string for prompt injection."""
        lines: list[str] = []
        for turn in self._history:
            prefix = {"user": "Q", "assistant": "A", "system": "SYS"}[turn.role]
            lines.append(f"[{prefix}] {turn.content}")
        return "\n".join(lines)

    def clear_history(self) -> None:
        self._history.clear()

    # ------------------------------------------------------------------
    # Fact store
    # ------------------------------------------------------------------

    def set_fact(self, key: str, value: str) -> None:
        self._facts[key] = value

    def get_fact(self, key: str) -> str | None:
        return self._facts.get(key)

    def all_facts(self) -> dict[str, str]:
        return dict(self._facts)

    def __repr__(self) -> str:
        return (
            f"<SessionContext id={self.session_id!r} "
            f"turns={len(self._history)}/{self._max_turns}>"
        )


class ContextRegistry:
    """Thread-safe registry mapping WebSocket client ids → SessionContext."""

    def __init__(self, max_turns_per_session: int = 10) -> None:
        self._sessions: dict[str, SessionContext] = {}
        self._max_turns = max_turns_per_session

    def get_or_create(self, session_id: str) -> SessionContext:
        if session_id not in self._sessions:
            ctx = SessionContext(session_id, self._max_turns)
            self._sessions[session_id] = ctx
            logger.debug("Created new session context: %s", session_id)
        return self._sessions[session_id]

    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        logger.debug("Removed session context: %s", session_id)

    def active_count(self) -> int:
        return len(self._sessions)

