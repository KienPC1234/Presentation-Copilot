"""Decide when a live caption is worth sending to the client.

Captions are best-effort: the server transcribes a rolling window while the
client keeps streaming. We only push text when there is new audio, the
transcript is non-empty and it actually changed, so the HUD does not flicker.
"""

from __future__ import annotations

MIN_NEW_AUDIO_SECONDS = 0.8


def should_emit(new_audio_seconds: float, transcript: str, previous_text: str,
                min_seconds: float = MIN_NEW_AUDIO_SECONDS) -> bool:
    text = (transcript or "").strip()
    if not text:
        return False
    if new_audio_seconds < min_seconds:
        return False
    return text != (previous_text or "").strip()
