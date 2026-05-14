"""
Main FastAPI application for BARROW.AI.
Entry point for the entire backend service.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.database import init_database, close_database, check_database_health, async_session_factory
from app.core.redis_client import init_redis, close_redis, check_redis_health
from app.services.llm.factory import get_llm_provider, get_embedding_provider, close_llm_providers
from app.services.vector.qdrant_store import QdrantVectorStore
from app.services.rag_service import RAGService
from app.services.cache.redis_cache import cache_service
from app.core.metrics import metrics_endpoint

from app.middleware import (
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    RequestLoggerMiddleware,
    ErrorHandlerMiddleware,
    MetricsMiddleware,
    setup_cors,
)

from app.api.v1.router import api_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    
    Args:
        app: FastAPI application
        
    Yields:
        None
    """
    # =========================================================================
    # STARTUP
    # =========================================================================
    logger.info(
        "starting_application",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT.value,
    )
    
    # Initialize logging
    setup_logging()
    
    # Initialize database
    try:
        await init_database()
        logger.info("database_initialized")
    except Exception as e:
        logger.error("database_initialization_failed", error=str(e))
        raise
    
    # Initialize Redis
    try:
        await init_redis()
        logger.info("redis_initialized")
    except Exception as e:
        logger.error("redis_initialization_failed", error=str(e))
        # Continue without Redis (degraded mode)
    
    # Initialize LLM providers
    try:
        llm = get_llm_provider()
        embedding = get_embedding_provider()
        
        llm_available = await llm.is_available()
        embedding_available = await embedding.is_available()
        
        logger.info(
            "llm_providers_initialized",
            llm_provider=llm.get_provider_name(),
            llm_available=llm_available,
            embedding_available=embedding_available,
        )
    except Exception as e:
        logger.error("llm_initialization_failed", error=str(e))
    
    # Initialize RAG service (shared singleton)
    rag_service = RAGService()
    await rag_service.initialize()
    logger.info("rag_service_initialized")
    
    # Initialize chat and WhatsApp services (shared)
    from app.services.chat_service import ChatService
    from app.services.whatsapp_service import WhatsAppService
    from app.repositories.session_repository import SessionRepository
    from app.repositories.conversation_repository import ConversationRepository
    
    # ⭐ CREATE A SINGLE SHARED SESSION for all repositories
    shared_session = await async_session_factory()
    
    # Create repositories with the SAME shared session
    session_repo = SessionRepository(shared_session)
    conversation_repo = ConversationRepository(shared_session)
    
    # SINGLE ChatService instance
    chat_service = ChatService(session_repo, conversation_repo)
    chat_service._rag_service = rag_service
    logger.info("chat_service_initialized")
    
    # WhatsApp uses the SAME ChatService
    whatsapp_service = WhatsAppService(chat_service, session_repo)
    logger.info("whatsapp_service_initialized")
    
    logger.info("application_startup_complete")
    
    # Store singletons in app state for access by endpoints
    app.state.chat_service = chat_service
    app.state.whatsapp_service = whatsapp_service
    app.state.rag_service = rag_service
    app.state.db_session = shared_session
    
    yield
    
    # =========================================================================
    # SHUTDOWN
    # =========================================================================
    logger.info("shutting_down_application")
    
    # Close shared database session
    try:
        await app.state.db_session.close()
        logger.info("shared_db_session_closed")
    except Exception as e:
        logger.error("shared_db_session_close_error", error=str(e))
    
    # Close LLM providers
    try:
        await close_llm_providers()
        logger.info("llm_providers_closed")
    except Exception as e:
        logger.error("llm_shutdown_error", error=str(e))
    
    # Close Redis
    try:
        await close_redis()
        logger.info("redis_closed")
    except Exception as e:
        logger.error("redis_shutdown_error", error=str(e))
    
    # Close database
    try:
        await close_database()
        logger.info("database_closed")
    except Exception as e:
        logger.error("database_shutdown_error", error=str(e))
    
    logger.info("application_shutdown_complete")
     
def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI application
    """
    # Create FastAPI app
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Official AI-powered campaign platform for President Adama Barrow and the NPP of The Gambia.",
        docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
        redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
        openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan,
    )
    
    # Setup CORS
    setup_cors(app)
    
    # Add middleware (order matters - added in reverse execution order!)
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(RequestLoggerMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(MetricsMiddleware)  # Collect HTTP metrics for Prometheus
    
    # Include API router
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    
    # Custom OpenAPI schema
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        
        openapi_schema = get_openapi(
            title=settings.APP_NAME,
            version=settings.APP_VERSION,
            description="BARROW.AI - Official campaign intelligence platform for President Adama Barrow and the NPP.",
            routes=app.routes,
        )
        
        # Add security schemes
        openapi_schema["components"]["securitySchemes"] = {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Enter JWT access token",
            }
        }
        
        # Add tags
        openapi_schema["tags"] = [
            {"name": "Chat", "description": "Public chat endpoints"},
            {"name": "WhatsApp", "description": "WhatsApp webhook endpoints"},
            {"name": "Admin Authentication", "description": "Admin login and session management"},
            {"name": "Admin 2FA", "description": "Two-factor authentication management"},
            {"name": "Admin Analytics", "description": "Analytics and reporting endpoints"},
            {"name": "Admin Conversations", "description": "Conversation management"},
            {"name": "Admin Knowledge", "description": "Knowledge base management"},
            {"name": "Admin Users", "description": "User management"},
            {"name": "Health", "description": "Health check endpoints"},
        ]
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    
    app.openapi = custom_openapi
    
    # Health check endpoint
    @app.get("/health", tags=["Health"])
    async def health_check() -> JSONResponse:
        """
        Comprehensive health check endpoint.
        Returns status of all dependent services.
        """
        health_status = {
            "status": "healthy",
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT.value,
            "timestamp": None,  # Will be set
            "services": {},
        }
        
        from datetime import datetime
        health_status["timestamp"] = datetime.utcnow().isoformat()
        
        # Check database
        try:
            db_health = await check_database_health()
            health_status["services"]["database"] = db_health
            if db_health.get("status") == "unhealthy":
                health_status["status"] = "degraded"
        except Exception as e:
            health_status["services"]["database"] = {"status": "unhealthy", "error": str(e)}
            health_status["status"] = "degraded"
        
        # Check Redis
        try:
            redis_health = await check_redis_health()
            health_status["services"]["redis"] = redis_health
            if redis_health.get("status") == "unhealthy":
                health_status["status"] = "degraded"
        except Exception as e:
            health_status["services"]["redis"] = {"status": "unhealthy", "error": str(e)}
            health_status["status"] = "degraded"
        
        # Check LLM
        try:
            llm = get_llm_provider()
            llm_available = await llm.is_available()
            health_status["services"]["llm"] = {
                "status": "healthy" if llm_available else "unhealthy",
                "provider": llm.get_provider_name(),
                "model": llm.get_model_name(),
            }
            if not llm_available:
                health_status["status"] = "degraded"
        except Exception as e:
            health_status["services"]["llm"] = {"status": "unhealthy", "error": str(e)}
            health_status["status"] = "degraded"
        
        # Check Qdrant
        try:
            qdrant = QdrantVectorStore()
            await qdrant.initialize()
            qdrant_available = await qdrant.is_available()
            collection_info = await qdrant.get_collection_info()
            health_status["services"]["qdrant"] = {
                "status": "healthy" if qdrant_available else "unhealthy",
                "points_count": collection_info.get("points_count", 0),
            }
            if not qdrant_available:
                health_status["status"] = "degraded"
        except Exception as e:
            health_status["services"]["qdrant"] = {"status": "unhealthy", "error": str(e)}
            health_status["status"] = "degraded"
        
        # Check cache
        try:
            cache_stats = await cache_service.get_cache_stats()
            health_status["services"]["cache"] = {
                "status": "healthy",
                "hit_rate": cache_stats.get("hit_rate", 0),
                "used_memory": cache_stats.get("used_memory_human", "0"),
            }
        except Exception as e:
            health_status["services"]["cache"] = {"status": "unhealthy", "error": str(e)}
            health_status["status"] = "degraded"
        
        status_code = 200 if health_status["status"] == "healthy" else 503
        
        return JSONResponse(content=health_status, status_code=status_code)
    
    @app.get("/health/ready", tags=["Health"])
    async def readiness_check() -> JSONResponse:
        """Kubernetes-style readiness probe."""
        try:
            db_health = await check_database_health()
            redis_health = await check_redis_health()
            
            if db_health.get("status") == "healthy" and redis_health.get("status") == "healthy":
                return JSONResponse(content={"status": "ready"}, status_code=200)
            else:
                return JSONResponse(content={"status": "not_ready"}, status_code=503)
        except Exception:
            return JSONResponse(content={"status": "not_ready"}, status_code=503)
    
    @app.get("/health/live", tags=["Health"])
    async def liveness_check() -> JSONResponse:
        """Kubernetes-style liveness probe."""
        return JSONResponse(content={"status": "alive"}, status_code=200)
    
    # Metrics endpoint (Prometheus)
    if settings.PROMETHEUS_ENABLED:
        @app.get("/metrics", tags=["Monitoring"])
        async def metrics():
            """Prometheus metrics endpoint for scraping."""
            return metrics_endpoint()
    
    # Protected docs in production
    if settings.ENVIRONMENT == "production":
        @app.get("/docs", include_in_schema=False)
        async def get_docs():
            return get_swagger_ui_html(
                openapi_url="/openapi.json",
                title=f"{settings.APP_NAME} - API Documentation",
            )
        
        @app.get("/redoc", include_in_schema=False)
        async def get_redoc():
            return get_redoc_html(
                openapi_url="/openapi.json",
                title=f"{settings.APP_NAME} - API Documentation",
            )
    
    return app


# Create application instance
app = create_app()


# Run with: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --loop uvloop
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        workers=1,  # ⭐ FORCE SINGLE WORKER to avoid multiple instances of BGE model
        loop="uvloop",
        reload=settings.DEBUG,
    )