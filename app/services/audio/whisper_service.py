"""
Whisper transcription service with Redis caching using local faster-whisper.
"""

import hashlib
import io
import time
from typing import Optional

from faster_whisper import WhisperModel

from app.core.logging import get_logger
from app.core.config import settings
from app.core.metrics import whisper_transcription_duration_seconds
from app.services.cache.redis_cache import cache_service, CacheNamespace

import asyncio
from groq import AsyncGroq

logger = get_logger(__name__)


# Phonetic corrections for common speech-to-text mishearings
PHONETIC_CORRECTIONS = {
    "net system": "NETSYSTEME",
    "netsystem": "NETSYSTEME",
    "net-systeme": "NETSYSTEME",
    "net-système": "NETSYSTEME",
    "netsystème": "NETSYSTEME",
}

IT_PROMPT = (
    "network, server, firewall, router, cloud, cybersecurity, support, "
    "maintenance, infrastructure, backup, VPN, incident, troubleshoot, "
    "configuration, NETSYSTEME"
)


class WhisperTranscriber:
    """
    Hybrid Whisper speech-to-text transcription service.
    
    1. Primary: Ultra-fast Groq Cloud Whisper API (whisper-large-v3-turbo, ~350ms)
    2. Fallback: Local faster-whisper model executed in thread pool (non-blocking)
    3. Caching: Redis cache to avoid re-transcribing identical audio.
    """
    
    CACHE_TTL = getattr(settings, "AUDIO_CACHE_TTL_SECONDS", 86400)  # 24h
    
    def __init__(self):
        self.model_size = settings.WHISPER_MODEL_SIZE
        self._model: Optional[WhisperModel] = None
        self._groq_client: Optional[AsyncGroq] = None
        self._init_groq_client()

    def _init_groq_client(self) -> None:
        """Initialize Groq client if API key is configured and feature is enabled."""
        groq_key = settings.GROQ_API_KEY.get_secret_value() if settings.GROQ_API_KEY else None
        use_groq = getattr(settings, "WHISPER_USE_GROQ", True)
        if groq_key and use_groq:
            try:
                self._groq_client = AsyncGroq(api_key=groq_key, timeout=12.0)
                logger.info("whisper_groq_client_initialized", model=getattr(settings, "GROQ_WHISPER_MODEL", "whisper-large-v3-turbo"))
            except Exception as e:
                logger.warning("whisper_groq_client_init_failed", error=str(e))
                self._groq_client = None
        else:
            self._groq_client = None

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            logger.info(f"Loading local faster-whisper model: {self.model_size}")
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8"
            )
        return self._model
    
    def _compute_hash(self, audio_bytes: bytes) -> str:
        """Compute SHA-256 hash of audio for cache key."""
        return hashlib.sha256(audio_bytes).hexdigest()

    def _post_process(
        self,
        transcript: Optional[str],
        raw_lang: Optional[str] = "fr",
        prob: float = 1.0,
    ) -> tuple[Optional[str], str]:
        """Apply phonetic corrections and language resolution."""
        if not transcript or not transcript.strip():
            return None, "fr"
            
        cleaned_transcript = transcript.strip()
        lower_transcript = cleaned_transcript.lower()
        import re
        for wrong, correct in PHONETIC_CORRECTIONS.items():
            if wrong in lower_transcript:
                pattern = re.compile(re.escape(wrong), re.IGNORECASE)
                cleaned_transcript = pattern.sub(correct, cleaned_transcript)
                lower_transcript = cleaned_transcript.lower()

        # Language detection logic: prioritize French (corporate primary)
        detected_lang = raw_lang or "fr"
        if detected_lang == "fr" and prob >= 0.15:
            detected_lang = "fr"
        elif detected_lang == "en" and prob >= 0.75:
            detected_lang = "en"
        else:
            detected_lang = "fr"

        return cleaned_transcript, detected_lang

    async def _transcribe_groq(
        self,
        audio_bytes: bytes,
        language: Optional[str] = None,
    ) -> tuple[Optional[str], str]:
        """Ultra-fast cloud STT using Groq Whisper LPU (~300-500ms)."""
        if not self._groq_client:
            raise RuntimeError("Groq client not available")

        model_name = getattr(settings, "GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
        groq_lang = language if language in ("fr", "en") else None

        transcription = await self._groq_client.audio.transcriptions.create(
            file=("voice_message.ogg", audio_bytes),
            model=model_name,
            prompt=IT_PROMPT,
            response_format="verbose_json",
            language=groq_lang,
        )

        raw_text = getattr(transcription, "text", "") or ""
        detected_lang = getattr(transcription, "language", "fr") or "fr"
        return self._post_process(raw_text, detected_lang, prob=0.95)

    async def _transcribe_local(
        self,
        audio_bytes: bytes,
        beam_size: Optional[int] = None,
        language: Optional[str] = None,
    ) -> tuple[Optional[str], str]:
        """
        Local faster-whisper inference executed in a background worker thread.
        Never blocks the asyncio event loop.
        """
        effective_beam = beam_size if beam_size is not None else getattr(settings, "WHISPER_BEAM_SIZE", 1)

        def _sync_worker():
            audio_file = io.BytesIO(audio_bytes)
            model = self._get_model()
            segments, info = model.transcribe(
                audio_file,
                beam_size=effective_beam,
                language=language,
                initial_prompt=IT_PROMPT,
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )
            raw_text = " ".join([segment.text for segment in segments]).strip()
            return raw_text, info.language, info.language_probability

        raw_text, detected_lang, prob = await asyncio.to_thread(_sync_worker)
        return self._post_process(raw_text, detected_lang, prob)

    async def _run_transcription(
        self,
        audio_bytes: bytes,
        beam_size: Optional[int] = None,
        language: Optional[str] = None,
    ) -> tuple[Optional[str], str]:
        """
        Main transcription router:
        1. Attempt Groq Cloud Whisper if configured.
        2. Fallback gracefully to non-blocking local faster-whisper.
        """
        start_time = time.time()

        # 1. Try Groq Cloud Whisper first
        if self._groq_client:
            try:
                transcript, detected_lang = await self._transcribe_groq(audio_bytes, language=language)
                duration = time.time() - start_time
                whisper_transcription_duration_seconds.observe(duration)
                if transcript:
                    logger.info(
                        "voice_transcribed_groq",
                        length=len(transcript),
                        processing_time_sec=round(duration, 3),
                        detected_lang=detected_lang,
                    )
                    return transcript, detected_lang
            except Exception as e:
                logger.warning("whisper_groq_failed_falling_back_to_local", error=str(e))

        # 2. Fallback to non-blocking local faster-whisper
        try:
            transcript, detected_lang = await self._transcribe_local(
                audio_bytes=audio_bytes,
                beam_size=beam_size,
                language=language,
            )
            duration = time.time() - start_time
            whisper_transcription_duration_seconds.observe(duration)
            if transcript:
                logger.info(
                    "voice_transcribed_local",
                    length=len(transcript),
                    processing_time_sec=round(duration, 3),
                    detected_lang=detected_lang,
                )
                return transcript, detected_lang
            else:
                logger.warning("empty_transcript_from_whisper")
                return None, "fr"
        except Exception as e:
            logger.error("whisper_local_failed", error=str(e))
            return None, "fr"


    async def transcribe(
        self,
        audio_bytes: bytes,
        language: Optional[str] = None,
        beam_size: Optional[int] = None,
    ) -> Optional[str]:
        """
        Transcribe audio bytes to text (with Redis cache).
        """
        audio_hash = self._compute_hash(audio_bytes)
        cache_key = f"audio_transcript:{language or 'auto'}:{audio_hash}"
        cached = await cache_service.get(CacheNamespace.RAG_RESPONSE, cache_key)
        if cached:
            logger.debug("audio_transcript_cache_hit", hash=audio_hash[:8])
            return cached

        transcript, _ = await self._run_transcription(audio_bytes, beam_size=beam_size, language=language)
        if transcript:
            await cache_service.set(
                CacheNamespace.RAG_RESPONSE, cache_key,
                value=transcript, ttl=self.CACHE_TTL,
            )
        return transcript

    async def transcribe_detect(
        self,
        audio_bytes: bytes,
        beam_size: Optional[int] = None,
    ) -> tuple[Optional[str], str]:
        """
        Transcribe audio and return text with detected language.
        """
        audio_hash = self._compute_hash(audio_bytes)
        cache_key = f"audio_transcript:auto:{audio_hash}"
        cached = await cache_service.get(CacheNamespace.RAG_RESPONSE, cache_key)
        
        if cached and isinstance(cached, dict):
            logger.debug("audio_transcript_detect_cache_hit", hash=audio_hash[:8])
            return cached.get("text"), cached.get("lang", "en")

        transcript, detected_lang = await self._run_transcription(audio_bytes, beam_size=beam_size)
        if transcript:
            await cache_service.set(
                CacheNamespace.RAG_RESPONSE, cache_key,
                value={"text": transcript, "lang": detected_lang},
                ttl=self.CACHE_TTL,
            )
        return transcript, detected_lang


# Global singleton
whisper = WhisperTranscriber()

