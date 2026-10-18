"""Benchmark Whisper models on real clips: latency, WER, and the effect of filters.

Compares faster-whisper model sizes for Vietnamese and English, with and without
the production post-processing (repetition collapse + prompt-echo guard), so the
model choice and the filters can be judged with numbers instead of guesswork.

Manifest (JSON): {"clips": [{"id","audio_file","reference","lang"}, ...]}

    python tools/stt_benchmark.py --manifest bench.json --models tiny,base,small,medium \
        --device cuda --compute-type float16 --out bench.json
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from faster_whisper import WhisperModel  # noqa: E402
from services.transcript import collapse_repetitions  # noqa: E402


def _normalise(text):
    keep = []
    for ch in text.lower():
        keep.append(ch if (ch.isalnum() or ch.isspace()) else " ")
    return " ".join("".join(keep).split())


def wer(reference, hypothesis):
    ref, hyp = _normalise(reference).split(), _normalise(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i]
        for j, h in enumerate(hyp, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h)))
        previous = current
    return previous[-1] / len(ref)


def run_model(name, clips, device, compute_type, vad, apply_filters, languages):
    model = WhisperModel(name, device=device, compute_type=compute_type)
    rows = []
    for clip in clips:
        started = time.perf_counter()
        segments, info = model.transcribe(
            clip["audio_file"],
            language=clip.get("lang") or None,
            initial_prompt=None,
            vad_filter=vad,
            vad_parameters={"min_silence_duration_ms": 300} if vad else None,
        )
        raw = " ".join(segment.text.strip() for segment in segments).strip()
        seconds = time.perf_counter() - started
        filtered = collapse_repetitions(raw) if apply_filters else raw
        rows.append({
            "id": clip["id"], "lang": clip.get("lang"), "seconds": round(seconds, 2),
            "raw": raw, "filtered": filtered,
            "wer_raw": round(wer(clip["reference"], raw), 3),
            "wer_filtered": round(wer(clip["reference"], filtered), 3),
            "detected": getattr(info, "language", None),
        })
    del model
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--models", default="tiny,base,small,medium")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--no-vad", action="store_true", help="disable VAD (see if it cuts content)")
    parser.add_argument("--out", default="")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    clips = data["clips"][: args.limit] if args.limit else data["clips"]
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    results = {}
    for name in models:
        print(f"\n=== model {name} ({args.device}/{args.compute_type}, vad={not args.no_vad})")
        try:
            rows = run_model(name, clips, args.device, args.compute_type,
                             not args.no_vad, True, set(c["lang"] for c in clips))
        except Exception as exc:  # a model that cannot load must not stop the run
            print(f"  failed: {type(exc).__name__}: {exc}")
            results[name] = {"error": str(exc)}
            continue
        wers = [r["wer_raw"] for r in rows]
        secs = [r["seconds"] for r in rows]
        results[name] = {
            "mean_wer": round(sum(wers) / len(wers), 3),
            "mean_seconds": round(sum(secs) / len(secs), 2),
            "rows": rows,
        }
        for row in rows:
            print(f"  [{row['lang']}] {row['seconds']:5.2f}s wer={row['wer_raw']:.2f} "
                  f"filtered={row['wer_filtered']:.2f} :: {row['raw'][:70]}")

    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== summary")
    for name, data in results.items():
        if "error" in data:
            print(f"  {name:14} FAILED")
        else:
            print(f"  {name:14} mean WER {data['mean_wer']:.2f} | mean {data['mean_seconds']:.2f}s/clip")


if __name__ == "__main__":
    main()
