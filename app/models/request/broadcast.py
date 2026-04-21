"""
Broadcast request models for WhatsApp messaging.
Phase 2 feature - prepared for future implementation.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


class BroadcastTemplateParameter(BaseModel):
    """
    Parameter for WhatsApp template message.
    """
    
    type: str = Field(
        ...,
        description="Parameter type",
        pattern="^(text|currency|date_time|image|document|video)$"
    )
    
    text: Optional[str] = Field(None, description="Text value")
    
    currency: Optional[Dict[str, str]] = Field(
        None,
        description="Currency value with fallback_value and code"
    )
    
    date_time: Optional[Dict[str, str]] = Field(
        None,
        description="DateTime value with fallback_value"
    )


class BroadcastRequest(BaseModel):
    """
    Request model for sending a WhatsApp broadcast.
    Phase 2 feature.
    """
    
    template_name: str = Field(
        ...,
        min_length=1,
        max_length=60,
        description="WhatsApp template name",
        pattern=r"^[a-z_][a-z0-9_]*$"
    )
    
    template_language: str = Field(
        default="en",
        description="Template language code"
    )
    
    recipients: List[str] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="List of recipient phone numbers (E.164 format)"
    )
    
    parameters: Optional[List[BroadcastTemplateParameter]] = Field(
        None,
        description="Template parameters"
    )
    
    scheduled_at: Optional[str] = Field(
        None,
        description="ISO 8601 timestamp for scheduled broadcast"
    )
    
    segment_filter: Optional[Dict[str, Any]] = Field(
        None,
        description="Filter criteria for segment-based broadcast"
    )
    
    @field_validator('recipients', mode='after')
    @classmethod
    def validate_recipients(cls, value: List[str]) -> List[str]:
        """Validate phone numbers are in E.164 format."""
        import re
        pattern = re.compile(r"^\+[1-9]\d{1,14}$")
        
        for phone in value:
            if not pattern.match(phone):
                raise ValueError(f"Invalid phone number format: {phone}")
        
        return value
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "template_name": "npp_announcement",
                "template_language": "en",
                "recipients": ["+2201234567", "+2209876543"],
                "parameters": [
                    {"type": "text", "text": "Digital Transformation"}
                ]
            }
        }
    }