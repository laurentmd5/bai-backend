"""
Unit tests for Conversation History Memory & Chronological Order.
Verifies that conversation history is retrieved in chronological order (oldest to newest)
and injected properly into the LLM context.
"""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.models.domain.conversation import Conversation
from app.repositories.conversation_repository import ConversationRepository
from app.core.company_config import company


class TestConversationMemoryOrdering:
    """Test suite for conversation history ordering and retrieval."""

    @pytest.mark.asyncio
    async def test_get_recent_by_session_returns_chronological_order(self):
        """
        Verify that get_recent_by_session selects the most recent N items
        and returns them sorted chronologically (oldest to newest).
        """
        session_id = uuid.uuid4()
        now = datetime.utcnow()

        # Create mock conversations from oldest to newest
        conv1 = Conversation(
            id=uuid.uuid4(),
            session_id=session_id,
            user_message="Msg 1 (oldest)",
            bot_response="Resp 1",
            channel="whatsapp",
            created_at=now - timedelta(minutes=10)
        )
        conv2 = Conversation(
            id=uuid.uuid4(),
            session_id=session_id,
            user_message="Msg 2",
            bot_response="Resp 2",
            channel="whatsapp",
            created_at=now - timedelta(minutes=5)
        )
        conv3 = Conversation(
            id=uuid.uuid4(),
            session_id=session_id,
            user_message="Msg 3 (newest)",
            bot_response="Resp 3",
            channel="whatsapp",
            created_at=now - timedelta(minutes=1)
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        # Simulated SQL query ordered by created_at DESC -> [conv3, conv2, conv1]
        mock_result.scalars.return_value.all.return_value = [conv3, conv2, conv1]
        mock_db.execute.return_value = mock_result

        repo = ConversationRepository(session=mock_db)
        recent = await repo.get_recent_by_session(session_id=session_id, limit=3)

        # Must return in chronological order: conv1, conv2, conv3
        assert len(recent) == 3
        assert recent[0].user_message == "Msg 1 (oldest)"
        assert recent[1].user_message == "Msg 2"
        assert recent[2].user_message == "Msg 3 (newest)"


class TestPromptMemoryRules:
    """Verify company prompt rules for conversational memory."""

    def test_company_prompt_has_anti_repetition_rules(self):
        """Prompt must instruct bot not to re-introduce itself if history exists."""
        prompt_fr = company.get_prompt(language="fr")
        assert "ANTI-RÉPÉTITION" in prompt_fr
        assert "NE TE RE-PRÉSENTE JAMAIS" in prompt_fr
        assert "{history}" in prompt_fr

    def test_company_prompt_has_recruitment_specific_conclusion(self):
        """Recruitment inquiries must not force commercial sales quotes."""
        prompt_fr = company.get_prompt(language="fr")
        assert "NE PROPOSE JAMAIS DE DEVIS COMMERCIAL" in prompt_fr
        assert "adiarraa@gmail.com" in prompt_fr
