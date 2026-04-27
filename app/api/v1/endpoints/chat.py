"""
Chat endpoints for BARROW.AI.
"""

from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.request.chat import ChatMessageRequest, ChatFeedbackRequest
from app.models.response.chat import ChatMessageResponse, ChatFeedbackResponse
from app.repositories.session_repository import SessionRepository
from app.repositories.conversation_repository import ConversationRepository
from app.services.chat_service import ChatService
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


def get_chat_service(session: AsyncSession = Depends(get_session)) -> ChatService:
    """Dependency injection for ChatService."""
    session_repo = SessionRepository(session)
    conversation_repo = ConversationRepository(session)
    return ChatService(session_repo, conversation_repo)


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    request: Request,
    chat_request: ChatMessageRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatMessageResponse:
    """Send a message to the chatbot and receive a response."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    
    response = await chat_service.process_message(
        message=chat_request.message,
        session_id=chat_request.session_id,
        language=chat_request.language,
        channel=chat_request.channel,
        ip_address=client_ip,
        user_agent=user_agent,
        metadata=chat_request.metadata,
    )
    
    return ChatMessageResponse(**response)


@router.post("/feedback", response_model=ChatFeedbackResponse)
async def submit_feedback(
    feedback_request: ChatFeedbackRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatFeedbackResponse:
    """Submit feedback for a conversation."""
    success = await chat_service.process_feedback(
        conversation_id=feedback_request.conversation_id,
        feedback=feedback_request.feedback,
        session_id=feedback_request.session_id,
    )
    
    return ChatFeedbackResponse(
        conversation_id=feedback_request.conversation_id,
        feedback=feedback_request.feedback,
        message="Feedback recorded successfully" if success else "Failed to record feedback",
    )