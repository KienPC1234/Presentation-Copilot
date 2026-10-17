from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_base_url: str = ""
    ollama_model: str = "qwen2.5:7b"
    ollama_answer_model: str = ""  # Empty uses ollama_model.
    ollama_review_model: str = ""  # Empty uses the answer model; no independence claim.
    llm_timeout_seconds: float = Field(default=45, gt=0, le=120)
    llm_max_output_tokens: int = Field(default=4096, ge=256, le=32768)
    # The markdown document pack is one large JSON; give it a bigger budget.
    document_max_output_tokens: int = Field(default=16384, ge=1024, le=32768)
    ollama_json_disable_thinking: bool = True
    response_style: Literal["plain", "technical"] = "plain"

    # Whisper STT
    whisper_model_size: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str = "vi"  # "vi", "en", "auto", "ja", "zh", etc.
    whisper_initial_prompt: str = "Thuyết trình bảo vệ dự án, phần mềm, công nghệ, kiến trúc, API, microservices, database, latency."

    # Storage
    chroma_persist_dir: str = "./data/chroma"
    docs_dir: str = "./data/docs"
    tmp_dir: str = "./data/tmp"
    export_dir: str = "./data/exports"
    data_dir: str = "./data"

    # Server
    host: str = "127.0.0.1"
    port: int = 8765
    api_token: str = ""
    max_audio_seconds: int = 90

    # API token self-provisioning (used by Docker; see server/token_store.py)
    token_file: str = "./data/.api-token"
    auto_generate_token: bool = False

    # Agent tool policy. Bash and index ingestion are powerful; keep them off
    # unless an operator turns them on from the admin panel or .env.
    agent_bash_enabled: bool = False
    agent_ingest_enabled: bool = False
    agent_max_iterations: int = Field(default=3, ge=1, le=8)
    # How many times a failed review is repaired before refusing to answer.
    agent_max_repairs: int = Field(default=3, ge=0, le=4)
    bash_timeout_seconds: int = Field(default=15, ge=1, le=120)
    bash_max_output_chars: int = Field(default=4000, ge=200, le=20000)

    # Remote administration panel
    # ``host_mount_root`` is the read-only bind mount of the server machine that
    # the panel may browse and ingest from. Empty disables host-mount browsing.
    host_mount_root: str = ""
    admin_settings_file: str = "./data/admin-settings.json"
    export_retention_days: int = Field(default=14, ge=0, le=3650)
    cleanup_on_startup: bool = True

    # Audio
    audio_sample_rate: int = 16000
    # Container/codec for the temporary file handed to Whisper. "m4a"/"ogg" encode
    # Opus with ffmpeg (compact); the server falls back to "wav" automatically.
    transcription_audio_format: Literal["m4a", "ogg", "wav"] = "m4a"

    # Live captions: while the client streams audio, periodically transcribe the
    # rolling window and push partial text so the HUD can show the question as it
    # is being asked, before the hotkey is pressed. Uses the accelerator.
    live_caption_enabled: bool = False
    live_caption_interval_seconds: float = Field(default=2.5, ge=0.5, le=30)
    live_caption_window_seconds: int = Field(default=12, ge=3, le=60)

    # Logging
    log_level: str = "INFO"


settings = Settings()
