"""
Candidate Application repository for recruitment pipeline.
Handles persistence of candidate screening interviews and CV profiles in PostgreSQL.
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import uuid

from sqlalchemy import select, func, update, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain.candidate import CandidateApplication, ApplicationStatus
from app.repositories.base import BaseRepository
from app.core.logging import get_logger
from app.core.database import get_session_context

logger = get_logger(__name__)


class CandidateApplicationRepository(BaseRepository[CandidateApplication, Dict[str, Any], Dict[str, Any]]):
    """
    Repository for CandidateApplication database operations.
    """

    def __init__(self, session: Optional[AsyncSession] = None):
        self._session_context = None
        self._persistent_session = None

        if session:
            super().__init__(CandidateApplication, session)
        else:
            super().__init__(CandidateApplication, None)

    async def _get_session(self) -> AsyncSession:
        """Get or create an AsyncSession."""
        if self.session is not None:
            return self.session

        self._session_context = get_session_context()
        self._persistent_session = await self._session_context.__aenter__()
        self.session = self._persistent_session
        return self.session

    async def close(self):
        """Close the session if created by this repository."""
        if self._session_context is not None:
            await self._session_context.__aexit__(None, None, None)
            self._session_context = None
            self.session = None

    async def save_application(
        self,
        full_name: str,
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
        session_id: Optional[str] = None,
        channel: str = "whatsapp",
        answers: Optional[Dict[str, Any]] = None,
        parsed_cv: Optional[Dict[str, Any]] = None,
        cv_filename: Optional[str] = None,
        raw_cv_text: Optional[str] = None,
        match_score: float = 0.0,
        target_domains: Optional[List[str]] = None,
        status: ApplicationStatus = ApplicationStatus.PRESCREENED,
        notes: Optional[str] = None,
    ) -> CandidateApplication:
        """
        Create or update a candidate application in PostgreSQL.
        """
        db_session = await self._get_session()

        # Check if an application already exists for this session or phone
        existing = None
        if session_id:
            stmt = select(CandidateApplication).where(CandidateApplication.session_id == session_id)
            res = await db_session.execute(stmt)
            existing = res.scalar_one_or_none()

        if not existing and phone_number:
            stmt = (
                select(CandidateApplication)
                .where(CandidateApplication.phone_number == phone_number)
                .order_by(desc(CandidateApplication.created_at))
                .limit(1)
            )
            res = await db_session.execute(stmt)
            existing = res.scalar_one_or_none()

        if existing:
            # Update existing record
            existing.full_name = full_name or existing.full_name
            if phone_number:
                existing.phone_number = phone_number
            if email:
                existing.email = email
            if channel:
                existing.channel = channel
            if answers:
                existing.answers_json = answers
            if parsed_cv:
                existing.parsed_profile = parsed_cv
            if cv_filename:
                existing.cv_filename = cv_filename
            if raw_cv_text:
                existing.raw_cv_text = raw_cv_text
            if match_score > 0:
                existing.match_score = match_score
            if target_domains:
                existing.target_domains = target_domains
            existing.status = status
            if notes:
                existing.notes = notes
            existing.updated_at = datetime.utcnow()

            await db_session.flush()
            logger.info(
                "candidate_application_updated",
                candidate_id=existing.id,
                full_name=existing.full_name,
                phone=phone_number,
                status=status.value
            )
            return existing
        else:
            # Create new record
            app_id = str(uuid.uuid4())
            new_app = CandidateApplication(
                id=app_id,
                session_id=session_id,
                channel=channel,
                full_name=full_name or "Candidat",
                email=email,
                phone_number=phone_number,
                cv_filename=cv_filename,
                raw_cv_text=raw_cv_text,
                parsed_profile=parsed_cv,
                answers_json=answers or {},
                match_score=match_score,
                target_domains=target_domains or [],
                status=status,
                notes=notes,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db_session.add(new_app)
            await db_session.flush()
            logger.info(
                "candidate_application_created",
                candidate_id=app_id,
                full_name=new_app.full_name,
                phone=phone_number,
                status=status.value
            )
            return new_app

    async def get_by_id(self, application_id: str) -> Optional[CandidateApplication]:
        """Find application by ID."""
        db_session = await self._get_session()
        stmt = select(CandidateApplication).where(CandidateApplication.id == application_id)
        res = await db_session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_applications(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[ApplicationStatus] = None,
        channel: Optional[str] = None,
        min_score: Optional[float] = None,
        search: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Tuple[List[CandidateApplication], int]:
        """
        List candidate applications with filtering, search, and pagination.
        Returns (list_of_candidates, total_count).
        """
        db_session = await self._get_session()
        
        conditions = []
        if status is not None:
            conditions.append(CandidateApplication.status == status)
        if channel:
            conditions.append(CandidateApplication.channel == channel.lower())
        if min_score is not None:
            conditions.append(CandidateApplication.match_score >= min_score)
        if search and search.strip():
            term = f"%{search.strip()}%"
            conditions.append(
                (CandidateApplication.full_name.ilike(term)) |
                (CandidateApplication.email.ilike(term)) |
                (CandidateApplication.phone_number.ilike(term))
            )
            
        # Count query
        count_stmt = select(func.count(CandidateApplication.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        count_res = await db_session.execute(count_stmt)
        total = count_res.scalar() or 0
        
        # Data query
        stmt = select(CandidateApplication)
        if conditions:
            stmt = stmt.where(and_(*conditions))
            
        # Sorting
        if sort_by == "match_score":
            order_col = CandidateApplication.match_score
        else:
            order_col = CandidateApplication.created_at
            
        if sort_order.lower() == "asc":
            stmt = stmt.order_by(order_col.asc())
        else:
            stmt = stmt.order_by(order_col.desc())
            
        stmt = stmt.offset(offset).limit(limit)
        res = await db_session.execute(stmt)
        items = list(res.scalars().all())
        
        return items, total

    async def update_status(
        self,
        application_id: str,
        status: ApplicationStatus,
        notes: Optional[str] = None
    ) -> Optional[CandidateApplication]:
        """Update status and optional recruiter notes."""
        db_session = await self._get_session()
        app = await self.get_by_id(application_id)
        if not app:
            return None
            
        app.status = status
        if notes is not None:
            app.notes = notes
        app.updated_at = datetime.utcnow()
        await db_session.flush()
        
        logger.info(
            "candidate_status_updated",
            candidate_id=application_id,
            status=status.value
        )
        return app

    async def delete_application(self, application_id: str) -> bool:
        """Delete candidate application by ID."""
        db_session = await self._get_session()
        app = await self.get_by_id(application_id)
        if not app:
            return False
            
        await db_session.delete(app)
        await db_session.flush()
        logger.info("candidate_deleted", candidate_id=application_id)
        return True

    async def get_stats(self) -> Dict[str, Any]:
        """Aggregate stats for admin dashboard."""
        db_session = await self._get_session()
        
        # Total count
        total_stmt = select(func.count(CandidateApplication.id))
        total_res = await db_session.execute(total_stmt)
        total = total_res.scalar() or 0
        
        # By status
        status_stmt = select(CandidateApplication.status, func.count(CandidateApplication.id)).group_by(CandidateApplication.status)
        status_res = await db_session.execute(status_stmt)
        by_status = {str(row[0].value if hasattr(row[0], "value") else row[0]): row[1] for row in status_res.all()}
        
        # By channel
        channel_stmt = select(CandidateApplication.channel, func.count(CandidateApplication.id)).group_by(CandidateApplication.channel)
        channel_res = await db_session.execute(channel_stmt)
        by_channel = {str(row[0]): row[1] for row in channel_res.all()}
        
        # Average match score (where score > 0)
        avg_stmt = select(func.avg(CandidateApplication.match_score)).where(CandidateApplication.match_score > 0)
        avg_res = await db_session.execute(avg_stmt)
        avg_score = float(avg_res.scalar() or 0.0)
        
        # Count with CV
        cv_stmt = select(func.count(CandidateApplication.id)).where(CandidateApplication.cv_filename.isnot(None))
        cv_res = await db_session.execute(cv_stmt)
        cv_count = cv_res.scalar() or 0
        
        return {
            "total_applications": total,
            "by_status": by_status,
            "by_channel": by_channel,
            "avg_match_score": round(avg_score, 1),
            "with_cv_count": cv_count
        }
