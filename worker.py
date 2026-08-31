"""
Lightweight RabbitMQ Worker for Company Bot (Solution 3).
Delegates all heavy AI/ML processing to the backend via internal HTTP API.
Maintains an ultra-low memory footprint (~50-70 MB).
"""

import asyncio
import signal
import sys
from typing import Optional
import httpx

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.services.queue.rabbitmq_service import rabbitmq_service

logger = get_logger("worker")


async def init_services():
    """Initialize lightweight worker services (RabbitMQ queue only)."""
    setup_logging()
    
    logger.info(
        "starting_lightweight_worker",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT.value,
        backend_url=settings.BACKEND_INTERNAL_URL,
    )
    
    try:
        await rabbitmq_service.connect()
        logger.info("rabbitmq_service_connected")
    except Exception as e:
        logger.error("rabbitmq_connection_failed", error=str(e))
        raise


async def close_services():
    """Close RabbitMQ connection."""
    logger.info("shutting_down_worker")
    try:
        await rabbitmq_service.close()
    except Exception as e:
        logger.warning("error_closing_rabbitmq", error=str(e))
    logger.info("worker_shutdown_complete")


async def process_webhook_task(payload: dict, raw_body: bytes, signature: str | None):
    """
    Delegate WhatsApp webhook processing to FastAPI backend via internal HTTP endpoint.
    """
    endpoint = f"{settings.BACKEND_INTERNAL_URL.rstrip('/')}/api/v1/internal/process-whatsapp"
    headers = {
        "X-Internal-Secret": settings.INTERNAL_API_SECRET.get_secret_value(),
        "Content-Type": "application/json",
    }
    
    raw_body_str = raw_body.decode("utf-8", errors="replace") if isinstance(raw_body, bytes) else (raw_body or "")
    
    body = {
        "payload": payload,
        "raw_body": raw_body_str,
        "signature": signature,
    }
    
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(endpoint, json=body, headers=headers)
            
            if response.status_code == 200:
                logger.info("webhook_task_delegated_successfully", endpoint=endpoint)
            else:
                logger.error(
                    "webhook_task_delegation_error_response",
                    status_code=response.status_code,
                    response_preview=response.text[:200]
                )
                response.raise_for_status()

    except Exception as e:
        logger.error("webhook_task_delegation_failed", error=str(e), exc_info=True)
        raise


async def main():
    """Main worker event loop."""
    await init_services()
    
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    
    def signal_handler():
        logger.info("received_shutdown_signal")
        shutdown_event.set()
        
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows platform compatibility for signal handlers
            pass
        
    try:
        # Start consuming messages from RabbitMQ queue
        consumer_task = asyncio.create_task(
            rabbitmq_service.consume_webhook_events(process_webhook_task)
        )
        
        # Keep running until shutdown signal is received
        await shutdown_event.wait()
        
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
            
        await close_services()


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
