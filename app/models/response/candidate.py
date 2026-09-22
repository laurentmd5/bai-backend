"""
Candidate response models for Company Bot admin API.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.domain.candidate import ApplicationStatus


class CandidateApplicationResponse(BaseModel):
    """Detailed candidate application response model."""
    id: str = Field(..., description="Unique application identifier (UUID)")
    session_id: Optional[str] = Field(None, description="Conversation session ID")
    channel: str = Field(default="whatsapp", description="Origination channel (whatsapp, web, email)")
    
    full_name: str = Field(..., description="Candidate full name")
    email: Optional[str] = Field(None, description="Candidate contact email")
    phone_number: Optional[str] = Field(None, description="Candidate phone number")
    
    cv_filename: Optional[str] = Field(None, description="Uploaded CV filename")
    raw_cv_text: Optional[str] = Field(None, description="Extracted raw text from CV")
    parsed_profile: Optional[Dict[str, Any]] = Field(None, description="AI parsed structured CV profile")
    
    answers_json: Optional[Dict[str, Any]] = Field(None, description="Candidate screening questionnaire responses")
    match_score: float = Field(default=0.0, description="AI matching score percentage (0-100)")
    target_domains: Optional[List[str]] = Field(default_factory=list, description="Matched business/technical domains")
    
    status: ApplicationStatus = Field(..., description="Application workflow status")
    notes: Optional[str] = Field(None, description="Internal recruiter notes")
    created_at: datetime = Field(..., description="Application creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "session_id": "sess_whatsapp_221770000000",
                "channel": "whatsapp",
                "full_name": "Moussa Diop",
                "email": "moussa.diop@example.com",
                "phone_number": "+221770000000",
                "cv_filename": "CV_Moussa_Diop.pdf",
                "match_score": 85.0,
                "target_domains": ["Réseaux", "Télécom"],
                "status": "prescreened",
                "created_at": "2026-09-14T10:00:00Z",
                "updated_at": "2026-09-14T10:05:00Z"
            }
        }
    }


class CandidateListResponse(BaseModel):
    """Paginated list of candidate applications."""
    candidates: List[CandidateApplicationResponse] = Field(..., description="List of candidate applications")
    total: int = Field(..., description="Total candidate count matching filters")
    limit: int = Field(..., description="Pagination limit")
    offset: int = Field(..., description="Pagination offset")


class CandidateStatsResponse(BaseModel):
    """Aggregated statistics for candidates dashboard."""
    total_applications: int = Field(..., description="Total number of applications")
    by_status: Dict[str, int] = Field(..., description="Count of applications grouped by status")
    by_channel: Dict[str, int] = Field(..., description="Count of applications grouped by channel")
    avg_match_score: float = Field(..., description="Average match score across scored applications")
    with_cv_count: int = Field(..., description="Number of candidates who uploaded a CV")
