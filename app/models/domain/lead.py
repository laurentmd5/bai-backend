"""
Commercial Lead / Quote Request domain model for automated sales pipeline.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    JSON,
    Enum as SQLEnum,
    Index,
)
import enum

from app.models.domain.admin import Base


class LeadStatus(str, enum.Enum):
    """Lead qualification & follow-up workflow status."""
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    PROPOSAL_SENT = "proposal_sent"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class CommercialLead(Base):
    """
    SQLAlchemy model for commercial leads and quote requests.
    """
    __tablename__ = "commercial_leads"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(255), nullable=True, index=True)
    channel = Column(String(50), default="web", index=True)  # web, whatsapp

    # Prospect details
    full_name = Column(String(255), nullable=False, index=True)
    company_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    phone_number = Column(String(50), nullable=True, index=True)
    location = Column(String(255), nullable=True)  # City, district or site location

    # Business need / quote details
    service_category = Column(String(100), nullable=True, index=True)  # Video surveillance, Solar, Networks, Web, etc.
    requirements_summary = Column(Text, nullable=False)  # Detailed or summarized requirements
    qualification_answers = Column(JSON, nullable=True)  # Conversation answers

    # Workflow & tracking
    status = Column(
        SQLEnum(LeadStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=LeadStatus.NEW,
        nullable=False,
        index=True
    )
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_lead_status_created", "status", "created_at"),
        Index("idx_lead_category", "service_category"),
    )
