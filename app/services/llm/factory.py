"""
LLM Provider factory for BARROW.AI.
Provides dependency injection for LLM and embedding providers.
"""

from typing import Optional

from app.services.interfaces.llm_provider import ILLMProvider
from app.services.interfaces.embedding_provider import IEmbeddingProvider
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.embedding.local_embedding import LocalEmbeddingProvider
from app.core.config import settings, LLMProvider
from app.core.logging import get_logger

logger = get_logger(__name__)

# Singleton instances
_llm_provider: Optional[ILLMProvider] = None
_embedding_provider: Optional[IEmbeddingProvider] = None


def get_llm_provider() -> ILLMProvider:
    """
    Get the configured LLM provider instance.
    
    Uses singleton pattern to avoid creating multiple instances.
    
    Returns:
        ILLMProvider implementation based on settings.LLM_PROVIDER
    """
    global _llm_provider
    
    if _llm_provider is not None:
        return _llm_provider
    
    if settings.LLM_PROVIDER == LLMProvider.GEMINI:
        logger.info("using_gemini_llm_provider")
        _llm_provider = GeminiProvider()
    elif settings.LLM_PROVIDER == LLMProvider.OLLAMA:
        logger.info("using_ollama_llm_provider")
        _llm_provider = OllamaProvider()
    else:
        logger.warning(
            "unknown_llm_provider_falling_back_to_gemini",
            provider=settings.LLM_PROVIDER
        )
        _llm_provider = GeminiProvider()
    
    return _llm_provider


def get_embedding_provider() -> IEmbeddingProvider:
    """
    Get the configured embedding provider instance.
    
    Uses singleton pattern.
    Uses local sentence-transformers model for offline embedding.
    
    Returns:
        IEmbeddingProvider implementation
    """
    global _embedding_provider
    
    if _embedding_provider is not None:
        return _embedding_provider
    
    logger.info("using_local_embedding_provider")
    _embedding_provider = LocalEmbeddingProvider()
    
    return _embedding_provider


async def close_llm_providers() -> None:
    """
    Close all LLM provider connections.
    Should be called on application shutdown.
    """
    global _llm_provider, _embedding_provider
    
    if _llm_provider and hasattr(_llm_provider, 'close'):
        await _llm_provider.close()
        _llm_provider = None
        logger.info("llm_provider_closed")
    
    if _embedding_provider and hasattr(_embedding_provider, 'close'):
        await _embedding_provider.close()
        _embedding_provider = None
        logger.info("embedding_provider_closed")


def reset_llm_providers() -> None:
    """
    Reset provider singletons.
    Useful for testing.
    """
    global _llm_provider, _embedding_provider
    _llm_provider = None
    _embedding_provider = None