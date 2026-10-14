import wave
import struct
import logging
import numpy as np

logger = logging.getLogger(__name__)


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

