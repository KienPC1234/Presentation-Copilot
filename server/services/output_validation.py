"""Validate model output before any content is displayed or remembered."""
import json
import re


def parse_suggestion(text: str) -> dict:
    if not isinstance(text, str) or len(text) > 20000:
        raise ValueError("Invalid model output")
    text = text.strip()
    if text.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if not match:
            raise ValueError("Malformed JSON fence")
        text = match.group(1)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    point = data.get("key_point")
    if not isinstance(point, str) or not point.strip() or len(point) > 2000:
        raise ValueError("Invalid key_point")
    result = {"key_point": point.strip()}
    for name, limit in (("keywords", 5), ("framework_steps", 4)):
        values = data.get(name)
        if not isinstance(values, list) or len(values) > limit or any(
            not isinstance(value, str) or not value.strip() or len(value) > 1000 for value in values
        ):
            raise ValueError(f"Invalid {name}")
        result[name] = list(dict.fromkeys(value.strip() for value in values))
    # Unknown model fields cannot overwrite protocol fields or forge provenance.
    return result
