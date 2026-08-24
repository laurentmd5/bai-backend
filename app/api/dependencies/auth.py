"""
Authentication dependencies for Company Bot FastAPI endpoints.
"""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_jwt_token
from app.services.admin_service import AdminService
from app.repositories.admin_repository import AdminRepository, AuditLogRepository
from app.services.cache.redis_cache import cache_service, CacheNamespace

security = HTTPBearer(auto_error=False)


async def get_admin_service(
    session: AsyncSession = Depends(get_session),
) -> AdminService:
    """
    Dependency to get AdminService instance.
    """
    admin_repo = AdminRepository(session)
    audit_repo = AuditLogRepository(session)
    return AdminService(admin_repo, audit_repo)


async def get_current_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    admin_service: AdminService = Depends(get_admin_service),
) -> dict:
    """
    Get current authenticated admin user from JWT token.
    """
    if credentials:
        token = credentials.credentials
    else:
        # Browser navigation sends cookie, not Authorization header
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload = decode_jwt_token(token, "access")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get session ID from token
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing session",
        )
    
    # Validate session
    csrf_token = request.headers.get("X-CSRF-Token")
    session_data = await admin_service.validate_session(session_id, csrf_token)
    
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
        )
    
    # Check if token is blacklisted
    jti = payload.get("jti")
    if jti and await cache_service.is_token_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )
    
    return {
        "id": UUID(payload["sub"]),
        "email": payload["email"],
        "role": payload["role"],
        "full_name": payload.get("full_name", ""),
        "session_id": session_id,
    }


async def get_current_active_admin(
    current_admin: dict = Depends(get_current_admin),
) -> dict:
    """
    Verify that current admin is active.
    """
    # Additional checks can be added here
    return current_admin


async def require_superadmin(
    current_admin: dict = Depends(get_current_admin),
) -> dict:
    """
    Require superadmin role.
    """
    if current_admin["role"] != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin privileges required",
        )
    return current_admin


async def require_admin(
    current_admin: dict = Depends(get_current_admin),
) -> dict:
    """
    Require admin or superadmin role.
    """
    if current_admin["role"] not in ["admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_admin
