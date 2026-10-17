"""Runtime-editable settings exposed by the remote admin panel.

Environment variables remain the deployment defaults; this store holds the
values an operator changes from the browser so they survive a restart without
editing ``.env``. Anything security-relevant (mounts, the API token) is not
editable here.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from services.document_kinds import DOCUMENT_KINDS, LANGUAGES

logger = logging.getLogger(__name__)

_CLEANUP_TARGETS = ("runtime", "exports", "logs")
_MAX_PREBUILD_TOPICS = 20


def _clean_str_list(value: Any, allowed: tuple[str, ...] | None, limit: int) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Expected a list of strings")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("List items must be non-empty strings")
        item = item.strip()
        if allowed is not None and item not in allowed:
            raise ValueError(f"Unsupported value: {item}")
        if item not in cleaned:
            cleaned.append(item)
    if len(cleaned) > limit:
        raise ValueError("Too many items")
    return cleaned


class AdminSettingsStore:
    def __init__(self, settings) -> None:
        self._settings = settings
        self._path = Path(settings.admin_settings_file)
        self._data = self._defaults()
        self._load()

    # ── Defaults / persistence ─────────────────────────────────────────────

    def _defaults(self) -> dict[str, Any]:
        return {
            "response_style": self._settings.response_style,
            "default_language": "vi",
            "default_count": 6,
            "default_kinds": list(DOCUMENT_KINDS),
            "auto_prebuild": False,
            "prebuild_topics": [],
            "export_retention_days": self._settings.export_retention_days,
            "cleanup_on_startup": self._settings.cleanup_on_startup,
            "cleanup_targets": list(_CLEANUP_TARGETS),
            "agent_bash_enabled": self._settings.agent_bash_enabled,
            "agent_ingest_enabled": self._settings.agent_ingest_enabled,
            "agent_max_iterations": self._settings.agent_max_iterations,
            "live_caption_enabled": self._settings.live_caption_enabled,
            "live_caption_interval_seconds": self._settings.live_caption_interval_seconds,
        }

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError):
            logger.warning("Ignoring unreadable admin settings at %s", self._path)
            return
        if not isinstance(raw, dict):
            return
        try:
            merged = self._defaults()
            merged.update({key: raw[key] for key in merged if key in raw})
            self._data = self._validate(merged)
        except ValueError:
            logger.warning("Ignoring invalid admin settings at %s", self._path)

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self._path)
        except OSError:
            logger.exception("Could not persist admin settings to %s", self._path)

    def _validate(self, data: dict[str, Any]) -> dict[str, Any]:
        style = data.get("response_style")
        if style not in ("plain", "technical"):
            raise ValueError("Unsupported response style")
        language = data.get("default_language")
        if language not in LANGUAGES:
            raise ValueError("Unsupported language")

        count = data.get("default_count")
        if not isinstance(count, int) or isinstance(count, bool) or not 3 <= count <= 12:
            raise ValueError("Question count must be between 3 and 12")

        retention = data.get("export_retention_days")
        if not isinstance(retention, int) or isinstance(retention, bool) or not 0 <= retention <= 3650:
            raise ValueError("Retention days must be between 0 and 3650")

        for flag in ("auto_prebuild", "cleanup_on_startup", "agent_bash_enabled", "agent_ingest_enabled",
                     "live_caption_enabled"):
            if not isinstance(data.get(flag), bool):
                raise ValueError(f"{flag} must be a boolean")

        iterations = data.get("agent_max_iterations")
        if not isinstance(iterations, int) or isinstance(iterations, bool) or not 1 <= iterations <= 8:
            raise ValueError("Agent max iterations must be between 1 and 8")

        interval = data.get("live_caption_interval_seconds")
        if not isinstance(interval, (int, float)) or isinstance(interval, bool) or not 0.5 <= float(interval) <= 30:
            raise ValueError("Live caption interval must be between 0.5 and 30 seconds")

        topics = _clean_str_list(data.get("prebuild_topics", []), None, _MAX_PREBUILD_TOPICS)
        for topic in topics:
            if not 3 <= len(topic) <= 200:
                raise ValueError("Prebuild topics must be 3-200 characters")

        return {
            "response_style": style,
            "default_language": language,
            "default_count": count,
            "default_kinds": _clean_str_list(data.get("default_kinds", []), DOCUMENT_KINDS, len(DOCUMENT_KINDS)) or list(DOCUMENT_KINDS),
            "auto_prebuild": data["auto_prebuild"],
            "prebuild_topics": topics,
            "export_retention_days": retention,
            "cleanup_on_startup": data["cleanup_on_startup"],
            "cleanup_targets": _clean_str_list(data.get("cleanup_targets", []), _CLEANUP_TARGETS, len(_CLEANUP_TARGETS)) or list(_CLEANUP_TARGETS),
            "agent_bash_enabled": data["agent_bash_enabled"],
            "agent_ingest_enabled": data["agent_ingest_enabled"],
            "agent_max_iterations": iterations,
            "live_caption_enabled": data["live_caption_enabled"],
            "live_caption_interval_seconds": float(interval),
        }

    # ── Public API ─────────────────────────────────────────────────────────

    def get(self) -> dict[str, Any]:
        return dict(self._data)

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate a partial update and persist it. Raises ValueError on bad input."""
        if not isinstance(payload, dict):
            raise ValueError("Expected a settings object")
        candidate = dict(self._data)
        for key in candidate:
            if key in payload:
                candidate[key] = payload[key]
        self._data = self._validate(candidate)
        self._save()
        return self.get()
