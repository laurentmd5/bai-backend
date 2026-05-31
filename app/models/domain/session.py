"""
Session domain model for BARROW.AI.
Tracks user sessions across web and WhatsApp channels.
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from uuid import uuid4
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.domain.conversation import Conversation


class Session(Base):
    """
    Session model representing a user conversation session.
    
    Sessions can span multiple conversations and channels.
    """
    
    __tablename__ = "sessions"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        comment="Unique session identifier"
    )
    
    # Channel information
    channel: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Channel: 'web' or 'whatsapp'"
    )
    
    # External identifier (cookie ID for web, phone number for WhatsApp - encrypted)
    external_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="External identifier (cookie_id for web, encrypted phone for WhatsApp)"
    )
    
    # User preferences
    language: Mapped[str] = mapped_column(
        String(20),
        default="en",
        nullable=False,
        comment="User's preferred language (en, fr, mandinka, wolof)"
    )
    
    # Client metadata
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="User agent string from client"
    )
    
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),  # Supports both IPv4 and IPv6
        nullable=True,
        comment="Client IP address"
    )
    
    # Status flags
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="Whether session is still active"
    )
    
    opted_out: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Whether user has opted out (WhatsApp only)"
    )
    
    # Session metrics
    message_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
        comment="Total number of messages in this session"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        comment="When the session was created"
    )
    
    last_active: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="When the session was last active"
    )
    
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the session was closed (if applicable)"
    )
    
    # Relationships
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation",
        back_populates="session",
        lazy="selectin",
        order_by="Conversation.created_at",
        cascade="all, delete-orphan"
    )
    
    # Table constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "channel IN ('web', 'whatsapp')",
            name="ck_sessions_channel_valid"
        ),
        CheckConstraint(
            "language IN ('en', 'fr', 'mandinka', 'wolof')",
            name="ck_sessions_language_valid"
        ),
        Index("idx_sessions_external_id", "external_id", postgresql_where="external_id IS NOT NULL"),
        Index("idx_sessions_channel_active", "channel", "is_active"),
        Index("idx_sessions_last_active", "last_active", postgresql_where="is_active = true"),
    )
    
    def __repr__(self) -> str:
        return f"<Session(id={self.id}, channel={self.channel}, messages={self.message_count})>"
    
    def to_dict(self, include_conversations: bool = False) -> dict:
        """
        Convert session to dictionary.
        
        Args:
            include_conversations: Whether to include related conversations
            
        Returns:
            Dict containing session data
        """
        result = {
            "id": str(self.id),
            "channel": self.channel,
            "language": self.language,
            "is_active": self.is_active,
            "opted_out": self.opted_out,
            "message_count": self.message_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
        }
        
        if include_conversations:
            result["conversations"] = [c.to_dict() for c in self.conversations]
        
        return result
    
    def touch(self) -> None:
        """Update last_active timestamp and increment message count."""
        self.last_active = datetime.utcnow()
        self.message_count += 1
    
    def close(self) -> None:
        """Mark session as closed."""
        self.is_active = False
        self.closed_at = datetime.utcnow()
    
    def opt_out(self) -> None:
        """Mark session as opted out (WhatsApp)."""
        self.opted_out = True
        self.is_active = False
        self.closed_at = datetime.utcnow()
    
    def opt_in(self) -> None:
        """Mark session as opted in (WhatsApp)."""
        self.opted_out = False
        self.is_active = True
        self.closed_at = None