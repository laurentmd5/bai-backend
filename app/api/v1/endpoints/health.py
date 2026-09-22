"""
Health check endpoints for Company Bot.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.database import check_database_health
from app.core.redis_client import check_redis_health
from app.services.llm.factory import get_llm_provider, get_embedding_provider
from app.services.vector.qdrant_store import QdrantVectorStore

router = APIRouter(tags=["Health"])


@router.get("/database")
async def database_health() -> JSONResponse:
    """Check database health."""
    health = await check_database_health()
    status_code = 200 if health.get("status") == "healthy" else 503
    return JSONResponse(content=health, status_code=status_code)


@router.get("/redis")
async def redis_health() -> JSONResponse:
    """Check Redis health."""
    health = await check_redis_health()
    status_code = 200 if health.get("status") == "healthy" else 503
    return JSONResponse(content=health, status_code=status_code)


@router.get("/llm")
async def llm_health() -> JSONResponse:
    """Check LLM provider health."""
    try:
        llm = get_llm_provider()
        embedding = get_embedding_provider()
        
        llm_available = await llm.is_available()
        embedding_available = await embedding.is_available()
        
        health = {
            "status": "healthy" if (llm_available and embedding_available) else "degraded",
            "llm": {
                "available": llm_available,
                "provider": llm.get_provider_name(),
                "model": llm.get_model_name(),
            },
            "embedding": {
                "available": embedding_available,
                "model": embedding.get_model_name(),
                "dimension": embedding.get_dimension(),
            },
        }
        
        status_code = 200 if health["status"] == "healthy" else 503
        return JSONResponse(content=health, status_code=status_code)
        
    except Exception as e:
        return JSONResponse(
            content={"status": "unhealthy", "error": str(e)},
            status_code=503,
        )


@router.get("/qdrant")
async def qdrant_health() -> JSONResponse:
    """Check Qdrant vector store health."""
    try:
        qdrant = QdrantVectorStore()
        await qdrant.initialize()
        
        available = await qdrant.is_available()
        info = await qdrant.get_collection_info()
        
        health = {
            "status": "healthy" if available else "unhealthy",
            "available": available,
            "collection": info,
        }
        
        status_code = 200 if available else 503
        return JSONResponse(content=health, status_code=status_code)
        
    except Exception as e:
        return JSONResponse(
            content={"status": "unhealthy", "error": str(e)},
            status_code=503,
        )
