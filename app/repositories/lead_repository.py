"""
Commercial Lead repository for sales pipeline.
Handles persistence and querying of commercial leads and quote requests in PostgreSQL.
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import uuid

from sqlalchemy import select, func, update, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain.lead import CommercialLead, LeadStatus
from app.repositories.base import BaseRepository
from app.core.logging import get_logger
from app.core.database import get_session_context

logger = get_logger(__name__)


class CommercialLeadRepository(BaseRepository[CommercialLead, Dict[str, Any], Dict[str, Any]]):
    """
    Repository for CommercialLead database operations.
    """

    def __init__(self, session: Optional[AsyncSession] = None):
        self._session_context = None
        self._persistent_session = None

        if session:
            super().__init__(CommercialLead, session)
        else:
            super().__init__(CommercialLead, None)

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

    async def save_lead(
        self,
        full_name: str,
        requirements_summary: str,
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
        company_name: Optional[str] = None,
        location: Optional[str] = None,
        service_category: Optional[str] = None,
        session_id: Optional[str] = None,
        channel: str = "web",
        qualification_answers: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> CommercialLead:
        """
        Create and persist a new commercial lead.
        """
        session = await self._get_session()

        lead = CommercialLead(
            id=str(uuid.uuid4()),
            session_id=session_id,
            channel=channel,
            full_name=full_name,
            company_name=company_name,
            email=email,
            phone_number=phone_number,
            location=location,
            service_category=service_category,
            requirements_summary=requirements_summary,
            qualification_answers=qualification_answers,
            status=LeadStatus.NEW,
            notes=notes,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        session.add(lead)
        await session.commit()
        await session.refresh(lead)

        logger.info(
            "commercial_lead_saved",
            lead_id=lead.id,
            full_name=lead.full_name,
            service_category=lead.service_category,
            channel=lead.channel,
        )
        return lead

    async def get_by_id(self, lead_id: str) -> Optional[CommercialLead]:
        """Fetch lead by UUID."""
        session = await self._get_session()
        stmt = select(CommercialLead).where(CommercialLead.id == lead_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_leads(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[LeadStatus] = None,
        channel: Optional[str] = None,
        service_category: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Tuple[List[CommercialLead], int]:
        """
        List commercial leads with filtering, search, and pagination.
        Returns (list_of_leads, total_count).
        """
        session = await self._get_session()
        conditions = []

        if status:
            conditions.append(CommercialLead.status == status)
        if channel:
            conditions.append(CommercialLead.channel == channel.lower())
        if service_category:
            conditions.append(CommercialLead.service_category.ilike(f"%{service_category}%"))
        if search and search.strip():
            term = f"%{search.strip()}%"
            conditions.append(
                (CommercialLead.full_name.ilike(term)) |
                (CommercialLead.company_name.ilike(term)) |
                (CommercialLead.email.ilike(term)) |
                (CommercialLead.phone_number.ilike(term)) |
                (CommercialLead.requirements_summary.ilike(term))
            )

        # Count total
        count_stmt = select(func.count(CommercialLead.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one()

        # Query items
        stmt = select(CommercialLead)
        if conditions:
            stmt = stmt.where(and_(*conditions))

        order_col = CommercialLead.created_at
        if sort_order.lower() == "desc":
            stmt = stmt.order_by(desc(order_col))
        else:
            stmt = stmt.order_by(order_col)

        stmt = stmt.limit(limit).offset(offset)
        result = await session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def update_status(
        self,
        lead_id: str,
        status: LeadStatus,
        notes: Optional[str] = None,
    ) -> Optional[CommercialLead]:
        """Update lead status and optional notes."""
        session = await self._get_session()
        lead = await self.get_by_id(lead_id)
        if not lead:
            return None

        lead.status = status
        lead.updated_at = datetime.utcnow()
        if notes is not None:
            lead.notes = notes

        await session.commit()
        await session.refresh(lead)

        logger.info(
            "commercial_lead_status_updated",
            lead_id=lead_id,
            new_status=status.value,
        )
        return lead

    async def delete_lead(self, lead_id: str) -> bool:
        """Delete lead by ID."""
        session = await self._get_session()
        lead = await self.get_by_id(lead_id)
        if not lead:
            return False

        await session.delete(lead)
        await session.commit()
        logger.info("commercial_lead_deleted", lead_id=lead_id)
        return True

    async def get_stats(self) -> Dict[str, Any]:
        """Get aggregated metrics for the commercial dashboard."""
        session = await self._get_session()

        # Total leads count
        total_stmt = select(func.count(CommercialLead.id))
        total = (await session.execute(total_stmt)).scalar_one()

        # By status
        status_stmt = select(CommercialLead.status, func.count(CommercialLead.id)).group_by(CommercialLead.status)
        status_rows = (await session.execute(status_stmt)).all()
        by_status = {row[0].value if hasattr(row[0], 'value') else str(row[0]): row[1] for row in status_rows}

        # By channel
        channel_stmt = select(CommercialLead.channel, func.count(CommercialLead.id)).group_by(CommercialLead.channel)
        channel_rows = (await session.execute(channel_stmt)).all()
        by_channel = {str(row[0]): row[1] for row in channel_rows}

        # By category
        category_stmt = select(CommercialLead.service_category, func.count(CommercialLead.id)).where(CommercialLead.service_category.isnot(None)).group_by(CommercialLead.service_category)
        category_rows = (await session.execute(category_stmt)).all()
        by_category = {str(row[0]): row[1] for row in category_rows}

        return {
            "total_leads": total,
            "by_status": by_status,
            "by_channel": by_channel,
            "by_category": by_category,
        }
