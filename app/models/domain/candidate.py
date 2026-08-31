"""
Candidate Application domain model for NETSYSTEME recruitment.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Float,
    JSON,
    Enum as SQLEnum,
    Index,
)
import enum

from app.models.domain.admin import Base


class ApplicationStatus(str, enum.Enum):
    """Candidate application workflow status."""
    NEW = "new"
    PRESCREENED = "prescreened"
    SHORTLISTED = "shortlisted"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    REJECTED = "rejected"
    HIRED = "hired"


class CandidateApplication(Base):
    """
    SQLAlchemy model for candidate job and internship applications.
    """
    __tablename__ = "candidate_applications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(255), nullable=True, index=True)
    channel = Column(String(50), default="whatsapp", index=True)  # whatsapp, web, email
    
    # Candidate details
    full_name = Column(String(255), nullable=False, index=True)
    email = Column(String(255), nullable=True, index=True)
    phone_number = Column(String(50), nullable=True, index=True)
    
    # Profile & CV analysis
    cv_filename = Column(String(255), nullable=True)
    raw_cv_text = Column(Text, nullable=True)
    parsed_profile = Column(JSON, nullable=True)
    
    # Screening answers (5 NETSYSTEME questions)
    answers_json = Column(JSON, nullable=True)
    
    # Scoring & Domain matching
    match_score = Column(Float, default=0.0)
    target_domains = Column(JSON, nullable=True)
    
    # Lifecycle
    status = Column(
        SQLEnum(ApplicationStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=ApplicationStatus.NEW,
        nullable=False,
        index=True
    )
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_candidate_status_score", "status", "match_score"),
        Index("ix_candidate_created_at", "created_at"),
    )
