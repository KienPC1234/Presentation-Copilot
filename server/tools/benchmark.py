"""Measure STT, retrieval and agent latency with installed local models.

Examples:
    python benchmark.py --question "Hệ thống chịu tải thế nào?" --runs 3
    python benchmark.py --wav question.wav --runs 3
"""

import sys
from pathlib import Path as _Path

# Allow running from server/tools/ by putting the server package root on the path.
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse
import json
import statistics
import time
from pathlib import Path

from services.agent_service import AgentService
from services.context_manager import SessionContext
from services.rag_service import RAGService
from services.transcriber import TranscriberService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--question", help="Skip STT and use this question directly")
    source.add_argument("--wav", type=Path, help="Audio input for Whisper")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1 or args.runs > 20:
        parser.error("--runs must be between 1 and 20")
    if args.wav and not args.wav.is_file():
        parser.error("--wav must point to an existing file")

    transcriber = TranscriberService() if args.wav else None
    rag = RAGService()
    agent = AgentService(rag)
    samples: list[dict[str, float]] = []
    for run in range(args.runs):
        start = time.perf_counter()
        question = transcriber.transcribe(str(args.wav)) if transcriber else args.question
        stt_end = time.perf_counter()
        if not question:
            raise RuntimeError("No speech detected in input audio")
        rag.query(question, top_k=3)
        rag_end = time.perf_counter()
        result = agent.run(question, SessionContext(f"benchmark-{run}", max_turns=5))
        end = time.perf_counter()
        sample = {
            "stt_ms": round((stt_end - start) * 1000, 1),
            "retrieval_ms": round((rag_end - stt_end) * 1000, 1),
            "agent_ms": round((end - rag_end) * 1000, 1),
            "total_ms": round((end - start) * 1000, 1),
        }
        samples.append(sample)
        print(json.dumps({"run": run + 1, "question": question, "timings": sample,
                          "key_point": result.get("key_point", ""),
                          "error": result.get("error")}, ensure_ascii=False))

    print(json.dumps({"median_ms": {key: round(statistics.median(s[key] for s in samples), 1)
                                    for key in samples[0]}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
