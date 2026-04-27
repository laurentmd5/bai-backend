"""
Admin users management endpoints for BARROW.AI.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.api.dependencies.auth import get_current_admin
from app.services.admin_service import AdminService
from app.api.dependencies.auth import get_admin_service
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["Admin Users Management"])


@router.get("")
async def list_users(
    admin_service: AdminService = Depends(get_admin_service),
    current_admin = Depends(get_current_admin),
):
    """
    List all admin users.
    """
    logger.info("list_admin_users_requested", admin_id=current_admin.id)
    # TODO: Implement user listing
    return {"users": []}


@router.post("")
async def create_user(
    admin_service: AdminService = Depends(get_admin_service),
    current_admin = Depends(get_current_admin),
):
    """
    Create a new admin user.
    """
    logger.info("create_admin_user_requested", admin_id=current_admin.id)
    # TODO: Implement user creation
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Endpoint not yet implemented"
    )


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    admin_service: AdminService = Depends(get_admin_service),
    current_admin = Depends(get_current_admin),
):
    """
    Get details of a specific admin user.
    """
    logger.info("get_admin_user_requested", user_id=user_id, admin_id=current_admin.id)
    # TODO: Implement user retrieval
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Endpoint not yet implemented"
    )


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    admin_service: AdminService = Depends(get_admin_service),
    current_admin = Depends(get_current_admin),
):
    """
    Update an admin user.
    """
    logger.info("update_admin_user_requested", user_id=user_id, admin_id=current_admin.id)
    # TODO: Implement user update
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Endpoint not yet implemented"
    )


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    admin_service: AdminService = Depends(get_admin_service),
    current_admin = Depends(get_current_admin),
):
    """
    Delete an admin user.
    """
    logger.info("delete_admin_user_requested", user_id=user_id, admin_id=current_admin.id)
    # TODO: Implement user deletion
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Endpoint not yet implemented"
    )
