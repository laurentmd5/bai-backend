"""
Admin candidate management endpoints for Company Bot.
Allows viewing, filtering, status tracking, statistics, and CSV export of recruitment applications.
"""

import csv
import io
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_admin
from app.core.database import get_session
from app.core.logging import get_logger
from app.models.domain.candidate import ApplicationStatus
from app.models.request.candidate import UpdateCandidateStatusRequest
from app.models.response.candidate import (
    CandidateApplicationResponse,
    CandidateListResponse,
    CandidateStatsResponse,
)
from app.repositories.candidate_repository import CandidateApplicationRepository

logger = get_logger(__name__)

router = APIRouter(prefix="/candidates", tags=["Admin Candidates Management"])


def get_candidate_repository(
    session: AsyncSession = Depends(get_session)
) -> CandidateApplicationRepository:
    """Dependency providing CandidateApplicationRepository bound to request session."""
    return CandidateApplicationRepository(session=session)


@router.get("", response_model=CandidateListResponse)
async def list_candidates(
    limit: int = Query(50, ge=1, le=100, description="Number of results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    status: Optional[ApplicationStatus] = Query(None, description="Filter by application status"),
    channel: Optional[str] = Query(None, description="Filter by channel (whatsapp, web)"),
    min_score: Optional[float] = Query(None, ge=0, le=100, description="Minimum AI CV match score"),
    search: Optional[str] = Query(None, description="Search query in full name, email or phone"),
    sort_by: str = Query("created_at", regex="^(created_at|match_score)$", description="Sort field"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sort direction"),
    current_admin: dict = Depends(get_current_admin),
    repo: CandidateApplicationRepository = Depends(get_candidate_repository),
) -> CandidateListResponse:
    """
    List candidate applications with pagination, search, and filtering.
    """
    try:
        items, total = await repo.list_applications(
            limit=limit,
            offset=offset,
            status=status,
            channel=channel,
            min_score=min_score,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        logger.info(
            "admin_candidates_listed",
            admin_id=current_admin.get("id"),
            total=total,
            returned=len(items),
        )

        return CandidateListResponse(
            candidates=[CandidateApplicationResponse.model_validate(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.error("admin_candidates_list_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve candidate applications",
        )


@router.get("/stats", response_model=CandidateStatsResponse)
async def get_candidates_stats(
    current_admin: dict = Depends(get_current_admin),
    repo: CandidateApplicationRepository = Depends(get_candidate_repository),
) -> CandidateStatsResponse:
    """
    Get aggregated recruitment statistics for dashboard display.
    """
    try:
        stats_data = await repo.get_stats()
        return CandidateStatsResponse(**stats_data)
    except Exception as exc:
        logger.error("admin_candidates_stats_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute recruitment statistics",
        )


@router.get("/export/csv")
async def export_candidates_csv(
    status: Optional[ApplicationStatus] = Query(None, description="Filter export by status"),
    channel: Optional[str] = Query(None, description="Filter export by channel"),
    min_score: Optional[float] = Query(None, ge=0, le=100, description="Minimum match score"),
    current_admin: dict = Depends(get_current_admin),
    repo: CandidateApplicationRepository = Depends(get_candidate_repository),
) -> Response:
    """
    Export candidate applications to downloadable CSV file.
    """
    try:
        items, _ = await repo.list_applications(
            limit=1000,
            offset=0,
            status=status,
            channel=channel,
            min_score=min_score,
        )

        output = io.StringIO()
        writer = csv.writer(output, delimiter=",", quoting=csv.QUOTE_MINIMAL)

        # Header row
        writer.writerow([
            "ID",
            "Nom Complet",
            "Email",
            "Téléphone",
            "Canal",
            "Statut",
            "Score Matching (%)",
            "Domaines",
            "Fichier CV",
            "Date Candidature",
            "Notes RH",
        ])

        # Data rows
        for c in items:
            writer.writerow([
                c.id,
                c.full_name,
                c.email or "",
                c.phone_number or "",
                c.channel,
                c.status.value if hasattr(c.status, "value") else str(c.status),
                f"{c.match_score:.1f}",
                ", ".join(c.target_domains or []),
                c.cv_filename or "",
                c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else "",
                c.notes or "",
            ])

        csv_content = output.getvalue().encode("utf-8-sig")  # BOM for Excel UTF-8 compatibility
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=candidatures_export.csv",
                "Cache-Control": "no-cache",
            },
        )
    except Exception as exc:
        logger.error("admin_candidates_csv_export_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate CSV export",
        )


@router.get("/{candidate_id}", response_model=CandidateApplicationResponse)
async def get_candidate_detail(
    candidate_id: str,
    current_admin: dict = Depends(get_current_admin),
    repo: CandidateApplicationRepository = Depends(get_candidate_repository),
) -> CandidateApplicationResponse:
    """
    Get detailed candidate application by ID (includes CV analysis and all 5 answers).
    """
    app = await repo.get_by_id(candidate_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate application not found",
        )

    return CandidateApplicationResponse.model_validate(app)


@router.patch("/{candidate_id}/status", response_model=CandidateApplicationResponse)
async def update_candidate_status(
    candidate_id: str,
    body: UpdateCandidateStatusRequest,
    current_admin: dict = Depends(get_current_admin),
    repo: CandidateApplicationRepository = Depends(get_candidate_repository),
) -> CandidateApplicationResponse:
    """
    Update candidate workflow status (e.g. prescreened -> shortlisted / rejected) and notes.
    """
    updated_app = await repo.update_status(
        application_id=candidate_id,
        status=body.status,
        notes=body.notes,
    )
    if not updated_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate application not found",
        )

    logger.info(
        "admin_candidate_status_changed",
        admin_id=current_admin.get("id"),
        candidate_id=candidate_id,
        new_status=body.status.value,
    )
    return CandidateApplicationResponse.model_validate(updated_app)


@router.delete("/{candidate_id}")
async def delete_candidate(
    candidate_id: str,
    current_admin: dict = Depends(get_current_admin),
    repo: CandidateApplicationRepository = Depends(get_candidate_repository),
) -> Dict[str, Any]:
    """
    Delete a candidate application.
    """
    success = await repo.delete_application(candidate_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate application not found",
        )

    logger.info(
        "admin_candidate_deleted",
        admin_id=current_admin.get("id"),
        candidate_id=candidate_id,
    )
    return {"success": True, "message": "Candidate application deleted successfully"}
