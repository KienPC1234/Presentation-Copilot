"""Real loopback TCP/WebSocket audio load, with real STT/RAG/LLM services.

Repeating one public human clip measures contention, not acoustic diversity,
semantic accuracy, remote-network performance or cross-talk resistance.
All output is allowlisted metadata; server logs can contain private transcripts.
"""
import argparse
import asyncio
from contextlib import AsyncExitStack
import hashlib
import json
import math
from pathlib import Path
import socket
import tempfile
import time


async def event(ws):
    while True:
        value = json.loads(await ws.recv())
        if value.get("type") != "ping":
            return value


async def evaluate(args, pcm):
    import uvicorn
    import websockets
    import main as app_module
    from config import settings
    rows, checks = [], []
    with tempfile.TemporaryDirectory(prefix="copilot-network-") as root:
        settings.chroma_persist_dir = str(Path(root) / "vectors")
        # Bind only an OS-selected loopback port; never expose this harness.
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            port = listener.getsockname()[1]
            server = uvicorn.Server(uvicorn.Config(app_module.app, log_level="warning", lifespan="on"))
            task = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                while not server.started:
                    if task.done():
                        await task
                        raise RuntimeError("Server did not start")
                    await asyncio.sleep(.1)
                await asyncio.to_thread(app_module._rag.ingest_documents, str(args.evidence))
                for run in range(1, args.runs + 1):
                    async with AsyncExitStack() as stack:
                        clients = [await stack.enter_async_context(websockets.connect(
                            f"ws://127.0.0.1:{port}/ws", max_size=2**20, ping_timeout=None))
                            for _ in range(args.sessions)]
                        async def set_topic(ws):
                            await ws.send(json.dumps({"type": "set_topic", "topic": args.topic}))
                            reply = await event(ws)
                            if reply != {"type": "topic_set", "topic": args.topic}:
                                raise RuntimeError("Topic handshake failed")
                        await asyncio.gather(*(set_topic(ws) for ws in clients))
                        checks.append({"run": run, "check": "distinct_active_contexts",
                                       "passed": app_module._ctx_registry.active_count() == args.sessions})
                        async def request(index, ws):
                            request_id = f"audio-{run}-{index}"
                            started = time.perf_counter()
                            received = []
                            try:
                                await ws.send(pcm)
                                await ws.send(json.dumps({"type": "trigger", "request_id": request_id}))
                                while True:
                                    reply = await asyncio.wait_for(event(ws), timeout=args.timeout)
                                    received.append(reply)
                                    if reply.get("type") in ("suggestion", "error"):
                                        break
                                types = [reply.get("type") for reply in received]
                                matched = all(reply.get("request_id") == request_id for reply in received)
                                ok = types == ["processing", "transcript", "suggestion"] and matched
                                transcript = next((r.get("transcript", "") for r in received if r.get("type") == "transcript"), "")
                                return {"run": run, "client": index, "seconds": round(time.perf_counter()-started, 3),
                                        "event_types": types, "request_ids_match": matched, "execution_passed": ok,
                                        "transcript_sha256": hashlib.sha256(transcript.encode()).hexdigest(),
                                        "transcript_units": len(transcript.split()),
                                        "server_timings_ms": reply.get("timings_ms", {})}
                            except Exception as exc:
                                return {"run": run, "client": index, "seconds": round(time.perf_counter()-started, 3),
                                        "execution_passed": False, "exception_type": type(exc).__name__}
                        batch = await asyncio.gather(*(request(i, ws) for i, ws in enumerate(clients)))
                        rows.extend(batch)
                        print(json.dumps({"run": run, "completed": len(batch),
                            "passed": sum(r["execution_passed"] for r in batch),
                            "slowest_seconds": max(r["seconds"] for r in batch)}), flush=True)
                    for _ in range(100):
                        if app_module._ctx_registry.active_count() == 0:
                            break
                        await asyncio.sleep(.05)
                    checks.append({"run": run, "check": "contexts_removed_after_disconnect",
                                   "passed": app_module._ctx_registry.active_count() == 0})
            finally:
                server.should_exit = True
                await task
    latencies = sorted(row["seconds"] for row in rows)
    p95 = latencies[math.ceil(.95 * len(latencies)) - 1]
    passed = all(row["execution_passed"] for row in rows) and all(c["passed"] for c in checks)
    return {"scope": __doc__, "sessions": args.sessions, "runs": args.runs,
            "whisper": args.whisper, "model": args.model, "answer_model": args.answer_model,
            "review_model": args.review_model, "style": "technical", "transport": "loopback TCP WebSocket",
            "audio_sha256": hashlib.sha256(args.audio.read_bytes()).hexdigest(),
            "clip_start_seconds": args.start, "clip_duration_seconds": len(pcm)/32000,
            "evidence_sha256": hashlib.sha256(args.evidence.read_bytes()).hexdigest(),
            "checks": checks, "results": rows, "execution_passed": passed,
            "all_requests_p95_seconds": p95, "audio_latency_gate_passed": p95 <= 60,
            "semantic_acceptance": "not evaluated", "reference_transcript": "not supplied; no WER claim",
            "isolation_limit": "Checks request IDs and context count/cleanup; repeated audio cannot establish semantic cross-session isolation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=float, default=516)
    parser.add_argument("--duration", type=float, default=24)
    parser.add_argument("--sessions", type=int, choices=range(1, 9), default=8)
    parser.add_argument("--runs", type=int, choices=range(1, 4), default=1)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--whisper", default="medium")
    parser.add_argument("--model", required=True)
    parser.add_argument("--answer-model", required=True)
    parser.add_argument("--review-model", required=True)
    parser.add_argument("--embedding-url", required=True)
    parser.add_argument("--topic", default="FPTEELiterature: học liệu và thi thử cho học sinh, giáo viên, trường học")
    args = parser.parse_args()
    if args.start < 0 or not 0 < args.duration <= 90 or args.timeout <= 0:
        parser.error("Invalid clip or timeout")
    from config import settings
    settings.whisper_model_size, settings.whisper_language = args.whisper, "vi"
    settings.whisper_initial_prompt = ""
    settings.ollama_model, settings.ollama_answer_model = args.model, args.answer_model
    settings.ollama_review_model, settings.ollama_embedding_base_url = args.review_model, args.embedding_url
    settings.response_style, settings.api_token = "technical", ""
    from faster_whisper.audio import decode_audio
    data = decode_audio(str(args.audio), sampling_rate=16000)
    data = data[int(args.start*16000):int((args.start+args.duration)*16000)]
    if not len(data):
        parser.error("Empty audio clip")
    pcm = (data.clip(-1, 1)*32767).astype("<i2").tobytes()
    report = asyncio.run(evaluate(args, pcm))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    if not report["execution_passed"] or not report["audio_latency_gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
