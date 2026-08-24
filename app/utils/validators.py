"""
Validators for Company Bot.
Provides email, phone, UUID, and other input validators.
"""

import re
from typing import Optional
from uuid import UUID
import email_validator


def validate_email(email: str) -> bool:
    """
    Validate email address format.
    
    Args:
        email: Email address to validate
        
    Returns:
        bool: True if valid email format
    """
    if not email:
        return False
    try:
        email_validator.validate_email(email)
        return True
    except Exception:
        return False


def validate_phone_number(phone: str) -> bool:
    """
    Validate phone number in E.164 format.
    
    Args:
        phone: Phone number to validate
        
    Returns:
        bool: True if valid E.164 format (+1-15 digits)
    """
    if not phone:
        return False
    # E.164 format: +[1-15 digits]
    pattern = r'^\+[1-9]\d{1,14}$'
    return bool(re.match(pattern, phone))


def validate_uuid(uuid_string: str) -> bool:
    """
    Validate UUID v4 format.
    
    Args:
        uuid_string: UUID string to validate
        
    Returns:
        bool: True if valid UUID
    """
    if not uuid_string:
        return False
    try:
        UUID(uuid_string)
        return True
    except (ValueError, AttributeError):
        return False

