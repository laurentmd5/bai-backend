"""
Whisper transcription service with Redis caching.
"""

import asyncio
import tempfile
import hashlib
import functools
import time
from pathlib import Path
from typing import Optional

from faster_whisper import WhisperModel

from app.core.logging import get_logger
from app.core.config import settings
from app.core.metrics import whisper_transcription_duration_seconds
from app.services.cache.redis_cache import cache_service, CacheNamespace

logger = get_logger(__name__)


class WhisperTranscriber:
    """
    Local Whisper model for speech-to-text transcription.
    Uses Redis cache to avoid re‑transcribing identical audio.
    """
    
    MODEL_SIZE = getattr(settings, "WHISPER_MODEL_SIZE", "base")
    COMPUTE_TYPE = "int8"  # Fast on CPU
    CACHE_TTL = getattr(settings, "AUDIO_CACHE_TTL_SECONDS", 86400)  # 24h
    
    def __init__(self):
        self._model = None
        self._initialized = False
    
    def _ensure_model(self):
        if self._initialized:
            return
        logger.info("loading_whisper_model", model=self.MODEL_SIZE, compute=self.COMPUTE_TYPE)
        self._model = WhisperModel(
            self.MODEL_SIZE,
            device="cpu",
            compute_type=self.COMPUTE_TYPE,
            cpu_threads=4,
            num_workers=2
        )
        self._initialized = True
        logger.info("whisper_model_loaded")
    
    def _compute_hash(self, audio_bytes: bytes) -> str:
        """Compute SHA‑256 hash of audio for cache key."""
        return hashlib.sha256(audio_bytes).hexdigest()
    
    # Whisper language code → app language code mapping
    _WHISPER_LANG_MAP: dict = {
        "fr": "fr",
        "en": "en",
        "mn": "mandinka",  # Whisper uses "mn" for Mongolian, close enough fallback
    }
    # Supported app languages for TTS/RAG
    _SUPPORTED_LANGS: frozenset = frozenset({"en", "fr", "mandinka", "wolof"})

    async def _run_transcription(
        self,
        audio_bytes: bytes,
        language: Optional[str],
        beam_size: int,
    ) -> tuple[Optional[str], str]:
        """
        Core transcription logic. Returns (transcript, detected_language).
        When language=None, Whisper auto-detects the spoken language.
        """
        self._ensure_model()

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            loop = asyncio.get_event_loop()
            transcribe_func = functools.partial(
                self._model.transcribe,
                tmp_path,
                language=language,  # None → Whisper auto-detects
                beam_size=beam_size,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )

            start_time = time.time()
            segments, info = await loop.run_in_executor(None, transcribe_func)
            duration = time.time() - start_time
            whisper_transcription_duration_seconds.observe(duration)

            transcript = " ".join([seg.text for seg in segments]).strip()

            # info.language is always set by Whisper (auto-detected or confirmed)
            whisper_lang = getattr(info, "language", "en") or "en"
            detected_lang = self._WHISPER_LANG_MAP.get(whisper_lang, "en")

            if transcript:
                logger.info(
                    "voice_transcribed",
                    duration=info.duration,
                    whisper_language=whisper_lang,
                    app_language=detected_lang,
                    length=len(transcript),
                    processing_time_sec=round(duration, 2),
                )
                return transcript, detected_lang
            else:
                logger.warning("empty_transcript", duration=info.duration)
                return None, detected_lang

        except Exception as e:
            logger.error("whisper_transcription_failed", error=str(e))
            return None, language or "en"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: Optional[str] = "en",
        beam_size: int = 3,
    ) -> Optional[str]:
        """
        Transcribe audio bytes to text (with Redis cache).

        Args:
            audio_bytes: Raw audio data
            language: Expected language code, or None to auto-detect
            beam_size: Whisper beam search width

        Returns:
            Transcribed text, or None on failure.
        """
        self._ensure_model()

        audio_hash = self._compute_hash(audio_bytes)
        cache_key = f"audio_transcript:{language or 'auto'}:{audio_hash}"
        cached = await cache_service.get(CacheNamespace.RAG_RESPONSE, cache_key)
        if cached:
            logger.debug("audio_transcript_cache_hit", hash=audio_hash[:8])
            return cached

        transcript, _ = await self._run_transcription(audio_bytes, language, beam_size)
        if transcript:
            await cache_service.set(
                CacheNamespace.RAG_RESPONSE, cache_key,
                value=transcript, ttl=self.CACHE_TTL,
            )
        return transcript

    async def transcribe_detect(
        self,
        audio_bytes: bytes,
        beam_size: int = 3,
    ) -> tuple[Optional[str], str]:
        """
        Transcribe audio and auto-detect its language.

        Uses Whisper's built-in language identification (no language hint).
        Returns a tuple (transcript, language_code) where language_code is
        one of: "en", "fr", "mandinka", "wolof".

        Args:
            audio_bytes: Raw audio data
            beam_size: Whisper beam search width

        Returns:
            (transcript_text_or_None, detected_language_code)
        """
        self._ensure_model()

        audio_hash = self._compute_hash(audio_bytes)
        cache_key = f"audio_transcript:auto:{audio_hash}"
        cached = await cache_service.get(CacheNamespace.RAG_RESPONSE, cache_key)
        if cached and isinstance(cached, dict):
            logger.debug("audio_transcript_detect_cache_hit", hash=audio_hash[:8])
            return cached.get("text"), cached.get("lang", "en")

        transcript, detected_lang = await self._run_transcription(
            audio_bytes, language=None, beam_size=beam_size
        )
        if transcript:
            await cache_service.set(
                CacheNamespace.RAG_RESPONSE, cache_key,
                value={"text": transcript, "lang": detected_lang},
                ttl=self.CACHE_TTL,
            )
        return transcript, detected_lang


# Global singleton
whisper = WhisperTranscriber()