import wave
import struct
import logging
import shutil
import subprocess
import numpy as np

logger = logging.getLogger(__name__)

# Suffixes we can hand to ffmpeg for Opus encoding, and the muxer to force.
_OPUS_MUXERS = {
    ".m4a": "mp4",
    ".mp4": "mp4",
    ".oga": "ogg",
    ".ogg": "ogg",
    ".opus": "ogg",
    ".webm": "webm",
}


def pcm_bytes_to_wav(pcm_bytes: bytes, sample_rate: int, output_path: str) -> None:
    """Write raw 16-bit mono PCM bytes as a proper WAV file.

    Args:
        pcm_bytes: Raw PCM audio data (16-bit signed, mono).
        sample_rate: Sample rate in Hz (e.g. 16000).
        output_path: Destination file path for the WAV file.
    """
    num_channels = 1
    sample_width = 2  # 16-bit = 2 bytes

    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)

    logger.debug("Wrote WAV file: %s (%d bytes PCM)", output_path, len(pcm_bytes))


def pcm_bytes_to_opus(pcm_bytes: bytes, sample_rate: int, output_path: str,
                      bitrate: str = "32k") -> None:
    """Encode raw 16-bit mono PCM to Opus using ffmpeg (the modern narrowband codec).

    The container follows ``output_path``'s suffix: ``.m4a``/``.mp4`` (MP4),
    ``.ogg``/``.opus``/``.oga`` (Ogg) or ``.webm``. Raises ``RuntimeError`` when
    ffmpeg is missing or the encode fails so the caller can fall back to WAV.
    """
    suffix = ("." + output_path.rsplit(".", 1)[-1].lower()) if "." in output_path else ""
    muxer = _OPUS_MUXERS.get(suffix)
    if muxer is None:
        raise RuntimeError(f"Unsupported Opus container: {output_path}")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is not installed; cannot encode Opus audio")

    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "-i", "pipe:0",
        "-c:a", "libopus", "-b:a", bitrate, "-vbr", "on", "-application", "voip",
        "-f", muxer,
    ]
    if muxer == "mp4":
        # Opus-in-MP4 is still flagged experimental by some ffmpeg builds.
        command += ["-strict", "-2"]
    command.append(output_path)

    try:
        completed = subprocess.run(command, input=pcm_bytes, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Opus encoder could not run: {exc}") from exc

    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()[:300]
        raise RuntimeError(f"Opus encoder failed: {detail}")

    logger.debug("Wrote Opus file: %s (%d bytes PCM -> %s)", output_path, len(pcm_bytes), suffix)


def write_audio_file(pcm_bytes: bytes, sample_rate: int, output_path: str) -> None:
    """Write PCM to the format implied by ``output_path``'s suffix."""
    if output_path.lower().endswith(".wav"):
        pcm_bytes_to_wav(pcm_bytes, sample_rate, output_path)
        return
    pcm_bytes_to_opus(pcm_bytes, sample_rate, output_path)


def normalize_audio(pcm_bytes: bytes) -> bytes:
    """Normalize amplitude of 16-bit mono PCM audio.

    Scales samples so the peak amplitude reaches ~90% of the 16-bit maximum,
    which prevents clipping while maximising signal level.

    Args:
        pcm_bytes: Raw 16-bit signed mono PCM bytes.

    Returns:
        Amplitude-normalised PCM bytes in the same format.
    """
    if len(pcm_bytes) < 2:
        return pcm_bytes

    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    peak = np.abs(samples).max()

    if peak < 1.0:
        logger.debug("Audio is silent, skipping normalisation")
        return pcm_bytes

    target_peak = 0.9 * 32767.0
    scale = target_peak / peak
    normalised = np.clip(samples * scale, -32768, 32767).astype(np.int16)
    logger.debug("Normalised audio: peak %.1f → %.1f (scale %.4f)", peak, target_peak, scale)
    return normalised.tobytes()

