"""
Admin conversations management endpoints for BARROW.AI.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional

from app.api.dependencies.auth import get_current_admin
from app.services.admin_service import AdminService
from app.api.dependencies.auth import get_admin_service
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/conversations", tags=["Admin Conversations Management"])


@router.get("")
async def list_conversations(
    limit: int = 50,
    offset: int = 0,
    session_id: Optional[str] = None,
    admin_service: AdminService = Depends(get_admin_service),
    current_admin = Depends(get_current_admin),
):
    """
    List all conversations with optional filtering.
    """
    logger.info("list_conversations_requested", admin_id=current_admin.id, limit=limit)
    # TODO: Implement conversation listing
    return {"conversations": [], "total": 0}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    admin_service: AdminService = Depends(get_admin_service),
    current_admin = Depends(get_current_admin),
):
    """
    Get details of a specific conversation.
    """
    logger.info("get_conversation_requested", conversation_id=conversation_id, admin_id=current_admin.id)
    # TODO: Implement conversation retrieval
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Endpoint not yet implemented"
    )


@router.get("/session/{session_id}")
async def get_session_conversations(
    session_id: str,
    admin_service: AdminService = Depends(get_admin_service),
    current_admin = Depends(get_current_admin),
):
    """
    Get all conversations in a specific session.
    """
    logger.info("get_session_conversations_requested", session_id=session_id, admin_id=current_admin.id)
    # TODO: Implement session conversation retrieval
    return {"conversations": [], "total": 0}


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    admin_service: AdminService = Depends(get_admin_service),
    current_admin = Depends(get_current_admin),
):
    """
    Delete a conversation.
    """
    logger.info("delete_conversation_requested", conversation_id=conversation_id, admin_id=current_admin.id)
    # TODO: Implement conversation deletion
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Endpoint not yet implemented"
    )
