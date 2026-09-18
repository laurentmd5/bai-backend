"""
Knowledge document response models for Company Bot.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class KnowledgeDocumentResponse(BaseModel):
    """
    Knowledge document response.
    """
    
    id: str = Field(..., description="Document ID")
    
    filename: str = Field(..., description="Original filename")
    
    title: str = Field(..., description="Document title")
    
    description: Optional[str] = Field(None, description="Description")
    
    content_hash: str = Field(..., description="SHA-256 content hash")
    
    source_type: str = Field(..., description="Source type")
    
    language: str = Field(..., description="Document language")
    
    chunks_count: int = Field(..., description="Number of chunks in vector store")
    
    token_count: Optional[int] = Field(None, description="Estimated token count")
    
    status: str = Field(..., description="Indexing status")
    
    error_message: Optional[str] = Field(None, description="Error if failed")
    
    version: int = Field(..., description="Document version")
    
    times_retrieved: int = Field(..., description="Times retrieved in RAG")
    
    avg_relevance_score: Optional[float] = Field(None, description="Average relevance")
    
    is_public: bool = Field(..., description="Available for RAG")
    
    uploaded_by: Optional[str] = Field(None, description="Uploader ID")
    
    uploaded_by_name: Optional[str] = Field(None, description="Uploader name")
    
    uploaded_at: datetime = Field(..., description="Upload timestamp")
    
    indexed_at: Optional[datetime] = Field(None, description="Indexing completion")
    
    last_retrieved_at: Optional[datetime] = Field(None, description="Last retrieval")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "filename": "Digital.docx",
                "title": "NETSYSTEME Service Catalogue 2026",
                "description": "Official NETSYSTEME document outlining IT services",
                "content_hash": "sha256:abc123...",
                "source_type": "upload",
                "language": "en",
                "chunks_count": 45,
                "token_count": 12500,
                "status": "active",
                "error_message": None,
                "version": 1,
                "times_retrieved": 1520,
                "avg_relevance_score": 0.87,
                "is_public": True,
                "uploaded_by": "admin-uuid",
                "uploaded_by_name": "PACE Administrator",
                "uploaded_at": "2026-04-01T10:00:00Z",
                "indexed_at": "2026-04-01T10:05:00Z",
                "last_retrieved_at": "2026-04-17T10:30:00Z"
            }
        }
    }


class KnowledgeDocumentListResponse(BaseModel):
    """
    Paginated list of knowledge documents.
    """
    
    items: List[KnowledgeDocumentResponse] = Field(..., description="Documents")
    
    total: int = Field(..., description="Total count")
    
    page: int = Field(..., description="Current page")
    
    page_size: int = Field(..., description="Page size")
    
    pages: int = Field(..., description="Total pages")
    
    has_next: bool = Field(..., description="Has next page")
    
    has_previous: bool = Field(..., description="Has previous page")
    
    total_chunks: int = Field(..., description="Total chunks across all documents")
    
    active_documents: int = Field(..., description="Number of active documents")


class KnowledgeDocumentUploadResponse(BaseModel):
    """
    Response after document upload.
    """
    
    document_id: str = Field(..., description="New document ID")
    
    filename: str = Field(..., description="Uploaded filename")
    
    title: str = Field(..., description="Document title")
    
    status: str = Field(..., description="Initial status")
    
    message: str = Field(
        default="Document uploaded successfully. Indexing in progress.",
        description="Status message"
    )
    
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    
    estimated_indexing_time_seconds: Optional[int] = Field(
        None,
        description="Estimated time to complete indexing"
    )


class KnowledgeDocumentIndexStatusResponse(BaseModel):
    """
    Indexing status response.
    """
    
    document_id: str = Field(..., description="Document ID")
    
    status: str = Field(..., description="Current status")
    
    progress_percentage: Optional[float] = Field(
        None,
        description="Indexing progress (0-100)"
    )
    
    chunks_processed: int = Field(default=0, description="Chunks processed")
    
    chunks_total: int = Field(default=0, description="Total chunks")
    
    error_message: Optional[str] = Field(None, description="Error if failed")
    
    started_at: Optional[datetime] = Field(None, description="Indexing start time")
    
    completed_at: Optional[datetime] = Field(None, description="Indexing completion")

