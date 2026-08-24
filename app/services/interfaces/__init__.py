"""
Service interfaces package for Company Bot.
Defines abstract base classes for dependency inversion.
"""

from app.services.interfaces.llm_provider import ILLMProvider
from app.services.interfaces.embedding_provider import IEmbeddingProvider
from app.services.interfaces.vector_store import IVectorStore
from app.services.interfaces.cache_provider import ICacheProvider

__all__ = [
    "ILLMProvider",
    "IEmbeddingProvider",
    "IVectorStore",
    "ICacheProvider",
]
