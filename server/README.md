# Presentation Copilot — Server

Python WebSocket server that receives PCM audio from a C# client, transcribes it with Whisper, retrieves relevant project context via RAG (ChromaDB), and returns structured presentation suggestions from an Ollama LLM.

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

This embeds all documents into ChromaDB at `./data/chroma/`. Re-run whenever you add new files.

---

## Run the Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8765
```

The server exposes:

| Endpoint | Method | Description |
|---|---|---|
| `/ws` | WebSocket | Main audio + control channel |
| `/health` | GET | Liveness check |
| `/ingest` | POST | Trigger re-ingestion of `DOCS_DIR` |

---

## Docker

### Build and run with Docker Compose

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
| `{"type": "trigger"}` | Flush buffer, run STT → RAG → LLM pipeline, return suggestion |
| `{"type": "clear"}` | Discard the current audio buffer without processing |

### Server → client JSON responses

| `type` | Additional fields | Description |
|---|---|---|
| `"processing"` | — | Sent immediately after trigger, before pipeline runs |
| `"suggestion"` | `transcript`, `key_point`, `keywords`, `framework_steps` | Full pipeline result |
| `"error"` | `message` | Error detail |
| `"ping"` | — | Heartbeat every 30 s |
| `"cleared"` | — | Acknowledgement of `clear` request |

#### Example suggestion response

```json
{
  "type": "suggestion",
  "transcript": "How does our authentication system handle token refresh?",
  "key_point": "The system uses short-lived JWTs with a sliding-window refresh strategy.",
  "keywords": ["JWT", "token refresh", "sliding window", "authentication", "security"],
  "framework_steps": [
    "Explain the 15-minute access token lifetime",
    "Describe the refresh token rotation policy",
    "Highlight the revocation endpoint for logout"
  ]
}
```

---

## Whisper Model Size vs. Speed

| Model | VRAM | Relative Speed | WER (en) |
|---|---|---|---|
| `tiny` | ~1 GB | Fastest | Higher |
| `base` | ~1 GB | Fast | Good |
| `small` | ~2 GB | Moderate | Better |
| `medium` | ~5 GB | Slow | Very good |
| `large-v3` | ~10 GB | Slowest | Best |

Set `WHISPER_MODEL_SIZE` in `.env`. For CPU-only deployments `base` or `small` offer the best speed/accuracy tradeoff.

> [!TIP]
> Set `WHISPER_DEVICE=cuda` and `WHISPER_COMPUTE_TYPE=float16` if you have an NVIDIA GPU to achieve near-realtime transcription with `medium` or `large-v3`.

