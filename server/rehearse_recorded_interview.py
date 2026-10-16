"""Replay timestamped human questions about a real project through the real backend.

Audio, evidence and private answer reports stay on the test machine. No TTS.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time

from services.rehearsal_metrics import word_error_rate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--embedding-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    base = args.manifest.resolve().parent
    audio_path = (base / manifest["audio_file"]).resolve()
    evidence_path = (base / manifest["evidence_file"]).resolve()
    if not audio_path.is_relative_to(base) or not evidence_path.is_relative_to(base):
        raise ValueError("Fixture paths must remain inside the manifest directory")
    digest = hashlib.sha256(audio_path.read_bytes()).hexdigest()
    if digest != manifest["audio_sha256"]:
        raise ValueError("Audio checksum mismatch")
    from config import settings
    settings.ollama_model = args.model
    settings.ollama_embedding_base_url = args.embedding_url
    settings.whisper_model_size = "base"
    settings.whisper_language = "en"
    settings.whisper_initial_prompt = ""
    settings.api_token = ""
    from fastapi.testclient import TestClient
    from faster_whisper.audio import decode_audio
    import main as server
    decoded = decode_audio(str(audio_path), sampling_rate=16000)
    report = {"project": manifest["topic"], "recording_kind": manifest["recording_kind"],
              "source_page": manifest["source_page"], "audio_sha256": digest,
              "model": args.model, "whisper": "base", "clips": [],
              "scope": "In-process WebSocket; original public interview questions transferred to a different real product; no human candidate interviewed"}
    with tempfile.TemporaryDirectory(prefix="copilot-real-interview-") as root:
        settings.chroma_persist_dir = str(Path(root) / "vectors")
        with TestClient(server.app, base_url="http://localhost:8765") as client:
            server._rag.ingest_documents(str(evidence_path))
            response = client.post("/api/defense/prepare", json={"topic": manifest["topic"],
                "focus": "Trình bày sản phẩm thật, không khẳng định tải hoặc kết quả kiểm thử chưa có bằng chứng.", "count": 6, "language": "vi"})
            response.raise_for_status()
            report["preparation"] = response.json()
            with client.websocket_connect("ws://localhost:8765/ws") as ws:
                ws.send_json({"type": "set_topic", "topic": manifest["topic"]})
                assert ws.receive_json()["type"] == "topic_set"
                for index, clip in enumerate(manifest["clips"]):
                    start, end = clip["start_seconds"], clip["end_seconds"]
                    if not 0 <= start < end <= len(decoded) / 16000 or end - start > 90:
                        raise ValueError("Invalid audio clip range")
                    pcm = (decoded[int(start * 16000):int(end * 16000)].clip(-1, 1) * 32767).astype("<i2").tobytes()
                    request_id = f"recorded-{index}"
                    started = time.perf_counter()
                    ws.send_bytes(pcm)
                    ws.send_json({"type": "trigger", "request_id": request_id})
                    transcript = ""
                    events = []
                    while True:
                        event = ws.receive_json()
                        if event["type"] == "ping":
                            continue
                        assert event.get("request_id") == request_id
                        events.append(event["type"])
                        if event["type"] == "transcript":
                            transcript = event["transcript"]
                        if event["type"] in ("suggestion", "error"):
                            break
                    # Do not redistribute full copyrighted interview transcripts.
                    event.pop("transcript", None)
                    result = {"id": clip["id"], "range_seconds": [start, end], "events": events,
                              "duration_seconds": round(end - start, 2), "elapsed_seconds": round(time.perf_counter() - started, 2),
                              "asr_word_count": len(transcript.split()),
                              "asr_sha256": hashlib.sha256(transcript.encode()).hexdigest(),
                              "asr_keywords": {term: term.casefold() in transcript.casefold() for term in clip["asr_keywords"]},
                              "response": event}
                    if clip.get("reference_transcript"):
                        result["wer"] = word_error_rate(clip["reference_transcript"], transcript)
                    report["clips"].append(result)
                    print(json.dumps({"id": clip["id"], "events": events, "asr_keywords": result["asr_keywords"], "wer": result.get("wer")}), flush=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if any(item["response"]["type"] != "suggestion" for item in report["clips"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
