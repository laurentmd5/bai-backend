"""
WhatsApp webhook endpoints for Company Bot.
Handles incoming webhooks from Meta WhatsApp Cloud API.
"""

from fastapi import APIRouter, Request, Query, HTTPException, status, BackgroundTasks, Depends
from fastapi.responses import PlainTextResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.database import get_session, get_session_context
from app.services.whatsapp_service import WhatsAppService
from app.services.chat_service import ChatService
from app.repositories.session_repository import SessionRepository
from app.repositories.conversation_repository import ConversationRepository
from app.services.llm.factory import get_llm_provider
from app.services.queue.rabbitmq_service import rabbitmq_service

logger = get_logger(__name__)

router = APIRouter(tags=["WhatsApp"])

def get_whatsapp_service(request: Request, db: AsyncSession = Depends(get_session)) -> WhatsAppService:
    rag_service = request.app.state.rag_service
    if not rag_service:
        logger.error("rag_service_not_initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG service not available",
        )
    session_repo = SessionRepository(db)
    chat_service = ChatService(
        session_repo,
        ConversationRepository(db),
        rag_service=rag_service,
        llm_provider=get_llm_provider(),
    )
    return WhatsAppService(chat_service, session_repo)

async def process_webhook_task(payload: dict, raw_body: bytes, signature: str, app_state: object):
    """Background task to process webhook with its own database session."""
    rag_service = getattr(app_state, "rag_service", None)
    if not rag_service:
        logger.error("process_webhook_task_failed: rag_service_missing")
        return

    try:
        async with get_session_context() as db:
            session_repo = SessionRepository(db)
            chat_service = ChatService(
                session_repo,
                ConversationRepository(db),
                rag_service=rag_service,
                llm_provider=get_llm_provider(),
            )
            whatsapp_service = WhatsAppService(chat_service, session_repo)
            await whatsapp_service.process_webhook(
                payload=payload,
                raw_body=raw_body,
                signature=signature,
            )
    except Exception as e:
        logger.error("process_webhook_task_unhandled_error", error=str(e), exc_info=True)


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
) -> PlainTextResponse:
    """
    Verify WhatsApp webhook during initial setup.

    This endpoint is called by Meta when configuring the webhook URL.
    It must return the hub.challenge value to confirm ownership.
    """
    # Extract the actual value from SecretStr
    expected_token = settings.WHATSAPP_VERIFY_TOKEN.get_secret_value()

    # Simple verification without database dependency for faster response
    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        logger.info("webhook_verified", challenge=hub_challenge)
        return PlainTextResponse(content=hub_challenge)

    logger.warning("webhook_verification_failed", token_provided=hub_verify_token[:10] if hub_verify_token else None)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Verification failed",
    )


@router.post("/webhook")
async def receive_webhook(
    request: Request,
) -> JSONResponse:
    """
    Receive incoming WhatsApp webhook.
    Always returns 200 OK — Meta will retry if we return non-200.
    """
    signature = request.headers.get("X-Hub-Signature-256")
    try:
        raw_body = await request.body()
    except Exception as e:
        logger.warning("whatsapp_webhook_body_read_failed", error=str(e))
        return JSONResponse(content={"status": "ignored"}, status_code=200)

    # Parse JSON — if this fails it's malformed, not a Meta message
    try:
        payload = await request.json()
    except Exception as e:
        logger.error("whatsapp_webhook_invalid_json", error=str(e))
        # Still return 200 — malformed payloads should not trigger Meta retries
        return JSONResponse(content={"status": "ignored"}, status_code=200)


    # Validate payload structure — log but never block with non-200
    try:
        from app.models.request.whatsapp import WhatsAppWebhookRequest
        validated = WhatsAppWebhookRequest(**payload)
    except Exception as e:
        logger.warning(
            "whatsapp_webhook_validation_warning",
            error=str(e),
            # Log partial payload for debugging without exposing PII
            object_type=payload.get("object"),
            entry_count=len(payload.get("entry", [])),
        )
        # Return 200 — Meta must receive 200 or it will retry repeatedly
        return JSONResponse(content={"status": "received"}, status_code=200)

    # Publish to RabbitMQ queue
    await rabbitmq_service.publish_webhook_event(
        payload=payload,
        raw_body=raw_body,
        signature=signature,
    )

    return JSONResponse(content={"status": "received"}, status_code=200)


@router.get("/health")
async def health_check(
    request: Request,
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service)
) -> JSONResponse:
    """
    Check WhatsApp service health.
    """

    health = await whatsapp_service.health_check()

    status_code = status.HTTP_200_OK
    if health.get("status") == "unhealthy":
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(content=health, status_code=status_code)


@router.get("/profile")
async def get_business_profile(
    request: Request,
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service)
) -> JSONResponse:
    """
    Get WhatsApp Business Profile information.
    """
    profile = await whatsapp_service.get_business_profile()
    return JSONResponse(content=profile)


@router.get("/opt-outs")
async def get_opt_outs(
    request: Request,
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service)
) -> JSONResponse:
    """
    Get list of opted-out phone numbers (admin only).
    """
    opt_outs = await whatsapp_service.get_opt_out_list()
    
    return JSONResponse(
        content={
            "total": len(opt_outs),
            "phone_numbers": [f"{p[:4]}...{p[-4:]}" for p in opt_outs],
        }
    )
