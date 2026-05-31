"""
Admin users management endpoints for BARROW.AI.
Complete CRUD operations for admin user management with role-based access control.
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from pydantic import ValidationError

from app.api.dependencies.auth import get_current_admin, require_admin, get_admin_service
from app.services.admin_service import AdminService
from app.models.response.admin import AdminUserResponse
from app.models.request.admin import AdminCreateUserRequest, AdminUpdateUserRequest
from app.core.exceptions import (
    ValidationException,
    AuthorizationException,
    NotFoundException,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["Admin Users Management"])


@router.get("", response_model=Dict[str, Any])
async def list_users(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    role: Optional[str] = Query(None, regex="^(superadmin|admin|auditor|viewer)$"),
    is_active: Optional[bool] = Query(None),
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> Dict[str, Any]:
    """
    List admin users with pagination and filtering.
    
    **Query Parameters**:
    - `limit` (int, 1-100): Number of results (default: 50)
    - `offset` (int, ≥0): Pagination offset (default: 0)
    - `role` (str, optional): Filter by role (superadmin|admin|auditor|viewer)
    - `is_active` (bool, optional): Filter by active status (true|false)
    
    **Returns**: 
    - 200 OK: List of admin users with total count
    - 401 Unauthorized: Missing or invalid authentication
    - 500 Server Error: Database or service error
    
    **Example Response**:
    ```json
    {
        "users": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "admin@pace.gm",
                "full_name": "PACE Administrator",
                "role": "superadmin",
                "is_active": true,
                "two_factor_enabled": true,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-04-17T10:00:00Z"
            }
        ],
        "total": 5,
        "limit": 50,
        "offset": 0
    }
    ```
    """
    try:
        logger.info(
            "list_users_requested",
            admin_id=current_admin.get("id"),
            limit=limit,
            offset=offset,
            filters={"role": role, "is_active": is_active}
        )
        
        users, total = await admin_service.list_admins(skip=offset, limit=limit)
        
        # Filter by role if specified
        if role:
            users = [u for u in users if u.get("role") == role]
            total = len(users)
        
        # Filter by active status if specified
        if is_active is not None:
            users = [u for u in users if u.get("is_active") == is_active]
            total = len(users)
        
        logger.info(
            "users_listed_successfully",
            admin_id=current_admin.get("id"),
            count=len(users),
            total=total
        )
        
        return {
            "users": users,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    
    except Exception as e:
        logger.error(
            "list_users_failed",
            admin_id=current_admin.get("id"),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list users"
        )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def create_user(
    request: AdminCreateUserRequest,
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> Dict[str, Any]:
    """
    Create a new admin user.
    
    **Request Body**:
    ```json
    {
        "email": "newadmin@pace.gm",
        "full_name": "John Doe",
        "password": "SecureP@ssw0rd123!",
        "role": "admin"
    }
    ```
    
    **Password Requirements**:
    - Minimum 12 characters
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one digit (0-9)
    - At least one special character (!@#$%^&*...)
    - Not in common weak password list
    
    **Role Options**: superadmin, admin, auditor, viewer
    
    **Returns**:
    - 201 Created: New user created successfully
    - 400 Bad Request: Invalid input or email already exists
    - 401 Unauthorized: Missing or invalid authentication
    - 403 Forbidden: Insufficient permissions
    - 409 Conflict: Email already registered
    - 500 Server Error: Database or service error
    
    **Example Response**:
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "email": "newadmin@pace.gm",
        "full_name": "John Doe",
        "role": "admin",
        "is_active": true,
        "created_at": "2026-04-17T10:00:00Z",
        "message": "Admin user created successfully"
    }
    ```
    """
    try:
        logger.info(
            "create_user_requested",
            creator_id=current_admin.get("id"),
            email=request.email,
            role=request.role
        )
        
        # Check creator has admin permission
        creator_role = current_admin.get("role")
        if creator_role not in ["superadmin", "admin"]:
            logger.warning(
                "create_user_unauthorized",
                creator_id=current_admin.get("id"),
                creator_role=creator_role
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin users can create new users"
            )
        
        # Cannot create superadmin unless creator is superadmin
        if request.role == "superadmin" and creator_role != "superadmin":
            logger.warning(
                "create_superadmin_unauthorized",
                creator_id=current_admin.get("id"),
                creator_role=creator_role
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superadmin can create superadmin users"
            )
        
        # Create user via service
        current_admin_id = UUID(current_admin.get("id"))
        result = await admin_service.create_admin(
            created_by=current_admin_id,
            email=request.email,
            password=request.password,
            full_name=request.full_name,
            role=request.role
        )
        
        logger.info(
            "user_created_successfully",
            creator_id=current_admin.get("id"),
            new_user_id=result.get("id"),
            email=request.email
        )
        
        return {
            **result,
            "message": "Admin user created successfully"
        }
    
    except ValidationException as e:
        logger.warning(
            "create_user_validation_error",
            creator_id=current_admin.get("id"),
            email=request.email,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    except ValidationError as e:
        logger.warning(
            "create_user_validation_error",
            creator_id=current_admin.get("id"),
            email=request.email,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request data"
        )
    
    except Exception as e:
        logger.error(
            "create_user_failed",
            creator_id=current_admin.get("id"),
            email=request.email,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )


@router.get("/{user_id}", response_model=Dict[str, Any])
async def get_user(
    user_id: str,
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> Dict[str, Any]:
    """
    Get details of a specific admin user.
    
    **Path Parameters**:
    - `user_id` (UUID): Admin user ID
    
    **Returns**:
    - 200 OK: User details with metadata
    - 400 Bad Request: Invalid user ID format
    - 401 Unauthorized: Missing or invalid authentication
    - 404 Not Found: User not found
    - 500 Server Error: Database or service error
    
    **Example Response**:
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "admin@pace.gm",
        "full_name": "PACE Administrator",
        "role": "superadmin",
        "is_active": true,
        "two_factor_enabled": true,
        "last_login": "2026-04-17T09:00:00Z",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-04-17T10:00:00Z",
        "permissions": [
            "admin:read",
            "admin:write",
            "users:manage",
            "audit:read"
        ]
    }
    ```
    """
    try:
        # Validate UUID format
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            logger.warning(
                "get_user_invalid_id",
                admin_id=current_admin.get("id"),
                user_id=user_id
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format (must be UUID)"
            )
        
        logger.info(
            "get_user_requested",
            admin_id=current_admin.get("id"),
            user_id=user_id
        )
        
        user = await admin_service.get_admin(user_uuid)
        
        logger.info(
            "user_retrieved_successfully",
            admin_id=current_admin.get("id"),
            user_id=user_id
        )
        
        return user
    
    except NotFoundException as e:
        logger.warning(
            "user_not_found",
            admin_id=current_admin.get("id"),
            user_id=user_id
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found"
        )
    
    except Exception as e:
        logger.error(
            "get_user_failed",
            admin_id=current_admin.get("id"),
            user_id=user_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user"
        )


@router.put("/{user_id}", response_model=Dict[str, Any])
async def update_user(
    user_id: str,
    request: AdminUpdateUserRequest,
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> Dict[str, Any]:
    """
    Update an admin user's details.
    
    **Path Parameters**:
    - `user_id` (UUID): Admin user ID to update
    
    **Request Body** (all fields optional):
    ```json
    {
        "full_name": "Jane Doe",
        "role": "admin",
        "is_active": true
    }
    ```
    
    **Returns**:
    - 200 OK: User updated successfully
    - 400 Bad Request: Invalid input or user ID format
    - 401 Unauthorized: Missing or invalid authentication
    - 403 Forbidden: Insufficient permissions or cannot modify superadmin
    - 404 Not Found: User not found
    - 500 Server Error: Database or service error
    
    **Permissions**:
    - Admin users can update other admin users (except superadmin)
    - Superadmin users can update any user
    - Users cannot change their own role to superadmin
    
    **Example Response**:
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "admin@pace.gm",
        "full_name": "Jane Doe",
        "role": "admin",
        "is_active": true,
        "updated_at": "2026-04-17T10:15:00Z",
        "message": "User updated successfully",
        "changes": {
            "full_name": "Jane Doe",
            "role": "admin"
        }
    }
    ```
    """
    try:
        # Validate UUID format
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            logger.warning(
                "update_user_invalid_id",
                admin_id=current_admin.get("id"),
                user_id=user_id
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format (must be UUID)"
            )
        
        logger.info(
            "update_user_requested",
            admin_id=current_admin.get("id"),
            user_id=user_id,
            changes={k: v for k, v in request.model_dump().items() if v is not None}
        )
        
        # Update user via service
        current_admin_id = UUID(current_admin.get("id"))
        result = await admin_service.update_admin(
            admin_id=user_uuid,
            updated_by=current_admin_id,
            full_name=request.full_name,
            role=request.role,
            is_active=request.is_active
        )
        
        logger.info(
            "user_updated_successfully",
            admin_id=current_admin.get("id"),
            user_id=user_id
        )
        
        # Build change summary
        changes = {k: v for k, v in request.model_dump().items() if v is not None}
        
        return {
            **result,
            "message": "User updated successfully",
            "changes": changes
        }
    
    except ValidationException as e:
        logger.warning(
            "update_user_validation_error",
            admin_id=current_admin.get("id"),
            user_id=user_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    except AuthorizationException as e:
        logger.warning(
            "update_user_unauthorized",
            admin_id=current_admin.get("id"),
            user_id=user_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    
    except NotFoundException as e:
        logger.warning(
            "user_not_found",
            admin_id=current_admin.get("id"),
            user_id=user_id
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found"
        )
    
    except Exception as e:
        logger.error(
            "update_user_failed",
            admin_id=current_admin.get("id"),
            user_id=user_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user"
        )


@router.delete("/{user_id}", response_model=Dict[str, Any])
async def delete_user(
    user_id: str,
    current_admin: dict = Depends(get_current_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> Dict[str, Any]:
    """
    Deactivate/delete an admin user account.
    
    **Path Parameters**:
    - `user_id` (UUID): Admin user ID to delete
    
    **Returns**:
    - 200 OK: User deactivated successfully
    - 400 Bad Request: Invalid user ID format or cannot delete self
    - 401 Unauthorized: Missing or invalid authentication
    - 403 Forbidden: Insufficient permissions or cannot delete superadmin
    - 404 Not Found: User not found
    - 500 Server Error: Database or service error
    
    **Important**:
    - Users cannot delete/deactivate their own accounts
    - Only superadmin can delete/deactivate other superadmin users
    - Deletion is soft (sets is_active = false), user account is preserved
    - Audit logs are created for all deletions
    
    **Example Response**:
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "admin@pace.gm",
        "is_active": false,
        "message": "User deactivated successfully",
        "deactivated_at": "2026-04-17T10:20:00Z"
    }
    ```
    """
    try:
        # Validate UUID format
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            logger.warning(
                "delete_user_invalid_id",
                admin_id=current_admin.get("id"),
                user_id=user_id
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format (must be UUID)"
            )
        
        logger.info(
            "delete_user_requested",
            admin_id=current_admin.get("id"),
            user_id=user_id
        )
        
        # Delete user via service
        current_admin_id = UUID(current_admin.get("id"))
        success = await admin_service.deactivate_admin(
            admin_id=user_uuid,
            deactivated_by=current_admin_id
        )
        
        if not success:
            raise Exception("Failed to deactivate user")
        
        logger.info(
            "user_deactivated_successfully",
            admin_id=current_admin.get("id"),
            user_id=user_id
        )
        
        from datetime import datetime
        return {
            "id": user_id,
            "is_active": False,
            "message": "User deactivated successfully",
            "deactivated_at": datetime.utcnow().isoformat()
        }
    
    except ValidationException as e:
        logger.warning(
            "delete_user_validation_error",
            admin_id=current_admin.get("id"),
            user_id=user_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    except AuthorizationException as e:
        logger.warning(
            "delete_user_unauthorized",
            admin_id=current_admin.get("id"),
            user_id=user_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    
    except NotFoundException as e:
        logger.warning(
            "user_not_found",
            admin_id=current_admin.get("id"),
            user_id=user_id
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found"
        )
    
    except Exception as e:
        logger.error(
            "delete_user_failed",
            admin_id=current_admin.get("id"),
            user_id=user_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )

