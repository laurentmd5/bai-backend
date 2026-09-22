"""
Unit tests for Redis cache invalidation on knowledge base updates.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.models.domain.knowledge import DocumentStatus
from app.services.admin.knowledge_indexer import index_document_background_task


class TestKnowledgeCacheInvalidation:
    """Verify that document changes trigger RAG cache invalidation."""

    @pytest.mark.asyncio
    async def test_indexing_success_invalidates_rag_cache(self):
        """When background indexing completes successfully, invalidate_rag_cache is called."""
        doc_id = uuid4()
        chunks = ["Chunk 1 content", "Chunk 2 content"]

        mock_app = MagicMock()
        mock_rag_service = MagicMock()
        mock_rag_service.index_document_chunks = AsyncMock(return_value=2)
        mock_app.state.rag_service = mock_rag_service

        with patch("app.services.admin.knowledge_indexer._update_status", new_callable=AsyncMock) as mock_update_status:
            with patch("app.services.cache.redis_cache.cache_service.invalidate_rag_cache", new_callable=AsyncMock) as mock_invalidate:
                mock_invalidate.return_value = 5

                await index_document_background_task(
                    doc_id=doc_id,
                    chunks=chunks,
                    document_name="guide.pdf",
                    language="fr",
                    app=mock_app
                )

                # Assert status updated to ACTIVE
                mock_update_status.assert_called_once_with(doc_id, DocumentStatus.ACTIVE, chunks_count=2)
                # Assert RAG cache invalidated
                mock_invalidate.assert_called_once()
