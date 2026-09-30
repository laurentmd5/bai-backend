"""
Audit log response models for Company Bot.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class AuditLogResponse(BaseModel):
    """
    Audit log entry response.
    """
    
    id: str = Field(..., description="Audit log ID")
    
    admin_id: Optional[str] = Field(None, description="Admin user ID")
    
    admin_email: Optional[str] = Field(None, description="Admin email")
    
    action: str = Field(..., description="Action performed")
    
    ip_address: Optional[str] = Field(None, description="Client IP address")
    
    user_agent: Optional[str] = Field(None, description="Client user agent")
    
    details: Optional[Dict[str, Any]] = Field(None, description="Action details")
    
    severity: str = Field(..., description="Severity level")
    
    success: bool = Field(..., description="Action success")
    
    error_message: Optional[str] = Field(None, description="Error if failed")
    
    created_at: datetime = Field(..., description="Timestamp")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "admin_id": "admin-uuid",
                "admin_email": "admin@pace.gm",
                "action": "LOGIN_SUCCESS",
                "ip_address": "192.168.1.1",
                "user_agent": "Mozilla/5.0...",
                "details": {
                    "method": "password",
                    "2fa_verified": True
                },
                "severity": "INFO",
                "success": True,
                "error_message": None,
                "created_at": "2026-04-17T10:00:00Z"
            }
        }
    }


class AuditLogListResponse(BaseModel):
    """
    Paginated list of audit logs.
    """
    
    items: List[AuditLogResponse] = Field(..., description="Audit logs")
    
    total: int = Field(..., description="Total count")
    
    page: int = Field(..., description="Current page")
    
    page_size: int = Field(..., description="Page size")
    
    pages: int = Field(..., description="Total pages")
    
    has_next: bool = Field(..., description="Has next page")
    
    has_previous: bool = Field(..., description="Has previous page")
    
    severity_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts by severity"
    )
    
    action_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts by action type"
    )
