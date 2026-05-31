"""Admin health check endpoint for BARROW.AI.

Monitors the health of all services: PostgreSQL, Redis, Qdrant.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Dict, Any

from app.api.dependencies.auth import get_current_admin
from app.core.database import get_session
from app.core.logging import get_logger
from app.core.config import settings

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["Admin Health"])


@router.get("", response_model=Dict[str, Any])
async def health_check(
    current_admin: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    Health check endpoint for admin service.
    
    Verifies:
    - PostgreSQL connectivity
    - Redis availability (if configured)
    - Qdrant availability (if configured)
    
    Returns:
    - status: "healthy" | "degraded" | "unhealthy"
    - timestamp: ISO datetime when check was performed
    - services: dict with individual service statuses
    
    Status Code:
    - 200: All services healthy
    - 503: One or more services unhealthy
    """
    
    results = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {}
    }
    
    # ✓ Check PostgreSQL
    try:
        # Simple query to verify database connection
        result = await session.execute("SELECT 1")
        await session.commit()
        results["services"]["postgresql"] = {
            "status": "healthy",
            "message": "Database connection successful"
        }
        logger.debug("PostgreSQL health check: OK")
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {str(e)}")
        results["services"]["postgresql"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        results["status"] = "degraded"
    
    # ✓ Check Redis (if configured)
    if settings.REDIS_URL:
        try:
            from app.services.cache.redis_cache import cache_service
            # Test Redis connection
            await cache_service.ping()
            results["services"]["redis"] = {
                "status": "healthy",
                "message": "Cache connection successful"
            }
            logger.debug("Redis health check: OK")
        except Exception as e:
            logger.warning(f"Redis health check failed: {str(e)}")
            results["services"]["redis"] = {
                "status": "unavailable",
                "error": str(e)
            }
            # Don't fail overall status for Redis (it's optional)
    else:
        results["services"]["redis"] = {
            "status": "disabled",
            "message": "Redis not configured"
        }
    
    # ✓ Check Qdrant (if configured)
    if settings.QDRANT_URL:
        try:
            from qdrant_client import QdrantClient
            
            # Create client and check collection exists
            client = QdrantClient(url=settings.QDRANT_URL)
            # Try to get collections (simple connectivity test)
            collections = client.get_collections()
            
            results["services"]["qdrant"] = {
                "status": "healthy",
                "message": f"Qdrant available with {len(collections.collections)} collections"
            }
            logger.debug("Qdrant health check: OK")
        except Exception as e:
            logger.warning(f"Qdrant health check failed: {str(e)}")
            results["services"]["qdrant"] = {
                "status": "unavailable",
                "error": str(e)
            }
            # Don't fail overall status for Qdrant (it's optional in Phase 1)
    else:
        results["services"]["qdrant"] = {
            "status": "disabled",
            "message": "Qdrant not configured (Phase 2 feature)"
        }
    
    logger.info(
        "health_check_completed",
        admin_id=current_admin["id"],
        overall_status=results["status"]
    )
    
    # Return appropriate status code
    if results["status"] == "healthy":
        return results
    elif results["status"] == "degraded":
        # Return 503 with degraded status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=results
        )
    else:
        # Shouldn't reach here, but handle just in case
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=results
        )
