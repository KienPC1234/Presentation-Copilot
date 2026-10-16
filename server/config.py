from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_base_url: str = ""
    ollama_model: str = "qwen2.5:7b"
    ollama_answer_model: str = ""  # Empty uses ollama_model.
    ollama_review_model: str = ""  # Empty uses the answer model; no independence claim.
    llm_timeout_seconds: float = Field(default=45, gt=0, le=120)
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

    # Server
    host: str = "127.0.0.1"
    port: int = 8765
    api_token: str = ""
    max_audio_seconds: int = 90

    # Audio
    audio_sample_rate: int = 16000

    # Logging
    log_level: str = "INFO"


settings = Settings()
