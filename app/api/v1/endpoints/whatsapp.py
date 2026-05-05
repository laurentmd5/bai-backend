"""
WhatsApp webhook endpoints for BARROW.AI.
Handles incoming webhooks from Meta WhatsApp Cloud API.
"""

from fastapi import APIRouter, Request, Query, HTTPException, status, BackgroundTasks
from fastapi.responses import PlainTextResponse, JSONResponse

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["WhatsApp"])


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
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """
    Receive incoming WhatsApp webhook.
    Always returns 200 OK — Meta will retry if we return non-200.
    """
    signature = request.headers.get("X-Hub-Signature-256")
    raw_body = await request.body()

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

    # FIX: Use singleton service from app.state instead of creating new instance
    whatsapp_service = request.app.state.whatsapp_service
    if not whatsapp_service:
        logger.error("whatsapp_service_not_initialized")
        return JSONResponse(content={"status": "error"}, status_code=500)

    background_tasks.add_task(
        whatsapp_service.process_webhook,
        payload=payload,
        raw_body=raw_body,
        signature=signature,
    )

    return JSONResponse(content={"status": "received"}, status_code=200)


@router.get("/health")
async def health_check(request: Request) -> JSONResponse:
    """
    Check WhatsApp service health.
    """
    whatsapp_service = request.app.state.whatsapp_service
    if not whatsapp_service:
        return JSONResponse(
            content={"status": "unhealthy", "reason": "service_not_initialized"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    health = await whatsapp_service.health_check()

    status_code = status.HTTP_200_OK
    if health.get("status") == "unhealthy":
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(content=health, status_code=status_code)


@router.get("/profile")
async def get_business_profile(request: Request) -> JSONResponse:
    """
    Get WhatsApp Business Profile information.
    """
    whatsapp_service = request.app.state.whatsapp_service
    if not whatsapp_service:
        return JSONResponse(
            content={"status": "error", "reason": "service_not_initialized"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    profile = await whatsapp_service.get_business_profile()
    return JSONResponse(content=profile)


@router.get("/opt-outs")
async def get_opt_outs(request: Request) -> JSONResponse:
    """
    Get list of opted-out phone numbers (admin only).
    """
    whatsapp_service = request.app.state.whatsapp_service
    if not whatsapp_service:
        return JSONResponse(
            content={"status": "error", "reason": "service_not_initialized"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    opt_outs = await whatsapp_service.get_opt_out_list()
    
    return JSONResponse(
        content={
            "total": len(opt_outs),
            "phone_numbers": [f"{p[:4]}...{p[-4:]}" for p in opt_outs],
        }
    )