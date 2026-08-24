"""
LLM services package for Company Bot.
Contains concrete implementations of LLM providers.
"""

from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.embedding.gemini_embedding import GeminiEmbeddingProvider
from app.services.llm.factory import get_llm_provider, get_embedding_provider, close_llm_providers

__all__ = [
    "GeminiProvider",
    "OllamaProvider",
    "GeminiEmbeddingProvider",
    "get_llm_provider",
    "get_embedding_provider",
    "close_llm_providers",
]
