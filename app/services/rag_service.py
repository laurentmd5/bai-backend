"""
RAG (Retrieval-Augmented Generation) Service for BARROW.AI.
Orchestrates the complete RAG pipeline from embedding to context building.
"""

import uuid
import time
from typing import List, Dict, Any, Optional, Tuple
import asyncio
from datetime import datetime

from app.services.vector.qdrant_store import QdrantVectorStore
from app.services.llm.factory import get_embedding_provider
from app.services.cache.redis_cache import cache_service, CacheNamespace
from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import LowConfidenceException
from app.core.metrics import rag_retrieval_duration_seconds

logger = get_logger(__name__)


class RAGService:
    """
    Retrieval-Augmented Generation service.
    
    Handles:
    - Embedding generation with caching
    - Vector search in Qdrant
    - Context building for LLM
    - Confidence scoring
    - Document retrieval tracking
    
    NOTE: This service is instantiated once at application startup
    and stored in app.state.rag_service. All endpoints access the same
    singleton instance, ensuring the BGE embedding model is loaded only ONCE.
    """
    
    def __init__(self):
        """Initialize RAGService instance."""
        self._vector_store: Optional[QdrantVectorStore] = None
        self._embedding_provider = None
        self._similarity_threshold = settings.QDRANT_SIMILARITY_THRESHOLD
        self._top_k = settings.QDRANT_TOP_K
        self._initialized = False
        
        logger.info(f"📦 RAGService instance created: id={id(self)}")
    
    async def initialize(self) -> None:
        """
        Initialize RAG service components.
        
        Called once at application startup to:
        - Connect to Qdrant vector database
        - Load embedding model (BGE, ~8 seconds)
        - Load CrossEncoder reranker model
        
        After initialization, this instance is stored in app.state.rag_service
        and reused for all requests, preventing redundant model loads.
        """
        if self._initialized:
            logger.info(f"✅ RAGService already initialized, skipping")
            return
        
        logger.warning(f"🔥 RAGService INITIALIZING - LOADING MODELS")
        
        try:
            # Initialize vector store (Qdrant connection)
            self._vector_store = QdrantVectorStore()
            await self._vector_store.initialize()
            
            # Initialize embedding provider
            self._embedding_provider = get_embedding_provider()
            
            # Initialize Re-ranker
            try:
                from sentence_transformers import CrossEncoder
                import asyncio
                # Load in thread to not block event loop
                self._reranker = await asyncio.to_thread(
                    CrossEncoder, 
                    'cross-encoder/ms-marco-MiniLM-L-6-v2',
                    max_length=512
                )
                logger.info(f"✅ Re-ranker initialized: cross-encoder/ms-marco-MiniLM-L-6-v2")
            except ImportError:
                logger.warning(f"⚠️ sentence-transformers not found. Re-ranking disabled.")
                self._reranker = None
            except Exception as e:
                logger.error(f"❌ Failed to load Re-ranker: {str(e)}")
                self._reranker = None
            
            self._initialized = True
            logger.info(f"✅ RAGService initialization complete")
            
        except Exception as e:
            logger.error(f"❌ RAGService initialization failed: {str(e)}")
            raise
    
    def _ensure_initialized(self) -> None:
        """Verify that service is initialized."""
        if not self._initialized:
            raise RuntimeError(
                "RAGService not initialized. "
                "Ensure app.state.rag_service is set at startup."
            )
    
    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
    ) -> Tuple[List[Dict[str, Any]], float]:
        """
        Retrieve relevant document chunks for a query.
        
        Args:
            query: User question
            top_k: Number of chunks to retrieve
            score_threshold: Minimum similarity score
            filters: Optional metadata filters
            use_cache: Whether to use embedding cache
            
        Returns:
            Tuple of (retrieved chunks, top_score)
            
        Raises:
            LowConfidenceException: If no chunks meet threshold
        """
        self._ensure_initialized()
        
        k = top_k if top_k is not None else self._top_k
        threshold = score_threshold if score_threshold is not None else self._similarity_threshold
        
        # Generate embedding (with cache)
        query_vector = await self._embedding_provider.embed(query)
        
        # Search in Qdrant with timing (Dense + Sparse/Keyword)
        start_time = time.time()
        
        # Run Vector Search and Keyword Search concurrently
        import asyncio
        vector_search_task = asyncio.create_task(
            self._vector_store.search(
                query_vector=query_vector,
                limit=k,
                score_threshold=threshold,
                filters=filters,
            )
        )
        
        # Extract potential keyword for text match
        keyword_task = asyncio.create_task(
            self._vector_store.keyword_search(
                query=query,
                limit=max(3, k // 2),  # Less results from keyword search
                filters=filters,
            )
        )
        
        vector_results, keyword_results = await asyncio.gather(vector_search_task, keyword_task)
        
        duration = time.time() - start_time
        rag_retrieval_duration_seconds.observe(duration)
        
        # Combine results, removing duplicates based on document and chunk_index
        combined_results = []
        seen_chunks = set()
        
        # Prioritize Vector results
        for res in vector_results:
            payload = res.get("payload", {})
            chunk_id = (payload.get("document_name"), payload.get("chunk_index"))
            if chunk_id not in seen_chunks:
                seen_chunks.add(chunk_id)
                combined_results.append(res)
                
        # Add missing Keyword results
        for res in keyword_results:
            payload = res.get("payload", {})
            chunk_id = (payload.get("document_name"), payload.get("chunk_index"))
            if chunk_id not in seen_chunks:
                seen_chunks.add(chunk_id)
                combined_results.append(res)
        
        if not combined_results:
            logger.info(
                "rag_no_results",
                query_preview=query[:100],
                threshold=threshold,
            )
            raise LowConfidenceException(0.0, threshold)
        
        # Top score is the highest vector score
        top_score = vector_results[0]["score"] if vector_results else 0.8
        
        logger.debug(
            "rag_retrieval_completed",
            query_preview=query[:100],
            vector_chunks=len(vector_results),
            keyword_chunks=len(keyword_results),
            total_chunks_found=len(combined_results),
            top_score=top_score,
            retrieval_time_sec=round(duration, 3),
        )
        
        return combined_results, top_score
    
    async def build_context(
        self,
        retrieved_chunks: List[Dict[str, Any]],
        include_sources: bool = True,
    ) -> str:
        """
        Build a formatted context string from retrieved chunks.
        
        Args:
            retrieved_chunks: List of chunks from vector search
            include_sources: Whether to include source citations
            
        Returns:
            Formatted context string for LLM
        """
        if not retrieved_chunks:
            return ""
        
        context_parts = []
        
        for i, chunk in enumerate(retrieved_chunks):
            payload = chunk.get("payload", {})
            
            text = payload.get("text", "")
            document_name = payload.get("document_name", "Unknown")
            section = payload.get("section", "")
            
            if include_sources:
                source_info = f"[Source: {document_name}"
                if section:
                    source_info += f", {section}"
                source_info += "]"
                context_parts.append(f"{source_info}\n{text}")
            else:
                context_parts.append(text)
        
        context = "\n\n---\n\n".join(context_parts)
        
        logger.debug(
            "rag_context_built",
            chunks_count=len(retrieved_chunks),
            context_length=len(context),
        )
        
        return context
    
    async def retrieve_and_build_context(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, List[Dict[str, Any]], float]:
        """
        Complete RAG pipeline: retrieve chunks, re-rank, and build context.
        
        Args:
            query: User question
            top_k: Number of chunks
            score_threshold: Minimum score
            filters: Optional filters
            
        Returns:
            Tuple of (context_string, sources, top_confidence)
        """
        # Retrieve more chunks initially for re-ranking (e.g., 20)
        initial_k = max(top_k * 2 if top_k else self._top_k * 2, 20)
        chunks, initial_top_score = await self.retrieve(
            query=query,
            top_k=initial_k,
            score_threshold=score_threshold,
            filters=filters,
        )
        
        # Apply Cross-Encoder Re-ranking
        top_score = initial_top_score
        final_chunks = chunks
        
        if hasattr(self, '_reranker') and self._reranker:
            try:
                pairs = [[query, chunk.get("payload", {}).get("text", "")] for chunk in chunks]
                
                # CrossEncoder prediction is CPU intensive, run in thread
                import asyncio
                scores = await asyncio.to_thread(self._reranker.predict, pairs)
                
                import math
                
                # Update scores and sort
                for i, chunk in enumerate(chunks):
                    logit = float(scores[i])
                    # Apply sigmoid to normalize logit to [0, 1] for database constraint
                    chunk["rerank_score"] = 1.0 / (1.0 + math.exp(-logit))
                    
                chunks.sort(key=lambda x: x["rerank_score"], reverse=True)
                
                # Take top_k after re-ranking
                final_k = top_k if top_k else self._top_k
                final_chunks = chunks[:final_k]
                
                if final_chunks:
                    # Keep track of the top rerank score for confidence
                    top_score = final_chunks[0]["rerank_score"]
                    
            except Exception as e:
                logger.error("reranking_failed", error=str(e))
                # Fallback to original chunks
                final_k = top_k if top_k else self._top_k
                final_chunks = chunks[:final_k]
        else:
            final_k = top_k if top_k else self._top_k
            final_chunks = chunks[:final_k]
        
        context = await self.build_context(final_chunks, include_sources=True)
        
        # Format sources for response
        sources = []
        for chunk in final_chunks:
            payload = chunk.get("payload", {})
            sources.append({
                "document": payload.get("document_name", "Unknown"),
                "section": payload.get("section", ""),
                "relevance": chunk.get("rerank_score", chunk.get("score", 0.0)),
                "chunk_index": payload.get("chunk_index"),
            })
        
        return context, sources, top_score
    
    async def index_document_chunks(
        self,
        chunks: List[str],
        document_name: str,
        section: str = "",
        language: str = "en",
        batch_size: int = 20,
    ) -> int:
        """
        Index document chunks into the vector store.
        
        Args:
            chunks: List of text chunks
            document_name: Source document name
            section: Document section
            language: Document language
            batch_size: Batch size for embedding generation
            
        Returns:
            Number of chunks indexed
        """
        self._ensure_initialized()
        
        if not chunks:
            return 0
        
        total_indexed = 0
        
        # Process in batches
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            # Generate embeddings
            vectors = await self._embedding_provider.embed_batch(batch)
            
            # Prepare points and payloads
            points = []
            payloads = []
            
            for j, (chunk, vector) in enumerate(zip(batch, vectors)):
                chunk_index = i + j
                
                points.append({"id": str(uuid.uuid4())})
                payloads.append({
                    "text": chunk,
                    "document_name": document_name,
                    "section": section,
                    "language": language,
                    "chunk_index": chunk_index,
                    "total_chunks": len(chunks),
                    "indexed_at": datetime.utcnow().isoformat(),
                })
            
            # Upsert to Qdrant
            indexed = await self._vector_store.upsert(
                points=points,
                vectors=vectors,
                payloads=payloads,
            )
            
            total_indexed += indexed
            
            logger.debug(
                "rag_batch_indexed",
                document=document_name,
                batch_start=i,
                batch_size=len(batch),
                indexed=indexed,
            )
        
        logger.info(
            "rag_document_indexed",
            document=document_name,
            chunks_total=total_indexed,
        )
        
        return total_indexed
    
    async def delete_document(self, document_name: str) -> int:
        """
        Delete all chunks from a specific document.
        
        Args:
            document_name: Name of document to delete
            
        Returns:
            Number of chunks deleted
        """
        self._ensure_initialized()
        
        deleted = await self._vector_store.delete_by_filter({
            "document_name": document_name
        })
        
        logger.info(
            "rag_document_deleted",
            document=document_name,
            chunks_deleted=deleted,
        )
        
        return deleted
    
    async def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get vector store statistics.
        
        Returns:
            Collection information and stats
        """
        self._ensure_initialized()
        
        info = await self._vector_store.get_collection_info()
        
        # Get document counts
        documents = set()
        
        points, offset = await self._vector_store.scroll_points(
            limit=1000,
            with_payload=True,
            with_vectors=False,
        )
        
        for point in points:
            doc_name = point.get("payload", {}).get("document_name")
            if doc_name:
                documents.add(doc_name)
        
        return {
            **info,
            "unique_documents": len(documents),
            "documents": list(documents),
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check RAG service health.
        
        Returns:
            Health status
        """
        try:
            self._ensure_initialized()
            
            vector_store_available = await self._vector_store.is_available()
            embedding_available = await self._embedding_provider.is_available()
            
            collection_info = await self._vector_store.get_collection_info()
            
            return {
                "status": "healthy" if (vector_store_available and embedding_available) else "degraded",
                "vector_store": {
                    "available": vector_store_available,
                    "points_count": collection_info.get("points_count", 0),
                },
                "embedding_provider": {
                    "available": embedding_available,
                    "model": self._embedding_provider.get_model_name(),
                },
            }
            
        except Exception as e:
            logger.error("rag_health_check_failed", error=str(e))
            return {
                "status": "unhealthy",
                "error": str(e),
            }