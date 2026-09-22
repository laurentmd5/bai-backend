"""
Conversation repository for Company Bot.
Handles conversation-specific database operations.
"""

from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.database import get_session_context
from app.models.domain.conversation import Conversation
from app.repositories.base import BaseRepository
from app.models.request.chat import ChatMessageRequest, ChatFeedbackRequest
from app.models.response.chat import ChatSourceResponse
from app.core.logging import get_logger

logger = get_logger(__name__)


class ConversationRepository(BaseRepository[Conversation, ChatMessageRequest, Dict[str, Any]]):
    """
    Repository for Conversation model operations.
    Extends base repository with conversation-specific queries.
    
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
            super().__init__(Conversation, session)
        else:
            super().__init__(Conversation, None)
    
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
    
    async def create_conversation(
        self,
        session_id: UUID,
        user_message: str,
        bot_response: str,
        channel: str = "web",
        sources: Optional[List[Dict[str, Any]]] = None,
        confidence: Optional[float] = None,
        latency_ms: Optional[int] = None,
        cache_hit: bool = False,
        llm_model: Optional[str] = None,
        llm_tokens_used: Optional[int] = None,
        fallback_triggered: bool = False,
        validation_failed: bool = False,
    ) -> Conversation:
        """
        Create a new conversation record with full metadata.
        
        Args:
            session_id: Session UUID
            user_message: Original user message
            bot_response: Generated bot response
            channel: 'web' or 'whatsapp'
            sources: RAG source documents
            confidence: Confidence score
            latency_ms: Response latency
            cache_hit: Whether response came from cache
            llm_model: LLM model used
            llm_tokens_used: Tokens consumed
            fallback_triggered: Whether fallback was used
            validation_failed: Whether validation failed
            
        Returns:
            Created Conversation instance
        """
        db_session = await self._get_session()
        
        conversation = Conversation(
            session_id=session_id,
            user_message=user_message,
            bot_response=bot_response,
            channel=channel,
            sources=sources,
            confidence=confidence,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            llm_model=llm_model,
            llm_tokens_used=llm_tokens_used,
            fallback_triggered=fallback_triggered,
            validation_failed=validation_failed,
        )
        
        db_session.add(conversation)
        await db_session.flush()
        await db_session.refresh(conversation)
        
        logger.debug(
            "conversation_created",
            conversation_id=str(conversation.id),
            session_id=str(session_id),
            channel=channel,
            cache_hit=cache_hit
        )
        
        return conversation
    
    async def get_by_session(
        self,
        session_id: UUID,
        skip: int = 0,
        limit: int = 50
    ) -> List[Conversation]:
        """
        Get all conversations for a session.
        
        Args:
            session_id: Session UUID
            skip: Pagination offset
            limit: Maximum results
            
        Returns:
            List of conversations ordered by created_at
        """
        db_session = await self._get_session()
        
        stmt = (
            select(Conversation)
            .where(Conversation.session_id == session_id)
            .order_by(Conversation.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        
        result = await db_session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_recent_by_session(
        self,
        session_id: UUID,
        limit: int = 10
    ) -> List[Conversation]:
        """
        Get the most recent conversations for a session in chronological order (oldest to newest).
        
        Args:
            session_id: Session UUID
            limit: Maximum recent results to fetch
            
        Returns:
            List of recent conversations in chronological order (oldest to newest)
        """
        db_session = await self._get_session()
        
        stmt = (
            select(Conversation)
            .where(Conversation.session_id == session_id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        
        result = await db_session.execute(stmt)
        recent_desc = list(result.scalars().all())
        # Return reversed so oldest is first and newest is last (natural conversation flow)
        return list(reversed(recent_desc))
    
    async def count_by_session(self, session_id: UUID) -> int:
        """
        Count conversations in a session.
        
        Args:
            session_id: Session UUID
            
        Returns:
            Total count
        """
        db_session = await self._get_session()
        
        stmt = (
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.session_id == session_id)
        )
        
        result = await db_session.execute(stmt)
        return result.scalar() or 0
    
    async def update_feedback(
        self,
        conversation_id: UUID,
        feedback: int,
        session_id: Optional[UUID] = None
    ) -> bool:
        """
        Update feedback for a conversation.
        
        Args:
            conversation_id: Conversation UUID
            feedback: 1 for positive, -1 for negative
            session_id: Optional session ID for validation
            
        Returns:
            True if updated, False if not found
        """
        from sqlalchemy import update
        
        db_session = await self._get_session()
        
        stmt = (
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(feedback=feedback)
        )
        
        if session_id:
            stmt = stmt.where(Conversation.session_id == session_id)
        
        result = await db_session.execute(stmt)
        await db_session.flush()
        
        updated = result.rowcount > 0
        if updated:
            logger.debug(
                "conversation_feedback_updated",
                conversation_id=str(conversation_id),
                feedback=feedback
            )
        
        return updated
    
    async def get_feedback_stats(
        self,
        session_id: Optional[UUID] = None,
        channel: Optional[str] = None,
        since: Optional[datetime] = None
    ) -> Dict[str, int]:
        """
        Get feedback statistics.
        
        Args:
            session_id: Optional session filter
            channel: Optional channel filter
            since: Optional time filter
            
        Returns:
            Dict with positive, negative, and total counts
        """
        db_session = await self._get_session()
        
        stmt = select(
            func.count().filter(Conversation.feedback == 1).label('positive'),
            func.count().filter(Conversation.feedback == -1).label('negative'),
            func.count().label('total')
        ).select_from(Conversation)
        
        if session_id:
            stmt = stmt.where(Conversation.session_id == session_id)
        
        if channel:
            stmt = stmt.where(Conversation.channel == channel)
        
        if since:
            stmt = stmt.where(Conversation.created_at >= since)
        
        result = await db_session.execute(stmt)
        row = result.one()
        
        return {
            'positive': row.positive,
            'negative': row.negative,
            'total': row.total,
            'neutral': row.total - row.positive - row.negative
        }
    
    async def search_conversations(
        self,
        query: Optional[str] = None,
        session_id: Optional[UUID] = None,
        channel: Optional[str] = None,
        feedback: Optional[int] = None,
        cache_hit: Optional[bool] = None,
        fallback_triggered: Optional[bool] = None,
        min_confidence: Optional[float] = None,
        max_confidence: Optional[float] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Tuple[List[Conversation], int]:
        """
        Advanced search for conversations with multiple filters.
        
        Returns:
            Tuple of (conversations, total_count)
        """
        db_session = await self._get_session()
        
        # Build base query
        stmt = select(Conversation)
        count_stmt = select(func.count()).select_from(Conversation)
        
        # Apply filters
        filters = []
        
        if query:
            filters.append(
                or_(
                    Conversation.user_message.ilike(f"%{query}%"),
                    Conversation.bot_response.ilike(f"%{query}%")
                )
            )
        
        if session_id:
            filters.append(Conversation.session_id == session_id)
        
        if channel:
            filters.append(Conversation.channel == channel)
        
        if feedback is not None:
            filters.append(Conversation.feedback == feedback)
        
        if cache_hit is not None:
            filters.append(Conversation.cache_hit == cache_hit)
        
        if fallback_triggered is not None:
            filters.append(Conversation.fallback_triggered == fallback_triggered)
        
        if min_confidence is not None:
            filters.append(Conversation.confidence >= min_confidence)
        
        if max_confidence is not None:
            filters.append(Conversation.confidence <= max_confidence)
        
        if start_date:
            filters.append(Conversation.created_at >= start_date)
        
        if end_date:
            filters.append(Conversation.created_at <= end_date)
        
        if filters:
            stmt = stmt.where(and_(*filters))
            count_stmt = count_stmt.where(and_(*filters))
        
        # Get total count
        count_result = await db_session.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # Apply sorting
        if hasattr(Conversation, sort_by):
            order_column = getattr(Conversation, sort_by)
            if sort_order == "desc":
                stmt = stmt.order_by(order_column.desc())
            else:
                stmt = stmt.order_by(order_column.asc())
        
        # Apply pagination
        stmt = stmt.offset(skip).limit(limit)
        
        # Execute
        result = await db_session.execute(stmt)
        conversations = list(result.scalars().all())
        
        return conversations, total
    
    async def get_daily_stats(
        self,
        days: int = 7,
        channel: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get daily conversation statistics.
        
        Args:
            days: Number of days to include
            channel: Optional channel filter
            
        Returns:
            List of daily stats
        """
        db_session = await self._get_session()
        since = datetime.utcnow() - timedelta(days=days)
        
        stmt = select(
            func.date_trunc('day', Conversation.created_at).label('day'),
            Conversation.channel,
            func.count().label('total'),
            func.avg(Conversation.confidence).label('avg_confidence'),
            func.avg(Conversation.latency_ms).label('avg_latency'),
            func.count().filter(Conversation.cache_hit == True).label('cache_hits'),
            func.count().filter(Conversation.fallback_triggered == True).label('fallbacks'),
            func.count().filter(Conversation.feedback == 1).label('positive_feedback'),
            func.count().filter(Conversation.feedback == -1).label('negative_feedback'),
        ).select_from(Conversation).where(Conversation.created_at >= since)
        
        if channel:
            stmt = stmt.where(Conversation.channel == channel)
        
        stmt = stmt.group_by(
            func.date_trunc('day', Conversation.created_at),
            Conversation.channel
        ).order_by(text('day DESC'))
        
        result = await db_session.execute(stmt)
        
        stats = []
        for row in result:
            stats.append({
                'day': row.day.isoformat() if row.day else None,
                'channel': row.channel,
                'total': row.total,
                'avg_confidence': round(row.avg_confidence, 3) if row.avg_confidence else None,
                'avg_latency': round(row.avg_latency, 0) if row.avg_latency else None,
                'cache_hits': row.cache_hits,
                'fallbacks': row.fallbacks,
                'positive_feedback': row.positive_feedback,
                'negative_feedback': row.negative_feedback,
            })
        
        return stats
    
    async def get_top_questions(
        self,
        limit: int = 20,
        days: int = 7,
        channel: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get most frequently asked questions.
        
        Args:
            limit: Maximum number of results
            days: Time window in days
            channel: Optional channel filter
            
        Returns:
            List of top questions with stats
        """
        db_session = await self._get_session()
        since = datetime.utcnow() - timedelta(days=days)
        
        stmt = select(
            func.left(Conversation.user_message, 100).label('question_preview'),
            func.count().label('frequency'),
            func.avg(Conversation.confidence).label('avg_confidence'),
            func.count().filter(Conversation.feedback == 1).label('positive_feedback'),
            func.count().filter(Conversation.feedback == -1).label('negative_feedback'),
        ).select_from(Conversation).where(Conversation.created_at >= since)
        
        if channel:
            stmt = stmt.where(Conversation.channel == channel)
        
        stmt = stmt.group_by(
            func.left(Conversation.user_message, 100)
        ).order_by(text('frequency DESC')).limit(limit)
        
        result = await db_session.execute(stmt)
        
        questions = []
        for row in result:
            questions.append({
                'question_preview': row.question_preview,
                'frequency': row.frequency,
                'avg_confidence': round(row.avg_confidence, 3) if row.avg_confidence else None,
                'positive_feedback': row.positive_feedback,
                'negative_feedback': row.negative_feedback,
                'satisfaction_rate': round(
                    row.positive_feedback / (row.positive_feedback + row.negative_feedback) * 100, 1
                ) if (row.positive_feedback + row.negative_feedback) > 0 else None
            })
        
        return questions
    
    async def get_latency_percentiles(
        self,
        days: int = 7,
        channel: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Get latency percentiles.
        
        Args:
            days: Time window in days
            channel: Optional channel filter
            
        Returns:
            Dict with p50, p90, p95, p99 values
        """
        db_session = await self._get_session()
        since = datetime.utcnow() - timedelta(days=days)
        
        stmt = select(
            func.percentile_cont(0.50).within_group(Conversation.latency_ms).label('p50'),
            func.percentile_cont(0.90).within_group(Conversation.latency_ms).label('p90'),
            func.percentile_cont(0.95).within_group(Conversation.latency_ms).label('p95'),
            func.percentile_cont(0.99).within_group(Conversation.latency_ms).label('p99'),
            func.min(Conversation.latency_ms).label('min'),
            func.max(Conversation.latency_ms).label('max'),
            func.avg(Conversation.latency_ms).label('avg'),
        ).select_from(Conversation).where(
            and_(
                Conversation.created_at >= since,
                Conversation.latency_ms.isnot(None)
            )
        )
        
        if channel:
            stmt = stmt.where(Conversation.channel == channel)
        
        result = await db_session.execute(stmt)
        row = result.one()
        
        return {
            'p50': round(row.p50, 2) if row.p50 else None,
            'p90': round(row.p90, 2) if row.p90 else None,
            'p95': round(row.p95, 2) if row.p95 else None,
            'p99': round(row.p99, 2) if row.p99 else None,
            'min': round(row.min, 2) if row.min else None,
            'max': round(row.max, 2) if row.max else None,
            'avg': round(row.avg, 2) if row.avg else None,
        }
    
    async def get_cache_stats(
        self,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get cache hit statistics.
        
        Args:
            days: Time window in days
            
        Returns:
            Cache statistics
        """
        db_session = await self._get_session()
        since = datetime.utcnow() - timedelta(days=days)
        
        stmt = select(
            func.count().label('total'),
            func.count().filter(Conversation.cache_hit == True).label('hits'),
            func.count().filter(Conversation.cache_hit == False).label('misses'),
        ).select_from(Conversation).where(Conversation.created_at >= since)
        
        result = await db_session.execute(stmt)
        row = result.one()
        
        hit_rate = (row.hits / row.total * 100) if row.total > 0 else 0
        
        return {
            'total': row.total,
            'hits': row.hits,
            'misses': row.misses,
            'hit_rate': round(hit_rate, 2),
        }
