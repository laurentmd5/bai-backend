"""
Qdrant Vector Store implementation for BARROW.AI.
Provides semantic search capabilities for RAG pipeline.
"""

import uuid
from typing import List, Dict, Any, Optional, Tuple
import asyncio

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse, ResponseHandlingException

from app.services.interfaces.vector_store import IVectorStore
from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import BarrowAIException, ErrorCode

logger = get_logger(__name__)


class QdrantException(BarrowAIException):
    """Qdrant-specific exception."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            message=f"Qdrant error: {message}",
            code=ErrorCode.VECTOR_SEARCH_FAILED,
            status_code=503,
            details={"original_error": str(original_error)} if original_error else None
        )


class QdrantVectorStore(IVectorStore):
    """
    Qdrant vector database implementation.
    
    Features:
    - HNSW indexing for fast approximate nearest neighbor search
    - Cosine similarity distance metric
    - Payload filtering for metadata-based search
    - Collection management with idempotent initialization
    """
    
    def __init__(self):
        self._url = settings.qdrant_url
        self._collection_name = settings.QDRANT_COLLECTION
        self._vector_size = settings.QDRANT_VECTOR_SIZE
        self._similarity_threshold = settings.QDRANT_SIMILARITY_THRESHOLD
        self._client: Optional[QdrantClient] = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
    
    def _get_client(self) -> QdrantClient:
        """
        Get or create Qdrant client.
        
        Returns:
            Configured QdrantClient
        """
        if self._client is None:
            self._client = QdrantClient(
                url=self._url,
                timeout=30.0,
                prefer_grpc=False,  # Use HTTP API
            )
        return self._client
    
    async def initialize(self) -> None:
        """
        Initialize the vector store.
        Creates collection if it doesn't exist.
        Thread-safe with lock.
        """
        async with self._init_lock:
            if self._initialized:
                return
            
            try:
                client = self._get_client()
                
                # Check if collection exists
                collections = client.get_collections()
                collection_names = [c.name for c in collections.collections]
                
                if self._collection_name not in collection_names:
                    logger.info(
                        "creating_qdrant_collection",
                        collection=self._collection_name,
                        vector_size=self._vector_size
                    )
                    
                    client.create_collection(
                        collection_name=self._collection_name,
                        vectors_config=models.VectorParams(
                            size=self._vector_size,
                            distance=models.Distance.COSINE,
                        ),
                        hnsw_config=models.HnswConfigDiff(
                            m=16,  # Number of edges per node
                            ef_construct=100,  # Construction time accuracy
                        ),
                        optimizers_config=models.OptimizersConfigDiff(
                            indexing_threshold=1000,  # Start indexing after 1000 points
                        ),
                    )
                    
                    # Create payload index for full-text keyword search
                    client.create_payload_index(
                        collection_name=self._collection_name,
                        field_name="text",
                        field_schema=models.TextIndexParams(
                            type="text",
                            tokenizer=models.TokenizerType.WORD,
                            min_token_len=2,
                            max_token_len=15,
                            lowercase=True,
                        )
                    )
                    
                    logger.info("qdrant_collection_created", collection=self._collection_name)
                else:
                    logger.info("qdrant_collection_exists", collection=self._collection_name)
                    # Try to create index on existing collection just in case
                    try:
                        client.create_payload_index(
                            collection_name=self._collection_name,
                            field_name="text",
                            field_schema=models.TextIndexParams(
                                type="text",
                                tokenizer=models.TokenizerType.WORD,
                                min_token_len=2,
                                max_token_len=15,
                                lowercase=True,
                            )
                        )
                    except Exception:
                        pass
                
                # Verify collection info
                info = await self.get_collection_info()
                logger.info(
                    "qdrant_initialized",
                    collection=self._collection_name,
                    points_count=info.get("points_count", 0),
                    vector_size=info.get("vector_size", 0),
                )
                
                self._initialized = True
                
            except Exception as e:
                logger.error("qdrant_initialization_failed", error=str(e))
                raise QdrantException(f"Failed to initialize Qdrant: {str(e)}", e)
    
    async def search(
        self,
        query_vector: List[float],
        limit: int = 5,
        score_threshold: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.
        
        Args:
            query_vector: 768-dimensional embedding vector
            limit: Maximum number of results (default 5)
            score_threshold: Minimum similarity score (default from settings)
            filters: Optional metadata filters
            
        Returns:
            List of search results with id, score, and payload
        """
        if not self._initialized:
            await self.initialize()
        
        threshold = score_threshold if score_threshold is not None else self._similarity_threshold
        
        # Build filter if provided
        qdrant_filter = None
        if filters:
            conditions = []
            for key, value in filters.items():
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value),
                    )
                )
            if conditions:
                qdrant_filter = models.Filter(must=conditions)
        
        try:
            client = self._get_client()
            
            logger.debug(
                "qdrant_search_started",
                collection=self._collection_name,
                limit=limit,
                threshold=threshold,
            )
            
            results = client.search(
                collection_name=self._collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=threshold,
                query_filter=qdrant_filter,
                with_payload=True,
                with_vectors=False,
            )
            
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "id": str(result.id),
                    "score": result.score,
                    "payload": result.payload,
                })
            
            logger.debug(
                "qdrant_search_completed",
                results_count=len(formatted_results),
                top_score=formatted_results[0]["score"] if formatted_results else None,
            )
            
            return formatted_results
            
        except ResponseHandlingException as e:
            logger.error("qdrant_search_error", error=str(e))
            raise QdrantException(f"Search failed: {str(e)}", e)
        except Exception as e:
            logger.error("qdrant_unexpected_error", error=str(e))
            raise QdrantException(f"Unexpected error during search: {str(e)}", e)
            
    async def keyword_search(
        self,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for exact keywords using Qdrant's payload text index (BM25).
        
        Args:
            query: User question/keywords
            limit: Maximum number of results (default 5)
            filters: Optional metadata filters
            
        Returns:
            List of search results with payload
        """
        if not self._initialized:
            await self.initialize()
            
        # Build filter condition combining metadata and full-text
        conditions = [
            models.FieldCondition(
                key="text",
                match=models.MatchText(text=query),
            )
        ]
        
        if filters:
            for key, value in filters.items():
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value),
                    )
                )
                
        qdrant_filter = models.Filter(must=conditions)
        
        try:
            client = self._get_client()
            
            # Since Qdrant scroll with full-text search returns matches, we use scroll
            points, _ = client.scroll(
                collection_name=self._collection_name,
                scroll_filter=qdrant_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            
            formatted_results = []
            for point in points:
                formatted_results.append({
                    "id": str(point.id),
                    "score": 0.8,  # Fake score for keyword matches
                    "payload": point.payload,
                })
                
            return formatted_results
            
        except Exception as e:
            logger.error("qdrant_keyword_search_error", error=str(e))
            # Gracefully degrade if index doesn't exist
            return []
    
    async def upsert(
        self,
        points: List[Dict[str, Any]],
        vectors: List[List[float]],
        payloads: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """
        Insert or update points in the collection.
        
        Args:
            points: List of point configurations (must include 'id')
            vectors: List of embedding vectors
            payloads: Optional list of metadata payloads
            
        Returns:
            Number of points upserted
        """
        if not self._initialized:
            await self.initialize()
        
        if len(vectors) == 0:
            return 0
        
        if payloads is None:
            payloads = [{}] * len(vectors)
        
        if not (len(points) == len(vectors) == len(payloads)):
            raise QdrantException(
                f"Length mismatch: points={len(points)}, vectors={len(vectors)}, payloads={len(payloads)}"
            )
        
        qdrant_points = []
        for i in range(len(vectors)):
            point_id = points[i].get("id", str(uuid.uuid4()))
            
            qdrant_points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vectors[i],
                    payload=payloads[i],
                )
            )
        
        try:
            client = self._get_client()
            
            logger.debug(
                "qdrant_upsert_started",
                collection=self._collection_name,
                points_count=len(qdrant_points),
            )
            
            result = client.upsert(
                collection_name=self._collection_name,
                points=qdrant_points,
                wait=True,
            )
            
            logger.info(
                "qdrant_upsert_completed",
                collection=self._collection_name,
                status=result.status,
            )
            
            return len(qdrant_points)
            
        except Exception as e:
            logger.error("qdrant_upsert_failed", error=str(e))
            raise QdrantException(f"Failed to upsert points: {str(e)}", e)
    
    async def delete(self, point_ids: List[str]) -> int:
        """
        Delete points by ID.
        
        Args:
            point_ids: List of point IDs to delete
            
        Returns:
            Number of points deleted
        """
        if not point_ids:
            return 0
        
        if not self._initialized:
            await self.initialize()
        
        try:
            client = self._get_client()
            
            result = client.delete(
                collection_name=self._collection_name,
                points_selector=models.PointIdsList(
                    points=point_ids,
                ),
                wait=True,
            )
            
            deleted = result.status.completed if hasattr(result, 'status') else 0
            
            logger.info(
                "qdrant_points_deleted",
                collection=self._collection_name,
                requested=len(point_ids),
                deleted=deleted,
            )
            
            return deleted
            
        except Exception as e:
            logger.error("qdrant_delete_failed", error=str(e))
            raise QdrantException(f"Failed to delete points: {str(e)}", e)
    
    async def delete_by_filter(self, filter_condition: Dict[str, Any]) -> int:
        """
        Delete points matching a filter.
        
        Args:
            filter_condition: Filter criteria (e.g., {"document_name": "Digital.docx"})
            
        Returns:
            Number of points deleted
        """
        if not filter_condition:
            return 0
        
        if not self._initialized:
            await self.initialize()
        
        conditions = []
        for key, value in filter_condition.items():
            conditions.append(
                models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=value),
                )
            )
        
        qdrant_filter = models.Filter(must=conditions)
        
        try:
            client = self._get_client()
            
            result = client.delete(
                collection_name=self._collection_name,
                points_selector=models.FilterSelector(
                    filter=qdrant_filter,
                ),
                wait=True,
            )
            
            deleted = result.status.completed if hasattr(result, 'status') else 0
            
            logger.info(
                "qdrant_points_deleted_by_filter",
                collection=self._collection_name,
                filter=filter_condition,
                deleted=deleted,
            )
            
            return deleted
            
        except Exception as e:
            logger.error("qdrant_delete_by_filter_failed", error=str(e))
            raise QdrantException(f"Failed to delete by filter: {str(e)}", e)
    
    async def get_collection_info(self) -> Dict[str, Any]:
        """
        Get collection information.
        
        Returns:
            Collection metadata
        """
        try:
            client = self._get_client()
            
            info = client.get_collection(self._collection_name)
            
            return {
                "name": self._collection_name,
                "vector_size": info.config.params.vectors.size,
                "distance": str(info.config.params.vectors.distance),
                "points_count": info.points_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "segments_count": info.segments_count,
                "status": str(info.status),
            }
            
        except UnexpectedResponse as e:
            if "Not found" in str(e):
                return {
                    "name": self._collection_name,
                    "status": "not_created",
                    "points_count": 0,
                }
            raise QdrantException(f"Failed to get collection info: {str(e)}", e)
        except Exception as e:
            raise QdrantException(f"Unexpected error: {str(e)}", e)
    
    async def count(self) -> int:
        """
        Get total point count.
        
        Returns:
            Number of points in collection
        """
        try:
            client = self._get_client()
            info = client.get_collection(self._collection_name)
            return info.points_count
        except UnexpectedResponse:
            return 0
        except Exception as e:
            logger.error("qdrant_count_failed", error=str(e))
            return 0
    
    async def is_available(self) -> bool:
        """
        Check if Qdrant is available.
        
        Returns:
            True if service is reachable
        """
        try:
            client = self._get_client()
            client.get_collections()
            return True
        except Exception:
            return False
    
    async def scroll_points(
        self,
        limit: int = 100,
        offset: Optional[str] = None,
        with_payload: bool = True,
        with_vectors: bool = False,
        filter_condition: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Scroll through all points in the collection.
        Useful for batch operations and exports.
        
        Args:
            limit: Maximum points to return
            offset: Pagination offset
            with_payload: Include payload in response
            with_vectors: Include vectors in response
            filter_condition: Optional filter
            
        Returns:
            Tuple of (points, next_offset)
        """
        if not self._initialized:
            await self.initialize()
        
        qdrant_filter = None
        if filter_condition:
            conditions = []
            for key, value in filter_condition.items():
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value),
                    )
                )
            if conditions:
                qdrant_filter = models.Filter(must=conditions)
        
        try:
            client = self._get_client()
            
            points, next_offset = client.scroll(
                collection_name=self._collection_name,
                limit=limit,
                offset=offset,
                with_payload=with_payload,
                with_vectors=with_vectors,
                scroll_filter=qdrant_filter,
            )
            
            formatted_points = []
            for point in points:
                formatted_points.append({
                    "id": str(point.id),
                    "payload": point.payload,
                    "vector": point.vector if with_vectors else None,
                })
            
            return formatted_points, next_offset
            
        except Exception as e:
            logger.error("qdrant_scroll_failed", error=str(e))
            raise QdrantException(f"Failed to scroll points: {str(e)}", e)
    
    async def create_snapshot(self) -> str:
        """
        Create a collection snapshot for backup.
        
        Returns:
            Snapshot file name
        """
        try:
            client = self._get_client()
            
            response = client.create_snapshot(
                collection_name=self._collection_name,
                wait=True,
            )
            
            logger.info(
                "qdrant_snapshot_created",
                collection=self._collection_name,
                snapshot=response.name,
            )
            
            return response.name
            
        except Exception as e:
            logger.error("qdrant_snapshot_failed", error=str(e))
            raise QdrantException(f"Failed to create snapshot: {str(e)}", e)