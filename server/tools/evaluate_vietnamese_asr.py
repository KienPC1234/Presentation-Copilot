"""Score real Vietnamese speech with existing reference transcripts.

Never generates references from recognition output. Data stays outside Git.
"""

import sys
from pathlib import Path as _Path

# Allow running from server/tools/ by putting the server package root on the path.
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

import numpy as np
from faster_whisper.audio import decode_audio

from services.rehearsal_metrics import word_error_rate


def noisy_audio(audio, snr_db, seed):
    """Deterministic additive Gaussian noise, not an actual meeting recording."""
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(len(audio)).astype(np.float32)
    signal_power = float(np.mean(audio ** 2))
    noise_power = float(np.mean(noise ** 2))
    if signal_power == 0 or noise_power == 0:
        raise ValueError("Non-silent speech required for SNR")
    noisy = audio + noise * np.sqrt(signal_power / (10 ** (snr_db / 10) * noise_power))
    # Scale both signal and noise together, preserving the requested SNR.
    return noisy / max(1.0, float(np.max(np.abs(noisy))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--whisper-model", choices=["tiny", "base", "small", "medium", "large-v3"], default="base")
    parser.add_argument("--noise-snr-db", type=float)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    base = args.manifest.resolve().parent
    from config import settings
    settings.whisper_model_size = args.whisper_model
    settings.whisper_language = "vi"
    settings.whisper_initial_prompt = ""
    from services.transcriber import TranscriberService
    from services.audio_utils import normalize_audio, pcm_bytes_to_wav
    import tempfile
    transcriber = TranscriberService()
    results = []
    for index, item in enumerate(manifest["clips"]):
        path = (base / item["audio_file"]).resolve()
        if not path.is_relative_to(base):
            raise ValueError("Fixture outside manifest directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["audio_sha256"]:
            raise ValueError("Audio checksum mismatch")
        audio = decode_audio(str(path), sampling_rate=16000)
        if args.noise_snr_db is not None:
            audio = noisy_audio(audio, args.noise_snr_db, 20261016 + index)
        pcm = (audio.clip(-1, 1) * 32767).astype("<i2").tobytes()
        with tempfile.TemporaryDirectory(prefix="copilot-asr-") as root:
            wav = str(Path(root) / "input.wav")
            pcm_bytes_to_wav(normalize_audio(pcm), 16000, wav)
            started = time.perf_counter()
            hypothesis = transcriber.transcribe(wav)
            seconds = time.perf_counter() - started
        words = len(re.findall(r"\w+", item["reference"].casefold()))
        wer = word_error_rate(item["reference"], hypothesis)
        result = {"id": item["id"], "audio_file": item["audio_file"], "audio_sha256": item["audio_sha256"],
                  "reference_sha256": hashlib.sha256(item["reference"].encode()).hexdigest(),
                  "duration_seconds": round(len(audio) / 16000, 2), "elapsed_seconds": round(seconds, 2),
                  "reference_words": words, "word_errors": round(wer * words), "wer": wer,
                  "hypothesis_sha256": hashlib.sha256(hypothesis.encode()).hexdigest()}
        results.append(result)
        print(json.dumps(result), flush=True)
    report = {"scope": "Human-read Vietnamese benchmark speech, not spontaneous interview or room acoustics",
              "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
              "dataset": manifest.get("dataset"), "revision": manifest.get("revision"), "split": manifest.get("split"),
              "selection": manifest.get("selection"), "model": args.whisper_model,
              "noise": None if args.noise_snr_db is None else {"type": "additive Gaussian, generated", "snr_db": args.noise_snr_db, "seed_base": 20261016},
              "normalization": "casefold, Unicode word tokens; Vietnamese whitespace units, not linguistic word segmentation",
              "aggregate_wer": sum(r["word_errors"] for r in results) / sum(r["reference_words"] for r in results),
              "clips": results}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "clips"}), flush=True)


if __name__ == "__main__":
    main()
