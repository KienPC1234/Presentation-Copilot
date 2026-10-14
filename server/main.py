"""FastAPI WebSocket & Web Management Server for the Presentation Copilot."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from config import settings
from services.agent_service import AgentService, PERSONA_PRESETS
from services.audio_utils import normalize_audio, pcm_bytes_to_wav
from services.context_manager import ContextRegistry, SessionContext
from services.rag_service import RAGService
from services.transcriber import TranscriberService

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------
_transcriber: TranscriberService | None = None
_rag: RAGService | None = None
_agent: AgentService | None = None
_ctx_registry: ContextRegistry = ContextRegistry(max_turns_per_session=10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise core services once at startup."""
    global _transcriber, _rag, _agent  # noqa: PLW0603

    logger.info("Initializing Presentation Copilot server …")

    logger.info("Loading TranscriberService (Whisper) …")
    _transcriber = TranscriberService()

    logger.info("Loading RAGService (ChromaDB) …")
    _rag = RAGService()

    logger.info("Loading AgentService (Ollama + Tools) …")
    _agent = AgentService(_rag)

    logger.info("All services loaded. Server ready.")
    yield

    logger.info("Server shutdown complete.")


app = FastAPI(title="Presentation Copilot", version="2.5.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Pipeline execution helper (offloaded to threadpool)
# ---------------------------------------------------------------------------

def _blocking_pipeline(pcm_buffer: bytearray, session_id: str) -> dict[str, Any]:
    normalised = normalize_audio(bytes(pcm_buffer))

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        pcm_bytes_to_wav(normalised, settings.audio_sample_rate, tmp_path)
        transcript: str = _transcriber.transcribe(tmp_path)  # type: ignore[union-attr]
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if not transcript.strip():
        return {"type": "suggestion", "error": "No speech detected", "transcript": ""}

    ctx = _ctx_registry.get_or_create(session_id)
    suggestion = _agent.run(transcript, ctx)  # type: ignore[union-attr]

    return {
        "type": "suggestion",
        "transcript": transcript,
        **suggestion,
    }


async def _run_pipeline(pcm_buffer: bytearray, session_id: str) -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _blocking_pipeline, bytearray(pcm_buffer), session_id
    )


# ---------------------------------------------------------------------------
# WebSocket Audio Stream Endpoint
# ---------------------------------------------------------------------------

_HEARTBEAT_INTERVAL = 30


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    client = websocket.client
    session_id = f"{client.host}:{client.port}" if client else "unknown"
    logger.info("Client connected: %s", session_id)

    pcm_buffer: bytearray = bytearray()

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        while True:
            message = await websocket.receive()

            # Binary frame -> Audio PCM
            if "bytes" in message and message["bytes"] is not None:
                chunk: bytes = message["bytes"]
                pcm_buffer.extend(chunk)

            # Text frame -> Control JSON
            elif "text" in message and message["text"] is not None:
                try:
                    ctrl: dict = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                msg_type = ctrl.get("type")

                if msg_type == "trigger":
                    if not pcm_buffer:
                        await websocket.send_json({"type": "error", "message": "No audio buffered"})
                        continue

                    snapshot = bytearray(pcm_buffer)
                    pcm_buffer.clear()
                    await websocket.send_json({"type": "processing"})

                    try:
                        result = await _run_pipeline(snapshot, session_id)
                    except Exception:
                        logger.exception("Pipeline error for %s", session_id)
                        result = {"type": "error", "message": "Internal pipeline error"}

                    await websocket.send_json(result)

                elif msg_type == "clear":
                    pcm_buffer.clear()
                    _ctx_registry.get_or_create(session_id).clear_history()
                    await websocket.send_json({"type": "cleared"})

    except WebSocketDisconnect:
        logger.info("Client disconnected: %s", session_id)
    except Exception:
        logger.exception("Error in WS handler for %s", session_id)
    finally:
        heartbeat_task.cancel()
        pcm_buffer.clear()
        _ctx_registry.remove(session_id)


# ---------------------------------------------------------------------------
# Web UI Dashboard & Management Endpoints
# ---------------------------------------------------------------------------

class VerifyPathRequest(BaseModel):
    path: str


class IngestRequest(BaseModel):
    path: str = "./data/docs"


class PersonaRequest(BaseModel):
    key: str
    custom_text: str = ""


class SimulationRequest(BaseModel):
    question: str


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard() -> HTMLResponse:
    html_path = Path(__file__).parent / "web" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>Web dashboard file not found.</h2>", status_code=404)


@app.get("/health")
async def health_check() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "transcriber": _transcriber is not None,
        "rag": _rag is not None,
        "agent": _agent is not None,
        "active_sessions": _ctx_registry.active_count(),
    })


@app.get("/api/stats")
async def get_stats() -> JSONResponse:
    rag_stats = _rag.get_stats() if _rag else {}
    return JSONResponse({
        **rag_stats,
        "active_sessions": _ctx_registry.active_count(),
    })


@app.post("/api/verify-path")
async def verify_path(req: VerifyPathRequest) -> JSONResponse:
    if not _rag:
        return JSONResponse(status_code=503, content={"valid": False, "error": "RAG not initialized"})
    result = _rag.verify_path(req.path)
    return JSONResponse(result)


@app.post("/api/ingest")
async def ingest_documents(req: IngestRequest) -> JSONResponse:
    if not _rag:
        return JSONResponse(status_code=503, content={"error": "RAG service not ready"})

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, lambda: _rag.ingest_documents(req.path))
        return JSONResponse(result)
    except Exception as exc:
        logger.exception("Ingest failed")
        return JSONResponse(status_code=500, content={"status": "error", "error": str(exc)})


@app.post("/api/clear-vectors")
async def clear_vectors() -> JSONResponse:
    if not _rag:
        return JSONResponse(status_code=503, content={"error": "RAG service not ready"})
    success = _rag.clear_store()
    return JSONResponse({"status": "success" if success else "error"})


@app.get("/api/persona")
async def get_persona() -> JSONResponse:
    if not _agent:
        return JSONResponse(status_code=503, content={"error": "Agent not ready"})
    return JSONResponse(_agent.get_persona_info())


@app.post("/api/persona")
async def update_persona(req: PersonaRequest) -> JSONResponse:
    if not _agent:
        return JSONResponse(status_code=503, content={"error": "Agent not ready"})
    _agent.set_persona(req.key, req.custom_text)
    return JSONResponse({"status": "success", "active": _agent.get_persona_info()})


@app.post("/api/simulate")
async def simulate_query(req: SimulationRequest) -> JSONResponse:
    if not _agent or not _rag:
        return JSONResponse(status_code=503, content={"error": "Services not ready"})

    temp_ctx = SessionContext("simulation_temp", max_turns=5)
    chunks = _rag.query(req.question, top_k=3)
    loop = asyncio.get_event_loop()
    suggestion = await loop.run_in_executor(None, lambda: _agent.run(req.question, temp_ctx))

    return JSONResponse({
        **suggestion,
        "retrieved_chunks": chunks,
    })


class EngineConfigRequest(BaseModel):
    whisper_language: str = "vi"
    whisper_initial_prompt: str = ""


@app.get("/api/config")
async def get_engine_config() -> JSONResponse:
    whisper_cfg = _transcriber.get_config() if _transcriber else {}
    return JSONResponse({
        "whisper": whisper_cfg,
        "ollama_model": settings.ollama_model,
        "ollama_base_url": settings.ollama_base_url,
    })


@app.post("/api/config")
async def update_engine_config(req: EngineConfigRequest) -> JSONResponse:
    if _transcriber:
        _transcriber.set_language(req.whisper_language, req.whisper_initial_prompt)
    return JSONResponse({"status": "success", "config": _transcriber.get_config() if _transcriber else {}})

