import logging
from faster_whisper import WhisperModel

from config import settings

logger = logging.getLogger(__name__)


class TranscriberService:
    """Wraps faster-whisper for speech-to-text transcription with language & prompt tuning."""

    def __init__(self) -> None:
        self.language: str | None = settings.whisper_language if settings.whisper_language != "auto" else None
        self.initial_prompt: str = settings.whisper_initial_prompt

        logger.info(
            "Loading Whisper model '%s' (lang=%s, device=%s, compute_type=%s)",
            settings.whisper_model_size,
            self.language or "auto-detect",
            settings.whisper_device,
            settings.whisper_compute_type,
        )
        self._model = WhisperModel(
            settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        logger.info("Whisper model loaded successfully")

    def set_language(self, language: str, initial_prompt: str = "") -> None:
        """Dynamically configure language code (e.g. 'vi', 'en', 'auto') without reloading model."""
        self.language = None if language.lower() in ("auto", "", "none") else language.lower()
        if initial_prompt:
            self.initial_prompt = initial_prompt
        logger.info("Transcriber language set to '%s' (prompt: %.50s)", self.language or "auto", self.initial_prompt)

    def get_config(self) -> dict[str, str | None]:
        return {
            "model_size": settings.whisper_model_size,
            "language": self.language or "auto",
            "initial_prompt": self.initial_prompt,
        }

    def transcribe(self, audio_path: str) -> str:
        """Transcribe audio with custom language targeting and initial vocabulary prompt."""
        logger.debug("Transcribing audio: %s", audio_path)
        try:
            segments, info = self._model.transcribe(
                audio_path,
                language=self.language,
                initial_prompt=self.initial_prompt if self.initial_prompt else None,
                language_detection_threshold=0.5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
            )
            detected = info.language
            logger.info("Whisper detected language: %s (probability=%.2f)", detected, info.language_probability)

            transcript_parts: list[str] = []
            for segment in segments:
                text = segment.text.strip()
                if text:
                    transcript_parts.append(text)

            transcript = " ".join(transcript_parts).strip()
            logger.info("Transcript: %s", transcript[:120])
            return transcript

        except Exception:
            logger.exception("Transcription failed for %s", audio_path)
            return ""
