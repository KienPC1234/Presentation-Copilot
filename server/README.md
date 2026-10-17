# Presentation Copilot — Server

Python WebSocket server that receives PCM audio from a C# client, transcribes it with Whisper, retrieves relevant project context via RAG (ChromaDB), and returns structured presentation suggestions from an Ollama LLM.

Professional acceptance is still pending. The technical-style structured review,
new evaluation runners, reproducible commands and known limits are documented in
[STRUCTURED_AI_REVIEW.md](../STRUCTURED_AI_REVIEW.md). Plain style still uses the
earlier review path; model-reviewed output is not independently verified truth.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Tested on 3.11 |
| [Ollama](https://ollama.com/) | Must be running locally or accessible via network |
| ffmpeg | Required by faster-whisper for audio decoding |

### Install ffmpeg

- **Windows**: `winget install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html)
- **macOS**: `brew install ffmpeg`
- **Linux**: `apt-get install ffmpeg`

---

## Setup (Local)

### 1. Clone and enter the server directory

```bash
cd server
```

### 2. Copy environment config

```bash
cp .env.example .env
```

Edit `.env` as needed (Ollama URL, model names, device settings).

### 3. Create a virtual environment and install dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Pull Ollama models

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

---

## Ingest Project Documents

Copy your project files (PDF, Markdown, or plain text) into `data/docs/`:

```bash
cp /path/to/your/project/docs/*.pdf data/docs/
cp /path/to/your/project/docs/*.md  data/docs/
```

Then run the ingestion CLI:

```bash
python ingest.py
# or specify a custom directory:
python ingest.py --docs-dir /path/to/custom/docs
```

This embeds all documents into ChromaDB at `./data/chroma/`. Re-run whenever you add or change files. Existing chunks for each re-indexed file are replaced; the response includes related source names and PDF page numbers where available.

---

## Run the Server

```bash
uvicorn main:app --host 127.0.0.1 --port 8765
```

The server exposes:

| Endpoint | Method | Description |
|---|---|---|
| `/ws` | WebSocket | Main audio + control channel |
| `/health` | GET | Liveness check |
| `/api/ingest` | POST | Trigger re-ingestion of a chosen path |

By default, API and WebSocket access is limited to the local machine. For access from another machine, set a long random `API_TOKEN` in `server/.env`, start Uvicorn on an explicitly chosen network interface, and set `PRESENTATION_COPILOT_API_TOKEN` to the same value in the Windows client's environment. Use TLS (`wss://`) across untrusted networks. The dashboard prompts for the bearer token when required and holds it in browser session storage. Browser requests with a different Origin are rejected.

Audio is capped at `MAX_AUDIO_SECONDS` (default 90). The client stores editable settings in `%LOCALAPPDATA%/PresentationCopilot/appsettings.json` and loads them over the bundled defaults.

---

## Docker

### Build and run with Docker Compose

Set `API_TOKEN` to a long random value in `server/.env` before starting Docker. Docker Compose requires it because connections forwarded into the container do not appear as loopback clients. Give the Windows client the same value in `PRESENTATION_COPILOT_API_TOKEN`.

```bash
docker compose up --build
```

> [!NOTE]
> The GPU section in `docker-compose.yml` is optional. Remove the `deploy:` block entirely if running CPU-only.

### Pull models into the Ollama container

```bash
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull nomic-embed-text
```

### Ingest documents (Docker)

```bash
docker compose exec copilot-server python ingest.py
```

---

## WebSocket Protocol

### Binary frames → PCM audio

Send raw **16-bit signed, mono, little-endian PCM** bytes at the configured sample rate (default 16000 Hz). Frames can be any size; they are accumulated server-side in a buffer.

### JSON control messages (text frames)

| Message | Description |
|---|---|
| `{"type": "trigger", "request_id": "unique-id"}` | Flush buffer, run STT → RAG → LLM pipeline, return suggestion |
| `{"type": "clear"}` | Discard the current audio buffer without processing |

### Server → client JSON responses

| `type` | Additional fields | Description |
|---|---|---|
| `"processing"` | `request_id` | Sent immediately after trigger |
| `"transcript"` | `request_id`, `transcript`, `stt_ms` | Sent after STT, before agent completion |
| `"suggestion"` | `request_id`, `transcript`, `key_point`, `keywords`, `framework_steps`, `retrieved_sources`, `timings_ms` | Full pipeline result |
| `"error"` | `message` | Error detail |
| `"ping"` | — | Heartbeat every 30 s |
| `"cleared"` | — | Acknowledgement of `clear` request |

#### Example suggestion response

```json
{
  "type": "suggestion",
  "request_id": "example-123",
  "transcript": "How does our authentication system handle token refresh?",
  "key_point": "The system uses short-lived JWTs with a sliding-window refresh strategy.",
  "keywords": ["JWT", "token refresh", "sliding window", "authentication", "security"],
  "framework_steps": [
    "Explain the 15-minute access token lifetime",
    "Describe the refresh token rotation policy",
    "Highlight the revocation endpoint for logout"
  ],
  "retrieved_sources": ["[architecture.md]"],
  "timings_ms": {"stt": 650, "agent": 2200, "total": 2850}
}
```

---

## Measured Vietnamese speech results

The professional acceptance goal is active; this branch has not passed acceptance.
See [the acceptance criteria](../PROFESSIONAL_ACCEPTANCE.md) and
[the measured report](../PROFESSIONAL_VALIDATION.md).

On 12 original Google FLEURS Vietnamese recordings (5 distinct sentences, 303
normalized whitespace units), the measured CPU results were:

| Model | Aggregate WER | Median seconds per clip |
| --- | --- | --- |
| base | 46.86% | 1.63 |
| small | 25.74% | 4.09 |
| medium | 11.55% | 11.08 |

Medium with generated 15 dB Gaussian noise scored 14.52% WER. These are small
read-speech experiments, not representative meeting, hardware or realtime guarantees.
Startup/model download is excluded. GPU performance was not measured.

Set `WHISPER_MODEL_SIZE` in `server/.env` and restart to load a different model.
The default remains base. A larger model requires measuring both recognition
quality and latency on the actual deployment hardware.

`OLLAMA_ANSWER_MODEL` and `OLLAMA_REVIEW_MODEL` optionally separate composition
and review from the ReAct model. JSON calls use final content with a per-call
`LLM_TIMEOUT_SECONDS`; that timeout is not an end-to-end deadline. A completed
model review is not independent factual verification. Cloud models receive
the question and supplied excerpts; use only material authorized for that provider.

Run one server worker per Chroma persistence directory. After an interrupted
index write, clear the vectors and re-ingest all original scopes; do not remove
the pending marker to bypass recovery. Re-ingestion is required to synchronize
deleted source files; no filesystem watcher is running.

