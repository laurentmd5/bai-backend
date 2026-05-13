"""
Edge TTS service – free, no API key required.
"""

from typing import Optional, Dict
import edge_tts

from app.core.logging import get_logger
from app.core.config import settings

logger = get_logger(__name__)


class EdgeTTSService:
    """
    Free TTS using Microsoft Edge voices.
    Caches synthesized audio in memory (simple dict).
    """
    
    VOICES = {
        "en": "en-US-JennyNeural",
        "fr": "fr-FR-DeniseNeural",
    }
    MAX_CACHE_SIZE = 100
    
    def __init__(self):
        self._cache: Dict[str, bytes] = {}
    
    async def synthesize(self, text: str, language: str = "en") -> Optional[bytes]:
        """
        Convert text to MP3 audio.
        
        Returns:
            Audio bytes or None.
        """
        if not text:
            return None
        
        voice = self.VOICES.get(language, self.VOICES["en"])
        cache_key = f"{voice}:{hash(text)}"
        
        # Cache check
        if cache_key in self._cache:
            logger.debug("tts_cache_hit")
            return self._cache[cache_key]
        
        try:
            communicate = edge_tts.Communicate(text, voice, rate="+0%", volume="+0%")
            audio_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])
            
            if not audio_chunks:
                logger.error("tts_no_audio_chunks")
                return None
            
            audio_bytes = b"".join(audio_chunks)
            
            # Simple cache eviction
            if len(self._cache) >= self.MAX_CACHE_SIZE:
                self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key] = audio_bytes
            
            logger.info("tts_synthesized", text_len=len(text), audio_size=len(audio_bytes))
            return audio_bytes
            
        except Exception as e:
            logger.error("tts_synthesis_failed", error=str(e))
            return None


# Global singleton
tts = EdgeTTSService()