"""Clean up speech transcripts before the answer engine sees them.

Whisper sometimes repeats the tail of a question, especially on unclear audio.
A repeated sentence wastes context and pushes the model to hedge, so immediate
duplicates are collapsed. Conservative by design: only a sentence equal to, or
contained in, one of the previous few is removed, plus adjacent repeated word
blocks of three words or more.
"""

from __future__ import annotations

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
_NORMALISE = re.compile(r"\W+", re.UNICODE)
_MIN_CONTAINED_CHARS = 12
_MIN_BLOCK_WORDS = 3
_MAX_BLOCK_WORDS = 8


def _norm(sentence: str) -> str:
    return _NORMALISE.sub(" ", sentence).strip().casefold()


def _collapse_adjacent_blocks(words: list[str]) -> list[str]:
    changed = True
    while changed:
        changed = False
        out: list[str] = []
        index = 0
        while index < len(words):
            limit = min(_MAX_BLOCK_WORDS, (len(words) - index) // 2)
            for size in range(limit, _MIN_BLOCK_WORDS - 1, -1):
                if words[index:index + size] == words[index + size:index + 2 * size]:
                    out.extend(words[index:index + size])
                    index += 2 * size
                    changed = True
                    break
            else:
                out.append(words[index])
                index += 1
        words = out
    return words


def collapse_repetitions(text: str, lookback: int = 8) -> str:
    """Drop repeated sentences and adjacent repeated phrases.

    Whisper can repeat a phrase several sentences later, so the lookback is
    generous; containment still requires a 12+ character, near-exact match.
    """
    if not text:
        return text
    seen: list[str] = []
    kept: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        key = _norm(sentence)
        repeated = key in seen[-lookback:]
        contained = len(key) >= _MIN_CONTAINED_CHARS and any(key in prior for prior in seen[-lookback:])
        if key and (repeated or contained):
            continue
        kept.append(sentence)
        if key:
            seen.append(key)
    joined = " ".join(kept)
    return " ".join(_collapse_adjacent_blocks(joined.split()))
