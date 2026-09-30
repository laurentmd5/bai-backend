"""
Lead request models for Company Bot admin API.
"""

from typing import Optional
from pydantic import BaseModel, Field

from app.models.domain.lead import LeadStatus


class UpdateLeadStatusRequest(BaseModel):
    """Request body for updating lead status and notes."""
    status: LeadStatus = Field(..., description="Target lead workflow status")
    notes: Optional[str] = Field(None, max_length=2000, description="Internal sales notes or follow-up feedback")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "contacted",
                "notes": "Client contacté par téléphone. Devis pour 3 caméras extérieures envoyé par email."
            }
        }
    }
