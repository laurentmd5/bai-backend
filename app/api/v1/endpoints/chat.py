"""
Chat endpoints for BARROW.AI.
"""

from fastapi import APIRouter, Request, HTTPException, status

from app.models.request.chat import ChatMessageRequest, ChatFeedbackRequest
from app.models.response.chat import ChatMessageResponse, ChatFeedbackResponse
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    request: Request,
    chat_request: ChatMessageRequest,
) -> ChatMessageResponse:
    """
    Send a chat message and get AI response.
    """
    # FIX: Use singleton service from app.state instead of creating new instance
    chat_service = request.app.state.chat_service
    if not chat_service:
        logger.error("chat_service_not_initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat service not available",
        )

    try:
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
    except Exception as e:
        logger.error("chat_message_processing_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process chat message",
        )


@router.post("/feedback", response_model=ChatFeedbackResponse)
async def submit_feedback(
    request: Request,
    feedback_request: ChatFeedbackRequest,
) -> ChatFeedbackResponse:
    """
    Submit feedback for a chat message.
    """
    # FIX: Use singleton service from app.state instead of creating new instance
    chat_service = request.app.state.chat_service
    if not chat_service:
        logger.error("chat_service_not_initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat service not available",
        )

    try:
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
    except Exception as e:
        logger.error("chat_feedback_processing_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process feedback",
        )