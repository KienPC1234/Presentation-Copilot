"""Audio container handling: WAV always works, Opus needs ffmpeg."""
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

try:
    from services.audio_utils import (
        _OPUS_MUXERS,
        normalize_audio,
        pcm_bytes_to_opus,
        pcm_bytes_to_wav,
        write_audio_file,
    )
except ImportError:  # numpy (and therefore the module) may be absent
    write_audio_file = None


def _tone_pcm(seconds: float = 0.5, sample_rate: int = 16000) -> bytes:
    import math
    count = int(seconds * sample_rate)
    frames = bytearray()
    for index in range(count):
        value = int(12000 * math.sin(2 * 3.141592653589793 * 440 * index / sample_rate))
        frames += value.to_bytes(2, "little", signed=True)
    return bytes(frames)


@unittest.skipIf(write_audio_file is None, "Requires numpy")
class AudioFormatTests(unittest.TestCase):
    def test_wav_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.wav"
            pcm = _tone_pcm()
            pcm_bytes_to_wav(pcm, 16000, str(path))
            with wave.open(str(path), "rb") as handle:
                self.assertEqual(handle.getnchannels(), 1)
                self.assertEqual(handle.getframerate(), 16000)
                self.assertEqual(handle.getsampwidth(), 2)
                self.assertEqual(handle.getnframes(), len(pcm) // 2)

    def test_write_audio_file_dispatches_on_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.wav"
            write_audio_file(_tone_pcm(), 16000, str(path))
            self.assertTrue(path.exists())

    def test_unknown_container_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                write_audio_file(_tone_pcm(), 16000, str(Path(tmp) / "clip.flac"))

    def test_mapping_covers_the_documented_containers(self):
        for suffix in (".m4a", ".mp4", ".ogg", ".opus", ".oga", ".webm"):
            self.assertIn(suffix, _OPUS_MUXERS)

    def test_normalize_scales_towards_target_peak(self):
        quiet = (100).to_bytes(2, "little", signed=True) * 100
        import numpy as np
        samples = np.frombuffer(normalize_audio(quiet), dtype=np.int16)
        self.assertGreater(int(np.abs(samples).max()), 100)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_opus_encode_decodes_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            pcm = _tone_pcm(1.0)
            for suffix in (".ogg", ".m4a"):
                path = Path(tmp) / f"clip{suffix}"
                write_audio_file(pcm, 16000, str(path))
                self.assertGreater(path.stat().st_size, 0)
                probe = subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
                     "-f", "null", "-"],
                    capture_output=True, timeout=60)
                self.assertEqual(probe.returncode, 0, probe.stderr.decode("utf-8", "replace"))

    @unittest.skipIf(shutil.which("ffmpeg"), "only meaningful without ffmpeg")
    def test_opus_without_ffmpeg_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                pcm_bytes_to_opus(_tone_pcm(), 16000, str(Path(tmp) / "clip.m4a"))


if __name__ == "__main__":
    unittest.main()
