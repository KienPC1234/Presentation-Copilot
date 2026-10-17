"""Sliding audio window used by the WebSocket handler.

The Windows client streams loopback audio continuously. The server keeps only
the most recent ``MAX_AUDIO_SECONDS`` of it and analyses a bounded tail when the
hotkey fires, so a long session never loses the question just asked and an
older question cannot leak into the next answer.
"""

from __future__ import annotations


def append_chunk(buffer: bytearray, chunk: bytes, max_bytes: int) -> bool:
    """Append ``chunk`` keeping at most ``max_bytes``. True if old audio was dropped."""
    if max_bytes <= 0:
        dropped = bool(buffer) or bool(chunk)
        buffer.clear()
        return dropped

    if len(chunk) >= max_bytes:
        buffer[:] = chunk[-max_bytes:]
        return True

    buffer.extend(chunk)
    excess = len(buffer) - max_bytes
    if excess > 0:
        del buffer[:excess]
        return True
    return False


def snapshot(buffer: bytearray, seconds: int | None, sample_rate: int) -> bytearray:
    """Return the analysis window and clear the buffer.

    16-bit mono PCM means two bytes per sample. ``seconds is None`` keeps the
    whole buffer, which preserves behaviour for clients that send audio only
    when the hotkey is pressed.
    """
    if seconds is None:
        window = bytearray(buffer)
    else:
        window_bytes = max(1, sample_rate * 2 * seconds)
        window = bytearray(buffer[-window_bytes:])
    buffer.clear()
    return window
