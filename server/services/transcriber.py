import logging
import re
from threading import RLock
from faster_whisper import WhisperModel

from config import settings
from services.transcript import collapse_repetitions

logger = logging.getLogger(__name__)

# Whisper sometimes echoes the biasing prompt on unclear or silent audio. That
# would send the presenter's own vocabulary list to the answer engine as if it
# were the question, so such transcripts are discarded as "no speech".
_PROMPT_ECHO_OVERLAP = 0.8


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _echoes_prompt(transcript: str, prompt: str) -> bool:
    """True when the transcript is essentially the biasing prompt read back."""
    if not prompt.strip() or not transcript.strip():
        return False
    transcript_tokens = _tokens(transcript)
    if len(transcript_tokens) < 3:
        return False
    prompt_tokens = _tokens(prompt)
    return len(transcript_tokens & prompt_tokens) / len(transcript_tokens) >= _PROMPT_ECHO_OVERLAP


class TranscriberService:
    """Wraps faster-whisper for speech-to-text transcription with language & prompt tuning.

    The model is loaded lazily on first use (or via :meth:`ensure_loaded`). Loading it
    in ``__init__`` would download hundreds of megabytes during server startup and
    take the whole container down when that download fails.
    """

    def __init__(self) -> None:
        self._config_lock = RLock()
        self.model_size = settings.whisper_model_size
        self.language: str | None = settings.whisper_language if settings.whisper_language != "auto" else None
        self.initial_prompt: str = settings.whisper_initial_prompt
        self._model = None
        self._active_device: str | None = None
        logger.info(
            "Whisper model '%s' (lang=%s, device=%s, compute_type=%s) will load on first use",
            settings.whisper_model_size,
            self.language or "auto-detect",
            settings.whisper_device,
            settings.whisper_compute_type,
        )

    def is_model_loaded(self) -> bool:
        return self._model is not None

    def active_device(self) -> str:
        return self._active_device or settings.whisper_device

    def ensure_loaded(self) -> None:
        """Load the Whisper model now, if it is not loaded yet.

        If the configured accelerator fails to start (for example a transient
        ``CUDA failed ... no CUDA-capable device`` error in Docker), fall back to
        CPU rather than leaving the server unable to transcribe anything.
        """
        if self._model is not None:
            return
        with self._config_lock:
            if self._model is not None:
                return
            device, compute = settings.whisper_device, settings.whisper_compute_type
            logger.info("Loading Whisper model '%s' on %s …", self.model_size, device)
            try:
                model = WhisperModel(self.model_size, device=device, compute_type=compute)
            except Exception as exc:
                if device == "cpu":
                    raise
                logger.warning("Whisper could not start on %s (%s); falling back to CPU/int8", device, exc)
                model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                device, compute = "cpu", "int8"
            self._model = model
            self._active_device = device
            if self.language is not None and self.language not in model.supported_languages:
                logger.warning("Configured language '%s' is unsupported by this model; using auto-detect",
                               self.language)
                self.language = None
            logger.info("Whisper model loaded on %s (%s)", device, compute)

    def set_language(self, language: str, initial_prompt: str = "") -> None:
        """Dynamically configure language code (e.g. 'vi', 'en', 'auto') without reloading model."""
        code = language.strip().lower()
        code = None if code in ("auto", "", "none") else code
        if code is not None and self._model is not None and code not in self._model.supported_languages:
            raise ValueError("Language is not supported by the loaded speech model")
        if len(initial_prompt) > 2000:
            raise ValueError("Speech prompt must contain at most 2000 characters")
        with self._config_lock:
            self.language = code
            self.initial_prompt = initial_prompt
        logger.info("Transcriber language set to '%s' (prompt: %.50s)", self.language or "auto", self.initial_prompt)

    def get_config(self) -> dict[str, str | None]:
        with self._config_lock:
            return {
                "model_size": self.model_size,
                "language": self.language or "auto",
                "initial_prompt": self.initial_prompt,
            }

    def transcribe(self, audio_path: str) -> str:
        """Transcribe audio with custom language targeting and initial vocabulary prompt."""
        logger.debug("Transcribing audio: %s", audio_path)
        self.ensure_loaded()
        with self._config_lock:
            language, initial_prompt = self.language, self.initial_prompt
        try:
            segments, info = self._model.transcribe(
                audio_path,
                language=language,
                initial_prompt=initial_prompt or None,
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
            transcript = collapse_repetitions(transcript)
            if _echoes_prompt(transcript, initial_prompt):
                logger.warning("Discarding a transcript that only echoes the biasing prompt: %.70s", transcript)
                return ""
            # Keep meeting content out of INFO logs; the text is available at DEBUG.
            logger.info("Transcript ready (%d characters)", len(transcript))
            logger.debug("Transcript: %s", transcript[:200])
            return transcript

        except Exception:
            logger.exception("Transcription failed for %s", audio_path)
            raise RuntimeError("Speech transcription failed") from None
