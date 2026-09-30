"""
Session repository for Company Bot.
Handles chat session database operations.
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy import select, func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain.session import Session
from app.repositories.base import BaseRepository
from app.core.logging import get_logger
from app.core.database import get_session_context

logger = get_logger(__name__)


class SessionRepository(BaseRepository[Session, Dict[str, Any], Dict[str, Any]]):
    """
    Repository for Session model operations.
    
    Can be initialized with an existing session or will create one on demand.
    """
    
    def __init__(self, session: Optional[AsyncSession] = None):
        """
        Initialize repository with optional session.
        
        Args:
            session: Optional existing AsyncSession. If not provided,
                     a new session will be created on first operation.
        """
        self._session_context = None
        self._persistent_session = None
        
        if session:
            super().__init__(Session, session)
        else:
            # Initialize without session - will create on demand
            super().__init__(Session, None)
    
    async def _get_session(self) -> AsyncSession:
        """Get or create a session."""
        if self.session is not None:
            return self.session
        
        # Create a new session context
        self._session_context = get_session_context()
        self._persistent_session = await self._session_context.__aenter__()
        self.session = self._persistent_session
        return self.session
    
    async def close(self):
        """Close the session if it was created by this repository."""
        if self._session_context is not None:
            await self._session_context.__aexit__(None, None, None)
            self._session_context = None
            self._persistent_session = None
            self.session = None
    
    async def create_session(
        self,
        channel: str = "web",
        external_id: Optional[str] = None,
        language: str = "en",
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Session:
        """
        Create a new chat session.
        
        Args:
            channel: 'web' or 'whatsapp'
            external_id: Cookie ID or phone number
            language: Preferred language
            user_agent: Client user agent
            ip_address: Client IP address
            
        Returns:
            Created Session instance
        """
        session = Session(
            channel=channel,
            external_id=external_id,
            language=language,
            user_agent=user_agent,
            ip_address=ip_address,
            is_active=True,
            message_count=0,
        )
        
        db_session = await self._get_session()
        db_session.add(session)
        await db_session.flush()
        await db_session.refresh(session)
        
        logger.debug(
            "session_created",
            session_id=str(session.id),
            channel=channel,
            language=language
        )
        
        return session
    
    async def get_or_create_session(
        self,
        session_id: Optional[UUID] = None,
        channel: str = "web",
        external_id: Optional[str] = None,
        language: str = "en",
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Session:
        """
        Get existing session or create a new one.
        
        Args:
            session_id: Optional existing session ID
            channel: Channel for new session
            external_id: External identifier
            language: Language preference
            user_agent: Client user agent
            ip_address: Client IP address
            
        Returns:
            Session instance
        """
        if session_id:
            existing = await self.get_by_id(session_id)
            if existing and existing.is_active and not existing.opted_out:
                await self.touch_session(session_id)
                return existing
                
        if external_id:
            existing = await self.get_by_external_id(external_id, channel)
            if existing:
                if not existing.is_active or existing.opted_out:
                    logger.warning("session_found_but_inactive_reactivating", external_id=external_id, session_id=str(existing.id))
                    existing.is_active = True
                    existing.opted_out = False
                    
                logger.info("session_recovered_by_external_id", external_id=external_id, channel=channel, session_id=str(existing.id))
                await self.touch_session(existing.id)
                return existing
        
        return await self.create_session(
            channel=channel,
            external_id=external_id,
            language=language,
            user_agent=user_agent,
            ip_address=ip_address,
        )
    
    async def get_by_id(self, session_id: UUID) -> Optional[Session]:
        """Get session by ID."""
        db_session = await self._get_session()
        stmt = select(Session).where(Session.id == session_id)
        result = await db_session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def touch_session(self, session_id: UUID) -> Optional[Session]:
        """
        Update session last_active timestamp and increment message count.
        
        Args:
            session_id: Session UUID
            
        Returns:
            Updated session or None
        """
        db_session = await self._get_session()
        
        stmt = (
            update(Session)
            .where(Session.id == session_id)
            .values(
                last_active=datetime.utcnow(),
                message_count=Session.message_count + 1
            )
            .returning(Session)
        )
        
        result = await db_session.execute(stmt)
        await db_session.flush()
        
        return result.scalar_one_or_none()
    
    async def get_by_external_id(
        self,
        external_id: str,
        channel: str
    ) -> Optional[Session]:
        """
        Find session by external ID and channel.
        
        Args:
            external_id: Cookie ID or phone number
            channel: 'web' or 'whatsapp'
            
        Returns:
            Session instance or None
        """
        db_session = await self._get_session()
        
        stmt = (
            select(Session)
            .where(
                and_(
                    Session.external_id == external_id,
                    Session.channel == channel
                )
            )
            .order_by(Session.last_active.desc())
            .limit(1)
        )
        
        result = await db_session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_active_sessions(
        self,
        channel: Optional[str] = None,
        since: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Session]:
        """
        Get active sessions.
        
        Args:
            channel: Optional channel filter
            since: Optional time filter
            skip: Pagination offset
            limit: Maximum results
            
        Returns:
            List of active sessions
        """
        db_session = await self._get_session()
        
        stmt = select(Session).where(Session.is_active == True)
        
        if channel:
            stmt = stmt.where(Session.channel == channel)
        
        if since:
            stmt = stmt.where(Session.last_active >= since)
        
        stmt = stmt.order_by(Session.last_active.desc()).offset(skip).limit(limit)
        
        result = await db_session.execute(stmt)
        return list(result.scalars().all())
    
    async def count_active_sessions(
        self,
        channel: Optional[str] = None,
        since: Optional[datetime] = None
    ) -> int:
        """
        Count active sessions.
        
        Args:
            channel: Optional channel filter
            since: Optional time filter
            
        Returns:
            Active session count
        """
        db_session = await self._get_session()
        
        stmt = (
            select(func.count())
            .select_from(Session)
            .where(Session.is_active == True)
        )
        
        if channel:
            stmt = stmt.where(Session.channel == channel)
        
        if since:
            stmt = stmt.where(Session.last_active >= since)
        
        result = await db_session.execute(stmt)
        return result.scalar() or 0
    
    async def close_session(self, session_id: UUID) -> bool:
        """
        Mark a session as closed.
        
        Args:
            session_id: Session UUID
            
        Returns:
            True if updated
        """
        db_session = await self._get_session()
        
        stmt = (
            update(Session)
            .where(Session.id == session_id)
            .values(
                is_active=False,
                closed_at=datetime.utcnow()
            )
        )
        
        result = await db_session.execute(stmt)
        await db_session.flush()
        
        updated = result.rowcount > 0
        if updated:
            logger.debug("session_closed", session_id=str(session_id))
        
        return updated
    
    async def opt_out_session(self, session_id: UUID) -> bool:
        """
        Mark a WhatsApp session as opted out.
        
        Args:
            session_id: Session UUID
            
        Returns:
            True if updated
        """
        db_session = await self._get_session()
        
        stmt = (
            update(Session)
            .where(Session.id == session_id)
            .values(
                opted_out=True,
                is_active=False,
                closed_at=datetime.utcnow()
            )
        )
        
        result = await db_session.execute(stmt)
        await db_session.flush()
        
        updated = result.rowcount > 0
        if updated:
            logger.debug("session_opted_out", session_id=str(session_id))
        
        return updated
    
    async def opt_in_session(self, session_id: UUID) -> bool:
        """
        Mark a WhatsApp session as opted in.
        
        Args:
            session_id: Session UUID
            
        Returns:
            True if updated
        """
        db_session = await self._get_session()
        
        stmt = (
            update(Session)
            .where(Session.id == session_id)
            .values(
                opted_out=False,
                is_active=True,
                closed_at=None
            )
        )
        
        result = await db_session.execute(stmt)
        await db_session.flush()
        
        updated = result.rowcount > 0
        if updated:
            logger.debug("session_opted_in", session_id=str(session_id))
        
        return updated
    
    async def cleanup_expired_sessions(self, inactive_days: int = 7) -> int:
        """
        Close sessions inactive for specified days.
        
        Args:
            inactive_days: Days of inactivity to consider expired
            
        Returns:
            Number of sessions closed
        """
        db_session = await self._get_session()
        cutoff = datetime.utcnow() - timedelta(days=inactive_days)
        
        stmt = (
            update(Session)
            .where(
                and_(
                    Session.is_active == True,
                    Session.last_active < cutoff
                )
            )
            .values(
                is_active=False,
                closed_at=datetime.utcnow()
            )
        )
        
        result = await db_session.execute(stmt)
        await db_session.flush()
        
        closed = result.rowcount
        if closed > 0:
            logger.info("sessions_cleaned_up", closed=closed, cutoff=cutoff.isoformat())
        
        return closed
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """
        Get overall session statistics.
        
        Returns:
            Session statistics
        """
        db_session = await self._get_session()
        
        # Active sessions by channel
        active_stmt = select(
            Session.channel,
            func.count().label('count')
        ).where(
            Session.is_active == True
        ).group_by(Session.channel)
        
        active_result = await db_session.execute(active_stmt)
        active_by_channel = {row.channel: row.count for row in active_result}
        
        # Total sessions
        total_stmt = select(func.count()).select_from(Session)
        total_result = await db_session.execute(total_stmt)
        total = total_result.scalar() or 0
        
        # Opted-out count
        opted_out_stmt = select(func.count()).select_from(Session).where(
            Session.opted_out == True
        )
        opted_out_result = await db_session.execute(opted_out_stmt)
        opted_out = opted_out_result.scalar() or 0
        
        # Sessions created today
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_stmt = select(func.count()).select_from(Session).where(
            Session.created_at >= today
        )
        today_result = await db_session.execute(today_stmt)
        today_count = today_result.scalar() or 0
        
        return {
            'total_sessions': total,
            'active_sessions': sum(active_by_channel.values()),
            'active_by_channel': active_by_channel,
            'opted_out': opted_out,
            'created_today': today_count,
        }
