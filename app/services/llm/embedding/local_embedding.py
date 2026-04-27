"""
Local embedding provider using sentence-transformers.
No API key required, runs entirely on CPU of the server.
"""

from typing import List, Optional
from sentence_transformers import SentenceTransformer

from app.services.interfaces.embedding_provider import IEmbeddingProvider
from app.core.logging import get_logger

logger = get_logger(__name__)


class LocalEmbeddingProvider(IEmbeddingProvider):
    """
    Local embedding provider using sentence-transformers.
    Uses all-MiniLM-L6-v2 model (384 dimensions, lightweight).
    """

    MODEL_NAME = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION = 384

    def __init__(self):
        self._model: Optional[SentenceTransformer] = None

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info("loading_local_embedding_model", model=self.MODEL_NAME)
            self._model = SentenceTransformer(self.MODEL_NAME)
            logger.info("local_embedding_model_loaded")
        return self._model

    async def embed(self, text: str) -> List[float]:
        model = self._get_model()
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    async def is_available(self) -> bool:
        return True

    def get_dimension(self) -> int:
        return self.EMBEDDING_DIMENSION

    def get_model_name(self) -> str:
        return self.MODEL_NAME