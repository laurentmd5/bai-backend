import asyncio
import hashlib
from collections import OrderedDict
from typing import List, Optional
from fastembed import TextEmbedding

from app.services.interfaces.embedding_provider import IEmbeddingProvider
from app.core.logging import get_logger

logger = get_logger(__name__)


class LocalEmbeddingProvider(IEmbeddingProvider):
    """Local embedding using fastembed (lightweight) with in-memory LRU vector cache."""

    MODEL_NAME = "intfloat/multilingual-e5-large"
    EMBEDDING_DIMENSION = 1024
    MAX_CACHE_SIZE = 1000

    def __init__(self):
        self._model: Optional[TextEmbedding] = None
        self._cache: OrderedDict[str, List[float]] = OrderedDict()

    def _get_model(self) -> TextEmbedding:
        if self._model is None:
            logger.info("loading_local_embedding_model", model=self.MODEL_NAME)
            self._model = TextEmbedding(model_name=self.MODEL_NAME)
            logger.info("local_embedding_model_loaded")
        return self._model

    def _get_cache_key(self, text: str) -> str:
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    async def embed(self, text: str) -> List[float]:
        key = self._get_cache_key(text)
        if key in self._cache:
            # Move to end for LRU freshness
            self._cache.move_to_end(key)
            return self._cache[key]

        # Using to_thread because embed generates vectors synchronously and blocks the event loop
        embeddings = await asyncio.to_thread(self._embed_sync, [text])
        vector = embeddings[0]

        # Store in LRU cache
        if len(self._cache) >= self.MAX_CACHE_SIZE:
            self._cache.popitem(last=False)
        self._cache[key] = vector

        return vector

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        # Check cache for any hits
        results: List[Optional[List[float]]] = [None] * len(texts)
        missing_indices: List[int] = []
        missing_texts: List[str] = []

        for idx, text in enumerate(texts):
            key = self._get_cache_key(text)
            if key in self._cache:
                self._cache.move_to_end(key)
                results[idx] = self._cache[key]
            else:
                missing_indices.append(idx)
                missing_texts.append(text)

        if missing_texts:
            new_embeddings = await asyncio.to_thread(self._embed_sync, missing_texts)
            for original_idx, missing_text, vector in zip(missing_indices, missing_texts, new_embeddings):
                key = self._get_cache_key(missing_text)
                if len(self._cache) >= self.MAX_CACHE_SIZE:
                    self._cache.popitem(last=False)
                self._cache[key] = vector
                results[original_idx] = vector

        return results  # type: ignore

    def _embed_sync(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model()
        embeddings = list(model.embed(texts))
        return [e.tolist() for e in embeddings]

    async def is_available(self) -> bool:
        return True

    def get_dimension(self) -> int:
        return self.EMBEDDING_DIMENSION

    def get_model_name(self) -> str:
        return self.MODEL_NAME