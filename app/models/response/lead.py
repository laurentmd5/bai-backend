"""
Lead response models for Company Bot admin API.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.domain.lead import LeadStatus


class CommercialLeadResponse(BaseModel):
    """Detailed commercial lead response model."""
    id: str = Field(..., description="Unique lead identifier (UUID)")
    session_id: Optional[str] = Field(None, description="Conversation session ID")
    channel: str = Field(default="web", description="Origination channel (web, whatsapp)")

    full_name: str = Field(..., description="Prospect full name or contact person")
    company_name: Optional[str] = Field(None, description="Company name if applicable")
    email: Optional[str] = Field(None, description="Prospect email address")
    phone_number: Optional[str] = Field(None, description="Prospect phone number")
    location: Optional[str] = Field(None, description="Project location, city or district")

    service_category: Optional[str] = Field(None, description="Identified service category (Vidéosurveillance, Solaire, etc.)")
    requirements_summary: str = Field(..., description="Detailed or summarized requirements")
    qualification_answers: Optional[Dict[str, Any]] = Field(None, description="Full answers captured during chat")

    status: LeadStatus = Field(..., description="Lead workflow status")
    notes: Optional[str] = Field(None, description="Internal sales notes")
    created_at: datetime = Field(..., description="Lead creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "e2b3c4d5-6f7a-8b9c-0d1e-2f3a4b5c6d7e",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "channel": "web",
                "full_name": "Laurent Mavoungou",
                "company_name": "MAB Services",
                "email": "laurent@example.com",
                "phone_number": "+221770000000",
                "location": "Dakar, Keur Gorgui",
                "service_category": "Vidéosurveillance",
                "requirements_summary": "Demande de devis pour 3 caméras extérieures analogiques 2 MP",
                "status": "new",
                "created_at": "2026-09-30T12:00:00Z",
                "updated_at": "2026-09-30T12:00:00Z"
            }
        }
    }


class CommercialLeadListResponse(BaseModel):
    """Paginated list of commercial leads."""
    leads: List[CommercialLeadResponse] = Field(..., description="List of commercial leads")
    total: int = Field(..., description="Total leads count matching filters")
    limit: int = Field(..., description="Pagination limit")
    offset: int = Field(..., description="Pagination offset")


class CommercialLeadStatsResponse(BaseModel):
    """Aggregated statistics for commercial leads dashboard."""
    total_leads: int = Field(..., description="Total number of leads")
    by_status: Dict[str, int] = Field(..., description="Count of leads grouped by status")
    by_channel: Dict[str, int] = Field(..., description="Count of leads grouped by channel")
    by_category: Dict[str, int] = Field(..., description="Count of leads grouped by service category")
