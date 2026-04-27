"""
Gemini Embedding Provider implementation for BARROW.AI.
Integrates with Google text-embedding-004 model.
"""

import asyncio
from typing import List, Optional
import hashlib

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.services.interfaces.embedding_provider import IEmbeddingProvider
from app.services.cache.redis_cache import cache_service, CacheNamespace
from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import BarrowAIException, ErrorCode

logger = get_logger(__name__)


class EmbeddingException(BarrowAIException):
    """Embedding generation exception."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            message=f"Embedding error: {message}",
            code=ErrorCode.EMBEDDING_FAILED,
            status_code=503,
            details={"original_error": str(original_error)} if original_error else None
        )


class GeminiEmbeddingProvider(IEmbeddingProvider):
    """
    Google text-embedding-004 provider implementation.
    
    Generates 768-dimensional embeddings for semantic search.
    Includes caching to reduce API calls and improve performance.
    """
    
    EMBEDDING_DIMENSION = 768
    BATCH_SIZE = 100
    CACHE_TTL = settings.CACHE_EMBEDDING_TTL_SECONDS
    
    def __init__(self):
        self._api_key = settings.gemini_api_key_str
        self._model = settings.GEMINI_EMBED_MODEL
        self._base_url = "https://generativelanguage.googleapis.com/v1beta"
        self._client: Optional[httpx.AsyncClient] = None
        self._cache_enabled = True
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=10.0, read=15.0, write=10.0),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self._api_key,
                },
            )
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.sha256(text.encode()).hexdigest()
    
    async def embed(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            768-dimensional vector
        """
        if not text or not text.strip():
            raise EmbeddingException("Cannot embed empty text")
        
        # Check cache first
        if self._cache_enabled:
            cache_key = self._get_cache_key(text)
            cached = await cache_service.get_embedding(text)
            if cached is not None:
                logger.debug("embedding_cache_hit", text_preview=text[:50])
                return cached
        
        url = f"{self._base_url}/{self._model}:embedContent"
        
        payload = {
            "model": self._model,
            "content": {"parts": [{"text": text}]},
        }
        
        try:
            client = await self._get_client()
            
            response = await client.post(url, json=payload)
            
            if response.status_code != 200:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                raise EmbeddingException(error_msg)
            
            data = response.json()
            embedding = data.get("embedding", {}).get("values", [])
            
            if len(embedding) != self.EMBEDDING_DIMENSION:
                raise EmbeddingException(
                    f"Unexpected embedding dimension: {len(embedding)}"
                )
            
            # Cache the result
            if self._cache_enabled:
                await cache_service.set_embedding(text, embedding, ttl=self.CACHE_TTL)
            
            logger.debug("embedding_generated", text_preview=text[:50])
            
            return embedding
            
        except httpx.TimeoutException as e:
            raise EmbeddingException("Timeout generating embedding", e) from e
        except httpx.ConnectError as e:
            raise EmbeddingException("Failed to connect to embedding API", e) from e
        except EmbeddingException:
            raise
        except Exception as e:
            raise EmbeddingException(f"Unexpected error: {str(e)}", e) from e
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        embeddings = []
        
        # Process in batches
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i:i + self.BATCH_SIZE]
            
            url = f"{self._base_url}/{self._model}:batchEmbedContents"
            
            requests = [
                {"model": self._model, "content": {"parts": [{"text": text}]}}
                for text in batch
            ]
            
            payload = {"requests": requests}
            
            try:
                client = await self._get_client()
                response = await client.post(url, json=payload)
                response.raise_for_status()
                
                data = response.json()
                
                for item in data.get("embeddings", []):
                    embedding = item.get("values", [])
                    embeddings.append(embedding)
                    
                    # Cache individual embeddings
                    if self._cache_enabled and i + len(embeddings) <= len(texts):
                        text = texts[i + len(embeddings) - 1]
                        await cache_service.set_embedding(text, embedding, ttl=self.CACHE_TTL)
                
            except Exception as e:
                logger.error("batch_embedding_failed", batch_index=i, error=str(e))
                # Fall back to individual embeddings for this batch
                for text in batch:
                    emb = await self.embed(text)
                    embeddings.append(emb)
        
        logger.debug("batch_embeddings_generated", count=len(embeddings))
        
        return embeddings
    
    async def is_available(self) -> bool:
        """Check if embedding API is available."""
        try:
            client = await self._get_client()
            url = f"{self._base_url}/models?key={self._api_key}"
            response = await client.get(url)
            return response.status_code == 200
        except Exception:
            return False
    
    def get_dimension(self) -> int:
        """Get embedding dimension."""
        return self.EMBEDDING_DIMENSION
    
    def get_model_name(self) -> str:
        """Get model name."""
        return self._model