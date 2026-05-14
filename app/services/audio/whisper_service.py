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
    
    async def transcribe(self, audio_bytes: bytes, language: str = "en", beam_size: int = 3) -> Optional[str]:
        """
        Transcribe audio bytes to text, using Redis cache.
        
        Args:
            audio_bytes: Audio data in bytes
            language: Language code (default: "en")
            beam_size: Beam search size for better accuracy (default: 3)
        
        Returns:
            Transcribed text or None if failed.
        """
        self._ensure_model()
        
        # Check cache
        audio_hash = self._compute_hash(audio_bytes)
        cache_key = f"audio_transcript:{audio_hash}"
        cached = await cache_service.get(CacheNamespace.RAG_RESPONSE, cache_key)
        if cached:
            logger.debug("audio_transcript_cache_hit", hash=audio_hash[:8])
            return cached
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        try:
            loop = asyncio.get_event_loop()
            # Create a partial function with named arguments
            transcribe_func = functools.partial(
                self._model.transcribe,
                tmp_path,
                language=language,
                beam_size=beam_size,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500}
            )
            
            # Measure transcription time
            start_time = time.time()
            segments, info = await loop.run_in_executor(None, transcribe_func)
            duration = time.time() - start_time
            whisper_transcription_duration_seconds.observe(duration)
            
            transcript = " ".join([seg.text for seg in segments]).strip()
            
            if transcript:
                # Cache result
                await cache_service.set(
                    CacheNamespace.RAG_RESPONSE,
                    cache_key,
                    value=transcript,
                    ttl=self.CACHE_TTL
                )
                logger.info(
                    "voice_transcribed",
                    duration=info.duration,
                    language=info.language,
                    length=len(transcript),
                    processing_time_sec=round(duration, 2)
                )
                return transcript
            else:
                logger.warning("empty_transcript", duration=info.duration)
                return None
                
        except Exception as e:
            logger.error("whisper_transcription_failed", error=str(e))
            return None
        finally:
            Path(tmp_path).unlink()


# Global singleton
whisper = WhisperTranscriber()