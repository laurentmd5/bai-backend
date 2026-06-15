import asyncio
from typing import List, Optional
from fastembed import TextEmbedding

from app.services.interfaces.embedding_provider import IEmbeddingProvider
from app.core.logging import get_logger

logger = get_logger(__name__)


class LocalEmbeddingProvider(IEmbeddingProvider):
    """Local embedding using fastembed (lightweight)."""

    MODEL_NAME = "intfloat/multilingual-e5-large"
    EMBEDDING_DIMENSION = 1024

    def __init__(self):
        self._model: Optional[TextEmbedding] = None
        # Eagerly load the model to avoid 30s latency on the very first query
        self._get_model()

    def _get_model(self) -> TextEmbedding:
        if self._model is None:
            logger.info("loading_local_embedding_model", model=self.MODEL_NAME)
            self._model = TextEmbedding(model_name=self.MODEL_NAME)
            logger.info("local_embedding_model_loaded")
        return self._model

    async def embed(self, text: str) -> List[float]:
        # Using to_thread because embed generates vectors synchronously and blocks the event loop
        embeddings = await asyncio.to_thread(self._embed_sync, [text])
        return embeddings[0]

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        # Using to_thread to prevent blocking the event loop for batch operations
        embeddings = await asyncio.to_thread(self._embed_sync, texts)
        return embeddings

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