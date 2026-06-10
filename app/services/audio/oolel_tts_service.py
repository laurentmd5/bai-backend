import asyncio
import io
from typing import Optional, Dict
import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class OolelTTSService:
    """
    TTS Service using Oolel Voices (Soynade Research) via Hugging Face Inference API.
    Designed for Wolof and Wolof-English/French code-switching.
    """
    
    MAX_CACHE_SIZE = 100
    
    def __init__(self):
        self._cache: Dict[str, bytes] = {}
        self.endpoint = settings.OOLEL_TTS_ENDPOINT
        self.api_key = settings.HF_API_KEY.get_secret_value() if settings.HF_API_KEY else None
        
        self.headers = {}
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"
            
    async def is_available(self) -> bool:
        """Check if API key is configured."""
        return self.api_key is not None

    async def synthesize(
        self,
        text: str,
        language: str = "wolof",
        **kwargs
    ) -> Optional[bytes]:
        """
        Convert text to audio using Oolel Voices.
        
        Args:
            text: Text to speak (supports Wolof/English/French mixing)
            language: Base language (usually wolof)
            
        Returns:
            Raw audio bytes (usually WAV or FLAC from HF Inference API), or None on failure.
        """
        if not text or not text.strip():
            return None
            
        if not self.api_key:
            logger.error("oolel_tts_no_api_key")
            return None

        # Check cache
        cache_key = f"{language}:{text}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        payload = {
            "inputs": text,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for attempt in range(3):
                    response = await client.post(
                        self.endpoint,
                        headers=self.headers,
                        json=payload
                    )
                    
                    if response.status_code == 200:
                        # Success, HF API returns audio bytes
                        audio_data = response.content
                        
                        # Update cache
                        if len(self._cache) >= self.MAX_CACHE_SIZE:
                            # Remove oldest
                            first_key = next(iter(self._cache))
                            del self._cache[first_key]
                        self._cache[cache_key] = audio_data
                        
                        logger.info("oolel_tts_success", length=len(audio_data))
                        return audio_data
                        
                    elif response.status_code == 503:
                        # Model is loading
                        try:
                            data = response.json()
                            estimated_time = data.get("estimated_time", 10.0)
                        except:
                            estimated_time = 10.0
                            
                        logger.warning("oolel_tts_loading", estimated_time=estimated_time, attempt=attempt+1)
                        await asyncio.sleep(min(estimated_time, 20.0))
                        
                    elif response.status_code == 429:
                        wait_time = 2 ** attempt
                        logger.warning("oolel_tts_rate_limit", wait_seconds=wait_time, attempt=attempt+1)
                        await asyncio.sleep(wait_time)
                        
                    else:
                        logger.error("oolel_tts_error", status_code=response.status_code, text=response.text)
                        return None
                        
                logger.error("oolel_tts_max_retries_exceeded")
                return None

        except Exception as e:
            logger.error("oolel_tts_exception", error=str(e))
            return None

# Singleton instance
oolel_tts = OolelTTSService()
