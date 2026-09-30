"""
Conversation response models for Company Bot.
Serializes conversation history and exports.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.response.chat import ChatSourceResponse


class ConversationResponse(BaseModel):
    """
    Individual conversation response.
    """
    
    id: str = Field(..., description="Conversation ID")
    
    session_id: str = Field(..., description="Session ID")
    
    user_message: str = Field(..., description="User message")
    
    bot_response: str = Field(..., description="Bot response")
    
    sources: List[ChatSourceResponse] = Field(
        default_factory=list,
        description="RAG sources"
    )
    
    confidence: Optional[float] = Field(None, description="Confidence score")
    
    feedback: Optional[int] = Field(None, description="User feedback")
    
    channel: str = Field(..., description="Channel")
    
    latency_ms: Optional[int] = Field(None, description="Response latency")
    
    cache_hit: bool = Field(..., description="Cache hit")
    
    fallback_triggered: bool = Field(..., description="Fallback triggered")
    
    llm_model: Optional[str] = Field(None, description="LLM model used")
    
    created_at: datetime = Field(..., description="Creation timestamp")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "session_id": "550e8400-e29b-41d4-a716-446655440001",
                "user_message": "What services does NETSYSTEME offer?",
                "bot_response": "NETSYSTEME offers networking, cybersecurity and IT support services.",
                "sources": [],
                "confidence": 0.94,
                "feedback": 1,
                "channel": "web",
                "latency_ms": 1243,
                "cache_hit": False,
                "fallback_triggered": False,
                "llm_model": "gemini-2.5-flash-lite",
                "created_at": "2026-04-17T10:30:45Z"
            }
        }
    }


class ConversationDetailResponse(ConversationResponse):
    """
    Detailed conversation response with additional metadata.
    """
    
    session: Optional[Dict[str, Any]] = Field(None, description="Session information")
    
    llm_tokens_used: Optional[int] = Field(None, description="Tokens used")
    
    validation_failed: bool = Field(..., description="Validation failed")
    
    qdrant_search_ms: Optional[int] = Field(None, description="Qdrant search latency")
    
    embedding_ms: Optional[int] = Field(None, description="Embedding generation latency")
    
    llm_generation_ms: Optional[int] = Field(None, description="LLM generation latency")
    
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class ConversationListResponse(BaseModel):
    """
    Paginated list of conversations.
    """
    
    items: List[ConversationResponse] = Field(..., description="Conversations")
    
    total: int = Field(..., description="Total count")
    
    page: int = Field(..., description="Current page")
    
    page_size: int = Field(..., description="Page size")
    
    pages: int = Field(..., description="Total pages")
    
    has_next: bool = Field(..., description="Has next page")
    
    has_previous: bool = Field(..., description="Has previous page")
    
    filters_applied: Optional[Dict[str, Any]] = Field(
        None,
        description="Filters that were applied"
    )


class ConversationExportResponse(BaseModel):
    """
    Export response with pre-signed URL.
    """
    
    export_id: str = Field(..., description="Export job ID")
    
    status: str = Field(
        ...,
        description="Export status",
        examples=["pending", "processing", "completed", "failed"]
    )
    
    download_url: Optional[str] = Field(
        None,
        description="Pre-signed download URL (when completed)"
    )
    
    expires_at: Optional[datetime] = Field(
        None,
        description="URL expiration time"
    )
    
    total_records: Optional[int] = Field(None, description="Total records exported")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

