"""
Admin commercial leads management endpoints for Company Bot.
Allows viewing, filtering, status tracking, statistics, and CSV export of commercial prospects / quote requests.
"""

import csv
import io
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_admin
from app.core.database import get_session
from app.core.logging import get_logger
from app.models.domain.lead import LeadStatus
from app.models.request.lead import UpdateLeadStatusRequest
from app.models.response.lead import (
    CommercialLeadResponse,
    CommercialLeadListResponse,
    CommercialLeadStatsResponse,
)
from app.repositories.lead_repository import CommercialLeadRepository

logger = get_logger(__name__)

router = APIRouter(prefix="/leads", tags=["Admin Commercial Leads Management"])


def get_lead_repository(
    session: AsyncSession = Depends(get_session)
) -> CommercialLeadRepository:
    """Dependency providing CommercialLeadRepository bound to request session."""
    return CommercialLeadRepository(session=session)


@router.get("", response_model=CommercialLeadListResponse)
async def list_leads(
    limit: int = Query(50, ge=1, le=100, description="Number of results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    status: Optional[LeadStatus] = Query(None, description="Filter by lead status"),
    channel: Optional[str] = Query(None, description="Filter by channel (web, whatsapp)"),
    category: Optional[str] = Query(None, description="Filter by service category"),
    search: Optional[str] = Query(None, description="Search query in full name, company, email, phone or need"),
    sort_by: str = Query("created_at", regex="^(created_at)$", description="Sort field"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sort direction"),
    current_admin: dict = Depends(get_current_admin),
    repo: CommercialLeadRepository = Depends(get_lead_repository),
) -> CommercialLeadListResponse:
    """
    List commercial leads with pagination, search, and filtering.
    """
    try:
        items, total = await repo.list_leads(
            limit=limit,
            offset=offset,
            status=status,
            channel=channel,
            service_category=category,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        logger.info(
            "admin_leads_listed",
            admin_id=current_admin.get("id"),
            total=total,
            returned=len(items),
        )

        return CommercialLeadListResponse(
            leads=[CommercialLeadResponse.model_validate(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.error("admin_leads_list_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve commercial leads",
        )


@router.get("/stats", response_model=CommercialLeadStatsResponse)
async def get_leads_stats(
    current_admin: dict = Depends(get_current_admin),
    repo: CommercialLeadRepository = Depends(get_lead_repository),
) -> CommercialLeadStatsResponse:
    """
    Get aggregated commercial statistics for admin dashboard display.
    """
    try:
        stats_data = await repo.get_stats()
        return CommercialLeadStatsResponse(**stats_data)
    except Exception as exc:
        logger.error("admin_leads_stats_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute commercial leads statistics",
        )


@router.get("/export/csv")
async def export_leads_csv(
    status: Optional[LeadStatus] = Query(None, description="Filter export by status"),
    channel: Optional[str] = Query(None, description="Filter export by channel"),
    category: Optional[str] = Query(None, description="Filter export by service category"),
    current_admin: dict = Depends(get_current_admin),
    repo: CommercialLeadRepository = Depends(get_lead_repository),
) -> Response:
    """
    Export commercial leads to downloadable CSV file.
    """
    try:
        items, _ = await repo.list_leads(
            limit=1000,
            offset=0,
            status=status,
            channel=channel,
            service_category=category,
        )

        output = io.StringIO()
        writer = csv.writer(output, delimiter=",", quoting=csv.QUOTE_MINIMAL)

        # Header row
        writer.writerow([
            "ID",
            "Nom / Contact",
            "Entreprise",
            "Email",
            "Téléphone",
            "Ville / Site",
            "Catégorie",
            "Canal",
            "Statut",
            "Besoin Résumé",
            "Date Demande",
            "Notes Commerciales",
        ])

        # Data rows
        for lead in items:
            writer.writerow([
                lead.id,
                lead.full_name,
                lead.company_name or "",
                lead.email or "",
                lead.phone_number or "",
                lead.location or "",
                lead.service_category or "",
                lead.channel,
                lead.status.value if hasattr(lead.status, "value") else str(lead.status),
                (lead.requirements_summary or "").replace("\n", " "),
                lead.created_at.strftime("%Y-%m-%d %H:%M:%S") if lead.created_at else "",
                (lead.notes or "").replace("\n", " "),
            ])

        csv_content = output.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=prospects_commerciaux.csv",
                "Cache-Control": "no-cache",
            },
        )
    except Exception as exc:
        logger.error("admin_leads_csv_export_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate CSV export",
        )


@router.get("/{lead_id}", response_model=CommercialLeadResponse)
async def get_lead_detail(
    lead_id: str,
    current_admin: dict = Depends(get_current_admin),
    repo: CommercialLeadRepository = Depends(get_lead_repository),
) -> CommercialLeadResponse:
    """
    Get detailed commercial lead by ID.
    """
    lead = await repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Commercial lead not found",
        )

    return CommercialLeadResponse.model_validate(lead)


@router.patch("/{lead_id}/status", response_model=CommercialLeadResponse)
async def update_lead_status(
    lead_id: str,
    body: UpdateLeadStatusRequest,
    current_admin: dict = Depends(get_current_admin),
    repo: CommercialLeadRepository = Depends(get_lead_repository),
) -> CommercialLeadResponse:
    """
    Update lead workflow status (e.g. new -> contacted / qualified) and sales notes.
    """
    updated_lead = await repo.update_status(
        lead_id=lead_id,
        status=body.status,
        notes=body.notes,
    )
    if not updated_lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Commercial lead not found",
        )

    logger.info(
        "admin_lead_status_changed",
        admin_id=current_admin.get("id"),
        lead_id=lead_id,
        new_status=body.status.value,
    )
    return CommercialLeadResponse.model_validate(updated_lead)


@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: str,
    current_admin: dict = Depends(get_current_admin),
    repo: CommercialLeadRepository = Depends(get_lead_repository),
) -> Dict[str, Any]:
    """
    Delete a commercial lead.
    """
    success = await repo.delete_lead(lead_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Commercial lead not found",
        )

    logger.info(
        "admin_lead_deleted",
        admin_id=current_admin.get("id"),
        lead_id=lead_id,
    )
    return {"success": True, "message": "Commercial lead deleted successfully"}
