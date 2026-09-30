"""
Unit tests for ChatService fallback responses.
Verifies that low confidence, irrelevant sources, opt-out, and hostile content
trigger their appropriate responses without raising AttributeError.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.chat_service import ChatService
from app.core.exceptions import LowConfidenceException, HostileContentException


def test_fallback_responses_attributes_exist_and_valid():
    """Verify FALLBACK_RESPONSES, STOP_RESPONSE, HOSTILE_CONTENT_RESPONSE are defined on ChatService."""
    assert hasattr(ChatService, "FALLBACK_RESPONSES")
    assert "fr" in ChatService.FALLBACK_RESPONSES
    assert "en" in ChatService.FALLBACK_RESPONSES
    assert len(ChatService.FALLBACK_RESPONSES["fr"]) > 20
    assert len(ChatService.FALLBACK_RESPONSES["en"]) > 20

    assert hasattr(ChatService, "STOP_RESPONSE")
    assert "fr" in ChatService.STOP_RESPONSE
    assert "en" in ChatService.STOP_RESPONSE

    assert hasattr(ChatService, "HOSTILE_CONTENT_RESPONSE")
    assert "fr" in ChatService.HOSTILE_CONTENT_RESPONSE
    assert "en" in ChatService.HOSTILE_CONTENT_RESPONSE


def test_get_fallback_message_returns_localized_response():
    """Verify _get_fallback_message returns company-specific message in the requested language."""
    mock_session_repo = MagicMock()
    mock_conv_repo = MagicMock()
    mock_rag = MagicMock()

    service = ChatService(
        session_repository=mock_session_repo,
        conversation_repository=mock_conv_repo,
        rag_service=mock_rag,
    )

    fr_msg = service._get_fallback_message("fr")
    en_msg = service._get_fallback_message("en")
    unknown_msg = service._get_fallback_message("de")

    assert "contact@netsys-info.com" in fr_msg or "base de connaissances" in fr_msg
    assert "contact@netsys-info.com" in en_msg or "knowledge base" in en_msg
    # Unknown language falls back to French default
    assert fr_msg == unknown_msg


@pytest.mark.asyncio
async def test_low_confidence_triggers_fallback_without_attribute_error():
    """Verify LowConfidenceException returns fallback message cleanly without crashing."""
    mock_session_repo = MagicMock()
    mock_session = MagicMock()
    mock_session.id = "33333333-3333-3333-3333-333333333333"
    mock_session.opted_out = False
    mock_session_repo.get_or_create_session = AsyncMock(return_value=mock_session)
    mock_session_repo.touch_session = AsyncMock()

    mock_conv_repo = MagicMock()
    mock_conv_repo.get_recent_by_session = AsyncMock(return_value=[])
    mock_conv_repo.create_conversation = AsyncMock()

    mock_rag = MagicMock()
    mock_rag.retrieve_and_build_context = AsyncMock(
        side_effect=LowConfidenceException(score=0.42, threshold=0.70)
    )

    mock_llm = MagicMock()
    mock_llm.get_model_name = MagicMock(return_value="gemini-2.5-flash-lite")

    chat_service = ChatService(
        session_repository=mock_session_repo,
        conversation_repository=mock_conv_repo,
        rag_service=mock_rag,
        llm_provider=mock_llm,
    )

    with patch("app.core.database.get_session_context") as mock_ctx:
        mock_db = AsyncMock()
        mock_ctx.return_value.__aenter__.return_value = mock_db
        mock_ctx.return_value.__aexit__.return_value = None

        with patch("app.repositories.session_repository.SessionRepository", return_value=mock_session_repo), \
             patch("app.repositories.conversation_repository.ConversationRepository", return_value=mock_conv_repo):

            response = await chat_service.process_message(
                message="Avez-vous des caméras de surveillance thermique industrielle ?",
                channel="whatsapp"
            )

            assert response["fallback_triggered"] is True
            assert "contact@netsys-info.com" in response["message"] or "base de connaissances" in response["message"]
            assert response.get("error") is None
            mock_conv_repo.create_conversation.assert_awaited_once()


@pytest.mark.asyncio
async def test_irrelevant_sources_triggers_fallback_without_attribute_error():
    """Verify irrelevant_sources_filtered returns fallback cleanly without crashing."""
    mock_session_repo = MagicMock()
    mock_session = MagicMock()
    mock_session.id = "44444444-4444-4444-4444-444444444444"
    mock_session.opted_out = False
    mock_session_repo.get_or_create_session = AsyncMock(return_value=mock_session)
    mock_session_repo.touch_session = AsyncMock()

    mock_conv_repo = MagicMock()
    mock_conv_repo.get_recent_by_session = AsyncMock(return_value=[])
    mock_conv_repo.create_conversation = AsyncMock()

    # RAG returns sources that will be judged irrelevant by _is_response_relevant
    mock_rag = MagicMock()
    mock_rag.retrieve_and_build_context = AsyncMock(return_value=(
        "<context_knowledge_base>NETSYSTEME Cloud</context_knowledge_base>",
        [{"document": "doc1", "score": 0.85, "text": "NETSYSTEME propose du cloud", "chunk_index": 1}],
        0.85
    ))

    mock_llm = MagicMock()
    mock_llm.get_model_name = MagicMock(return_value="gemini-2.5-flash-lite")

    chat_service = ChatService(
        session_repository=mock_session_repo,
        conversation_repository=mock_conv_repo,
        rag_service=mock_rag,
        llm_provider=mock_llm,
    )

    # Force _is_response_relevant to False (as happened in prod with sources_theme_mismatch)
    chat_service._is_response_relevant = MagicMock(return_value=False)

    with patch("app.core.database.get_session_context") as mock_ctx:
        mock_db = AsyncMock()
        mock_ctx.return_value.__aenter__.return_value = mock_db
        mock_ctx.return_value.__aexit__.return_value = None

        with patch("app.repositories.session_repository.SessionRepository", return_value=mock_session_repo), \
             patch("app.repositories.conversation_repository.ConversationRepository", return_value=mock_conv_repo):

            response = await chat_service.process_message(
                message="Bonjour, je vous ai besoin de la caméra de surveil",
                channel="whatsapp"
            )

            assert response["fallback_triggered"] is True
            assert response["irrelevant_sources"] is True
            assert "contact@netsys-info.com" in response["message"] or "base de connaissances" in response["message"]
            assert response.get("error") is None
            mock_conv_repo.create_conversation.assert_awaited_once()


@pytest.mark.asyncio
async def test_opted_out_session_returns_stop_response_without_attribute_error():
    """Verify opted-out WhatsApp user gets stop response cleanly without AttributeError."""
    mock_session_repo = MagicMock()
    mock_session = MagicMock()
    mock_session.id = "55555555-5555-5555-5555-555555555555"
    mock_session.opted_out = True
    mock_session_repo.get_or_create_session = AsyncMock(return_value=mock_session)

    chat_service = ChatService(
        session_repository=mock_session_repo,
        conversation_repository=MagicMock(),
        rag_service=MagicMock(),
    )

    with patch("app.core.database.get_session_context") as mock_ctx:
        mock_db = AsyncMock()
        mock_ctx.return_value.__aenter__.return_value = mock_db
        mock_ctx.return_value.__aexit__.return_value = None

        with patch("app.repositories.session_repository.SessionRepository", return_value=mock_session_repo):
            response = await chat_service.process_message(
                message="Hello",
                channel="whatsapp"
            )

            assert response["opted_out"] is True
            assert "désabonné" in response["message"] or "unsubscribed" in response["message"]
