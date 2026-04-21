"""
WhatsApp webhook endpoints for BARROW.AI.
Handles incoming webhooks from Meta WhatsApp Cloud API.
"""

from fastapi import APIRouter, Request, Query, HTTPException, status, BackgroundTasks
from fastapi.responses import PlainTextResponse, JSONResponse

from app.services.whatsapp_service import WhatsAppService
from app.core.database import get_session
from app.repositories.session_repository import SessionRepository
from app.services.chat_service import ChatService
from app.repositories.conversation_repository import ConversationRepository
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


async def get_whatsapp_service() -> WhatsAppService:
    """
    Dependency to get WhatsApp service instance.
    """
    async with get_session() as session:
        session_repo = SessionRepository(session)
        conversation_repo = ConversationRepository(session)
        chat_service = ChatService(session_repo, conversation_repo)
        return WhatsAppService(chat_service, session_repo)


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
    service = await get_whatsapp_service()
    
    verified, challenge = service.verify_webhook(
        mode=hub_mode,
        challenge=hub_challenge,
        verify_token=hub_verify_token,
    )
    
    if not verified:
        logger.warning("whatsapp_webhook_verification_failed")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verification failed",
        )
    
    return PlainTextResponse(content=challenge)


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """
    Receive incoming WhatsApp webhook.
    
    Processes messages, status updates, and other events from WhatsApp.
    Returns 200 OK immediately to acknowledge receipt, then processes asynchronously.
    """
    # Get signature header for validation
    signature = request.headers.get("X-Hub-Signature-256")
    
    # Read raw body for signature validation
    raw_body = await request.body()
    
    # Parse JSON payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error("whatsapp_webhook_parse_error", error=str(e))
        return JSONResponse(
            content={"status": "error", "reason": "invalid_json"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    
    # Initialize service
    service = await get_whatsapp_service()
    
    # Process asynchronously
    background_tasks.add_task(
        service.process_webhook,
        payload=payload,
        raw_body=raw_body,
        signature=signature,
    )
    
    # Always return 200 OK to acknowledge receipt
    return JSONResponse(
        content={"status": "received"},
        status_code=status.HTTP_200_OK,
    )


@router.get("/health")
async def health_check() -> JSONResponse:
    """
    Check WhatsApp service health.
    """
    service = await get_whatsapp_service()
    health = await service.health_check()
    
    status_code = status.HTTP_200_OK
    if health.get("status") == "unhealthy":
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(content=health, status_code=status_code)


@router.get("/profile")
async def get_business_profile() -> JSONResponse:
    """
    Get WhatsApp Business Profile information.
    """
    service = await get_whatsapp_service()
    profile = await service.get_business_profile()
    return JSONResponse(content=profile)


@router.get("/opt-outs")
async def get_opt_outs() -> JSONResponse:
    """
    Get list of opted-out phone numbers (admin only).
    """
    service = await get_whatsapp_service()
    opt_outs = await service.get_opt_out_list()
    
    return JSONResponse(
        content={
            "total": len(opt_outs),
            "phone_numbers": [f"{p[:4]}...{p[-4:]}" for p in opt_outs],  # Masked
        }
    )