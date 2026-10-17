"""Validate the AI-generated markdown pack before it is cached or shown.

The rules mirror the defense service: fixed section shapes, bounded strings,
evidence references limited to IDs the server actually supplied, and no
model-authored provenance fields.
"""

from __future__ import annotations

from typing import Any

_MAX_REBUTTALS = 12
_MAX_OUTLINE_SECTIONS = 12
_MAX_POINTS = 6
_MAX_CHEAT_NUMBERS = 12
_MAX_ONE_LINERS = 12


def _text(value: Any, limit: int, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"Invalid {field}")
    return value.strip()


def _refs(value: Any, allowed: set[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or item not in allowed for item in value):
        raise ValueError("Unknown evidence reference")
    return list(dict.fromkeys(value))


def _string_list(value: Any, limit: int, item_limit: int, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"Invalid {field}")
    return [_text(item, item_limit, field) for item in value]


def validate_rebuttals(items: Any, allowed: set[str], question_ids: set[str]) -> list[dict[str, Any]]:
    if not isinstance(items, list) or len(items) > _MAX_REBUTTALS:
        raise ValueError("Invalid rebuttal list")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid rebuttal entry")
        question_id = _text(item.get("question_id"), 40, "question_id")
        if question_id not in question_ids:
            raise ValueError("Unknown question reference")
        result.append({
            "question_id": question_id,
            "objection": _text(item.get("objection"), 1000, "objection"),
            "answer_points": _string_list(item.get("answer_points", []), _MAX_POINTS, 700, "answer_points"),
            "evidence_ids": _refs(item.get("evidence_ids"), allowed),
            "fallback": _text(item.get("fallback"), 1000, "fallback"),
        })
    return result


def validate_outline(items: Any, allowed: set[str]) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not items or len(items) > _MAX_OUTLINE_SECTIONS:
        raise ValueError("Invalid outline")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid outline section")
        result.append({
            "title": _text(item.get("title"), 200, "title"),
            "points": _string_list(item.get("points", []), _MAX_POINTS, 700, "points"),
            "evidence_ids": _refs(item.get("evidence_ids"), allowed),
        })
    return result


def validate_cheatsheet(data: Any, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Invalid cheatsheet")
    one_liners = data.get("one_liners", [])
    if not isinstance(one_liners, list) or len(one_liners) > _MAX_ONE_LINERS:
        raise ValueError("Invalid one_liners")
    cleaned = []
    for item in one_liners:
        if not isinstance(item, dict):
            raise ValueError("Invalid one-liner")
        cleaned.append({
            "question": _text(item.get("question"), 500, "question"),
            "answer": _text(item.get("answer"), 700, "answer"),
            "evidence_ids": _refs(item.get("evidence_ids"), allowed),
        })
    return {
        "key_numbers": _string_list(data.get("key_numbers", []), _MAX_CHEAT_NUMBERS, 300, "key_numbers"),
        "key_terms": _string_list(data.get("key_terms", []), _MAX_CHEAT_NUMBERS, 120, "key_terms"),
        "one_liners": cleaned,
    }
