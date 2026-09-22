"""
Knowledge document request models for Company Bot.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class KnowledgeDocumentUploadRequest(BaseModel):
    """
    Request model for uploading a knowledge document.
    """
    
    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Document title for display"
    )
    
    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Document description"
    )
    
    section: Optional[str] = Field(
        None,
        max_length=100,
        description="Section or category"
    )
    
    language: str = Field(
        default="en",
        description="Document language",
        pattern="^(en|fr|mandinka|wolof)$"
    )
    
    is_public: bool = Field(
        default=True,
        description="Whether document is available for RAG"
    )
    
    @field_validator('title', mode='after')
    @classmethod
    def sanitize_title(cls, value: str) -> str:
        """Sanitize document title."""
        return value.strip()
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "title": "NETSYSTEME IT Services Guide 2026",
                "description": "Official NETSYSTEME document",
                "section": "ICT Policy",
                "language": "en",
                "is_public": True
            }
        }
    }


class KnowledgeDocumentUpdateRequest(BaseModel):
    """
    Request model for updating knowledge document metadata.
    """
    
    title: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Document title"
    )
    
    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Document description"
    )
    
    section: Optional[str] = Field(
        None,
        max_length=100,
        description="Section or category"
    )
    
    is_public: Optional[bool] = Field(
        None,
        description="Whether document is available for RAG"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "title": "Updated NPP Digital Transformation Plan",
                "is_public": True
            }
        }
    }

