"""
Services package for BARROW.AI.
Exports all service classes and factory functions.
"""

from app.services.llm import (
    GeminiProvider,
    OllamaProvider,
    GeminiEmbeddingProvider,
    get_llm_provider,
    get_embedding_provider,
    close_llm_providers,
)
from app.services.cache.redis_cache import cache_service, RedisCacheService
from app.services.vector.qdrant_store import QdrantVectorStore
from app.services.rag_service import RAGService
from app.services.chat_service import ChatService
from app.services.validation import InputValidator, OutputValidator, SecurityValidator
from app.services.whatsapp_service import WhatsAppService
from app.services.analytics_service import AnalyticsService
from app.services.admin_service import AdminService
from app.services.processing.document_processor import DocumentProcessor

__all__ = [
    # LLM
    "GeminiProvider",
    "OllamaProvider",
    "GeminiEmbeddingProvider",
    "get_llm_provider",
    "get_embedding_provider",
    "close_llm_providers",
    
    # Cache
    "cache_service",
    "RedisCacheService",
    
    # Vector Store
    "QdrantVectorStore",
    
    # Core Services
    "RAGService",
    "ChatService",
    
    # Validation
    "InputValidator",
    "OutputValidator",
    "SecurityValidator",
    
    # Integration
    "WhatsAppService",
    
    # Analytics
    "AnalyticsService",
    
    # Admin
    "AdminService",
    
    # Processing
    "DocumentProcessor",
]