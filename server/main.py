"""FastAPI WebSocket & Web Management Server for the Presentation Copilot."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
import time
from uuid import uuid4
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from config import settings
from security import authorized, same_origin
from services.agent_service import AgentService, PERSONA_PRESETS
from services.audio_utils import normalize_audio, pcm_bytes_to_wav
from services.context_manager import ContextRegistry, SessionContext
from services.rag_service import RAGService
from services.transcriber import TranscriberService
from services.defense_service import DefenseService

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


app = FastAPI(title="Presentation Copilot", version="2.6.0", lifespan=lifespan)


@app.middleware("http")
async def protect_api(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        if not same_origin(request.headers.get("origin"), request.headers.get("host")):
            return JSONResponse({"error": "Cross-origin requests are not allowed"}, status_code=403)
        if not authorized(request.client.host if request.client else None,
                          request.headers.get("authorization"), settings.api_token,
                          request.headers.get("host")):
            return JSONResponse({"error": "Authorization required"}, status_code=401)
    return await call_next(request)


# ---------------------------------------------------------------------------
# Pipeline execution helper (offloaded to threadpool)
# ---------------------------------------------------------------------------

def _blocking_transcribe(pcm_buffer: bytes) -> str:
    normalised = normalize_audio(pcm_buffer)

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

    return transcript


async def _run_pipeline(pcm_buffer: bytes, session_id: str, request_id: str,
                        send_update) -> dict[str, Any]:
    start = time.perf_counter()
    transcript = await asyncio.to_thread(_blocking_transcribe, pcm_buffer)
    stt_ms = round((time.perf_counter() - start) * 1000)
    await send_update({"type": "transcript", "request_id": request_id,
                       "transcript": transcript, "stt_ms": stt_ms})
    if not transcript.strip():
        return {"type": "error", "request_id": request_id, "message": "No speech detected"}
    ctx = _ctx_registry.get_or_create(session_id)
    suggestion = await asyncio.to_thread(_agent.run, transcript, ctx)  # type: ignore[union-attr]
    if suggestion.get("error"):
        return {"type": "error", "request_id": request_id, "message": suggestion["error"]}
    total_ms = round((time.perf_counter() - start) * 1000)
    logger.info("Analysis %s: STT=%d ms, agent=%d ms, total=%d ms",
                request_id, stt_ms, total_ms - stt_ms, total_ms)
    return {"type": "suggestion", "request_id": request_id, "transcript": transcript,
            "timings_ms": {"stt": stt_ms, "agent": total_ms - stt_ms, "total": total_ms},
            **suggestion}


# ---------------------------------------------------------------------------
# WebSocket Audio Stream Endpoint
# ---------------------------------------------------------------------------

_HEARTBEAT_INTERVAL = 30


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    if not same_origin(websocket.headers.get("origin"), websocket.headers.get("host")):
        await websocket.close(code=1008, reason="Cross-origin connection rejected")
        return
    if not authorized(websocket.client.host if websocket.client else None,
                      websocket.headers.get("authorization"), settings.api_token,
                      websocket.headers.get("host")):
        await websocket.close(code=1008, reason="Authorization required")
        return
    await websocket.accept()
    client = websocket.client
    # Connection identity must not depend on reusable peer ports, proxy
    # addresses or the identical addresses supplied by test transports.
    session_id = uuid4().hex
    logger.info("Client connected: %s", session_id)

    pcm_buffer: bytearray = bytearray()
    max_pcm_bytes = settings.audio_sample_rate * 2 * settings.max_audio_seconds
    send_lock = asyncio.Lock()

    async def send_json(payload: dict[str, Any]) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            try:
                await send_json({"type": "ping"})
            except Exception:
                break

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            # Binary frame -> Audio PCM
            if "bytes" in message and message["bytes"] is not None:
                chunk: bytes = message["bytes"]
                if len(chunk) + len(pcm_buffer) > max_pcm_bytes:
                    pcm_buffer.clear()
                    await send_json({"type": "error", "message": "Audio buffer limit exceeded"})
                    continue
                pcm_buffer.extend(chunk)

            # Text frame -> Control JSON
            elif "text" in message and message["text"] is not None:
                try:
                    ctrl: dict = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                if not isinstance(ctrl, dict):
                    await send_json({"type": "error", "message": "Control message must be a JSON object"})
                    continue

                msg_type = ctrl.get("type")

                if msg_type == "trigger":
                    request_id = ctrl.get("request_id")
                    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
                        await send_json({"type": "error", "message": "Invalid request_id"})
                        continue
                    if not pcm_buffer:
                        await send_json({"type": "error", "request_id": request_id, "message": "No audio buffered"})
                        continue

                    snapshot = bytearray(pcm_buffer)
                    pcm_buffer.clear()
                    await send_json({"type": "processing", "request_id": request_id})

                    try:
                        result = await _run_pipeline(bytes(snapshot), session_id, request_id, send_json)
                    except Exception:
                        logger.exception("Pipeline error for %s", session_id)
                        result = {"type": "error", "request_id": request_id,
                                  "message": "Internal pipeline error"}

                    await send_json(result)

                elif msg_type == "clear":
                    pcm_buffer.clear()
                    _ctx_registry.get_or_create(session_id).clear_history()
                    await send_json({"type": "cleared"})
                elif msg_type == "set_topic":
                    topic = ctrl.get("topic")
                    if not isinstance(topic, str) or not 3 <= len(topic.strip()) <= 200:
                        await send_json({"type": "error", "message": "Topic must contain 3–200 characters"})
                        continue
                    ctx = _ctx_registry.get_or_create(session_id)
                    ctx.clear_history()
                    ctx.set_fact("presentation_topic", topic.strip())
                    await send_json({"type": "topic_set", "topic": topic.strip()})

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
    question: str = Field(min_length=1, max_length=12000)
    topic: str = Field(default="", max_length=200)


class DefenseRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    focus: str = Field(default="", max_length=2000)
    count: int = Field(default=6, ge=3, le=12)
    language: Literal["vi", "en"] = "vi"

    @field_validator("topic")
    @classmethod
    def nonblank_topic(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Topic must contain at least 3 non-whitespace characters")
        return value


@app.post("/api/defense/prepare")
async def prepare_defense(req: DefenseRequest) -> JSONResponse:
    if _rag is None:
        raise HTTPException(status_code=503, detail="RAG service not ready")
    try:
        service = DefenseService(_rag)
        result = await asyncio.to_thread(service.prepare, req.topic.strip(), req.focus, req.count, req.language)
        return JSONResponse(result)
    except ValueError as exc:
        logger.warning("Invalid defense plan: %s", exc)
        raise HTTPException(status_code=502, detail="AI returned an invalid preparation plan; please retry") from exc
    except Exception as exc:
        logger.exception("Defense preparation failed")
        raise HTTPException(status_code=503, detail="Preparation service unavailable") from exc


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
    try:
        _agent.set_persona(req.key, req.custom_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse({"status": "success", "active": _agent.get_persona_info()})


@app.post("/api/simulate")
async def simulate_query(req: SimulationRequest) -> JSONResponse:
    if not _agent or not _rag:
        return JSONResponse(status_code=503, content={"error": "Services not ready"})

    temp_ctx = SessionContext("simulation_temp", max_turns=5)
    if req.topic.strip():
        temp_ctx.set_fact("presentation_topic", req.topic.strip())
    loop = asyncio.get_event_loop()
    suggestion = await loop.run_in_executor(None, lambda: _agent.run(req.question, temp_ctx, include_evidence=True))

    return JSONResponse(suggestion, status_code=502 if suggestion.get("error") else 200)


class EngineConfigRequest(BaseModel):
    whisper_language: str = Field(default="vi", max_length=16)
    whisper_initial_prompt: str = Field(default="", max_length=2000)


@app.get("/api/config")
async def get_engine_config() -> JSONResponse:
    whisper_cfg = _transcriber.get_config() if _transcriber else {}
    return JSONResponse({
        "whisper": whisper_cfg,
        "ollama_model": settings.ollama_model,
        "ollama_answer_model": settings.ollama_answer_model or settings.ollama_model,
        "ollama_review_model": settings.ollama_review_model or settings.ollama_answer_model or settings.ollama_model,
        "ollama_base_url": settings.ollama_base_url,
        "response_style": settings.response_style,
    })


@app.post("/api/config")
async def update_engine_config(req: EngineConfigRequest) -> JSONResponse:
    if _transcriber:
        try:
            _transcriber.set_language(req.whisper_language, req.whisper_initial_prompt)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse({"status": "success", "config": _transcriber.get_config() if _transcriber else {}})

