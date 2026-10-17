"""Resolve and provision the bearer API token without surprising the operator.

Precedence for the effective token:

1. An in-memory rotation issued from the admin panel (survives until restart).
2. ``API_TOKEN`` from the environment / ``.env`` — the value an operator sets.
3. A token persisted to ``TOKEN_FILE``. Docker generates this on first run so
   the server never accepts unauthenticated remote traffic by accident.
4. Empty, which falls back to the original loopback-only policy.

The environment always wins over the stored file so that a documented ``.env``
value remains authoritative across restarts.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)

_MIN_TOKEN_CHARS = 16


class TokenStore:
    def __init__(self, settings) -> None:
        self._settings = settings
        self._path = Path(settings.token_file)
        self._rotated = ""
        self._file_token = self._load_or_generate()

    # ── Internal helpers ───────────────────────────────────────────────────

    def _read_file(self) -> str:
        try:
            value = self._path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
        return value if len(value) >= _MIN_TOKEN_CHARS else ""

    def _load_or_generate(self) -> str:
        existing = self._read_file()
        if existing:
            return existing
        # An explicit environment token is authoritative: never create a second,
        # confusing token file beside it.
        if self._settings.api_token.strip():
            return ""
        if not self._settings.auto_generate_token:
            return ""
        token = self.rotate()
        # A first-run token is provenance "generated", not an explicit rotation.
        self._rotated = ""
        logger.warning("Generated a new API token at %s", self._path)
        return token

    # ── Public API ─────────────────────────────────────────────────────────

    def current(self) -> str:
        """The token that protects HTTP and WebSocket access right now."""
        return self._rotated or self._settings.api_token.strip() or self._file_token

    def source(self) -> str:
        if self._rotated:
            return "rotated"
        if self._settings.api_token.strip():
            return "env"
        if self._file_token:
            return "generated"
        return "loopback-only"

    def masked(self) -> str:
        token = self.current()
        if not token:
            return ""
        return f"{token[:4]}…{token[-4:]}" if len(token) > 12 else "…"

    def rotate(self) -> str:
        """Generate and activate a new token.

        The token is persisted only when the environment does not already define
        one; otherwise ``API_TOKEN`` is authoritative across restarts and a stray
        file would just disagree with it.
        """
        token = secrets.token_urlsafe(32)
        if not self._settings.api_token.strip():
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                # Create with restrictive permissions before writing the secret.
                fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(token)
            except OSError:
                logger.exception("Could not persist rotated API token to %s", self._path)
        self._file_token = token
        self._rotated = token
        return token
