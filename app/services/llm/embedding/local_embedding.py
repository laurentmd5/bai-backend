from typing import List, Optional
from fastembed import TextEmbedding

from app.services.interfaces.embedding_provider import IEmbeddingProvider
from app.core.logging import get_logger

logger = get_logger(__name__)


class LocalEmbeddingProvider(IEmbeddingProvider):
    """Local embedding using fastembed (lightweight)."""

    MODEL_NAME = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSION = 384

    def __init__(self):
        self._model: Optional[TextEmbedding] = None

    def _get_model(self) -> TextEmbedding:
        if self._model is None:
            logger.info("loading_local_embedding_model", model=self.MODEL_NAME)
            self._model = TextEmbedding(model_name=self.MODEL_NAME)
            logger.info("local_embedding_model_loaded")
        return self._model

    async def embed(self, text: str) -> List[float]:
        model = self._get_model()
        embeddings = list(model.embed([text]))
        return embeddings[0].tolist()

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model()
        embeddings = list(model.embed(texts))
        return [e.tolist() for e in embeddings]

    async def is_available(self) -> bool:
        return True

    def get_dimension(self) -> int:
        return self.EMBEDDING_DIMENSION

    def get_model_name(self) -> str:
        return self.MODEL_NAME