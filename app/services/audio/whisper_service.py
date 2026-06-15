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

logger = get_logger(__name__)


class WhisperTranscriber:
    """
    Local Whisper model for speech-to-text transcription.
    Uses Redis cache to avoid re-transcribing identical audio.
    """
    
    CACHE_TTL = getattr(settings, "AUDIO_CACHE_TTL_SECONDS", 86400)  # 24h
    
    def __init__(self):
        self.model_size = settings.WHISPER_MODEL_SIZE
        # Initialize model on CPU with INT8 quantization for efficiency
        logger.info(f"Loading local faster-whisper model: {self.model_size}")
        self.model = WhisperModel(
            self.model_size,
            device="cpu",
            compute_type="int8"
        )
    
    def _compute_hash(self, audio_bytes: bytes) -> str:
        """Compute SHA-256 hash of audio for cache key."""
        return hashlib.sha256(audio_bytes).hexdigest()

    async def _run_transcription(
        self,
        audio_bytes: bytes,
        beam_size: int = 5,
        language: Optional[str] = None
    ) -> tuple[Optional[str], str]:
        """
        Core transcription logic using local faster-whisper.
        Uses aggressive Wolof/English initial prompt to force code-switching.
        """
        start_time = time.time()
        
        try:
            # Wrap bytes in BytesIO
            audio_file = io.BytesIO(audio_bytes)
            
            # Wolof code-switching prompt to guide Whisper with diverse vocabulary and specific Gambian names
            wolof_prompt = "Salaamalekum, nanga def? Jërëjëf. Waaw, déedéet, loolu deug la. Lu xew? Numu tudd? Dama bëgg xam ndax mën nga ma dimbali. The National People's Party (NPP), Adama Barrow, Kan moy, and President Barrow are great."
            
            # Run inference synchronously (we could use an executor but this is POC)
            segments, info = self.model.transcribe(
                audio_file,
                beam_size=beam_size,
                language=language,
                initial_prompt=wolof_prompt,
                condition_on_previous_text=False, # Prevent hallucination loops
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # Consume the generator
            transcript = " ".join([segment.text for segment in segments]).strip()
            
            duration = time.time() - start_time
            whisper_transcription_duration_seconds.observe(duration)
            
            detected_lang = info.language
            prob = info.language_probability
            
            # Whisper struggles with Wolof and usually outputs random languages with low confidence (e.g. 'ms' 0.36).
            # However, for English it will output 'en' with higher confidence (e.g. 0.55+ despite the Wolof prompt).
            # We add a confidence threshold to avoid overriding legitimate English audio.
            if detected_lang == "en" and prob >= 0.30:
                pass  # Keep 'en'
            else:
                detected_lang = "wolof"
            
            if transcript:
                logger.info(
                    "voice_transcribed_local",
                    length=len(transcript),
                    processing_time_sec=round(duration, 2),
                    detected_lang=detected_lang
                )
                return transcript, detected_lang
            else:
                logger.warning("empty_transcript_from_whisper")
                return None, "wolof"

        except Exception as e:
            logger.error("whisper_local_failed", error=str(e))
            return None, "wolof"

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: Optional[str] = None,
        beam_size: int = 5,
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

        transcript, _ = await self._run_transcription(audio_bytes, beam_size, language)
        if transcript:
            await cache_service.set(
                CacheNamespace.RAG_RESPONSE, cache_key,
                value=transcript, ttl=self.CACHE_TTL,
            )
        return transcript

    async def transcribe_detect(
        self,
        audio_bytes: bytes,
        beam_size: int = 5,
    ) -> tuple[Optional[str], str]:
        """
        Transcribe audio and return text with detected language.
        """
        audio_hash = self._compute_hash(audio_bytes)
        cache_key = f"audio_transcript:auto:{audio_hash}"
        cached = await cache_service.get(CacheNamespace.RAG_RESPONSE, cache_key)
        
        if cached and isinstance(cached, dict):
            logger.debug("audio_transcript_detect_cache_hit", hash=audio_hash[:8])
            return cached.get("text"), cached.get("lang", "wolof")

        transcript, detected_lang = await self._run_transcription(audio_bytes, beam_size)
        if transcript:
            await cache_service.set(
                CacheNamespace.RAG_RESPONSE, cache_key,
                value={"text": transcript, "lang": detected_lang},
                ttl=self.CACHE_TTL,
            )
        return transcript, detected_lang


# Global singleton
whisper = WhisperTranscriber()