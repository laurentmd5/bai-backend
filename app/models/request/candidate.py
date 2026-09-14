"""
Candidate request models for Company Bot admin API.
"""

from typing import Optional
from pydantic import BaseModel, Field

from app.models.domain.candidate import ApplicationStatus


class UpdateCandidateStatusRequest(BaseModel):
    """Request body for updating candidate application status and notes."""
    status: ApplicationStatus = Field(..., description="Target application workflow status")
    notes: Optional[str] = Field(None, max_length=2000, description="Internal recruiter notes or evaluation feedback")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "shortlisted",
                "notes": "Profil solide en administration réseau et configuration routeurs. Convoquer pour test technique."
            }
        }
    }
