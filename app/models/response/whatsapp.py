"""
WhatsApp response models for Company Bot.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class WhatsAppOptOutResponse(BaseModel):
    """
    WhatsApp opt-out entry response.
    """
    
    phone_number: str = Field(..., description="Phone number (masked)")
    
    opted_out_at: datetime = Field(..., description="Opt-out timestamp")
    
    source: str = Field(..., description="Opt-out source")
    
    session_id: Optional[str] = Field(None, description="Associated session ID")


class WhatsAppOptOutListResponse(BaseModel):
    """
    Paginated list of opt-outs.
    """
    
    items: List[WhatsAppOptOutResponse] = Field(..., description="Opt-outs")
    
    total: int = Field(..., description="Total count")
    
    page: int = Field(..., description="Current page")
    
    page_size: int = Field(..., description="Page size")
    
    pages: int = Field(..., description="Total pages")


class WhatsAppWebhookVerificationResponse(BaseModel):
    """
    Webhook verification response (GET).
    """
    
    challenge: str = Field(..., description="Hub challenge token")
    
    verified: bool = Field(default=True, description="Verification status")


class WhatsAppSendMessageResponse(BaseModel):
    """
    Response after sending WhatsApp message.
    """
    
    message_id: str = Field(..., description="WhatsApp message ID")
    
    recipient: str = Field(..., description="Recipient phone number (masked)")
    
    status: str = Field(..., description="Message status")
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "message_id": "wamid.xxx",
                "recipient": "+220XXXXX67",
                "status": "sent",
                "timestamp": "2026-04-17T10:30:45Z"
            }
        }
    }
