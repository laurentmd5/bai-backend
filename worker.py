import asyncio
import signal
import sys
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.database import init_database, close_database, get_session_context
from app.core.redis_client import init_redis, close_redis
from app.services.llm.factory import get_llm_provider, close_llm_providers
from app.services.rag_service import RAGService
from app.services.queue.rabbitmq_service import rabbitmq_service
from app.services.whatsapp_service import WhatsAppService
from app.services.chat_service import ChatService
from app.repositories.session_repository import SessionRepository
from app.repositories.conversation_repository import ConversationRepository

logger = get_logger("worker")

# Global reference to RAG service
rag_service: Optional[RAGService] = None

async def init_services():
    """Initialize all services needed by the worker."""
    global rag_service
    
    logger.info(
        "starting_worker",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT.value,
    )
    
    setup_logging()
    
    try:
        await init_database()
        logger.info("database_initialized")
    except Exception as e:
        logger.error("database_initialization_failed", error=str(e))
        raise
        
    try:
        await init_redis()
        logger.info("redis_initialized")
    except Exception as e:
        logger.error("redis_initialization_failed", error=str(e))
        
    try:
        llm = get_llm_provider()
        llm_available = await llm.is_available()
        logger.info("llm_initialized", available=llm_available)
    except Exception as e:
        logger.error("llm_initialization_failed", error=str(e))
        
    rag_service = RAGService()
    await rag_service.initialize()
    logger.info("rag_service_initialized")
    
    try:
        await rabbitmq_service.connect()
        logger.info("rabbitmq_service_initialized")
    except Exception as e:
        logger.error("rabbitmq_initialization_failed", error=str(e))
        raise

async def close_services():
    """Close all connections."""
    logger.info("shutting_down_worker")
    
    await rabbitmq_service.close()
    await close_llm_providers()
    await close_redis()
    await close_database()
    
    logger.info("worker_shutdown_complete")

async def process_webhook_task(payload: dict, raw_body: bytes, signature: str | None):
    """Process a single webhook event."""
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

async def main():
    """Main worker loop."""
    await init_services()
    
    # Setup graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    
    def signal_handler():
        logger.info("received_shutdown_signal")
        shutdown_event.set()
        
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
        
    try:
        # Start consuming messages
        consumer_task = asyncio.create_task(
            rabbitmq_service.consume_webhook_events(process_webhook_task)
        )
        
        # Wait until shutdown signal is received
        await shutdown_event.wait()
        
    finally:
        # Cancel the consumer task
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
