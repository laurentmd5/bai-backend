"""
Knowledge document domain model for BARROW.AI.
Tracks documents indexed in the RAG vector store.
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import uuid4
from enum import Enum

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    CheckConstraint,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.domain.admin import AdminUser


class DocumentStatus(str, Enum):
    """Status of a knowledge document."""
    PENDING = "pending"
    INDEXING = "indexing"
    ACTIVE = "active"
    ERROR = "error"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class KnowledgeDocument(Base):
    """
    Knowledge document model for tracking RAG-indexed content.
    Maintains metadata about source documents in the vector store.
    """
    
    __tablename__ = "knowledge_docs"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        comment="Unique document identifier"
    )
    
    # Document identification
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Original filename"
    )
    
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Document title for display"
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Document description"
    )
    
    content_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="SHA-256 hash of document content for deduplication"
    )
    
    # Document metadata
    source_type: Mapped[str] = mapped_column(
        String(50),
        default="upload",
        nullable=False,
        comment="Source type: upload, system, import"
    )
    
    language: Mapped[str] = mapped_column(
        String(10),
        default="en",
        nullable=False,
        comment="Document language"
    )
    
    # Indexing information
    chunks_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of chunks in vector store"
    )
    
    token_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Estimated token count of original document"
    )
    
    status: Mapped[str] = mapped_column(
        String(20),
        default=DocumentStatus.PENDING.value,
        nullable=False,
        index=True,
        comment="Current indexing status"
    )
    
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if indexing failed"
    )
    
    # Version tracking
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Document version number"
    )
    
    previous_version_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID of previous version (if updated)"
    )
    
    # Usage metrics
    times_retrieved: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of times chunks from this document were retrieved"
    )
    
    avg_relevance_score: Mapped[Optional[float]] = mapped_column(
        nullable=True,
        comment="Average relevance score when retrieved"
    )
    
    # Administrative
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether document is available for RAG"
    )
    
    uploaded_by: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Admin who uploaded the document"
    )
    
    # Timestamps
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="When document was uploaded"
    )
    
    indexed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When indexing completed"
    )
    
    last_retrieved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When document was last retrieved in RAG"
    )
    
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When document was deprecated"
    )
    
    # Relationships
    uploaded_by_user: Mapped[Optional["AdminUser"]] = relationship(
        "AdminUser",
        back_populates="knowledge_documents",
        lazy="selectin"
    )
    
    # Table constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'indexing', 'active', 'error', 'deprecated', 'archived')",
            name="ck_knowledge_docs_status_valid"
        ),
        CheckConstraint(
            "language IN ('en', 'fr', 'mandinka', 'wolof')",
            name="ck_knowledge_docs_language_valid"
        ),
        CheckConstraint(
            "chunks_count >= 0",
            name="ck_knowledge_docs_chunks_non_negative"
        ),
        Index("idx_knowledge_docs_status", "status"),
        Index("idx_knowledge_docs_uploaded_at", "uploaded_at"),
        Index("idx_knowledge_docs_public_active", "is_public", "status", postgresql_where="is_public = true AND status = 'active'"),
        Index("idx_knowledge_docs_retrieval_stats", "times_retrieved", "avg_relevance_score", postgresql_where="times_retrieved > 0"),
    )
    
    def __repr__(self) -> str:
        return f"<KnowledgeDocument(id={self.id}, title={self.title}, status={self.status})>"
    
    def to_dict(self) -> dict:
        """Convert knowledge document to dictionary."""
        return {
            "id": str(self.id),
            "filename": self.filename,
            "title": self.title,
            "description": self.description,
            "content_hash": self.content_hash,
            "source_type": self.source_type,
            "language": self.language,
            "chunks_count": self.chunks_count,
            "token_count": self.token_count,
            "status": self.status,
            "error_message": self.error_message,
            "version": self.version,
            "times_retrieved": self.times_retrieved,
            "avg_relevance_score": self.avg_relevance_score,
            "is_public": self.is_public,
            "uploaded_by": str(self.uploaded_by) if self.uploaded_by else None,
            "uploaded_by_name": self.uploaded_by_user.full_name if self.uploaded_by_user else None,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "indexed_at": self.indexed_at.isoformat() if self.indexed_at else None,
            "last_retrieved_at": self.last_retrieved_at.isoformat() if self.last_retrieved_at else None,
        }
    
    def mark_indexing_started(self) -> None:
        """Mark document as being indexed."""
        self.status = DocumentStatus.INDEXING.value
    
    def mark_indexing_complete(self, chunks_count: int, token_count: Optional[int] = None) -> None:
        """Mark document as successfully indexed."""
        self.status = DocumentStatus.ACTIVE.value
        self.chunks_count = chunks_count
        self.token_count = token_count
        self.indexed_at = datetime.utcnow()
        self.error_message = None
    
    def mark_indexing_failed(self, error_message: str) -> None:
        """Mark document as failed to index."""
        self.status = DocumentStatus.ERROR.value
        self.error_message = error_message
    
    def record_retrieval(self, relevance_score: float) -> None:
        """Record that this document was retrieved in a RAG query."""
        self.times_retrieved += 1
        
        if self.avg_relevance_score is None:
            self.avg_relevance_score = relevance_score
        else:
            # Exponential moving average
            alpha = 0.1
            self.avg_relevance_score = (
                alpha * relevance_score + (1 - alpha) * self.avg_relevance_score
            )
        
        self.last_retrieved_at = datetime.utcnow()
    
    def deprecate(self) -> None:
        """Mark document as deprecated."""
        self.status = DocumentStatus.DEPRECATED.value
        self.deprecated_at = datetime.utcnow()
        self.is_public = False
    
    def archive(self) -> None:
        """Archive the document."""
        self.status = DocumentStatus.ARCHIVED.value
        self.is_public = False