"""
Service dependencies for BARROW.AI FastAPI endpoints.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.core.database import get_session
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.analytics_service import AnalyticsService
from app.services.chat_service import ChatService


async def get_analytics_service(
    session: AsyncSession = Depends(get_session),
) -> AnalyticsService:
    """
    Dependency to get AnalyticsService instance.
    """
    conversation_repo = ConversationRepository(session)
    session_repo = SessionRepository(session)
    knowledge_repo = KnowledgeRepository(session)
    
    return AnalyticsService(
        conversation_repository=conversation_repo,
        session_repository=session_repo,
        knowledge_repository=knowledge_repo,
    )


async def get_chat_service(
    session: AsyncSession = Depends(get_session),
) -> ChatService:
    """
    Dependency to get ChatService instance.
    """
    session_repo = SessionRepository(session)
    conversation_repo = ConversationRepository(session)
    
    return ChatService(
        session_repository=session_repo,
        conversation_repository=conversation_repo,
    )