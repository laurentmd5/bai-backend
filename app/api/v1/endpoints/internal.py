"""
Internal inter-service endpoints for Company Bot.
Used by background workers to delegate heavy RAG/LLM/audio processing to the backend.
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger
from app.core.database import get_session_context
from app.services.whatsapp_service import WhatsAppService
from app.services.chat_service import ChatService
from app.repositories.session_repository import SessionRepository
from app.repositories.conversation_repository import ConversationRepository
from app.services.llm.factory import get_llm_provider

logger = get_logger("internal_api")

router = APIRouter(tags=["Internal"])


class InternalWhatsAppTaskRequest(BaseModel):
    """Payload sent by lightweight worker to delegate WhatsApp processing."""
    payload: Dict[str, Any] = Field(..., description="Meta WhatsApp webhook event payload")
    raw_body: Optional[str] = Field(default="", description="Raw request body string")
    signature: Optional[str] = Field(default=None, description="X-Hub-Signature-256 header")


@router.post("/process-whatsapp")
async def process_internal_whatsapp_task(
    request: Request,
    body: InternalWhatsAppTaskRequest
) -> JSONResponse:
    """
    Internal endpoint called by lightweight RabbitMQ workers.
    Processes WhatsApp webhooks using the backend's singleton RAG and ML providers.
    """
    # Verify internal secret token
    provided_secret = request.headers.get("X-Internal-Secret")
    expected_secret = settings.INTERNAL_API_SECRET.get_secret_value()
    
    if not provided_secret or provided_secret != expected_secret:
        logger.warning("unauthorized_internal_request_rejected")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized internal service call"
        )

    rag_service = getattr(request.app.state, "rag_service", None)
    if not rag_service:
        logger.error("internal_process_failed_rag_not_ready")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backend RAG service not ready"
        )

    try:
        raw_bytes = body.raw_body.encode("utf-8") if body.raw_body else b""
        
        async with get_session_context() as db:
            session_repo = SessionRepository(db)
            conv_repo = ConversationRepository(db)
            chat_service = ChatService(
                session_repo,
                conv_repo,
                rag_service=rag_service,
                llm_provider=get_llm_provider(),
            )
            whatsapp_service = WhatsAppService(chat_service, session_repo)
            
            result = await whatsapp_service.process_webhook(
                payload=body.payload,
                raw_body=raw_bytes,
                signature=body.signature,
            )

        logger.info("internal_whatsapp_task_completed", status=result.get("status"))
        return JSONResponse(content={"status": "success", "result": result}, status_code=200)

    except Exception as e:
        logger.error("internal_whatsapp_task_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal processing failed: {str(e)}"
        )
