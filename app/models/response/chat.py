"""
Chat response models for BARROW.AI.
Serializes chatbot responses with sources, confidence, and metadata.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

from app.core.config import settings


class ChatSourceResponse(BaseModel):
    """
    Source information for a RAG-generated response.
    """
    
    document: str = Field(
        ...,
        description="Source document name",
        examples=["Digital.docx"]
    )
    
    section: Optional[str] = Field(
        None,
        description="Document section",
        examples=["2. Expanding Connectivity"]
    )
    
    relevance: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relevance score (cosine similarity)",
        examples=[0.94]
    )
    
    chunk_index: Optional[int] = Field(
        None,
        description="Chunk index within document"
    )
    
    text_preview: Optional[str] = Field(
        None,
        description="Preview of the source text used",
        max_length=200
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "document": "Digital.docx",
                "section": "2. Expanding Connectivity",
                "relevance": 0.94,
                "chunk_index": 12,
                "text_preview": "Increased mobile penetration to 113%..."
            }
        }
    }


class ChatMessageResponse(BaseModel):
    """
    Complete response to a chat message.
    """
    
    message: str = Field(
        ...,
        description="Bot response text"
    )
    
    session_id: str = Field(
        ...,
        description="Session ID for conversation continuity"
    )
    
    conversation_id: Optional[str] = Field(
        None,
        description="Unique ID for this conversation"
    )
    
    sources: List[ChatSourceResponse] = Field(
        default_factory=list,
        description="Source documents used for RAG"
    )
    
    confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Overall confidence score"
    )
    
    cache_hit: bool = Field(
        default=False,
        description="Whether response came from cache"
    )
    
    fallback_triggered: bool = Field(
        default=False,
        description="Whether fallback response was used"
    )
    
    latency_ms: Optional[int] = Field(
        None,
        description="Response latency in milliseconds"
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp (UTC)"
    )
    
    model_used: Optional[str] = Field(
        None,
        description="LLM model used for generation"
    )
    
    suggested_questions: Optional[List[str]] = Field(
        None,
        description="Suggested follow-up questions"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "Under the NPP administration (2022-2026), mobile penetration reached 113%, one of the highest in West Africa. The government launched the US$25M Second Submarine Cable Project (WARDIP) and upgraded GAMTEL backbone from 40G to 800G.\n\nAsk. Know. Decide. - One Gambia. One People. One Barrow.",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "conversation_id": "660e8400-e29b-41d4-a716-446655440001",
                "sources": [
                    {
                        "document": "Digital.docx",
                        "section": "2. Expanding Connectivity",
                        "relevance": 0.94,
                        "chunk_index": 12
                    }
                ],
                "confidence": 0.94,
                "cache_hit": False,
                "fallback_triggered": False,
                "latency_ms": 1243,
                "timestamp": "2026-04-17T10:30:45Z",
                "model_used": "tunedModels/askbarrow-npp-v3",
                "suggested_questions": [
                    "What are the plans for 5G rollout?",
                    "Tell me about digital addressing"
                ]
            }
        }
    }


class ChatHistoryResponse(BaseModel):
    """
    Response containing chat history for a session.
    """
    
    session_id: str = Field(..., description="Session ID")
    
    messages: List[ChatMessageResponse] = Field(
        default_factory=list,
        description="List of messages in chronological order"
    )
    
    total_messages: int = Field(..., description="Total number of messages")
    
    channel: str = Field(..., description="Session channel")
    
    language: str = Field(..., description="Session language")
    
    created_at: datetime = Field(..., description="Session creation time")
    
    last_active: datetime = Field(..., description="Last activity time")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "messages": [],
                "total_messages": 5,
                "channel": "web",
                "language": "en",
                "created_at": "2026-04-17T10:00:00Z",
                "last_active": "2026-04-17T10:30:45Z"
            }
        }
    }


class ChatFeedbackResponse(BaseModel):
    """
    Response after submitting feedback.
    """
    
    conversation_id: str = Field(..., description="Conversation ID")
    
    feedback: int = Field(..., description="Recorded feedback value")
    
    message: str = Field(
        default="Feedback recorded successfully",
        description="Confirmation message"
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Feedback timestamp"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                "feedback": 1,
                "message": "Feedback recorded successfully",
                "timestamp": "2026-04-17T10:31:00Z"
            }
        }
    }


class ChatFallbackResponse(BaseModel):
    """
    Fallback response when information is not available.
    """
    
    message: str = Field(..., description="Fallback message")
    
    session_id: str = Field(..., description="Session ID")
    
    reason: str = Field(
        ...,
        description="Reason for fallback",
        examples=["low_confidence", "no_sources", "llm_timeout", "hostile_content"]
    )
    
    confidence: Optional[float] = Field(None, description="Confidence score if applicable")
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "I do not have this information in my campaign database. Please visit www.npp.gm or contact your nearest PACE office.\n\nAsk. Know. Decide. - One Gambia. One People. One Barrow.",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "reason": "low_confidence",
                "confidence": 0.45,
                "timestamp": "2026-04-17T10:30:45Z"
            }
        }
    }