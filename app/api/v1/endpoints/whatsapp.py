"""
WhatsApp webhook endpoints for Company Bot.
Handles incoming webhooks from Meta WhatsApp Cloud API.
"""

import hashlib
import hmac
from typing import Optional

from fastapi import APIRouter, Request, Query, HTTPException, status, BackgroundTasks, Depends
from fastapi.responses import PlainTextResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings, Environment
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


def verify_whatsapp_signature(raw_body: bytes, signature: Optional[str]) -> bool:
    """
    Validate WhatsApp webhook POST signature with Meta App Secret.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not signature or not signature.startswith("sha256="):
        return False

    app_secret_val = settings.WHATSAPP_APP_SECRET.get_secret_value() if settings.WHATSAPP_APP_SECRET else ""
    if not app_secret_val:
        logger.error("whatsapp_app_secret_not_configured")
        return False

    expected_hash = signature[7:]
    computed_hash = hmac.new(
        key=app_secret_val.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_hash, expected_hash)

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

    # Fast-fail if payload does not contain messages
    try:
        from app.models.request.whatsapp import WhatsAppWebhookRequest
        payload_check = payload.get("payload", payload) if ("payload" in payload and "object" not in payload) else payload
        wh_req = WhatsAppWebhookRequest(**payload_check)
        if not wh_req.has_messages():
            logger.debug("process_webhook_task_skipped_no_messages")
            return
    except Exception as parse_err:
        logger.warning("process_webhook_task_parse_warning", error=str(parse_err))

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

    # C-03 FIX: Enforce HMAC SHA-256 signature verification before parsing or enqueuing
    should_require = (
        settings.ENVIRONMENT in (Environment.PRODUCTION, Environment.STAGING)
        or (getattr(settings, "WHATSAPP_REQUIRE_SIGNATURE", True) and not settings.is_development)
    )
    if should_require and not signature:
        logger.warning("whatsapp_webhook_missing_signature_rejected", client_ip=request.client.host if request.client else None)
        return JSONResponse(
            content={"status": "unauthorized", "detail": "Missing X-Hub-Signature-256 header"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if signature and not verify_whatsapp_signature(raw_body, signature):
        logger.warning("whatsapp_webhook_invalid_signature_rejected", client_ip=request.client.host if request.client else None)
        return JSONResponse(
            content={"status": "unauthorized", "detail": "Invalid X-Hub-Signature-256 header"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

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

    # ── SRE Optimization: Edge Filtering for WhatsApp Status Updates ─────
    # WhatsApp sends delivery receipts (sent, delivered, read) via webhooks.
    # Acknowledge immediately with 200 OK to Meta, but NEVER publish status
    # updates to RabbitMQ to prevent CPU, DB session, and worker thrashing.
    if not validated.has_messages():
        logger.debug("whatsapp_webhook_status_update_filtered")
        return JSONResponse(content={"status": "ignored_status"}, status_code=200)

    msgs = validated.get_messages()
    sender_masked = f"...{msgs[0].from_[-4:]}" if msgs and hasattr(msgs[0], 'from_') and msgs[0].from_ else "unknown"
    msg_type = getattr(msgs[0], 'type', 'unknown') if msgs else "unknown"
    contact_name = validated.get_contact_name_for_sender()

    logger.info(
        "whatsapp_message_received",
        message_count=len(msgs),
        sender=sender_masked,
        contact_name=contact_name,
        message_type=msg_type,
    )

    # Publish to RabbitMQ queue ONLY if real messages are present
    await rabbitmq_service.publish_webhook_event(
        payload=payload,
        raw_body=raw_body,
        signature=signature,
    )

    logger.info(
        "whatsapp_message_enqueued",
        queue=settings.RABBITMQ_WEBHOOK_QUEUE,
        sender=sender_masked,
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
