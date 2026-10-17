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
| `/api/fs/list` | GET | Browse the server folders the panel is allowed to use |
| `/api/documents/generate` | POST | Render the cached markdown defence pack |
| `/api/documents/prebuild` | POST | Pre-generate the configured topics |
| `/api/admin/settings` | GET/POST | Panel defaults and pre-generation topics |
| `/api/agent/tools` | GET/POST | Enable/disable the agent's bash and ingest tools |
| `/api/maintenance/cleanup` | POST | Remove temp files, old exports and logs |

By default, API and WebSocket access is limited to the local machine. For access from another machine, set a long random `API_TOKEN` in `server/.env` (or run `python scripts/bootstrap_env.py`), start Uvicorn on an explicitly chosen network interface, and set `PRESENTATION_COPILOT_API_TOKEN` to the same value in the Windows client's environment. Use TLS (`wss://`) across untrusted networks. The dashboard prompts for the bearer token when required and holds it in browser session storage. Browser requests with a different Origin are rejected.

Audio is capped at `MAX_AUDIO_SECONDS` (default 90). The client stores editable settings in `%LOCALAPPDATA%/PresentationCopilot/appsettings.json` and loads them over the bundled defaults.

---

## Remote admin panel

The dashboard at `http://<server>:8765` is the remote control for the server. Besides ingestion, persona and the engine config, it can:

* **Browse server folders** — `/api/fs/roots` and `/api/fs/list` expose only the configured roots (`HOST_MOUNT_ROOT`, `DOCS_DIR`, `EXPORT_DIR`). Use **Browse Server** next to the ingestion path to pick a folder without typing it.
* **Generate markdown documents** — the **TÀI LIỆU MARKDOWN** tab renders a cached defence pack (questions, rebuttal script, outline, cheat sheet, evidence appendix). Files land in `EXPORT_DIR`.
* **Manage the API key** — the **SERVER ADMIN** tab shows where the key comes from and can rotate it. A rotated key is stored in `TOKEN_FILE` and lasts until restart; the environment value always wins again after a restart.
* **Toggle the agent tools** — bash and agent ingestion are off by default (see below).
* **Clean up storage** — remove temp audio, exports older than the retention window, logs, or purge all exports.

## AI-generated markdown documents

`POST /api/documents/generate` returns a bundle under `EXPORT_DIR/<topic>-<key8>/`:

| File | Content |
|---|---|
| `defense-pack.md` | Everything below, with a table of contents and limitations |
| `01-qa.md` | AI-suggested defence questions, grouped by category |
| `02-rebuttal.md` | Objection, answer points and a fallback for each question |
| `03-outline.md` | Presentation flow with evidence links |
| `04-cheatsheet.md` | One page of numbers, terms and quick answers |
| `05-evidence.md` | The exact excerpts the model was given |
| `manifest.json` | Cache key, topic, index fingerprint and file list |

Results are cached by a hash of topic, focus, language, count, document types and the current index fingerprint, so repeating a request does not call the model. `POST /api/documents/prebuild` generates the topics saved under **Panel defaults** so documents are ready before the presentation. Every file is labelled AI-generated preparation and every claim keeps its evidence ID; outlines are checklists, not verified facts.

## Agent tools

The ReAct loop always has `rag_search`, `web_search` and `calculator`. Two more tools are opt-in:

* `ingest_documents(path)` indexes a folder into the knowledge base from inside the answer loop.
* `bash(command)` runs a bounded shell command in an allowed root (timeout, output cap, denylist, absolute-path confinement).

Enable them in the **SERVER ADMIN** tab or via `AGENT_BASH_ENABLED` / `AGENT_INGEST_ENABLED`. **This is not a sandbox**: an enabled bash tool can do anything the server process can do. Keep it off unless every caller of the server is trusted, and never expose the port to an untrusted network.

## Cleanup

* In the container: the admin panel's **Cleanup & storage** card, or `CLEANUP_ON_STARTUP=true` for temp files at boot. The ChromaDB `index-write-pending` recovery marker is never deleted.
* On the host: `scripts/cleanup.sh` (Linux/macOS) or `scripts/cleanup.ps1` (Windows) remove Python/.NET caches, stray media files and old exports. Add `--docker` (or `-Docker`) to prune dangling images and build cache; `--volumes` also prunes unused volumes.

---

## Docker

### Build and run with Docker Compose

Compose mounts three things:

| Host | Container | Mode | Purpose |
|---|---|---|---|
| `HOST_DOCS_ROOT` (default `./data/docs`) | `/host` | read-only | the server-machine folder the panel browses and ingests |
| `./data` | `/app/data` | read-write | ChromaDB, temp files, exports and the token |
| `EXPORT_HOST_DIR` (default `./data/exports`) | `/app/data/exports` | read-write | where generated markdown lands |

Point `HOST_DOCS_ROOT` at the folder holding your project:

```bash
HOST_DOCS_ROOT=/srv/presentations docker compose up --build
```

The API key is generated automatically on first start and written to `./data/.api-token` (also `AUTO_GENERATE_TOKEN=true`). Read it with `cat data/.api-token`. To pin your own key instead, set `API_TOKEN` in `server/.env`; the environment value always takes precedence.

```bash
python scripts/bootstrap_env.py        # create server/.env + a key (no Docker needed)
cat server/data/.api-token             # key generated by the container
```

By default the port is published on `127.0.0.1:8765` only. Set `BIND_ADDRESS` to expose it on a trusted interface.

### Remote access over Tailscale

To let other devices on your Tailscale network use the panel and stream audio:

```bash
# server/.env
BIND_ADDRESS=100.115.199.119   # this machine's `tailscale ip -4`
```

Then `docker compose up -d` publishes `100.115.199.119:8765` and tailnet devices use `http://100.115.199.119:8765` (dashboard) and `ws://100.115.199.119:8765/ws` (client). Requests from non-loopback addresses always require the bearer token, so keep `API_TOKEN` set and hand it to the client via `PRESENTATION_COPILOT_API_TOKEN` or the client's **Settings → API Key** field.

If you prefer the whole tailnet to reach it without knowing the IP, use `tailscale serve --bg 8765` (proxied, TLS) instead of publishing the port. Do not expose the port to the public Internet: the API token is the only gate, and the optional agent `bash` tool can execute commands in the mounted project.

### GPU

The stack is GPU-first: both `copilot-server` (Whisper) and `ollama` request `gpus: all`, and the image installs the CUDA runtime/cuBLAS/cuDNN wheels. This requires the **NVIDIA Container Toolkit** on the host:

```bash
# once, on the host
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi   # verify
```

Whisper device is set from `.env` (`WHISPER_DEVICE=cuda`, `WHISPER_COMPUTE_TYPE=float16`, `WHISPER_MODEL_SIZE=small`). With a 12 GB card, `medium` fits comfortably and is much more accurate.

CPU-only host: set `INSTALL_CUDA=false`, `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8` in `.env`, and remove the two `gpus: all` lines from `docker-compose.yml`.

### Reaching services on the host

The container reaches host services through `host.docker.internal` (mapped with `host-gateway`). A service is only reachable if it listens on a **non-loopback** interface — a service bound to `127.0.0.1` is invisible to containers (connection refused).

Two options for a host Ollama:

```bash
# Option A — bind Ollama to the Docker bridge only (secure, no LAN exposure).
# Install this unit and keep Ollama on loopback:
cat >/tmp/ollama-docker-bridge.service <<'EOF'
[Unit]
Description=Expose host Ollama to the Docker bridge
After=network-online.target ollama.service
[Service]
ExecStart=/usr/bin/socat TCP-LISTEN:11435,bind=172.17.0.1,fork,reuseaddr TCP:127.0.0.1:11434
Restart=always
[Install]
WantedBy=multi-user.target
EOF
sudo cp /tmp/ollama-docker-bridge.service /etc/systemd/system/
sudo systemctl enable --now ollama-docker-bridge   # needs: sudo apt-get install -y socat

# Option B — make Ollama listen on all interfaces (simplest, exposes it on your LAN).
sudo systemctl edit ollama      # add: [Service]\nEnvironment="OLLAMA_HOST=0.0.0.0:11434"
sudo systemctl restart ollama
```

Then point the container at it:

```bash
# server/.env
OLLAMA_URL=http://host.docker.internal:11435   # Option A
# OLLAMA_URL=http://host.docker.internal:11434 # Option B
```

To use the bundled Ollama container instead, set `OLLAMA_URL=http://ollama:11434` and start it (`docker compose up -d ollama`).

`OLLAMA_URL` is the Compose-only override; `OLLAMA_BASE_URL` stays for non-Docker runs so the same `.env` works in both.

### Cloud LLM

Any Ollama-served model works, including cloud models. To answer with a cloud model while keeping embeddings local:

```bash
# server/.env
OLLAMA_MODEL=deepseek-v4.1-flash:cloud
OLLAMA_ANSWER_MODEL=deepseek-v4.1-flash:cloud
OLLAMA_REVIEW_MODEL=deepseek-v4.1-flash:cloud
OLLAMA_JSON_DISABLE_THINKING=true
```

Cloud models are proxied by the local Ollama daemon, so the container still only talks to `OLLAMA_URL`. `nomic-embed-text` (embeddings) stays local and small.

### Executing commands and reading host files from the container

* Read/inspect the host project tree from the admin panel or the agent through the read-only `/host` mount (`HOST_DOCS_ROOT`).
* The agent's opt-in `bash` tool runs bounded shell commands inside those allowed roots (see **Agent tools**). The agent's `ingest_documents` tool indexes a folder under them.
* Writes only reach `./data` and the export folder, so the container cannot modify the host tree it reads.

### Pull models into the Ollama container

```bash
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull nomic-embed-text
```

### Ingest documents (Docker)

Open the dashboard, click **📁 Browse Server** and choose a folder under `/host`, then **Ingest**. Or from the shell:

```bash
docker compose exec copilot-server python ingest.py
```

---

## WebSocket Protocol

### Binary frames → PCM audio

Send raw **16-bit signed, mono, little-endian PCM** bytes at the configured sample rate (default 16000 Hz). Frames can be any size; the server keeps a sliding window of the most recent `MAX_AUDIO_SECONDS` (default 90). The native client streams continuously while connected, so the window normally holds the question just asked; a client that only sends on trigger still works.

On `trigger` the server takes the last `seconds` of that window, transcribes it, and clears the buffer. Taking a bounded window means an older question cannot leak into the answer, and clearing means each answer starts clean.

### JSON control messages (text frames)

| Message | Description |
|---|---|
| `{"type": "trigger", "request_id": "unique-id", "seconds": 20}` | Analyse the last `seconds` of buffered audio; omit `seconds` to use the whole window |
| `{"type": "clear"}` | Discard the current audio buffer without processing |
| `{"type": "set_topic", "topic": "Product name"}` | Anchor retrieval/answers to a product for this connection |

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

## Transcription audio format

The analysis window is written to a temporary file for Whisper and deleted immediately after. By default it is an **M4A (Opus)** file encoded with ffmpeg (`TRANSCRIPTION_AUDIO_FORMAT=m4a`; `ogg` and `wav` are also accepted). Opus keeps the temp file roughly ten times smaller than WAV. If ffmpeg or the Opus codec is unavailable, or decoding fails, the server retries that clip as WAV, so the container choice can never block transcription.

The Whisper model loads lazily on the first transcription. Call **Engine Metrics → Nạp trước model** (`POST /api/config/warmup`) before a session so the first hotkey press is not slowed by the load.

---

## Voice & adversarial audit

`scripts/voice_audit.py` runs a repeatable audit against a running server. Cases
cover the six defence categories, prompt injection (including an injection hidden
in a quoted document and a "developer mode" request), requests to fabricate
metrics, ambiguous/underspecified follow-ups, an off-topic question and English —
plus a realistic set: a hostile judge, a false premise about the tech stack, a
rumour of a data breach, a demand for a 100% guarantee, compound and three-part
questions, an emotional-pressure request for a fake number, a question about a
non-existent feature, a compliance question and a bare "why?". Each answer is
checked against declared expectations.

```bash
# 1. Synthesize the audio cases (espeak-ng on the host or in the container)
python scripts/voice_audit.py --generate-audio --audio-dir server/data/audio

# 2. Run text + voice cases inside the container
docker compose exec -T -w /app -e API_TOKEN="$API_TOKEN" copilot-server \
    python /app/voice_audit.py --mode both --base http://127.0.0.1:8765 \
    --audio-dir data/audio --out data/audit
```

Results (`results.json`, `summary.md`) record each answer, its sources, the
review status, latency, and for voice cases the word error rate against the
synthesized ground truth. The synthesized voice is robotic eSpeak audio, so WER
is far worse than real speech; use it to prove the audio path and to catch
crashes, not to judge recognition quality.


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

