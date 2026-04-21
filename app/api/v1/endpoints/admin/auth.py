"""
Admin authentication endpoints for BARROW.AI.
"""

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.models.request.admin import (
    AdminLoginRequest,
    AdminLogin2FARequest,
    AdminRefreshTokenRequest,
    AdminChangePasswordRequest,
)
from app.models.response.admin import (
    TokenResponse,
    AdminLoginResponse,
    AdminUserResponse,
)
from app.services.admin_service import AdminService
from app.api.dependencies.auth import get_current_admin, get_admin_service
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Admin Authentication"])


@router.post("/login", response_model=AdminLoginResponse)
async def login(
    request: Request,
    login_data: AdminLoginRequest,
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminLoginResponse:
    """
    Admin login - first step.
    
    Returns tokens if 2FA is not enabled, or session_token if 2FA is required.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    
    result = await admin_service.login(
        email=login_data.email,
        password=login_data.password,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    
    return AdminLoginResponse(**result)


@router.post("/verify-2fa", response_model=TokenResponse)
async def verify_2fa(
    request: Request,
    data: AdminLogin2FARequest,
    admin_service: AdminService = Depends(get_admin_service),
) -> TokenResponse:
    """
    Verify 2FA code and complete login.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    
    result = await admin_service.verify_2fa(
        session_token=data.session_token,
        two_factor_code=data.two_factor_code,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    
    return TokenResponse(**result["tokens"])


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    data: AdminRefreshTokenRequest,
    admin_service: AdminService = Depends(get_admin_service),
) -> TokenResponse:
    """
    Refresh access token using refresh token.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    
    result = await admin_service.refresh_token(
        refresh_token=data.refresh_token,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    
    return TokenResponse(**result)


@router.post("/logout")
async def logout(
    request: Request,
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> JSONResponse:
    """
    Logout and invalidate session.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    
    await admin_service.logout(
        admin_id=current_admin["id"],
        session_id=current_admin["session_id"],
        ip_address=client_ip,
        user_agent=user_agent,
    )
    
    return JSONResponse(content={"message": "Logged out successfully"})


@router.get("/me", response_model=AdminUserResponse)
async def get_current_user(
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> AdminUserResponse:
    """
    Get current authenticated admin user.
    """
    admin = await admin_service.get_admin(current_admin["id"])
    return AdminUserResponse(**admin)


@router.post("/change-password")
async def change_password(
    request: Request,
    data: AdminChangePasswordRequest,
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> JSONResponse:
    """
    Change admin password.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    
    await admin_service.change_password(
        admin_id=current_admin["id"],
        current_password=data.current_password,
        new_password=data.new_password,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    
    return JSONResponse(content={"message": "Password changed successfully"})