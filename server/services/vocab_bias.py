"""Build a vocabulary-bias prompt for Whisper from the ingested corpus.

Whisper recognises English technical terms inside Vietnamese speech much better
when they appear in its ``initial_prompt``. Instead of hand-maintaining that list,
the terms are mined from the project documents that were indexed (identifiers,
acronyms, filenames, library names) and stored next to the Chroma database.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"(?<!\w)[A-Za-z][A-Za-z0-9+#._/-]{1,30}", re.UNICODE)
_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "are", "was", "were", "have", "has",
    "not", "you", "your", "our", "but", "can", "will", "all", "any", "use", "used", "using",
    "true", "false", "none", "null", "self", "return", "import", "class", "def", "print",
    "http", "https", "www", "com", "org", "và", "các", "cho", "với", "trong", "khi",
    "info", "warning", "error", "debug", "ok", "pass", "fail",
}
# A token is "technical-looking" if it is an acronym, CamelCase, contains a digit
# or a symbol words do not, or is a known tool/library name (Docker, Redis, …).
_TECHNICAL = re.compile(r"[0-9._/+#-]|[A-Z]")
_KNOWN_TECH = {
    "docker", "redis", "celery", "ollama", "chroma", "whisper", "faiss", "python", "django",
    "mysql", "postgres", "postgresql", "sqlite", "node", "react", "angular", "vue", "nginx",
    "kubernetes", "langchain", "fastapi", "uvicorn", "playwright", "selenium", "tensorflow",
    "pytorch", "openai", "gpt", "llm", "rag", "api", "gpu", "cpu", "ocr", "stt", "tts", "sse",
    "http", "json", "yaml", "jwt", "oauth", "tailwind", "typescript", "javascript", "dockerfile",
    "yara", "clamav", "pefile", "oletools", "vietocr", "cloudflare", "turnstile", "mcp", "faiss",
}


def _looks_technical(token: str) -> bool:
    folded = token.casefold()
    if folded in _STOPWORDS:
        return False
    if "/" in token or "\\" in token:  # filesystem paths are not spoken terms
        return False
    if folded in _KNOWN_TECH:
        return True
    return bool(_TECHNICAL.search(token[1:]))


def _is_strong(token: str) -> bool:
    """Acronyms, CamelCase and known tools rank above markup/CSS noise."""
    if token.casefold() in _KNOWN_TECH:
        return True
    return bool(re.search(r"[A-Z]", token[1:])) or token.isupper()


def extract_terms(texts: Iterable[str], limit: int = 60) -> list[str]:
    """Return the most relevant technical tokens, strong terms first."""
    counts: Counter[str] = Counter()
    original: dict[str, str] = {}
    for text in texts:
        for raw in _TOKEN.findall(text or ""):
            token = raw.rstrip(".")
            if len(token) < 2 or not _looks_technical(token):
                continue
            key = token.casefold()
            counts[key] += 1
            original.setdefault(key, token)
    ordered = sorted(counts, key=lambda key: (not _is_strong(original[key]), -counts[key]))
    return [original[key] for key in ordered[:limit]]


def compose_prompt(base: str, terms: list[str], max_chars: int = 900) -> str:
    """Append the mined terms to the configured prompt, within Whisper's taste."""
    base = (base or "").strip().rstrip(",;")
    if not terms:
        return base
    combined = f"{base}, {', '.join(terms)}" if base else ", ".join(terms)
    return combined[:max_chars]


_cache: dict[str, tuple[float, list[str]]] = {}


def load_vocab(path: str) -> list[str]:
    """Load the stored terms; reloads only when the file changes."""
    try:
        stat = Path(path).stat()
    except OSError:
        return []
    key = str(path)
    cached = _cache.get(key)
    if cached and cached[0] == stat.st_mtime:
        return cached[1]
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    terms = data.get("terms") if isinstance(data, dict) else None
    terms = [t for t in terms if isinstance(t, str)] if isinstance(terms, list) else []
    _cache[key] = (stat.st_mtime, terms)
    return terms


def store_vocab(path: str, terms: list[str]) -> None:
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"terms": terms}, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("Could not write the vocabulary file %s", target)
