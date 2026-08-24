"""
Admin 2FA management endpoints for Company Bot.
"""

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.models.request.admin import (
    AdminEnable2FARequest,
    AdminVerify2FARequest,
    AdminDisable2FARequest,
)
from app.models.response.admin import (
    TwoFactorSetupResponse,
    BackupCodesResponse,
)
from app.services.admin_service import AdminService
from app.api.dependencies.auth import get_current_admin, get_admin_service
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/2fa", tags=["Admin 2FA"])


@router.post("/enable", response_model=TwoFactorSetupResponse)
async def enable_2fa(
    request: Request,
    data: AdminEnable2FARequest,
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> TwoFactorSetupResponse:
    """
    Initiate 2FA setup.
    
    Returns TOTP secret, QR code URI, and backup codes.
    """
    result = await admin_service.enable_2fa(
        admin_id=current_admin["id"],
        password=data.password,
    )
    
    return TwoFactorSetupResponse(**result)


@router.post("/verify")
async def verify_and_enable_2fa(
    request: Request,
    data: AdminVerify2FARequest,
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> JSONResponse:
    """
    Verify 2FA setup and enable it.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    
    await admin_service.verify_and_enable_2fa(
        admin_id=current_admin["id"],
        temp_token=data.temp_token,
        two_factor_code=data.two_factor_code,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    
    return JSONResponse(content={"message": "2FA enabled successfully"})


@router.post("/disable")
async def disable_2fa(
    request: Request,
    data: AdminDisable2FARequest,
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> JSONResponse:
    """
    Disable 2FA.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    
    await admin_service.disable_2fa(
        admin_id=current_admin["id"],
        password=data.password,
        two_factor_code=data.two_factor_code,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    
    return JSONResponse(content={"message": "2FA disabled successfully"})


@router.post("/backup-codes/regenerate", response_model=BackupCodesResponse)
async def regenerate_backup_codes(
    request: Request,
    data: AdminEnable2FARequest,
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> BackupCodesResponse:
    """
    Regenerate backup codes.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    
    codes = await admin_service.regenerate_backup_codes(
        admin_id=current_admin["id"],
        password=data.password,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    
    return BackupCodesResponse(
        backup_codes=codes,
        message="Save these codes in a secure place. Each code can be used once."
    )
