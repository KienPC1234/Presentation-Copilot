"""Opt-in full pipeline smoke via FastAPI's in-process WebSocket client.

Run with public/synthetic audio only when --model selects a cloud model.
"""

import sys
from pathlib import Path as _Path

# Allow running from server/tools/ by putting the server package root on the path.
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
import argparse
import json
from pathlib import Path
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--embedding-url", required=True)
    parser.add_argument("--output", default="protocol-smoke.json")
    args = parser.parse_args()
    from config import settings
    settings.whisper_model_size = "tiny"
    settings.whisper_language = "en"
    settings.whisper_initial_prompt = ""
    settings.ollama_model = args.model
    settings.ollama_embedding_base_url = args.embedding_url
    settings.api_token = ""
    from fastapi.testclient import TestClient
    from faster_whisper.audio import decode_audio
    import main as server
    with tempfile.TemporaryDirectory(prefix="copilot-protocol-") as root:
        settings.chroma_persist_dir = str(Path(root) / "vectors")
        data = decode_audio(str(args.audio), sampling_rate=16000)
        pcm = (data.clip(-1, 1) * 32767).astype("<i2").tobytes()
        with TestClient(server.app, base_url="http://localhost:8765") as client:
            assert client.get("/health").status_code == 200
            events = []
            started = time.perf_counter()
            with client.websocket_connect("ws://localhost:8765/ws") as ws:
                ws.send_bytes(pcm)
                ws.send_json({"type": "trigger", "request_id": "protocol-smoke"})
                while True:
                    event = ws.receive_json()
                    if event["type"] == "ping":
                        continue
                    events.append(event)
                    if event["type"] in ("suggestion", "error"):
                        break
            assert [event["type"] for event in events][:2] == ["processing", "transcript"]
            assert events[-1]["type"] == "suggestion", events[-1]
            assert all(event.get("request_id") == "protocol-smoke" for event in events)
            report = {"transport": "FastAPI TestClient; not external network or WPF",
                      "model": args.model, "whisper": "tiny", "events": events,
                      "elapsed_seconds": round(time.perf_counter() - started, 2)}
            Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"events": [event["type"] for event in events],
                              "elapsed_seconds": report["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
