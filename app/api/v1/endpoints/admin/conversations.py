"""
Admin conversations management endpoints for Company Bot.
Complete endpoints for viewing, filtering, and managing user conversations.
"""

from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_admin
from app.api.dependencies.services import get_analytics_service
from app.core.database import get_session
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.session_repository import SessionRepository
from app.services.analytics_service import AnalyticsService
from app.core.exceptions import NotFoundException, ValidationException
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/conversations", tags=["Admin Conversations Management"])


@router.get("", response_model=Dict[str, Any])
async def list_conversations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    channel: Optional[str] = Query(None, regex="^(web|whatsapp)$"),
    session_id: Optional[str] = Query(None),
    current_admin: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    List all conversations with pagination and filtering.
    
    **Query Parameters**:
    - `limit` (int, 1-100): Number of results (default: 50)
    - `offset` (int, ≥0): Pagination offset (default: 0)
    - `channel` (str, optional): Filter by channel (web|whatsapp)
    - `session_id` (str, optional): Filter by session UUID
    
    **Returns**:
    - 200 OK: List of conversations with total count
    - 400 Bad Request: Invalid parameters
    - 401 Unauthorized: Missing or invalid authentication
    - 500 Server Error: Database error
    
    **Example Response**:
    ```json
    {
        "conversations": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "session_id": "550e8400-e29b-41d4-a716-446655440001",
                "user_message": "What is NPP?",
                "bot_response": "NPP (National Patriotic Party) is...",
                "channel": "web",
                "confidence": 0.95,
                "feedback": 1,
                "latency_ms": 1250,
                "created_at": "2026-04-17T10:30:00Z"
            }
        ],
        "total": 1520,
        "limit": 50,
        "offset": 0
    }
    ```
    """
    try:
        logger.info(
            "list_conversations_requested",
            admin_id=current_admin.get("id"),
            limit=limit,
            offset=offset,
            filters={"channel": channel, "session_id": session_id}
        )
        
        repo = ConversationRepository(session)
        
        # Build filter query
        from sqlalchemy import select, and_
        from app.models.domain.conversation import Conversation
        
        stmt = select(Conversation).order_by(Conversation.created_at.desc())
        filters = []
        
        if channel:
            filters.append(Conversation.channel == channel)
        
        if session_id:
            try:
                session_uuid = UUID(session_id)
                filters.append(Conversation.session_id == session_uuid)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid session_id format (must be UUID)"
                )
        
        if filters:
            stmt = stmt.where(and_(*filters))
        
        stmt = stmt.offset(offset).limit(limit)
        
        result = await session.execute(stmt)
        conversations = result.scalars().all()
        
        # Get total count
        count_stmt = select(Conversation)
        if filters:
            count_stmt = count_stmt.where(and_(*filters))
        
        from sqlalchemy import func
        count_result = await session.execute(
            select(func.count()).select_from(Conversation).where(and_(*filters)) if filters else select(func.count()).select_from(Conversation)
        )
        total = count_result.scalar() or 0
        
        logger.info(
            "conversations_listed_successfully",
            admin_id=current_admin.get("id"),
            count=len(conversations),
            total=total
        )
        
        return {
            "conversations": [
                {
                    "id": str(c.id),
                    "session_id": str(c.session_id),
                    "user_message": c.user_message,
                    "bot_response": c.bot_response,
                    "channel": c.channel,
                    "confidence": c.confidence,
                    "feedback": c.feedback,
                    "latency_ms": c.latency_ms,
                    "cache_hit": c.cache_hit,
                    "fallback_triggered": c.fallback_triggered,
                    "created_at": c.created_at.isoformat(),
                }
                for c in conversations
            ],
            "total": total,
            "limit": limit,
            "offset": offset
        }
    
    except Exception as e:
        logger.error(
            "list_conversations_failed",
            admin_id=current_admin.get("id"),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list conversations"
        )


@router.get("/{conversation_id}", response_model=Dict[str, Any])
async def get_conversation(
    conversation_id: str,
    current_admin: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    Get detailed information about a specific conversation.
    
    **Path Parameters**:
    - `conversation_id` (UUID): Conversation ID
    
    **Returns**:
    - 200 OK: Complete conversation details with all metadata
    - 400 Bad Request: Invalid conversation ID format
    - 401 Unauthorized: Missing or invalid authentication
    - 404 Not Found: Conversation not found
    - 500 Server Error: Database error
    
    **Example Response**:
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "session_id": "550e8400-e29b-41d4-a716-446655440001",
        "user_message": "What is NPP?",
        "bot_response": "NPP (National Patriotic Party) is...",
        "sources": [
            {
                "document_id": "doc-uuid",
                "title": "NPP History",
                "relevance": 0.95,
                "chunk_index": 0
            }
        ],
        "confidence": 0.95,
        "feedback": 1,
        "channel": "web",
        "latency_ms": 1250,
        "cache_hit": false,
        "fallback_triggered": false,
        "llm_model": "tunedModels/askbarrow-npp-v3",
        "llm_tokens_used": 245,
        "validation_failed": false,
        "created_at": "2026-04-17T10:30:00Z"
    }
    ```
    """
    try:
        # Validate UUID
        try:
            conv_uuid = UUID(conversation_id)
        except ValueError:
            logger.warning(
                "get_conversation_invalid_id",
                admin_id=current_admin.get("id"),
                conversation_id=conversation_id
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid conversation ID format (must be UUID)"
            )
        
        logger.info(
            "get_conversation_requested",
            admin_id=current_admin.get("id"),
            conversation_id=conversation_id
        )
        
        repo = ConversationRepository(session)
        conversation = await repo.get_by_id(conv_uuid)
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation {conversation_id} not found"
            )
        
        logger.info(
            "conversation_retrieved_successfully",
            admin_id=current_admin.get("id"),
            conversation_id=conversation_id
        )
        
        return {
            "id": str(conversation.id),
            "session_id": str(conversation.session_id),
            "user_message": conversation.user_message,
            "bot_response": conversation.bot_response,
            "sources": conversation.sources or [],
            "confidence": conversation.confidence,
            "feedback": conversation.feedback,
            "channel": conversation.channel,
            "latency_ms": conversation.latency_ms,
            "cache_hit": conversation.cache_hit,
            "fallback_triggered": conversation.fallback_triggered,
            "llm_model": conversation.llm_model,
            "llm_tokens_used": conversation.llm_tokens_used,
            "validation_failed": conversation.validation_failed,
            "created_at": conversation.created_at.isoformat(),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_conversation_failed",
            admin_id=current_admin.get("id"),
            conversation_id=conversation_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversation"
        )


@router.get("/session/{session_id}", response_model=Dict[str, Any])
async def get_session_conversations(
    session_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_admin: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    Get all conversations from a specific session.
    
    **Path Parameters**:
    - `session_id` (UUID): Session ID
    
    **Query Parameters**:
    - `limit` (int, 1-500): Number of results (default: 100)
    - `offset` (int, ≥0): Pagination offset (default: 0)
    
    **Returns**:
    - 200 OK: List of conversations in the session
    - 400 Bad Request: Invalid session ID format
    - 401 Unauthorized: Missing or invalid authentication
    - 500 Server Error: Database error
    
    **Example Response**:
    ```json
    {
        "conversations": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "session_id": "550e8400-e29b-41d4-a716-446655440001",
                "user_message": "What is NPP?",
                "bot_response": "NPP is...",
                "channel": "web",
                "created_at": "2026-04-17T10:30:00Z"
            }
        ],
        "total": 3,
        "limit": 100,
        "offset": 0
    }
    ```
    """
    try:
        # Validate UUID
        try:
            session_uuid = UUID(session_id)
        except ValueError:
            logger.warning(
                "get_session_conversations_invalid_id",
                admin_id=current_admin.get("id"),
                session_id=session_id
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session ID format (must be UUID)"
            )
        
        logger.info(
            "get_session_conversations_requested",
            admin_id=current_admin.get("id"),
            session_id=session_id,
            limit=limit,
            offset=offset
        )
        
        repo = ConversationRepository(session)
        conversations = await repo.get_by_session(session_uuid, skip=offset, limit=limit)
        total = await repo.count_by_session(session_uuid)
        
        logger.info(
            "session_conversations_retrieved_successfully",
            admin_id=current_admin.get("id"),
            session_id=session_id,
            count=len(conversations),
            total=total
        )
        
        return {
            "conversations": [
                {
                    "id": str(c.id),
                    "session_id": str(c.session_id),
                    "user_message": c.user_message,
                    "bot_response": c.bot_response,
                    "channel": c.channel,
                    "confidence": c.confidence,
                    "feedback": c.feedback,
                    "latency_ms": c.latency_ms,
                    "cache_hit": c.cache_hit,
                    "created_at": c.created_at.isoformat(),
                }
                for c in conversations
            ],
            "total": total,
            "limit": limit,
            "offset": offset
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_session_conversations_failed",
            admin_id=current_admin.get("id"),
            session_id=session_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session conversations"
        )


@router.delete("/{conversation_id}", response_model=Dict[str, Any])
async def delete_conversation(
    conversation_id: str,
    current_admin: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    Delete a conversation.
    
    **Path Parameters**:
    - `conversation_id` (UUID): Conversation ID to delete
    
    **Returns**:
    - 200 OK: Conversation deleted successfully
    - 400 Bad Request: Invalid conversation ID format
    - 401 Unauthorized: Missing or invalid authentication
    - 404 Not Found: Conversation not found
    - 500 Server Error: Database error
    
    **Example Response**:
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "message": "Conversation deleted successfully",
        "deleted_at": "2026-04-17T10:35:00Z"
    }
    ```
    """
    try:
        # Validate UUID
        try:
            conv_uuid = UUID(conversation_id)
        except ValueError:
            logger.warning(
                "delete_conversation_invalid_id",
                admin_id=current_admin.get("id"),
                conversation_id=conversation_id
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid conversation ID format (must be UUID)"
            )
        
        logger.info(
            "delete_conversation_requested",
            admin_id=current_admin.get("id"),
            conversation_id=conversation_id
        )
        
        repo = ConversationRepository(session)
        
        # Check if conversation exists
        conversation = await repo.get_by_id(conv_uuid)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation {conversation_id} not found"
            )
        
        # Delete conversation
        success = await repo.delete(conv_uuid)
        
        if not success:
            raise Exception("Failed to delete conversation")
        
        await session.commit()
        
        logger.info(
            "conversation_deleted_successfully",
            admin_id=current_admin.get("id"),
            conversation_id=conversation_id
        )
        
        return {
            "id": conversation_id,
            "message": "Conversation deleted successfully",
            "deleted_at": datetime.utcnow().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "delete_conversation_failed",
            admin_id=current_admin.get("id"),
            conversation_id=conversation_id,
            error=str(e)
        )
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete conversation"
        )


