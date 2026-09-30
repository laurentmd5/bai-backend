"""
Embedding Provider interface for Company Bot.
Defines abstract base class for embedding model providers.
"""

from abc import ABC, abstractmethod
from typing import List, Optional


class IEmbeddingProvider(ABC):
    """
    Abstract interface for Embedding model providers.
    
    Embeddings are vector representations of text used for semantic search.
    """
    
    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """
        Generate an embedding vector for the given text.
        
        Args:
            text: Text to embed
            
        Returns:
            Vector of floats (dimension depends on model)
            
        Raises:
            EmbeddingException: If embedding generation fails
        """
        pass
    
    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if the embedding provider is available.
        
        Returns:
            True if service is reachable
        """
        pass
    
    @abstractmethod
    def get_dimension(self) -> int:
        """
        Get the dimension of the embedding vectors.
        
        Returns:
            Vector dimension (e.g., 768 for text-embedding-004)
        """
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """
        Get the name of the embedding model.
        
        Returns:
            Model identifier string
        """
        pass
