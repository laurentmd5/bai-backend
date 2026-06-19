"""
Oolel TTS API Client.
Connects to a remote VM running the Oolel TTS engine for Wolof voice synthesis.
"""

import base64
import json
import httpx
from typing import Optional, Dict
import io
import wave
import re

from app.core.config import settings
from app.core.logging import get_logger
from app.services.cache.redis_cache import cache_service

logger = get_logger(__name__)


def split_into_sentences(text: str, max_length: int = 150) -> list[str]:
    """Split text into manageable chunks for TTS without breaking sentences if possible."""
    sentences = []
    parts = re.split(r'([.!?]+|\n+)', text)
    
    current_chunk = ""
    for i in range(0, len(parts), 2):
        sentence = parts[i]
        delim = parts[i+1] if i+1 < len(parts) else ""
        full_sentence = (sentence + delim).strip()
        
        if not full_sentence:
            continue
            
        if len(current_chunk) + len(full_sentence) <= max_length:
            current_chunk += " " + full_sentence if current_chunk else full_sentence
        else:
            if current_chunk:
                sentences.append(current_chunk.strip())
            
            if len(full_sentence) > max_length:
                sub_parts = full_sentence.split(',')
                sub_chunk = ""
                for sp in sub_parts:
                    if len(sub_chunk) + len(sp) + 1 <= max_length:
                        sub_chunk += "," + sp if sub_chunk else sp
                    else:
                        if sub_chunk:
                            sentences.append(sub_chunk.strip())
                        sub_chunk = sp
                if sub_chunk:
                    current_chunk = sub_chunk.strip()
            else:
                current_chunk = full_sentence
                
    if current_chunk:
        sentences.append(current_chunk.strip())
        
    return sentences


def concatenate_wavs(wav_bytes_list: list[bytes]) -> bytes:
    """Concatenate multiple WAV byte strings into a single WAV byte string."""
    valid_wavs = [w for w in wav_bytes_list if w]
    if not valid_wavs:
        return b""
    if len(valid_wavs) == 1:
        return valid_wavs[0]
        
    out_io = io.BytesIO()
    with wave.open(out_io, 'wb') as wav_out:
        for i, wav_bytes in enumerate(valid_wavs):
            try:
                wav_in = wave.open(io.BytesIO(wav_bytes), 'rb')
                if i == 0:
                    wav_out.setparams(wav_in.getparams())
                wav_out.writeframes(wav_in.readframes(wav_in.getnframes()))
                wav_in.close()
            except Exception as e:
                logger.error(f"Error concatenating WAV chunk: {e}")
                
    return out_io.getvalue()


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
        Automatically chunks long text to prevent GPU hangs and timeouts.
        """
        if not text or not text.strip():
            return None
            
        # Check persistent Redis cache
        cached_audio = await cache_service.get_oolel_tts(text)
        if cached_audio:
            logger.debug("oolel_tts_cache_hit")
            return cached_audio
            
        # Chunk text
        chunks = split_into_sentences(text)
        logger.info("oolel_tts_chunking", total_chunks=len(chunks), text_length=len(text))
        
        chunk_audios = []
        for chunk in chunks:
            chunk_audio = await self._synthesize_chunk(chunk)
            if chunk_audio:
                chunk_audios.append(chunk_audio)
                
        if not chunk_audios:
            return None
            
        # Concatenate chunks
        final_audio = concatenate_wavs(chunk_audios)
        
        # Save to persistent Redis cache
        if final_audio:
            await cache_service.set_oolel_tts(text, final_audio)
            
            logger.info(
                "oolel_tts_success_chunked", 
                audio_size=len(final_audio),
                chunks=len(chunks)
            )
            
        return final_audio

    async def _synthesize_chunk(self, text: str) -> Optional[bytes]:
        """Internal method to synthesize a single short chunk."""
        try:
            client = await self._get_client()
            
            is_hf = "huggingface.cloud" in self.api_url or "hf.space" in self.api_url
            endpoint_url = self.api_url if is_hf else f"{self.api_url}/synthesize"
            
            # Removed max_new_tokens to avoid GPU hang, letting Oolel stop naturally on short text
            payload = {"inputs": text} if is_hf else {"text": text}
            headers = {"Content-Type": "application/json"}
            
            if is_hf and settings.HF_TOKEN:
                headers["Authorization"] = f"Bearer {settings.HF_TOKEN.get_secret_value()}"
            
            response = await client.post(
                endpoint_url,
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            data = response.json()
            audio_base64 = data.get("audio") if is_hf else data.get("audio_base64")
            
            if not audio_base64:
                logger.error("oolel_tts_no_audio_in_response")
                return None
                
            audio_bytes = base64.b64decode(audio_base64)
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
