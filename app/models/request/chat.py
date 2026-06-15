"""
Chat request models for BARROW.AI.
Validates incoming chat messages and feedback.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, StringConstraints
from typing_extensions import Annotated
import re

from app.core.config import settings
from app.core.security import (
    detect_sql_injection,
    detect_xss,
    detect_prompt_injection,
    detect_hostile_content,
    sanitize_input,
    html_escape,
)
from app.core.exceptions import ValidationException, HostileContentException, PromptInjectionException


class ChatMessageRequest(BaseModel):
    """
    Request model for sending a chat message.
    
    Validates message content for security and length constraints.
    Supports session continuity and language preferences.
    """
    
    message: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=2000,
            strip_whitespace=True
        ),
        Field(
            ...,
            description="User message to the chatbot",
            examples=["What has NPP done for internet connectivity?"]
        )
    ]
    
    session_id: Optional[str] = Field(
        None,
        description="Existing session ID for conversation continuity",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    
    language: str = Field(
        default="en",
        description="Preferred language for response",
        examples=["en", "mandinka", "wolof"],
        pattern="^(en|mandinka|wolof)$"
    )
    
    channel: str = Field(
        default="web",
        description="Channel of the message",
        examples=["web", "whatsapp"],
        pattern="^(web|whatsapp)$"
    )
    
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional metadata for analytics"
    )
    
    @field_validator('message', mode='after')
    @classmethod
    def validate_message_security(cls, value: str) -> str:
        """
        Comprehensive security validation for chat messages.
        
        Args:
            value: Raw user message
            
        Returns:
            str: Sanitized message
            
        Raises:
            ValidationException: If message fails validation
            HostileContentException: If hostile content detected
            PromptInjectionException: If prompt injection detected
        """
        # Check for XSS patterns (critical - reject immediately)
        if detect_xss(value):
            raise ValidationException(
                "Invalid message content detected",
                details={"reason": "xss_pattern"}
            )
        
        # Check for prompt injection (critical - reject immediately)
        if detect_prompt_injection(value):
            raise PromptInjectionException()
        
        # Check for hostile content towards Barrow/NPP (critical - reject)
        is_hostile, matched = detect_hostile_content(value)
        if is_hostile:
            raise HostileContentException()
        
        # Check for SQL injection patterns (warning only - could be legitimate)
        if detect_sql_injection(value):
            # Logged by security module, but we allow the message
            pass
        
        # Sanitize input
        sanitized = sanitize_input(value)
        sanitized = html_escape(sanitized)
        
        return sanitized
    
    @field_validator('session_id', mode='after')
    @classmethod
    def validate_session_id(cls, value: Optional[str]) -> Optional[str]:
        """Validate session ID format if provided."""
        if value is None:
            return value
        
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            re.IGNORECASE
        )
        
        if not uuid_pattern.match(value):
            raise ValidationException(
                "Invalid session_id format - must be UUID v4",
                details={"provided": value}
            )
        
        return value.lower()
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "What has NPP done for internet connectivity?",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "language": "en",
                "channel": "web",
                "metadata": {
                    "user_agent": "Mozilla/5.0...",
                    "screen_size": "1920x1080"
                }
            }
        }
    }


class ChatFeedbackRequest(BaseModel):
    """
    Request model for submitting feedback on a chatbot response.
    """
    
    conversation_id: str = Field(
        ...,
        description="ID of the conversation being rated",
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    
    feedback: int = Field(
        ...,
        description="Feedback value: 1 for positive, -1 for negative",
        ge=-1,
        le=1
    )
    
    session_id: str = Field(
        ...,
        description="Session ID for validation (must match conversation's session)",
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    
    comment: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional feedback comment"
    )
    
    @field_validator('feedback', mode='after')
    @classmethod
    def validate_feedback(cls, value: int) -> int:
        """Ensure feedback is 1 or -1."""
        if value not in (1, -1):
            raise ValidationException(
                "Feedback must be 1 (positive) or -1 (negative)",
                details={"provided": value}
            )
        return value
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                "feedback": 1,
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "comment": "Very helpful response!"
            }
        }
    }