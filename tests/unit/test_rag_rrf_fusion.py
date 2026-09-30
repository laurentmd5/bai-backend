"""
Unit tests for Reciprocal Rank Fusion (RRF) algorithm in RAG pipeline.
"""

import pytest
from app.services.rag_service import reciprocal_rank_fusion


class TestRRFFusion:
    """Tests for reciprocal_rank_fusion."""

    def test_boosts_chunks_present_in_both_searches(self):
        """A chunk found in both vector and keyword search must rank higher than single-match chunks."""
        # Chunk A in both (rank 1 in vector, rank 1 in keyword)
        chunk_a = {"id": "1", "score": 0.9, "payload": {"document_name": "solar_catalog.pdf", "chunk_index": 0, "text": "Solar"}}
        # Chunk B only in vector (rank 2)
        chunk_b = {"id": "2", "score": 0.85, "payload": {"document_name": "network.pdf", "chunk_index": 1, "text": "Network"}}
        # Chunk C only in keyword (rank 2)
        chunk_c = {"id": "3", "score": 0.8, "payload": {"document_name": "voip.pdf", "chunk_index": 2, "text": "VoIP"}}

        vector_results = [chunk_a, chunk_b]
        keyword_results = [chunk_a, chunk_c]

        fused = reciprocal_rank_fusion(vector_results, keyword_results, k_rrf=60)

        assert len(fused) == 3
        # Chunk A must be #1 with highest RRF score: 1/(60+1) + 1/(60+1) = 2/61 ~ 0.03278
        assert fused[0]["payload"]["document_name"] == "solar_catalog.pdf"
        assert fused[0]["rrf_score"] == pytest.approx((1.0 / 61.0) + (1.0 / 61.0))
        # Chunk B and Chunk C should have 1/62 ~ 0.01612
        assert fused[1]["rrf_score"] == pytest.approx(1.0 / 62.0)
        assert fused[2]["rrf_score"] == pytest.approx(1.0 / 62.0)

    def test_rank_ordering_preservation(self):
        """Rank 1 in vector search gets a higher score than rank 2 in vector search."""
        chunk_1 = {"id": "1", "score": 0.95, "payload": {"document_name": "doc1.pdf", "chunk_index": 0, "text": "T1"}}
        chunk_2 = {"id": "2", "score": 0.80, "payload": {"document_name": "doc2.pdf", "chunk_index": 0, "text": "T2"}}

        fused = reciprocal_rank_fusion(vector_results=[chunk_1, chunk_2], keyword_results=[], k_rrf=60)

        assert len(fused) == 2
        assert fused[0]["payload"]["document_name"] == "doc1.pdf"
        assert fused[0]["rrf_score"] > fused[1]["rrf_score"]

    def test_handles_empty_inputs_gracefully(self):
        """Empty lists should return empty results without throwing."""
        assert reciprocal_rank_fusion([], []) == []
        
        chunk = {"id": "1", "score": 0.9, "payload": {"document_name": "doc.pdf", "chunk_index": 0, "text": "Text"}}
        fused = reciprocal_rank_fusion([chunk], [])
        assert len(fused) == 1
        assert fused[0]["rrf_score"] == pytest.approx(1.0 / 61.0)


class TestRAGAdaptiveThreshold:
    """Tests for adaptive thresholding and keyword synergy in RAGService."""

    @pytest.mark.asyncio
    async def test_keyword_match_rescues_low_vector_similarity(self, monkeypatch):
        """Exact keyword match ensures high confidence (>= 0.75) even with modest vector similarity."""
        from unittest.mock import AsyncMock, MagicMock
        from app.services.rag_service import RAGService
        from app.core.exceptions import LowConfidenceException

        service = RAGService()
        service._initialized = True
        service._similarity_threshold = 0.50

        # Mock embedding provider
        service._embedding_provider = MagicMock()
        service._embedding_provider.embed = AsyncMock(return_value=[0.1] * 768)

        # Mock vector store
        mock_vector_store = MagicMock()
        # Vector score below strict threshold (0.42 < 0.50)
        vector_chunk = {
            "id": "vec-1",
            "score": 0.42,
            "payload": {"document_name": "odoo_erp.pdf", "chunk_index": 0, "text": "Guide Odoo ERP"}
        }
        # Keyword match found via BM25
        keyword_chunk = {
            "id": "kw-1",
            "score": 0.80,
            "payload": {"document_name": "odoo_erp.pdf", "chunk_index": 0, "text": "Guide Odoo ERP"}
        }

        mock_vector_store.search = AsyncMock(return_value=[vector_chunk])
        mock_vector_store.keyword_search = AsyncMock(return_value=[keyword_chunk])
        service._vector_store = mock_vector_store

        # Should NOT raise LowConfidenceException because keyword matched
        results, top_score = await service.retrieve(query="odoo erp", score_threshold=0.50)

        assert len(results) > 0
        assert top_score >= 0.75  # Boosted adaptively

    @pytest.mark.asyncio
    async def test_low_confidence_raised_when_no_keyword_and_vector_below_threshold(self):
        """Without keyword match and vector score below threshold, LowConfidenceException is raised."""
        from unittest.mock import AsyncMock, MagicMock
        from app.services.rag_service import RAGService
        from app.core.exceptions import LowConfidenceException

        service = RAGService()
        service._initialized = True
        service._similarity_threshold = 0.50

        service._embedding_provider = MagicMock()
        service._embedding_provider.embed = AsyncMock(return_value=[0.1] * 768)

        mock_vector_store = MagicMock()
        # Low vector score and no keyword match
        vector_chunk = {
            "id": "vec-1",
            "score": 0.35,
            "payload": {"document_name": "doc.pdf", "chunk_index": 0, "text": "Unrelated"}
        }
        mock_vector_store.search = AsyncMock(return_value=[vector_chunk])
        mock_vector_store.keyword_search = AsyncMock(return_value=[])
        service._vector_store = mock_vector_store

        with pytest.raises(LowConfidenceException) as exc_info:
            await service.retrieve(query="quelque chose d'inconnu", score_threshold=0.50)

        assert exc_info.value.details["score"] == 0.35
        assert exc_info.value.details["threshold"] == 0.50
