"""
Whisper transcription service with Redis caching using Hugging Face Inference Providers.
"""

import hashlib
import time
from typing import Optional

import httpx

from app.core.logging import get_logger
from app.core.config import settings
from app.core.metrics import whisper_transcription_duration_seconds
from app.services.cache.redis_cache import cache_service, CacheNamespace

logger = get_logger(__name__)


class WhisperTranscriber:
    """
    Cloud Whisper model for speech-to-text transcription via Hugging Face.
    Uses Redis cache to avoid re-transcribing identical audio.
    """
    
    CACHE_TTL = getattr(settings, "AUDIO_CACHE_TTL_SECONDS", 86400)  # 24h
    
    def __init__(self):
        self._endpoint = settings.WHISPER_STT_ENDPOINT
        self._hf_token = settings.HF_TOKEN.get_secret_value() if settings.HF_TOKEN else None
    
    def _compute_hash(self, audio_bytes: bytes) -> str:
        """Compute SHA-256 hash of audio for cache key."""
        return hashlib.sha256(audio_bytes).hexdigest()

    async def _run_transcription(
        self,
        audio_bytes: bytes,
    ) -> tuple[Optional[str], str]:
        """
        Core transcription logic calling the Hugging Face Router API.
        """
        if not self._hf_token:
            logger.error("hf_token_missing_for_whisper")
            return None, "en"
            
        start_time = time.time()
        
        try:
            # We use a 30 second timeout as Whisper large can take a bit for long audios
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self._endpoint,
                    headers={"Authorization": f"Bearer {self._hf_token}"},
                    content=audio_bytes
                )
                
            response.raise_for_status()
            result = response.json()
            
            duration = time.time() - start_time
            whisper_transcription_duration_seconds.observe(duration)
            
            transcript = result.get("text", "").strip()
            
            if transcript:
                logger.info(
                    "voice_transcribed_hf_cloud",
                    length=len(transcript),
                    processing_time_sec=round(duration, 2),
                )
                # The HF API returns raw text. We return "en" as a safe fallback
                # because `whatsapp_service.py` uses `langdetect` on the output text anyway.
                return transcript, "en"
            else:
                logger.warning("empty_transcript_from_hf")
                return None, "en"

        except httpx.HTTPStatusError as e:
            logger.error("whisper_hf_api_http_error", status_code=e.response.status_code, text=e.response.text)
            return None, "en"
        except Exception as e:
            logger.error("whisper_hf_api_failed", error=str(e))
            return None, "en"

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: Optional[str] = "en",
        beam_size: int = 3,  # Kept for signature compatibility but ignored in Cloud API
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

        transcript, _ = await self._run_transcription(audio_bytes)
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
        Transcribe audio and return text with dummy language.
        `whatsapp_service.py` detects Wolof automatically from the returned text.
        """
        audio_hash = self._compute_hash(audio_bytes)
        cache_key = f"audio_transcript:auto:{audio_hash}"
        cached = await cache_service.get(CacheNamespace.RAG_RESPONSE, cache_key)
        
        if cached and isinstance(cached, dict):
            logger.debug("audio_transcript_detect_cache_hit", hash=audio_hash[:8])
            return cached.get("text"), cached.get("lang", "en")

        transcript, detected_lang = await self._run_transcription(audio_bytes)
        if transcript:
            await cache_service.set(
                CacheNamespace.RAG_RESPONSE, cache_key,
                value={"text": transcript, "lang": detected_lang},
                ttl=self.CACHE_TTL,
            )
        return transcript, detected_lang


# Global singleton
whisper = WhisperTranscriber()