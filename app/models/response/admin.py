"""
Admin response models for BARROW.AI.
Serializes authentication tokens, user data, and 2FA setup.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """
    JWT token response after successful authentication.
    """
    
    access_token: str = Field(
        ...,
        description="JWT access token"
    )
    
    refresh_token: str = Field(
        ...,
        description="JWT refresh token"
    )
    
    token_type: str = Field(
        default="bearer",
        description="Token type"
    )
    
    expires_in: int = Field(
        ...,
        description="Access token expiration in seconds"
    )
    
    requires_2fa: bool = Field(
        default=False,
        description="Whether 2FA verification is required"
    )
    
    session_token: Optional[str] = Field(
        None,
        description="Temporary session token for 2FA verification"
    )
    
    csrf_token: Optional[str] = Field(
        None,
        description="CSRF token for subsequent requests"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 900,
                "requires_2fa": False,
                "csrf_token": "a1b2c3d4e5f6..."
            }
        }
    }


class TwoFactorSetupResponse(BaseModel):
    """
    Response when enabling 2FA.
    """
    
    secret: str = Field(
        ...,
        description="Base32 TOTP secret"
    )
    
    qr_code_uri: str = Field(
        ...,
        description="otpauth:// URI for QR code generation"
    )
    
    backup_codes: List[str] = Field(
        ...,
        description="List of backup recovery codes (show once)"
    )
    
    message: str = Field(
        default="Scan QR code with Google Authenticator or Authy",
        description="Setup instructions"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "secret": "JBSWY3DPEHPK3PXP",
                "qr_code_uri": "otpauth://totp/BARROW.AI%20Admin:admin@pace.gm?secret=JBSWY3DPEHPK3PXP&issuer=BARROW.AI%20Admin",
                "backup_codes": ["A1B2C3D4", "E5F6G7H8", "I9J0K1L2"],
                "message": "Scan QR code with Google Authenticator or Authy"
            }
        }
    }


class QRCodeResponse(BaseModel):
    """
    QR code response for 2FA setup.
    """
    
    qr_code_uri: str = Field(..., description="otpauth:// URI")
    
    secret: str = Field(..., description="TOTP secret (for manual entry)")
    
    expires_in: int = Field(
        default=300,
        description="QR code validity in seconds"
    )


class BackupCodesResponse(BaseModel):
    """
    Backup codes response.
    """
    
    backup_codes: List[str] = Field(
        ...,
        description="New backup codes (show once)"
    )
    
    message: str = Field(
        default="Save these codes in a secure place. Each code can be used once.",
        description="Warning message"
    )


class AdminUserResponse(BaseModel):
    """
    Admin user profile response.
    """
    
    id: str = Field(..., description="Admin user ID")
    
    email: str = Field(..., description="Admin email")
    
    full_name: str = Field(..., description="Full name")
    
    role: str = Field(..., description="Admin role")
    
    is_active: bool = Field(..., description="Account status")
    
    two_factor_enabled: bool = Field(..., description="2FA status")
    
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")
    
    created_at: datetime = Field(..., description="Account creation timestamp")
    
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    preferences: Optional[Dict[str, Any]] = Field(
        None,
        description="User preferences"
    )
    
    permissions: List[str] = Field(
        default_factory=list,
        description="List of granted permissions"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "admin@pace.gm",
                "full_name": "PACE Administrator",
                "role": "superadmin",
                "is_active": True,
                "two_factor_enabled": True,
                "last_login": "2026-04-17T09:00:00Z",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-04-17T10:00:00Z",
                "preferences": {
                    "theme": "dark",
                    "notifications": True
                },
                "permissions": [
                    "admin:read",
                    "admin:write",
                    "conversations:read",
                    "conversations:export",
                    "knowledge:manage",
                    "audit:read",
                    "users:manage"
                ]
            }
        }
    }


class AdminSessionResponse(BaseModel):
    """
    Current admin session information.
    """
    
    user: AdminUserResponse = Field(..., description="Admin user")
    
    session_id: str = Field(..., description="Session ID")
    
    ip_address: str = Field(..., description="Client IP address")
    
    user_agent: str = Field(..., description="Client user agent")
    
    created_at: datetime = Field(..., description="Session creation time")
    
    expires_at: datetime = Field(..., description="Session expiration time")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "user": {},
                "session_id": "session_abc123",
                "ip_address": "192.168.1.1",
                "user_agent": "Mozilla/5.0...",
                "created_at": "2026-04-17T10:00:00Z",
                "expires_at": "2026-04-17T10:15:00Z"
            }
        }
    }


class AdminLoginResponse(BaseModel):
    """
    Response after successful login (before 2FA if required).
    """
    
    requires_2fa: bool = Field(
        ...,
        description="Whether 2FA is required"
    )
    
    session_token: Optional[str] = Field(
        None,
        description="Session token for 2FA verification"
    )
    
    expires_in: int = Field(
        ...,
        description="Token expiration in seconds"
    )
    
    user: Optional[AdminUserResponse] = Field(
        None,
        description="User information (only if 2FA not required)"
    )
    
    tokens: Optional[TokenResponse] = Field(
        None,
        description="JWT tokens (only if 2FA not required)"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "requires_2fa": True,
                "session_token": "a1b2c3d4e5f6...",
                "expires_in": 300,
                "user": None,
                "tokens": None
            }
        }
    }