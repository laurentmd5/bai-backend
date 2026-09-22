"""
Unit tests for QueryTransformer fast-path bypass optimization.
Verifies that self-contained queries skip the 1.5s-2.5s LLM rewriting step.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.chat_service import ChatService


def test_should_bypass_query_transformation_rules():
    """Verify the static rule evaluator for bypassing query transformation."""
    # 1. Self-contained questions WITHOUT history -> BYPASS
    assert ChatService._should_bypass_query_transformation(
        "Quels sont vos services d'hébergement ?", has_history=False
    ) is True
    assert ChatService._should_bypass_query_transformation(
        "Offres cloud", has_history=False
    ) is True

    # 2. Self-contained rich questions WITH history -> BYPASS
    assert ChatService._should_bypass_query_transformation(
        "Où sont situés vos bureaux à Dakar ?", has_history=True
    ) is True
    assert ChatService._should_bypass_query_transformation(
        "Comment contacter le support technique informatique ?", has_history=True
    ) is True

    # 3. Anaphoric or incomplete questions WITH history -> DO NOT BYPASS (need context)
    assert ChatService._should_bypass_query_transformation(
        "Et pour le second ?", has_history=True
    ) is False
    assert ChatService._should_bypass_query_transformation(
        "Pourquoi cela ?", has_history=True
    ) is False
    assert ChatService._should_bypass_query_transformation(
        "Combien ça coûte ?", has_history=True
    ) is False
    assert ChatService._should_bypass_query_transformation(
        "Oui", has_history=True
    ) is False
    assert ChatService._should_bypass_query_transformation(
        "D'accord merci", has_history=True
    ) is False

    # 4. Ultra-short empty or single-word queries -> DO NOT BYPASS
    assert ChatService._should_bypass_query_transformation(
        "", has_history=False
    ) is False
    assert ChatService._should_bypass_query_transformation(
        "Quoi", has_history=False
    ) is False


@pytest.mark.asyncio
async def test_process_message_bypasses_query_transformer_on_rich_query():
    """Verify process_message executes RAG directly without calling QueryTransformer."""
    mock_session_repo = MagicMock()
    mock_session = MagicMock()
    mock_session.id = "11111111-1111-1111-1111-111111111111"
    mock_session_repo.get_or_create_session = AsyncMock(return_value=mock_session)
    mock_session_repo.touch_session = AsyncMock()

    mock_conv_repo = MagicMock()
    mock_conv_repo.get_recent_by_session = AsyncMock(return_value=[])
    mock_conv_repo.create_conversation = AsyncMock()

    mock_rag = MagicMock()
    mock_rag.retrieve_and_build_context = AsyncMock(return_value=(
        "<context_knowledge_base>NETSYSTEME Cloud</context_knowledge_base>",
        [{"document": "doc1", "score": 0.85, "text": "NETSYSTEME propose du cloud", "chunk_index": 1}],
        0.85
    ))

    mock_llm = MagicMock()
    mock_llm.generate_with_retry = AsyncMock(return_value="Nous proposons des solutions de cloud managé.")
    mock_llm.get_model_name = MagicMock(return_value="gemini-2.5-flash-lite")

    chat_service = ChatService(
        session_repository=mock_session_repo,
        conversation_repository=mock_conv_repo,
        rag_service=mock_rag,
        llm_provider=mock_llm,
    )

    # Spy on QueryTransformer
    chat_service._query_transformer.transform_query = AsyncMock()

    with patch("app.core.database.get_session_context") as mock_ctx:
        mock_db = AsyncMock()
        mock_ctx.return_value.__aenter__.return_value = mock_db
        mock_ctx.return_value.__aexit__.return_value = None

        with patch("app.repositories.session_repository.SessionRepository", return_value=mock_session_repo), \
             patch("app.repositories.conversation_repository.ConversationRepository", return_value=mock_conv_repo):

            response = await chat_service.process_message(
                message="Quels sont les services d'infrastructure cloud proposés ?",
                channel="web"
            )

            # QueryTransformer MUST NOT be called for this self-contained query!
            chat_service._query_transformer.transform_query.assert_not_called()
            # RAG MUST be called directly with the user query
            mock_rag.retrieve_and_build_context.assert_awaited_once()
            assert "Nous proposons" in response["message"]


@pytest.mark.asyncio
async def test_process_message_calls_query_transformer_when_anaphoric():
    """Verify process_message calls QueryTransformer when query depends on conversation history."""
    mock_session_repo = MagicMock()
    mock_session = MagicMock()
    mock_session.id = "22222222-2222-2222-2222-222222222222"
    mock_session_repo.get_or_create_session = AsyncMock(return_value=mock_session)
    mock_session_repo.touch_session = AsyncMock()

    # Create mock history
    past_conv = MagicMock()
    past_conv.user_message = "Parlez-moi de vos serveurs dédiés."
    past_conv.bot_response = "Nous offrons des serveurs Linux et Windows."

    mock_conv_repo = MagicMock()
    mock_conv_repo.get_recent_by_session = AsyncMock(return_value=[past_conv])
    mock_conv_repo.create_conversation = AsyncMock()

    mock_rag = MagicMock()
    mock_rag.retrieve_and_build_context = AsyncMock(return_value=(
        "<context_knowledge_base>Prix serveurs</context_knowledge_base>",
        [{"document": "doc1", "score": 0.82, "text": "Prix à partir de 100€", "chunk_index": 1}],
        0.82
    ))

    mock_llm = MagicMock()
    mock_llm.generate_with_retry = AsyncMock(return_value="Le prix dépend de la configuration.")
    mock_llm.get_model_name = MagicMock(return_value="gemini-2.5-flash-lite")

    chat_service = ChatService(
        session_repository=mock_session_repo,
        conversation_repository=mock_conv_repo,
        rag_service=mock_rag,
        llm_provider=mock_llm,
    )

    chat_service._query_transformer.transform_query = AsyncMock(return_value={
        "detected_language": "fr",
        "is_casual_conversation": False,
        "optimized_search_query": "prix des serveurs dédiés",
    })

    with patch("app.core.database.get_session_context") as mock_ctx:
        mock_db = AsyncMock()
        mock_ctx.return_value.__aenter__.return_value = mock_db
        mock_ctx.return_value.__aexit__.return_value = None

        with patch("app.repositories.session_repository.SessionRepository", return_value=mock_session_repo), \
             patch("app.repositories.conversation_repository.ConversationRepository", return_value=mock_conv_repo):

            response = await chat_service.process_message(
                message="Et combien cela coûte ?",
                channel="web"
            )

            # QueryTransformer MUST be called because of anaphora ("Et combien...")
            chat_service._query_transformer.transform_query.assert_awaited_once()
            mock_rag.retrieve_and_build_context.assert_awaited_once()
            assert "prix" in response["message"]
