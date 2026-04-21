"""
Vector Store interface for BARROW.AI.
Defines abstract base class for vector database providers.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple


class IVectorStore(ABC):
    """
    Abstract interface for Vector Store providers.
    
    Vector stores are used for semantic search in RAG (Retrieval-Augmented Generation).
    They store embeddings (vectors) and their associated metadata.
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the vector store.
        Creates collections and indexes if they don't exist.
        """
        pass
    
    @abstractmethod
    async def search(
        self,
        query_vector: List[float],
        limit: int = 5,
        score_threshold: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors in the store.
        
        Args:
            query_vector: Embedding vector to search for
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score (0.0 to 1.0)
            filters: Optional metadata filters
            
        Returns:
            List of results with id, score, and payload
        """
        pass
    
    @abstractmethod
    async def upsert(
        self,
        points: List[Dict[str, Any]],
        vectors: List[List[float]],
        payloads: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """
        Insert or update points in the vector store.
        
        Args:
            points: List of point configurations (must include 'id')
            vectors: List of embedding vectors
            payloads: Optional list of metadata payloads
            
        Returns:
            Number of points upserted
        """
        pass
    
    @abstractmethod
    async def delete(self, point_ids: List[str]) -> int:
        """
        Delete points from the vector store.
        
        Args:
            point_ids: List of point IDs to delete
            
        Returns:
            Number of points deleted
        """
        pass
    
    @abstractmethod
    async def delete_by_filter(self, filter_condition: Dict[str, Any]) -> int:
        """
        Delete points matching a filter condition.
        
        Args:
            filter_condition: Filter criteria
            
        Returns:
            Number of points deleted
        """
        pass
    
    @abstractmethod
    async def get_collection_info(self) -> Dict[str, Any]:
        """
        Get information about the current collection.
        
        Returns:
            Collection metadata (name, size, vector dimension, etc.)
        """
        pass
    
    @abstractmethod
    async def count(self) -> int:
        """
        Get the total number of points in the collection.
        
        Returns:
            Point count
        """
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if the vector store is available.
        
        Returns:
            True if service is reachable
        """
        pass