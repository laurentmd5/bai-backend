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
