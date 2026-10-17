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
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from config import settings
from security import authorized, same_origin
from token_store import TokenStore
from services.admin_settings import AdminSettingsStore
from services.agent_service import AgentService, PERSONA_PRESETS
from services.audio_utils import normalize_audio, write_audio_file
from services.context_manager import ContextRegistry, SessionContext
from services.rag_service import RAGService
from services.transcriber import TranscriberService
from services.defense_service import DefenseService
from services.document_service import DocumentService
from services.document_kinds import DOCUMENT_KINDS, KIND_LABELS, LANGUAGES
from services import audio_buffer, maintenance, path_browser
from services.live_caption import should_emit

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
_documents: DocumentService | None = None
_ctx_registry: ContextRegistry = ContextRegistry(max_turns_per_session=10)
_token_store = TokenStore(settings)
_admin_settings = AdminSettingsStore(settings)


def _apply_agent_policy() -> None:
    """Push the persisted tool policy onto the live agent after startup."""
    if _agent is None:
        return
    policy = _admin_settings.get()
    _agent.set_tool_policy(
        bash_enabled=policy["agent_bash_enabled"],
        ingest_enabled=policy["agent_ingest_enabled"],
        max_iterations=policy["agent_max_iterations"],
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise core services once at startup."""
    global _transcriber, _rag, _agent, _documents  # noqa: PLW0603

    logger.info("Initializing Presentation Copilot server …")
    Path(settings.tmp_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.export_dir).mkdir(parents=True, exist_ok=True)

    if settings.cleanup_on_startup and _admin_settings.get()["cleanup_on_startup"]:
        report = maintenance.cleanup_runtime(settings)
        if report["removed"]:
            logger.info("Startup cleanup removed %d temp file(s)", report["removed"])

    logger.info("Loading TranscriberService (Whisper) …")
    _transcriber = TranscriberService()

    logger.info("Loading RAGService (ChromaDB) …")
    _rag = RAGService()

    logger.info("Loading AgentService (Ollama + Tools) …")
    _agent = AgentService(_rag)
    _apply_agent_policy()

    _documents = DocumentService(_rag)

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
                          request.headers.get("authorization"), _token_store.current(),
                          request.headers.get("host")):
            return JSONResponse({"error": "Authorization required"}, status_code=401)
    return await call_next(request)


# ---------------------------------------------------------------------------
# Pipeline execution helper (offloaded to threadpool)
# ---------------------------------------------------------------------------

def _blocking_transcribe(pcm_buffer: bytes) -> str:
    normalised = normalize_audio(pcm_buffer)

    tmp_dir = Path(settings.tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Prefer the configured compact container, but never let an encoder or a
    # codec problem block transcription: fall back to lossless WAV and retry.
    preferred = settings.transcription_audio_format
    formats = [preferred] if preferred == "wav" else [preferred, "wav"]

    last_error: Exception | None = None
    for audio_format in formats:
        fd, tmp_path = tempfile.mkstemp(suffix=f".{audio_format}", dir=str(tmp_dir))
        os.close(fd)
        try:
            write_audio_file(normalised, settings.audio_sample_rate, tmp_path)
            return _transcriber.transcribe(tmp_path)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 - retry with a safer format
            last_error = exc
            logger.warning("Transcription attempt with .%s failed: %s", audio_format, exc)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    raise RuntimeError("Speech transcription failed") from last_error


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
                      websocket.headers.get("authorization"), _token_store.current(),
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
    overflow_warned = False
    send_lock = asyncio.Lock()
    received_bytes = 0

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
    pipeline_task: asyncio.Task | None = None

    async def run_and_send(snapshot: bytes, request_id: str) -> None:
        """Run the pipeline off the receive loop so audio keeps flowing in."""
        try:
            result = await _run_pipeline(snapshot, session_id, request_id, send_json)
        except Exception:
            logger.exception("Pipeline error for %s", session_id)
            result = {"type": "error", "request_id": request_id, "message": "Internal pipeline error"}
        try:
            await send_json(result)
        except Exception:
            logger.debug("Could not deliver result for %s (client gone)", request_id)

    async def live_caption_loop() -> None:
        """Best-effort partial transcript while the client keeps streaming.

        Runs only when enabled (panel/.env) and never at the same time as the
        triggered pipeline, so it does not compete for the accelerator.
        """
        last_bytes = 0
        previous_text = ""
        while True:
            admin = _admin_settings.get()
            interval = max(0.5, float(admin.get("live_caption_interval_seconds",
                                               settings.live_caption_interval_seconds)))
            await asyncio.sleep(interval)
            if not admin.get("live_caption_enabled", settings.live_caption_enabled):
                continue
            if pipeline_task is not None and not pipeline_task.done():
                continue
            new_bytes = received_bytes - last_bytes
            new_seconds = new_bytes / (settings.audio_sample_rate * 2)
            if not pcm_buffer or new_seconds < 0.8:
                continue
            last_bytes = received_bytes
            window_bytes = settings.audio_sample_rate * 2 * settings.live_caption_window_seconds
            snapshot = bytes(pcm_buffer[-window_bytes:])
            try:
                text = await asyncio.to_thread(_blocking_transcribe, snapshot)
            except Exception:
                logger.debug("Live caption transcription failed for %s", session_id, exc_info=True)
                continue
            if not should_emit(new_seconds, text, previous_text):
                continue
            previous_text = text.strip()
            try:
                await send_json({"type": "caption", "text": previous_text, "final": False})
            except Exception:
                break

    caption_task = asyncio.create_task(live_caption_loop())

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            # Binary frame -> Audio PCM
            if "bytes" in message and message["bytes"] is not None:
                chunk: bytes = message["bytes"]
                received_bytes += len(chunk)
                # Continuous streaming: keep a sliding window of the most recent
                # audio instead of wiping everything, so a long session never
                # loses the question that was just asked.
                if audio_buffer.append_chunk(pcm_buffer, chunk, max_pcm_bytes) and not overflow_warned:
                    overflow_warned = True
                    logger.warning("Audio window at the %ds limit for %s; oldest audio dropped",
                                   settings.max_audio_seconds, session_id)

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

                    # Optional analysis window. The client streams audio
                    # continuously, so the server keeps recent context and only
                    # the last `seconds` are analysed; older audio is discarded
                    # so a previous question cannot leak into this answer.
                    seconds = ctrl.get("seconds")
                    if seconds is not None:
                        if not isinstance(seconds, int) or isinstance(seconds, bool) \
                                or not 1 <= seconds <= settings.max_audio_seconds:
                            await send_json({"type": "error", "request_id": request_id,
                                             "message": "Invalid analysis window"})
                            continue

                    if not pcm_buffer:
                        await send_json({"type": "error", "request_id": request_id, "message": "No audio buffered"})
                        continue

                    if pipeline_task is not None and not pipeline_task.done():
                        await send_json({"type": "error", "request_id": request_id,
                                         "message": "Analysis already in progress"})
                        continue

                    snapshot = audio_buffer.snapshot(pcm_buffer, seconds, settings.audio_sample_rate)
                    await send_json({"type": "processing", "request_id": request_id})
                    # Do not await the pipeline here: keep draining audio frames so
                    # the sliding window stays current for the next question.
                    pipeline_task = asyncio.create_task(run_and_send(bytes(snapshot), request_id))

                elif msg_type == "clear":
                    if pipeline_task is not None and not pipeline_task.done():
                        pipeline_task.cancel()
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
        caption_task.cancel()
        if pipeline_task is not None and not pipeline_task.done():
            pipeline_task.cancel()
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
        "whisper_model_loaded": _transcriber.is_model_loaded() if _transcriber else False,
        "whisper_device": _transcriber.active_device() if _transcriber else None,
        "rag": _rag is not None,
        "agent": _agent is not None,
        "documents": _documents is not None,
        "active_sessions": _ctx_registry.active_count(),
        "token_source": _token_store.source(),
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
    transcription_audio_format: Literal["m4a", "ogg", "wav"] | None = None


@app.get("/api/config")
async def get_engine_config() -> JSONResponse:
    whisper_cfg = _transcriber.get_config() if _transcriber else {}
    return JSONResponse({
        "whisper": whisper_cfg,
        "whisper_model_loaded": _transcriber.is_model_loaded() if _transcriber else False,
        "whisper_device": _transcriber.active_device() if _transcriber else None,
        "transcription_audio_format": settings.transcription_audio_format,
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
    if req.transcription_audio_format is not None:
        settings.transcription_audio_format = req.transcription_audio_format
    return JSONResponse({"status": "success", "config": _transcriber.get_config() if _transcriber else {},
                         "transcription_audio_format": settings.transcription_audio_format})


@app.post("/api/config/warmup")
async def warmup_transcriber() -> JSONResponse:
    """Load the speech model ahead of time so the first hotkey press is fast."""
    if _transcriber is None:
        return JSONResponse(status_code=503, content={"error": "Transcriber not ready"})
    try:
        await asyncio.to_thread(_transcriber.ensure_loaded)
    except Exception as exc:
        logger.exception("Speech model warm-up failed")
        return JSONResponse(status_code=503, content={"error": f"Speech model unavailable: {exc}"})
    return JSONResponse({"status": "success", "whisper_model_loaded": True})


# ---------------------------------------------------------------------------
# Server filesystem browser (used by the remote admin panel to pick paths)
# ---------------------------------------------------------------------------

@app.get("/api/fs/roots")
async def fs_roots() -> JSONResponse:
    return JSONResponse({"roots": path_browser.allowed_roots(settings)})


@app.get("/api/fs/list")
async def fs_list(path: str = "", show_hidden: bool = False) -> JSONResponse:
    roots = path_browser.allowed_roots(settings)
    if not roots:
        return JSONResponse(status_code=503, content={
            "ok": False,
            "error": "No browsable root is configured. Set HOST_MOUNT_ROOT or DOCS_DIR."})
    target = path.strip() or roots[0]["path"]
    return JSONResponse(await asyncio.to_thread(path_browser.list_directory, target, roots, show_hidden))


# ---------------------------------------------------------------------------
# Admin settings, API token and agent tool policy
# ---------------------------------------------------------------------------

def _document_kind_catalog() -> list[dict[str, str]]:
    return [{"key": kind, "label": KIND_LABELS[kind]} for kind in DOCUMENT_KINDS]


@app.get("/api/admin/settings")
async def get_admin_settings() -> JSONResponse:
    return JSONResponse({
        "settings": _admin_settings.get(),
        "document_kinds": _document_kind_catalog(),
        "languages": list(LANGUAGES),
    })


@app.post("/api/admin/settings")
async def update_admin_settings(payload: dict[str, Any]) -> JSONResponse:
    try:
        updated = _admin_settings.update(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _apply_agent_policy()
    return JSONResponse({"status": "success", "settings": updated})


@app.get("/api/admin/system")
async def get_system_info() -> JSONResponse:
    return JSONResponse({
        "version": app.version,
        "token": {"source": _token_store.source(), "masked": _token_store.masked(),
                  "configured": bool(_token_store.current())},
        "roots": path_browser.allowed_roots(settings),
        "host_mount_root": settings.host_mount_root,
        "export_dir": settings.export_dir,
        "tmp_dir": settings.tmp_dir,
        "retention_days": _admin_settings.get()["export_retention_days"],
        "storage": await asyncio.to_thread(maintenance.storage_report, settings),
    })


@app.post("/api/admin/token/rotate")
async def rotate_token() -> JSONResponse:
    token = _token_store.rotate()
    logger.warning("API token rotated from the admin panel")
    return JSONResponse({"status": "success", "token": token, "source": _token_store.source()})


class AgentToolPolicyRequest(BaseModel):
    bash_enabled: bool | None = None
    ingest_enabled: bool | None = None
    max_iterations: int | None = Field(default=None, ge=1, le=8)


@app.get("/api/agent/tools")
async def get_agent_tools() -> JSONResponse:
    if _agent is None:
        return JSONResponse(status_code=503, content={"error": "Agent not ready"})
    policy = {key: value for key, value in _admin_settings.get().items() if key.startswith("agent_")}
    return JSONResponse({**_agent.get_tool_policy(), "persisted": policy})


@app.post("/api/agent/tools")
async def update_agent_tools(req: AgentToolPolicyRequest) -> JSONResponse:
    if _agent is None:
        return JSONResponse(status_code=503, content={"error": "Agent not ready"})
    updates: dict[str, Any] = {}
    if req.bash_enabled is not None:
        updates["agent_bash_enabled"] = req.bash_enabled
    if req.ingest_enabled is not None:
        updates["agent_ingest_enabled"] = req.ingest_enabled
    if req.max_iterations is not None:
        updates["agent_max_iterations"] = req.max_iterations
    if updates:
        try:
            _admin_settings.update(updates)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    _apply_agent_policy()
    return JSONResponse({"status": "success", **_agent.get_tool_policy()})


# ---------------------------------------------------------------------------
# AI-generated markdown documents (defence pack)
# ---------------------------------------------------------------------------

class DocumentRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    focus: str = Field(default="", max_length=2000)
    language: Literal["vi", "en"] = "vi"
    count: int = Field(default=6, ge=3, le=12)
    kinds: list[str] = Field(default_factory=list)
    force: bool = False


class PrebuildRequest(BaseModel):
    topics: list[str] = Field(default_factory=list)
    force: bool = False


@app.post("/api/documents/generate")
async def generate_documents(req: DocumentRequest) -> JSONResponse:
    if _documents is None:
        return JSONResponse(status_code=503, content={"error": "Document service not ready"})
    kinds = req.kinds or _admin_settings.get()["default_kinds"]
    try:
        result = await asyncio.to_thread(_documents.generate, req.topic, req.focus,
                                         req.language, req.count, kinds, req.force)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("Document generation failed")
        return JSONResponse(status_code=502, content={"error": "Document generation failed; check the AI engine"})
    return JSONResponse(result)


@app.post("/api/documents/prebuild")
async def prebuild_documents(req: PrebuildRequest) -> JSONResponse:
    if _documents is None:
        return JSONResponse(status_code=503, content={"error": "Document service not ready"})
    admin = _admin_settings.get()
    topics = [topic.strip() for topic in req.topics if topic.strip()] or admin["prebuild_topics"]
    if not topics:
        raise HTTPException(status_code=422, detail="No topics configured to prebuild")
    results = []
    for topic in topics[:20]:
        try:
            result = await asyncio.to_thread(_documents.generate, topic, "", admin["default_language"],
                                             admin["default_count"], admin["default_kinds"], req.force)
            results.append({"topic": topic, "status": result.get("status"),
                            "cached": result.get("cached"), "cache_key": result.get("cache_key")})
        except Exception as exc:
            logger.warning("Prebuild failed for '%s': %s", topic, exc)
            results.append({"topic": topic, "status": "error", "error": str(exc)})
    return JSONResponse({"status": "success", "count": len(results), "results": results})


@app.get("/api/documents")
async def list_documents() -> JSONResponse:
    if _documents is None:
        return JSONResponse(status_code=503, content={"error": "Document service not ready"})
    documents = await asyncio.to_thread(_documents.list_documents)
    return JSONResponse({"documents": documents, "count": len(documents)})


@app.get("/api/documents/{cache_key}/markdown", response_class=PlainTextResponse)
async def document_markdown(cache_key: str) -> PlainTextResponse:
    if _documents is None:
        raise HTTPException(status_code=503, detail="Document service not ready")
    text = await asyncio.to_thread(_documents.read_document, cache_key)
    if text is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")


@app.delete("/api/documents/{cache_key}")
async def delete_document(cache_key: str) -> JSONResponse:
    if _documents is None:
        return JSONResponse(status_code=503, content={"error": "Document service not ready"})
    deleted = await asyncio.to_thread(_documents.delete_document, cache_key)
    return JSONResponse({"status": "success" if deleted else "not_found"},
                        status_code=200 if deleted else 404)


# ---------------------------------------------------------------------------
# Maintenance: disk report and cleanup
# ---------------------------------------------------------------------------

class CleanupRequest(BaseModel):
    targets: list[str] = Field(default_factory=lambda: ["runtime", "exports", "logs"])
    retention_days: int | None = Field(default=None, ge=0, le=3650)
    purge_exports: bool = False


@app.get("/api/maintenance/report")
async def maintenance_report() -> JSONResponse:
    return JSONResponse({
        "storage": await asyncio.to_thread(maintenance.storage_report, settings),
        "retention_days": _admin_settings.get()["export_retention_days"],
    })


@app.post("/api/maintenance/cleanup")
async def run_cleanup(req: CleanupRequest) -> JSONResponse:
    targets = [target for target in req.targets if target in ("runtime", "exports", "logs")]
    if not targets and not req.purge_exports:
        raise HTTPException(status_code=422, detail="No valid cleanup target selected")
    retention = req.retention_days if req.retention_days is not None \
        else _admin_settings.get()["export_retention_days"]
    results = []
    if "runtime" in targets:
        results.append(await asyncio.to_thread(maintenance.cleanup_runtime, settings))
    if "exports" in targets:
        action = maintenance.purge_exports if req.purge_exports else maintenance.cleanup_exports
        args = (settings.export_dir,) if req.purge_exports else (settings.export_dir, retention)
        results.append(await asyncio.to_thread(action, *args))
    if "logs" in targets:
        results.append(await asyncio.to_thread(maintenance.cleanup_logs, settings.data_dir, retention))
    logger.info("Maintenance cleanup ran: %s", [item["target"] for item in results])
    return JSONResponse({"status": "success", "results": results})

