"""
Unit tests for CrossEncoder RAG optimization.
Verifies candidate pool restriction and adaptive high-confidence bypass.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.rag_service import RAGService


@pytest.fixture
def rag_service():
    """Create a RAGService instance with mocked vector store and embeddings."""
    with patch("app.services.rag_service.settings") as mock_settings:
        mock_settings.QDRANT_SIMILARITY_THRESHOLD = 0.20
        mock_settings.QDRANT_TOP_K = 5
        mock_settings.RAG_ENABLE_RERANKER = True
        mock_settings.RAG_RERANK_TOP_K = 8
        mock_settings.RAG_RERANK_BYPASS_THRESHOLD = 0.82
        
        service = RAGService()
        service._initialized = True
        service._vector_store = MagicMock()
        service._embedding_provider = MagicMock()
        service._reranker = MagicMock()
        return service


@pytest.mark.asyncio
async def test_rerank_bypassed_when_confidence_is_high(rag_service):
    """Verify that CrossEncoder prediction is bypassed when initial top score >= 0.82."""
    mock_chunks = [
        {"payload": {"text": f"Chunk {i}", "document_name": "doc1", "chunk_index": i}, "score": 0.88 - (i * 0.05)}
        for i in range(12)
    ]
    
    # Mock retrieve returning high score (0.88 >= 0.82)
    rag_service.retrieve = AsyncMock(return_value=(mock_chunks, 0.88))
    
    context, sources, top_score = await rag_service.retrieve_and_build_context(
        query="Comment configurer le VPN ?",
        top_k=5
    )
    
    # Reranker MUST NOT be called!
    rag_service._reranker.predict.assert_not_called()
    assert top_score == 0.88
    assert len(sources) == 5


@pytest.mark.asyncio
async def test_rerank_executed_on_limited_pool_when_confidence_moderate(rag_service):
    """Verify that CrossEncoder is called ONLY on candidate pool (max 8) when score < 0.82."""
    mock_chunks = [
        {"payload": {"text": f"Chunk {i}", "document_name": "doc1", "chunk_index": i}, "score": 0.70 - (i * 0.02)}
        for i in range(15)
    ]
    
    # Mock retrieve returning moderate score (0.70 < 0.82)
    rag_service.retrieve = AsyncMock(return_value=(mock_chunks, 0.70))
    
    # Return fake logits for the 8 pairs
    # Note: candidate pool size is 8
    fake_logits = [2.0, 1.5, 0.5, -0.5, 3.0, 0.0, -1.0, 0.2]
    rag_service._reranker.predict = MagicMock(return_value=fake_logits)
    
    with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
        mock_to_thread.side_effect = lambda fn, pairs: rag_service._reranker.predict(pairs)
        
        context, sources, top_score = await rag_service.retrieve_and_build_context(
            query="Problème de connexion",
            top_k=4
        )
        
        # Verify predict was called with exactly 8 pairs (not all 15!)
        mock_to_thread.assert_awaited_once()
        args = mock_to_thread.call_args[0]
        passed_pairs = args[1]
        assert len(passed_pairs) == 8
        assert len(sources) == 4
        # Chunk with logit 3.0 (index 4) should be ranked first
        assert sources[0]["chunk_index"] == 4


@pytest.mark.asyncio
async def test_rerank_disabled_via_settings(rag_service):
    """Verify that when RAG_ENABLE_RERANKER is False, reranking is skipped."""
    mock_chunks = [
        {"payload": {"text": f"Chunk {i}", "document_name": "doc1", "chunk_index": i}, "score": 0.65}
        for i in range(10)
    ]
    rag_service.retrieve = AsyncMock(return_value=(mock_chunks, 0.65))
    
    with patch("app.services.rag_service.settings") as mock_settings:
        mock_settings.RAG_ENABLE_RERANKER = False
        mock_settings.RAG_RERANK_BYPASS_THRESHOLD = 0.82
        mock_settings.RAG_RERANK_TOP_K = 8
        
        context, sources, top_score = await rag_service.retrieve_and_build_context(
            query="Test sans reranker",
            top_k=3
        )
        
        rag_service._reranker.predict.assert_not_called()
        assert len(sources) == 3
        assert top_score == 0.65
