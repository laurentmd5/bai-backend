"""
Admin audit log endpoints for BARROW.AI.
Complete endpoints for viewing and managing audit logs with filtering and search.
"""

from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_admin
from app.core.database import get_session
from app.repositories.admin_repository import AdminRepository
from app.core.exceptions import NotFoundException, ValidationException
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/audit", tags=["Admin Audit Logs"])


@router.get("", response_model=Dict[str, Any])
async def list_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None),
    severity: Optional[str] = Query(None, regex="^(INFO|WARN|CRITICAL)$"),
    admin_id: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    current_admin: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    List audit logs with pagination and filtering.
    
    **Query Parameters**:
    - `limit` (int, 1-500): Number of results (default: 100)
    - `offset` (int, ≥0): Pagination offset (default: 0)
    - `action` (str, optional): Filter by action type
    - `severity` (str, optional): Filter by severity (INFO|WARN|CRITICAL)
    - `admin_id` (str, optional): Filter by admin user UUID
    - `success` (bool, optional): Filter by action success (true|false)
    
    **Returns**:
    - 200 OK: List of audit logs with total count and statistics
    - 400 Bad Request: Invalid parameters
    - 401 Unauthorized: Missing or invalid authentication
    - 500 Server Error: Database error
    
    **Example Response**:
    ```json
    {
        "logs": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "admin_id": "admin-uuid",
                "admin_email": "admin@pace.gm",
                "action": "LOGIN_SUCCESS",
                "ip_address": "192.168.1.1",
                "user_agent": "Mozilla/5.0...",
                "severity": "INFO",
                "success": true,
                "details": {
                    "method": "password",
                    "2fa_verified": true
                },
                "created_at": "2026-04-17T10:00:00Z"
            }
        ],
        "total": 245,
        "limit": 100,
        "offset": 0,
        "severity_counts": {
            "INFO": 200,
            "WARN": 40,
            "CRITICAL": 5
        }
    }
    ```
    """
    try:
        logger.info(
            "list_audit_logs_requested",
            admin_id=current_admin.get("id"),
            limit=limit,
            offset=offset,
            filters={"action": action, "severity": severity}
        )
        
        repo = AdminRepository(session)
        
        # Parse admin_id if provided
        filter_admin_id = None
        if admin_id:
            try:
                filter_admin_id = UUID(admin_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid admin_id format (must be UUID)"
                )
        
        # Get audit logs via repository
        logs, total = await repo.search_logs(
            admin_id=filter_admin_id,
            action=action,
            severity=severity,
            success=success,
            skip=offset,
            limit=limit,
        )
        
        logger.info(
            "audit_logs_listed_successfully",
            admin_id=current_admin.get("id"),
            count=len(logs),
            total=total
        )
        
        # Calculate severity counts
        severity_counts = {"INFO": 0, "WARN": 0, "CRITICAL": 0}
        for log in logs:
            sev = log.severity if hasattr(log, 'severity') else 'INFO'
            if sev in severity_counts:
                severity_counts[sev] += 1
        
        return {
            "logs": [
                {
                    "id": str(log.id) if hasattr(log, 'id') else log.get("id"),
                    "admin_id": str(log.admin_id) if hasattr(log, 'admin_id') and log.admin_id else None,
                    "admin_email": log.admin_email if hasattr(log, 'admin_email') else log.get("admin_email"),
                    "action": log.action if hasattr(log, 'action') else log.get("action"),
                    "ip_address": log.ip_address if hasattr(log, 'ip_address') else log.get("ip_address"),
                    "user_agent": log.user_agent if hasattr(log, 'user_agent') else log.get("user_agent"),
                    "severity": log.severity if hasattr(log, 'severity') else log.get("severity"),
                    "success": log.success if hasattr(log, 'success') else log.get("success"),
                    "details": log.details if hasattr(log, 'details') else log.get("details"),
                    "error_message": log.error_message if hasattr(log, 'error_message') else log.get("error_message"),
                    "created_at": log.created_at.isoformat() if hasattr(log, 'created_at') else log.get("created_at"),
                }
                for log in logs
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "severity_counts": severity_counts
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "list_audit_logs_failed",
            admin_id=current_admin.get("id"),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list audit logs"
        )


@router.get("/{log_id}", response_model=Dict[str, Any])
async def get_audit_log(
    log_id: str,
    current_admin: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    Get details of a specific audit log entry.
    
    **Path Parameters**:
    - `log_id` (UUID): Audit log ID
    
    **Returns**:
    - 200 OK: Complete audit log entry with all metadata
    - 400 Bad Request: Invalid log ID format
    - 401 Unauthorized: Missing or invalid authentication
    - 404 Not Found: Log entry not found
    - 500 Server Error: Database error
    
    **Example Response**:
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "admin_id": "admin-uuid",
        "admin_email": "admin@pace.gm",
        "action": "LOGIN_SUCCESS",
        "ip_address": "192.168.1.1",
        "user_agent": "Mozilla/5.0...",
        "severity": "INFO",
        "success": true,
        "details": {
            "method": "password",
            "2fa_verified": true
        },
        "error_message": null,
        "created_at": "2026-04-17T10:00:00Z"
    }
    ```
    """
    try:
        # Validate UUID
        try:
            log_uuid = UUID(log_id)
        except ValueError:
            logger.warning(
                "get_audit_log_invalid_id",
                admin_id=current_admin.get("id"),
                log_id=log_id
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid log ID format (must be UUID)"
            )
        
        logger.info(
            "get_audit_log_requested",
            admin_id=current_admin.get("id"),
            log_id=log_id
        )
        
        repo = AdminRepository(session)
        log = await repo.get_audit_log(log_uuid)
        
        if not log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Audit log {log_id} not found"
            )
        
        logger.info(
            "audit_log_retrieved_successfully",
            admin_id=current_admin.get("id"),
            log_id=log_id
        )
        
        return {
            "id": str(log.id) if hasattr(log, 'id') else log.get("id"),
            "admin_id": str(log.admin_id) if hasattr(log, 'admin_id') and log.admin_id else None,
            "admin_email": log.admin_email if hasattr(log, 'admin_email') else log.get("admin_email"),
            "action": log.action if hasattr(log, 'action') else log.get("action"),
            "ip_address": log.ip_address if hasattr(log, 'ip_address') else log.get("ip_address"),
            "user_agent": log.user_agent if hasattr(log, 'user_agent') else log.get("user_agent"),
            "severity": log.severity if hasattr(log, 'severity') else log.get("severity"),
            "success": log.success if hasattr(log, 'success') else log.get("success"),
            "details": log.details if hasattr(log, 'details') else log.get("details"),
            "error_message": log.error_message if hasattr(log, 'error_message') else log.get("error_message"),
            "created_at": log.created_at.isoformat() if hasattr(log, 'created_at') else log.get("created_at"),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_audit_log_failed",
            admin_id=current_admin.get("id"),
            log_id=log_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit log"
        )


@router.get("/user/{user_id}", response_model=Dict[str, Any])
async def get_user_audit_logs(
    user_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None),
    current_admin: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    Get all audit logs for a specific admin user.
    
    **Path Parameters**:
    - `user_id` (UUID): Admin user ID
    
    **Query Parameters**:
    - `limit` (int, 1-200): Number of results (default: 50)
    - `offset` (int, ≥0): Pagination offset (default: 0)
    - `action` (str, optional): Filter by action type
    
    **Returns**:
    - 200 OK: List of audit logs for the user
    - 400 Bad Request: Invalid user ID format
    - 401 Unauthorized: Missing or invalid authentication
    - 500 Server Error: Database error
    
    **Example Response**:
    ```json
    {
        "logs": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "admin_id": "user-uuid",
                "admin_email": "user@pace.gm",
                "action": "LOGIN_SUCCESS",
                "severity": "INFO",
                "success": true,
                "created_at": "2026-04-17T10:00:00Z"
            }
        ],
        "total": 42,
        "limit": 50,
        "offset": 0
    }
    ```
    """
    try:
        # Validate UUID
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            logger.warning(
                "get_user_audit_logs_invalid_id",
                admin_id=current_admin.get("id"),
                user_id=user_id
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format (must be UUID)"
            )
        
        logger.info(
            "get_user_audit_logs_requested",
            admin_id=current_admin.get("id"),
            user_id=user_id,
            limit=limit,
            offset=offset
        )
        
        repo = AdminRepository(session)
        logs, total = await repo.search_logs(
            admin_id=user_uuid,
            action=action,
            skip=offset,
            limit=limit,
        )
        
        logger.info(
            "user_audit_logs_retrieved_successfully",
            admin_id=current_admin.get("id"),
            user_id=user_id,
            count=len(logs),
            total=total
        )
        
        return {
            "logs": [
                {
                    "id": str(log.id) if hasattr(log, 'id') else log.get("id"),
                    "admin_id": str(log.admin_id) if hasattr(log, 'admin_id') and log.admin_id else None,
                    "admin_email": log.admin_email if hasattr(log, 'admin_email') else log.get("admin_email"),
                    "action": log.action if hasattr(log, 'action') else log.get("action"),
                    "severity": log.severity if hasattr(log, 'severity') else log.get("severity"),
                    "success": log.success if hasattr(log, 'success') else log.get("success"),
                    "details": log.details if hasattr(log, 'details') else log.get("details"),
                    "created_at": log.created_at.isoformat() if hasattr(log, 'created_at') else log.get("created_at"),
                }
                for log in logs
            ],
            "total": total,
            "limit": limit,
            "offset": offset
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_user_audit_logs_failed",
            admin_id=current_admin.get("id"),
            user_id=user_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user audit logs"
        )


@router.delete("/{log_id}", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
async def delete_audit_log(
    log_id: str,
    current_admin: dict = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    Delete an audit log entry (admin only).
    
    **Path Parameters**:
    - `log_id` (UUID): Audit log ID to delete
    
    **Returns**:
    - 200 OK: Audit log deleted successfully
    - 400 Bad Request: Invalid log ID format
    - 401 Unauthorized: Missing or invalid authentication
    - 403 Forbidden: Insufficient permissions
    - 404 Not Found: Log entry not found
    - 500 Server Error: Database error
    
    **Permissions**:
    - Only SUPERADMIN can delete audit logs
    
    **Example Response**:
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "message": "Audit log deleted successfully",
        "deleted_at": "2026-04-17T10:35:00Z"
    }
    ```
    """
    try:
        # Check permissions
        if current_admin.get("role") != "superadmin":
            logger.warning(
                "delete_audit_log_unauthorized",
                admin_id=current_admin.get("id"),
                role=current_admin.get("role")
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superadmin can delete audit logs"
            )
        
        # Validate UUID
        try:
            log_uuid = UUID(log_id)
        except ValueError:
            logger.warning(
                "delete_audit_log_invalid_id",
                admin_id=current_admin.get("id"),
                log_id=log_id
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid log ID format (must be UUID)"
            )
        
        logger.info(
            "delete_audit_log_requested",
            admin_id=current_admin.get("id"),
            log_id=log_id
        )
        
        repo = AdminRepository(session)
        
        # Check if log exists
        log = await repo.get_audit_log(log_uuid)
        if not log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Audit log {log_id} not found"
            )
        
        # Delete log
        success = await repo.delete_audit_log(log_uuid)
        
        if not success:
            raise Exception("Failed to delete audit log")
        
        await session.commit()
        
        logger.info(
            "audit_log_deleted_successfully",
            admin_id=current_admin.get("id"),
            log_id=log_id
        )
        
        return {
            "id": log_id,
            "message": "Audit log deleted successfully",
            "deleted_at": datetime.utcnow().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "delete_audit_log_failed",
            admin_id=current_admin.get("id"),
            log_id=log_id,
            error=str(e)
        )
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete audit log"
        )
