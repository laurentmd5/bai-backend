"""
Admin request models for BARROW.AI.
Validates authentication, 2FA, and admin operations.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator, EmailStr
import re

from app.core.exceptions import ValidationException
from app.core.security import validate_email, validate_uuid


class AdminLoginRequest(BaseModel):
    """
    Request model for admin login (first step).
    """
    
    email: EmailStr = Field(
        ...,
        description="Admin email address",
        examples=["admin@pace.gm"]
    )
    
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Admin password"
    )
    
    remember_me: bool = Field(
        default=False,
        description="Extend session duration"
    )
    
    @field_validator('email', mode='after')
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        """Validate email format."""
        if not validate_email(value):
            raise ValidationException(
                "Invalid email format",
                details={"email": value}
            )
        return value.lower()
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "admin@pace.gm",
                "password": "SecureP@ssw0rd123",
                "remember_me": False
            }
        }
    }


class AdminLogin2FARequest(BaseModel):
    """
    Request model for 2FA verification (second step).
    """
    
    session_token: str = Field(
        ...,
        min_length=32,
        max_length=128,
        description="Session token from initial login"
    )
    
    two_factor_code: str = Field(
        ...,
        min_length=6,
        max_length=8,
        description="TOTP code from authenticator app or backup code",
        pattern=r"^[0-9A-Z]{6,8}$"
    )
    
    @field_validator('two_factor_code', mode='after')
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Normalize 2FA code (remove spaces, uppercase)."""
        return value.strip().upper()
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "session_token": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
                "two_factor_code": "123456"
            }
        }
    }


class AdminRefreshTokenRequest(BaseModel):
    """
    Request model for refreshing an expired access token.
    """
    
    refresh_token: str = Field(
        ...,
        min_length=10,
        description="Valid refresh token"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }
    }


class AdminChangePasswordRequest(BaseModel):
    """
    Request model for changing password.
    """
    
    current_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Current password"
    )
    
    new_password: str = Field(
        ...,
        min_length=12,
        max_length=128,
        description="New password (min 12 chars, must include upper, lower, number, special)"
    )
    
    confirm_password: str = Field(
        ...,
        min_length=12,
        max_length=128,
        description="Confirm new password"
    )
    
    @field_validator('new_password', mode='after')
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        """
        Validate password strength.
        Requirements:
        - At least 12 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character
        """
        if len(value) < 12:
            raise ValidationException(
                "Password must be at least 12 characters long"
            )
        
        if not re.search(r"[A-Z]", value):
            raise ValidationException(
                "Password must contain at least one uppercase letter"
            )
        
        if not re.search(r"[a-z]", value):
            raise ValidationException(
                "Password must contain at least one lowercase letter"
            )
        
        if not re.search(r"\d", value):
            raise ValidationException(
                "Password must contain at least one digit"
            )
        
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", value):
            raise ValidationException(
                "Password must contain at least one special character"
            )
        
        # Check for common weak passwords
        common_passwords = ["password", "admin123", "barrow2024", "npp2024", "12345678"]
        if value.lower() in common_passwords:
            raise ValidationException(
                "Password is too common or easily guessable"
            )
        
        return value
    
    @field_validator('confirm_password', mode='after')
    @classmethod
    def validate_password_match(cls, value: str, info) -> str:
        """Ensure passwords match."""
        if 'new_password' in info.data and value != info.data['new_password']:
            raise ValidationException(
                "Passwords do not match"
            )
        return value
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "current_password": "OldP@ssw0rd123",
                "new_password": "NewSecureP@ssw0rd456!",
                "confirm_password": "NewSecureP@ssw0rd456!"
            }
        }
    }


class AdminResetPasswordRequest(BaseModel):
    """
    Request model for initiating password reset.
    """
    
    email: EmailStr = Field(
        ...,
        description="Admin email address"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "admin@pace.gm"
            }
        }
    }


class AdminResetPasswordConfirmRequest(BaseModel):
    """
    Request model for confirming password reset with token.
    """
    
    token: str = Field(
        ...,
        min_length=32,
        description="Password reset token"
    )
    
    new_password: str = Field(
        ...,
        min_length=12,
        max_length=128,
        description="New password"
    )
    
    confirm_password: str = Field(
        ...,
        min_length=12,
        max_length=128,
        description="Confirm new password"
    )
    
    @field_validator('new_password', mode='after')
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        """Reuse password strength validation."""
        return AdminChangePasswordRequest.validate_password_strength(value)
    
    @field_validator('confirm_password', mode='after')
    @classmethod
    def validate_password_match(cls, value: str, info) -> str:
        """Ensure passwords match."""
        if 'new_password' in info.data and value != info.data['new_password']:
            raise ValidationException("Passwords do not match")
        return value


class AdminEnable2FARequest(BaseModel):
    """
    Request model for enabling 2FA.
    Returns TOTP secret and QR code URI.
    """
    
    password: str = Field(
        ...,
        min_length=8,
        description="Current password for confirmation"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "password": "SecureP@ssw0rd123"
            }
        }
    }


class AdminVerify2FARequest(BaseModel):
    """
    Request model for verifying 2FA setup.
    """
    
    two_factor_code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        description="TOTP code from authenticator app",
        pattern=r"^\d{6}$"
    )
    
    @field_validator('two_factor_code', mode='after')
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Normalize TOTP code."""
        return value.strip()
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "two_factor_code": "123456"
            }
        }
    }


class AdminDisable2FARequest(BaseModel):
    """
    Request model for disabling 2FA.
    """
    
    password: str = Field(
        ...,
        min_length=8,
        description="Current password for confirmation"
    )
    
    two_factor_code: Optional[str] = Field(
        None,
        min_length=6,
        max_length=8,
        description="TOTP code or backup code (if 2FA is still functional)"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "password": "SecureP@ssw0rd123",
                "two_factor_code": "123456"
            }
        }
    }


class AdminCreateUserRequest(BaseModel):
    """
    Request model for creating a new admin user.
    """
    
    email: EmailStr = Field(
        ...,
        description="Admin email address (unique)",
        examples=["newadmin@pace.gm"]
    )
    
    full_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Full name of the admin",
        examples=["John Doe"]
    )
    
    password: str = Field(
        ...,
        min_length=12,
        max_length=128,
        description="Initial password (min 12 chars, must include upper, lower, number, special)"
    )
    
    role: str = Field(
        default="viewer",
        pattern="^(superadmin|admin|auditor|viewer)$",
        description="Admin role (superadmin, admin, auditor, viewer)"
    )
    
    @field_validator('email', mode='after')
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        """Validate email format."""
        if not validate_email(value):
            raise ValidationException(
                "Invalid email format",
                details={"email": value}
            )
        return value.lower()
    
    @field_validator('password', mode='after')
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        """
        Validate password strength.
        Requirements:
        - At least 12 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character
        """
        if len(value) < 12:
            raise ValidationException(
                "Password must be at least 12 characters long"
            )
        
        if not re.search(r"[A-Z]", value):
            raise ValidationException(
                "Password must contain at least one uppercase letter"
            )
        
        if not re.search(r"[a-z]", value):
            raise ValidationException(
                "Password must contain at least one lowercase letter"
            )
        
        if not re.search(r"\d", value):
            raise ValidationException(
                "Password must contain at least one digit"
            )
        
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", value):
            raise ValidationException(
                "Password must contain at least one special character"
            )
        
        common_passwords = ["password", "admin123", "barrow2024", "npp2024", "12345678"]
        if value.lower() in common_passwords:
            raise ValidationException(
                "Password is too common or easily guessable"
            )
        
        return value
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "newadmin@pace.gm",
                "full_name": "John Doe",
                "password": "SecureP@ssw0rd123!",
                "role": "admin"
            }
        }
    }


class AdminUpdateUserRequest(BaseModel):
    """
    Request model for updating an admin user.
    """
    
    full_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="New full name",
        examples=["Jane Doe"]
    )
    
    role: Optional[str] = Field(
        None,
        pattern="^(superadmin|admin|auditor|viewer)$",
        description="New admin role"
    )
    
    is_active: Optional[bool] = Field(
        None,
        description="Account active status (true/false)"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "full_name": "Jane Doe",
                "role": "admin",
                "is_active": True
            }
        }
    }