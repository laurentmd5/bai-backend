"""
Unit tests for the performance optimizations implemented:
1. DB Connection decoupling in ChatService
2. Global FAQ RAG Cache cross-session
3. Audio concise prompt for WhatsApp voice messages
4. In-memory LRU embedding cache in LocalEmbeddingProvider
5. Dynamic initial_k chunk candidate sizing in RAGService
6. Persistent HTTP client in worker
7. Concurrent processing in RabbitMQ consumer
"""

import pytest
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.chat_service import ChatService
from app.services.rag_service import RAGService
from app.services.llm.embedding.local_embedding import LocalEmbeddingProvider
from app.services.queue.rabbitmq_service import RabbitMQService
from worker import get_http_client, close_services


# =========================================================================
# 1. DB Connection Decoupling & Voice Prompt & Global Cache Tests
# =========================================================================

@pytest.mark.asyncio
async def test_chat_service_voice_metadata_adds_concise_spoken_instruction():
    """Verify that when metadata has is_voice=True, audio prompt instruction is added."""
    mock_session_repo = MagicMock()
    mock_session = MagicMock()
    mock_session.id = uuid.uuid4()
    mock_session.opted_out = False
    mock_session_repo.get_or_create_session = AsyncMock(return_value=mock_session)

    mock_conv_repo = MagicMock()
    mock_conv_repo.get_recent_by_session = AsyncMock(return_value=[])

    mock_rag = MagicMock()
    mock_rag.retrieve_and_build_context = AsyncMock(return_value=(
        "Contexte NETSYSTEME caméra", [{"document": "cam.pdf", "score": 0.88}], 0.88
    ))

    mock_groq = MagicMock()
    mock_groq.is_available = AsyncMock(return_value=True)
    mock_groq.generate_with_retry = AsyncMock(return_value="Nous proposons des caméras IP haute résolution.")
    mock_groq.get_model_name = MagicMock(return_value="llama-3.3-70b-versatile")

    chat_service = ChatService(
        session_repository=mock_session_repo,
        conversation_repository=mock_conv_repo,
        rag_service=mock_rag,
    )
    chat_service._groq_provider = mock_groq
    chat_service._record_conversation = AsyncMock()

    with patch("app.core.database.get_session_context") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = AsyncMock()
        mock_ctx.return_value.__aexit__.return_value = None

        with patch("app.repositories.session_repository.SessionRepository", return_value=mock_session_repo), \
             patch("app.repositories.conversation_repository.ConversationRepository", return_value=mock_conv_repo):

            res = await chat_service.process_message(
                message="Quelles caméras avez vous ?",
                channel="whatsapp",
                metadata={"is_voice": True}
            )

            assert res is not None
            mock_groq.generate_with_retry.assert_awaited_once()
            call_kwargs = mock_groq.generate_with_retry.call_args[1]
            assert "[INSTRUCTION SPÉCIALE AUDIO]" in call_kwargs["prompt"]
            assert "2 à 3 phrases" in call_kwargs["prompt"]


@pytest.mark.asyncio
async def test_global_rag_cache_hit_bypasses_rag_service():
    """Verify that a second user asking the same question gets a global FAQ cache hit."""
    mock_session_repo = MagicMock()
    mock_session = MagicMock()
    mock_session.id = uuid.uuid4()
    mock_session.opted_out = False
    mock_session_repo.get_or_create_session = AsyncMock(return_value=mock_session)

    mock_conv_repo = MagicMock()
    mock_conv_repo.get_recent_by_session = AsyncMock(return_value=[])

    mock_rag = MagicMock()
    mock_rag.retrieve_and_build_context = AsyncMock()

    chat_service = ChatService(
        session_repository=mock_session_repo,
        conversation_repository=mock_conv_repo,
        rag_service=mock_rag,
    )
    chat_service._record_conversation = AsyncMock()

    cached_faq = {
        "message": "Le protocole TCP assure un acheminement fiable et ordonné des paquets réseau.",
        "sources": [{"document": "reseau_guide.pdf"}],
        "confidence": 0.95
    }

    with patch("app.core.database.get_session_context") as mock_ctx, \
         patch("app.services.chat_service.cache_service") as mock_cache:

        mock_ctx.return_value.__aenter__.return_value = AsyncMock()
        mock_ctx.return_value.__aexit__.return_value = None

        mock_cache.get_rag_response = AsyncMock(side_effect=[None, cached_faq])

        with patch("app.repositories.session_repository.SessionRepository", return_value=mock_session_repo), \
             patch("app.repositories.conversation_repository.ConversationRepository", return_value=mock_conv_repo):

            response = await chat_service.process_message(
                message="Expliquez-moi le fonctionnement du protocole TCP",
                language="fr",
                channel="web"
            )

            assert response["cache_hit"] is True
            assert response["message"] == cached_faq["message"]
            # RAG was bypassed entirely
            mock_rag.retrieve_and_build_context.assert_not_called()


# =========================================================================
# 2. In-Memory LRU Vector Embedding Cache Tests
# =========================================================================

@pytest.mark.asyncio
async def test_local_embedding_lru_cache():
    """Verify that LocalEmbeddingProvider caches vectors and avoids recomputing."""
    provider = LocalEmbeddingProvider()
    dummy_vector = [0.1] * 1024

    with patch.object(provider, "_embed_sync", return_value=[dummy_vector]) as mock_sync:
        # First call: cache miss, computes
        v1 = await provider.embed("quelles caméras avez-vous ?")
        assert v1 == dummy_vector
        assert mock_sync.call_count == 1

        # Second call with identical text: cache hit, zero recompute
        v2 = await provider.embed("quelles caméras avez-vous ?")
        assert v2 == dummy_vector
        assert mock_sync.call_count == 1  # Unchanged!


# =========================================================================
# 3. Dynamic Candidate Chunk Pool in RAGService
# =========================================================================

@pytest.mark.asyncio
async def test_rag_service_initial_k_chunk_pool():
    """Verify initial_k is dynamically tuned to rerank_pool_size + 2 (not hardcoded to 20)."""
    rag = RAGService()
    rag.retrieve = AsyncMock(return_value=([], 0.0))

    with patch("app.core.config.settings.RAG_RERANK_TOP_K", 8):
        await rag.retrieve_and_build_context(query="test", top_k=4)
        rag.retrieve.assert_awaited_once()
        # initial_k should be max(4 * 2, 8 + 2) = 10 (not 20)
        assert rag.retrieve.call_args[1]["top_k"] == 10


# =========================================================================
# 4. Worker Persistent HTTP Client Test
# =========================================================================

@pytest.mark.asyncio
async def test_worker_get_http_client_singleton():
    """Verify worker get_http_client returns the same persistent client."""
    client1 = await get_http_client()
    client2 = await get_http_client()
    assert client1 is client2
    assert not client1.is_closed
    await close_services()
    assert client1.is_closed
