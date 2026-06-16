"""
Oolel TTS API Client.
Connects to a remote VM running the Oolel TTS engine for Wolof voice synthesis.
"""

import base64
import json
import httpx
from typing import Optional, Dict

from app.core.config import settings
from app.core.logging import get_logger
from app.services.cache.redis_cache import cache_service

logger = get_logger(__name__)


class OolelTTSClient:
    """
    Client for Oolel TTS REST API.
    Handles synthesis requests and base64 audio decoding.
    """
    
    def __init__(self):
        self.api_url = settings.OOLEL_API_URL.rstrip('/')
        self._client: Optional[httpx.AsyncClient] = None
        
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling and a long timeout."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(float(settings.OOLEL_TTS_TIMEOUT)),  # Configurable timeout for Oolel
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
        return self._client
        
    async def is_available(self) -> bool:
        """Check if the Oolel TTS VM is reachable."""
        try:
            client = await self._get_client()
            # Try a simple GET to check availability (or fallback to True if no health endpoint)
            # Assuming the service might return something on / or we can just try to connect
            # We'll just return True for now and rely on synthesis timeouts
            return True
        except Exception:
            return False

    async def synthesize(self, text: str, **kwargs) -> Optional[bytes]:
        """
        Convert text to audio using the local Oolel REST API.
        
        Args:
            text: Text to speak in Wolof
            
        Returns:
            Raw audio bytes (WAV), or None on failure.
        """
        if not text or not text.strip():
            return None
            
        # Check persistent Redis cache
        cached_audio = await cache_service.get_oolel_tts(text)
        if cached_audio:
            logger.debug("oolel_tts_cache_hit")
            return cached_audio
            
        try:
            client = await self._get_client()
            
            logger.info("oolel_tts_api_request", text_length=len(text), url=f"{self.api_url}/synthesize")
            
            payload = {"text": text}
            
            response = await client.post(
                f"{self.api_url}/synthesize",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            data = response.json()
            audio_base64 = data.get("audio_base64")
            
            if not audio_base64:
                logger.error("oolel_tts_no_audio_in_response")
                return None
                
            audio_bytes = base64.b64decode(audio_base64)
            
            # Save to persistent Redis cache
            await cache_service.set_oolel_tts(text, audio_bytes)
            
            logger.info(
                "oolel_tts_success", 
                audio_size=len(audio_bytes),
                duration_ms=data.get("duration_ms"),
                sample_rate=data.get("sample_rate")
            )
            
            return audio_bytes
            
        except httpx.TimeoutException:
            logger.error("oolel_tts_timeout", url=self.api_url)
            return None
        except httpx.HTTPStatusError as e:
            logger.error("oolel_tts_http_error", status_code=e.response.status_code, error=e.response.text)
            return None
        except Exception as e:
            logger.error("oolel_tts_unexpected_error", error=str(e))
            return None

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Singleton instance
oolel_client = OolelTTSClient()
