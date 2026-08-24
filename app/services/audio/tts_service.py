"""
Edge TTS service – free, no API key required.
"""

import os
import time
from typing import Optional, Dict
import edge_tts

from app.core.logging import get_logger
from app.core.config import settings
from app.core.metrics import tts_synthesis_duration_seconds

logger = get_logger(__name__)


class EdgeTTSService:
    """
    Unified TTS Service using Edge TTS.
    """
    
    # Male voices
    VOICES = {
        "en": "en-NG-AbeoNeural",      # Nigerian male
        "fr": "fr-FR-HenriNeural",    # French male
    }
    
    # Default speech rate (slower)
    DEFAULT_RATE = "-20%"   # Slow down by 20%
    DEFAULT_VOLUME = "+0%"
    
    MAX_CACHE_SIZE = 100
    
    def __init__(self):
        self._cache: Dict[str, bytes] = {}
        # Allow override via environment variables
        self._voice_override = os.getenv("TTS_VOICE", "")
        self._rate = os.getenv("TTS_RATE", self.DEFAULT_RATE)
        self._volume = os.getenv("TTS_VOLUME", self.DEFAULT_VOLUME)
    
    async def synthesize(
        self,
        text: str,
        language: str = "en",
        rate: Optional[str] = None,
        volume: Optional[str] = None,
        voice: Optional[str] = None
    ) -> Optional[bytes]:
        """
        Convert text to MP3 audio.
        
        Args:
            text: Text to speak
            language: Language code ('en' or 'fr')
            rate: Speaking rate (e.g. "-20%", "+0%")
            volume: Volume level
            voice: Specific voice name (overrides language mapping)
            
        Returns:
            Audio bytes or None.
        """
        if not text:
            return None
            
            # Edge TTS for all supported languages
        
        # Voice selection
        if voice:
            selected_voice = voice
        elif self._voice_override:
            selected_voice = self._voice_override
        else:
            selected_voice = self.VOICES.get(language, self.VOICES["en"])
        
        # Rate and volume selection
        selected_rate = rate or self._rate
        selected_volume = volume or self._volume
        
        cache_key = f"{selected_voice}:{hash(text)}:{selected_rate}:{selected_volume}"
        
        # Cache check
        if cache_key in self._cache:
            logger.debug("tts_cache_hit")
            return self._cache[cache_key]
        
        try:
            start_time = time.time()
            
            communicate = edge_tts.Communicate(
                text,
                selected_voice,
                rate=selected_rate,
                volume=selected_volume
            )
            audio_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])
            
            duration = time.time() - start_time
            tts_synthesis_duration_seconds.observe(duration)
            
            if not audio_chunks:
                logger.error("tts_no_audio_chunks")
                return None
            
            audio_bytes = b"".join(audio_chunks)
            
            # Simple cache eviction
            if len(self._cache) >= self.MAX_CACHE_SIZE:
                self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key] = audio_bytes
            
            logger.info(
                "tts_synthesized",
                text_len=len(text),
                audio_size=len(audio_bytes),
                voice=selected_voice,
                rate=selected_rate,
                synthesis_time_sec=round(duration, 2)
            )
            return audio_bytes
            
        except Exception as e:
            logger.error("tts_synthesis_failed", error=str(e))
            return None


# Global singleton
tts = EdgeTTSService()
