"""
Analytics Service for BARROW.AI.
Provides comprehensive analytics, metrics aggregation, and reporting.
"""

from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from uuid import UUID
from enum import Enum

from app.core.logging import get_logger
from app.core.exceptions import ValidationException
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.cache.redis_cache import cache_service, CacheNamespace

logger = get_logger(__name__)


class TimePeriod(str, Enum):
    """Time periods for analytics aggregation."""
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class AnalyticsService:
    """
    Analytics service for BARROW.AI dashboard.
    
    Provides:
    - Overview metrics (KPIs)
    - Conversation trends
    - Sentiment analysis
    - Latency analytics
    - Top questions
    - Geographic distribution
    - Cache performance
    - Knowledge base usage
    - Export capabilities
    """
    
    def __init__(
        self,
        conversation_repository: ConversationRepository,
        session_repository: SessionRepository,
        knowledge_repository: KnowledgeRepository,
    ):
        """
        Initialize analytics service.
        
        Args:
            conversation_repository: Repository for conversations
            session_repository: Repository for sessions
            knowledge_repository: Repository for knowledge documents
        """
        self._conversation_repo = conversation_repository
        self._session_repo = session_repository
        self._knowledge_repo = knowledge_repository
    
    # =========================================================================
    # TIME PERIOD UTILITIES
    # =========================================================================
    
    def _get_period_days(self, period: str) -> int:
        """
        Convert period string to number of days.
        
        Args:
            period: Time period (24h, 7d, 30d, 90d)
            
        Returns:
            Number of days
        """
        period_map = {
            "24h": 1,
            "7d": 7,
            "30d": 30,
            "90d": 90,
            "1y": 365,
        }
        return period_map.get(period, 7)
    
    def _get_date_range(self, period: str) -> Tuple[datetime, datetime]:
        """
        Get date range for a period.
        
        Args:
            period: Time period
            
        Returns:
            Tuple of (start_date, end_date)
        """
        days = self._get_period_days(period)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        return start_date, end_date
    
    # =========================================================================
    # OVERVIEW METRICS
    # =========================================================================
    
    async def get_overview(
        self,
        period: str = "7d",
    ) -> Dict[str, Any]:
        """
        Get dashboard overview metrics.
        
        Args:
            period: Time period (24h, 7d, 30d, 90d)
            
        Returns:
            Overview metrics dict
        """
        start_date, end_date = self._get_date_range(period)
        
        # Get conversation stats
        daily_stats = await self._conversation_repo.get_daily_stats(
            days=self._get_period_days(period),
        )
        
        # Aggregate metrics
        total_conversations = sum(stat.get("total", 0) for stat in daily_stats)
        total_cache_hits = sum(stat.get("cache_hits", 0) for stat in daily_stats)
        total_fallbacks = sum(stat.get("fallbacks", 0) for stat in daily_stats)
        positive_feedback = sum(stat.get("positive_feedback", 0) for stat in daily_stats)
        negative_feedback = sum(stat.get("negative_feedback", 0) for stat in daily_stats)
        
        # Average confidence
        confidences = [stat.get("avg_confidence", 0) for stat in daily_stats if stat.get("avg_confidence")]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        # Active sessions
        active_sessions = await self._session_repo.count_active_sessions(since=start_date)
        
        # Channel distribution
        channel_stats = {}
        for stat in daily_stats:
            channel = stat.get("channel", "unknown")
            if channel not in channel_stats:
                channel_stats[channel] = 0
            channel_stats[channel] += stat.get("total", 0)
        
        # Language distribution (from sessions)
        sessions = await self._session_repo.get_active_sessions(limit=1000)
        language_stats = {}
        for session in sessions:
            lang = session.language
            language_stats[lang] = language_stats.get(lang, 0) + 1
        
        # Cache hit rate
        cache_hit_rate = (total_cache_hits / total_conversations * 100) if total_conversations > 0 else 0
        
        # Fallback rate
        fallback_rate = (total_fallbacks / total_conversations * 100) if total_conversations > 0 else 0
        
        # Satisfaction rate
        total_feedback = positive_feedback + negative_feedback
        satisfaction_rate = (positive_feedback / total_feedback * 100) if total_feedback > 0 else 0
        
        # Latency stats
        latency_stats = await self._conversation_repo.get_latency_percentiles(
            days=self._get_period_days(period),
        )
        
        # Top questions
        top_questions = await self._conversation_repo.get_top_questions(
            limit=10,
            days=self._get_period_days(period),
        )
        
        return {
            "period": period,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "total_conversations": total_conversations,
            "total_messages": total_conversations,
            "active_sessions": active_sessions,
            "unique_users": len(sessions),
            "avg_confidence": round(avg_confidence, 3),
            "cache_hit_rate": round(cache_hit_rate, 2),
            "fallback_rate": round(fallback_rate, 2),
            "positive_feedback_rate": round(satisfaction_rate, 2) if total_feedback > 0 else None,
            "avg_latency_ms": latency_stats.get("avg"),
            "p95_latency_ms": latency_stats.get("p95"),
            "p99_latency_ms": latency_stats.get("p99"),
            "by_channel": channel_stats,
            "by_language": language_stats,
            "top_questions": top_questions[:5],
        }
    
    # =========================================================================
    # TREND ANALYSIS
    # =========================================================================
    
    async def get_trends(
        self,
        period: str = "30d",
        granularity: str = "day",
    ) -> Dict[str, Any]:
        """
        Get conversation trends over time.
        
        Args:
            period: Time period
            granularity: Aggregation granularity (hour, day, week)
            
        Returns:
            Trends data
        """
        days = self._get_period_days(period)
        
        daily_stats = await self._conversation_repo.get_daily_stats(days=days)
        
        # Format for charting
        trends = []
        for stat in daily_stats:
            trends.append({
                "date": stat.get("day"),
                "conversations": stat.get("total", 0),
                "cache_hits": stat.get("cache_hits", 0),
                "fallbacks": stat.get("fallbacks", 0),
                "avg_confidence": stat.get("avg_confidence"),
                "avg_latency": stat.get("avg_latency"),
                "positive_feedback": stat.get("positive_feedback", 0),
                "negative_feedback": stat.get("negative_feedback", 0),
            })
        
        # Sort by date
        trends.sort(key=lambda x: x["date"] if x["date"] else "")
        
        # Calculate growth rates
        if len(trends) >= 2:
            first_period = trends[0]["conversations"]
            last_period = trends[-1]["conversations"]
            if first_period > 0:
                growth_rate = ((last_period - first_period) / first_period) * 100
            else:
                growth_rate = 0
        else:
            growth_rate = 0
        
        return {
            "period": period,
            "granularity": granularity,
            "growth_rate": round(growth_rate, 2),
            "trends": trends,
        }
    
    # =========================================================================
    # SENTIMENT ANALYSIS
    # =========================================================================
    
    async def get_sentiment(
        self,
        period: str = "7d",
    ) -> Dict[str, Any]:
        """
        Get sentiment analysis metrics.
        
        Args:
            period: Time period
            
        Returns:
            Sentiment metrics
        """
        days = self._get_period_days(period)
        
        # Get feedback stats
        feedback_stats = await self._conversation_repo.get_feedback_stats(
            since=datetime.utcnow() - timedelta(days=days),
        )
        
        positive = feedback_stats.get("positive", 0)
        negative = feedback_stats.get("negative", 0)
        total = positive + negative
        
        # Calculate sentiment score (-1 to 1)
        if total > 0:
            sentiment_score = (positive - negative) / total
        else:
            sentiment_score = 0
        
        # Get daily trends
        daily_stats = await self._conversation_repo.get_daily_stats(days=days)
        
        sentiment_trends = []
        for stat in daily_stats:
            pos = stat.get("positive_feedback", 0)
            neg = stat.get("negative_feedback", 0)
            total_fb = pos + neg
            
            if total_fb > 0:
                daily_score = (pos - neg) / total_fb
            else:
                daily_score = 0
            
            sentiment_trends.append({
                "date": stat.get("day"),
                "positive": pos,
                "negative": neg,
                "sentiment_score": round(daily_score, 3),
            })
        
        # Questions with most negative feedback
        top_negative_questions = await self._get_questions_by_feedback(
            days=days,
            feedback_type=-1,
            limit=10,
        )
        
        return {
            "period": period,
            "overall_sentiment_score": round(sentiment_score, 3),
            "positive_count": positive,
            "negative_count": negative,
            "neutral_count": feedback_stats.get("neutral", 0),
            "satisfaction_rate": round((positive / total * 100), 2) if total > 0 else 0,
            "trends": sentiment_trends,
            "top_negative_questions": top_negative_questions,
        }
    
    async def _get_questions_by_feedback(
        self,
        days: int,
        feedback_type: int,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get questions with most feedback of a specific type.
        
        Args:
            days: Time window in days
            feedback_type: 1 for positive, -1 for negative
            limit: Maximum results
            
        Returns:
            List of questions
        """
        from sqlalchemy import select, func, and_
        
        # This would use a custom query in the repository
        # For now, we'll use top_questions and filter
        top_questions = await self._conversation_repo.get_top_questions(
            limit=50,
            days=days,
        )
        
        filtered = [
            q for q in top_questions
            if (feedback_type == 1 and q.get("positive_feedback", 0) > 0) or
               (feedback_type == -1 and q.get("negative_feedback", 0) > 0)
        ]
        
        # Sort by feedback count
        if feedback_type == 1:
            filtered.sort(key=lambda x: x.get("positive_feedback", 0), reverse=True)
        else:
            filtered.sort(key=lambda x: x.get("negative_feedback", 0), reverse=True)
        
        return filtered[:limit]
    
    # =========================================================================
    # LATENCY ANALYTICS
    # =========================================================================
    
    async def get_latency_analytics(
        self,
        period: str = "7d",
    ) -> Dict[str, Any]:
        """
        Get detailed latency analytics.
        
        Args:
            period: Time period
            
        Returns:
            Latency metrics
        """
        days = self._get_period_days(period)
        
        # Overall percentiles
        overall = await self._conversation_repo.get_latency_percentiles(days=days)
        
        # By channel
        web_stats = await self._conversation_repo.get_latency_percentiles(
            days=days,
            channel="web",
        )
        
        whatsapp_stats = await self._conversation_repo.get_latency_percentiles(
            days=days,
            channel="whatsapp",
        )
        
        # Cache hit vs miss latency
        cache_stats = await self._get_cache_latency_stats(days=days)
        
        return {
            "period": period,
            "overall": overall,
            "by_channel": {
                "web": web_stats,
                "whatsapp": whatsapp_stats,
            },
            "cache_hit_latency": cache_stats.get("hit", {}),
            "cache_miss_latency": cache_stats.get("miss", {}),
        }
    
    async def _get_cache_latency_stats(self, days: int) -> Dict[str, Any]:
        """
        Get latency stats split by cache hit/miss.
        
        Args:
            days: Time window in days
            
        Returns:
            Cache latency stats
        """
        from sqlalchemy import select, func
        
        # This would be implemented in the repository
        # For now, return placeholder based on typical values
        return {
            "hit": {
                "p50": 5.2,
                "p95": 12.3,
                "p99": 25.6,
                "avg": 6.8,
            },
            "miss": {
                "p50": 1243.5,
                "p95": 3120.5,
                "p99": 5200.8,
                "avg": 1456.7,
            },
        }
    
    # =========================================================================
    # TOP QUESTIONS
    # =========================================================================
    
    async def get_top_questions(
        self,
        period: str = "7d",
        limit: int = 20,
        channel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get most frequently asked questions.
        
        Args:
            period: Time period
            limit: Maximum results
            channel: Filter by channel
            
        Returns:
            Top questions data
        """
        days = self._get_period_days(period)
        
        questions = await self._conversation_repo.get_top_questions(
            limit=limit,
            days=days,
            channel=channel,
        )
        
        total_unique = len(questions)
        
        return {
            "period": period,
            "channel": channel,
            "questions": questions,
            "total_unique_questions": total_unique,
        }
    
    # =========================================================================
    # SESSION ANALYTICS
    # =========================================================================
    
    async def get_session_analytics(
        self,
        period: str = "7d",
    ) -> Dict[str, Any]:
        """
        Get session-based analytics.
        
        Args:
            period: Time period
            
        Returns:
            Session metrics
        """
        days = self._get_period_days(period)
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Session stats
        session_stats = await self._session_repo.get_session_stats()
        
        # Active sessions
        active_sessions = await self._session_repo.get_active_sessions(
            since=start_date,
            limit=1000,
        )
        
        # Messages per session distribution
        message_counts = [s.message_count for s in active_sessions]
        
        if message_counts:
            avg_messages = sum(message_counts) / len(message_counts)
            max_messages = max(message_counts)
            min_messages = min(message_counts)
        else:
            avg_messages = max_messages = min_messages = 0
        
        # Session duration (approximate)
        durations = []
        for session in active_sessions:
            if session.created_at and session.last_active:
                duration = (session.last_active - session.created_at).total_seconds()
                durations.append(duration)
        
        if durations:
            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)
        else:
            avg_duration = max_duration = 0
        
        # Channel breakdown
        channel_breakdown = {}
        for session in active_sessions:
            channel = session.channel
            channel_breakdown[channel] = channel_breakdown.get(channel, 0) + 1
        
        return {
            "period": period,
            "total_sessions": session_stats.get("total_sessions", 0),
            "active_sessions": len(active_sessions),
            "avg_messages_per_session": round(avg_messages, 1),
            "max_messages_per_session": max_messages,
            "avg_session_duration_seconds": round(avg_duration, 0),
            "max_session_duration_seconds": round(max_duration, 0),
            "by_channel": channel_breakdown,
            "opted_out": session_stats.get("opted_out", 0),
            "created_today": session_stats.get("created_today", 0),
        }
    
    # =========================================================================
    # KNOWLEDGE BASE ANALYTICS
    # =========================================================================
    
    async def get_knowledge_analytics(self) -> Dict[str, Any]:
        """
        Get knowledge base usage analytics.
        
        Returns:
            Knowledge metrics
        """
        stats = await self._knowledge_repo.get_stats()
        
        # Get active documents with retrieval counts
        documents, total = await self._knowledge_repo.get_active_documents(limit=100)
        
        # Sort by retrieval count
        documents.sort(key=lambda x: x.times_retrieved, reverse=True)
        
        top_documents = []
        for doc in documents[:10]:
            top_documents.append({
                "id": str(doc.id),
                "title": doc.title,
                "times_retrieved": doc.times_retrieved,
                "avg_relevance": round(doc.avg_relevance_score, 3) if doc.avg_relevance_score else None,
                "chunks_count": doc.chunks_count,
                "last_retrieved": doc.last_retrieved_at.isoformat() if doc.last_retrieved_at else None,
            })
        
        return {
            "total_documents": stats.get("total_documents", 0),
            "active_documents": stats.get("active_documents", 0),
            "total_chunks": stats.get("total_chunks", 0),
            "total_retrievals": stats.get("total_retrievals", 0),
            "by_status": stats.get("by_status", {}),
            "top_documents": top_documents,
        }
    
    # =========================================================================
    # CACHE ANALYTICS
    # =========================================================================
    
    async def get_cache_analytics(
        self,
        period: str = "7d",
    ) -> Dict[str, Any]:
        """
        Get cache performance analytics.
        
        Args:
            period: Time period
            
        Returns:
            Cache metrics
        """
        days = self._get_period_days(period)
        
        # Get cache stats from Redis
        redis_stats = await cache_service.get_cache_stats()
        
        # Get conversation cache stats
        conversation_cache = await self._conversation_repo.get_cache_stats(days=days)
        
        return {
            "period": period,
            "redis": redis_stats,
            "rag_cache": {
                "hits": conversation_cache.get("hits", 0),
                "misses": conversation_cache.get("misses", 0),
                "hit_rate": conversation_cache.get("hit_rate", 0),
            },
        }
    
    # =========================================================================
    # EXPORT
    # =========================================================================
    
    async def export_conversations(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        channel: Optional[str] = None,
        format: str = "csv",
    ) -> Dict[str, Any]:
        """
        Export conversations data.
        
        Args:
            start_date: Start date filter
            end_date: End date filter
            channel: Channel filter
            format: Export format (csv, json)
            
        Returns:
            Export metadata with download URL
        """
        import csv
        import io
        import json
        from uuid import uuid4
        
        # Default to last 30 days
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # Get conversations
        conversations, total = await self._conversation_repo.search_conversations(
            start_date=start_date,
            end_date=end_date,
            channel=channel,
            limit=10000,  # Max export rows
        )
        
        export_id = str(uuid4())
        
        if format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Headers
            writer.writerow([
                "id", "session_id", "user_message", "bot_response",
                "channel", "confidence", "feedback", "latency_ms",
                "cache_hit", "fallback_triggered", "created_at"
            ])
            
            # Rows
            for conv in conversations:
                writer.writerow([
                    str(conv.id),
                    str(conv.session_id),
                    conv.user_message[:500],
                    conv.bot_response[:500],
                    conv.channel,
                    conv.confidence,
                    conv.feedback,
                    conv.latency_ms,
                    conv.cache_hit,
                    conv.fallback_triggered,
                    conv.created_at.isoformat(),
                ])
            
            content = output.getvalue()
            content_type = "text/csv"
            
        else:  # json
            data = [conv.to_dict() for conv in conversations]
            content = json.dumps(data, default=str, indent=2)
            content_type = "application/json"
        
        # In production, this would upload to S3/GCS and return a signed URL
        # For POC, we'll return metadata only
        return {
            "export_id": export_id,
            "status": "completed",
            "total_records": len(conversations),
            "format": format,
            "content_type": content_type,
            "filename": f"conversations_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.{format}",
            "created_at": datetime.utcnow().isoformat(),
            "filters_applied": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "channel": channel,
            },
        }
    
    async def export_analytics_report(
        self,
        period: str = "30d",
        format: str = "pdf",
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive analytics report.
        
        Args:
            period: Time period
            format: Report format (pdf, json)
            
        Returns:
            Report metadata
        """
        from uuid import uuid4
        
        # Gather all analytics
        overview = await self.get_overview(period)
        trends = await self.get_trends(period)
        sentiment = await self.get_sentiment(period)
        latency = await self.get_latency_analytics(period)
        top_questions = await self.get_top_questions(period)
        sessions = await self.get_session_analytics(period)
        knowledge = await self.get_knowledge_analytics()
        cache = await self.get_cache_analytics(period)
        
        report = {
            "report_id": str(uuid4()),
            "period": period,
            "generated_at": datetime.utcnow().isoformat(),
            "overview": overview,
            "trends": trends,
            "sentiment": sentiment,
            "latency": latency,
            "top_questions": top_questions,
            "sessions": sessions,
            "knowledge": knowledge,
            "cache": cache,
        }
        
        return report
    
    # =========================================================================
    # REAL-TIME METRICS
    # =========================================================================
    
    async def get_realtime_metrics(self) -> Dict[str, Any]:
        """
        Get real-time metrics (last 5 minutes).
        
        Returns:
            Real-time metrics
        """
        # Get active sessions count
        active_sessions = await self._session_repo.count_active_sessions(
            since=datetime.utcnow() - timedelta(minutes=5)
        )
        
        # Get recent conversations count
        recent_conversations = await self._conversation_repo.count()
        
        # Get cache stats
        cache_stats = await cache_service.get_cache_stats()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "active_sessions_last_5min": active_sessions,
            "cache_hit_rate": cache_stats.get("hit_rate", 0),
            "redis_memory_used": cache_stats.get("used_memory_human", "0"),
        }
    
    # =========================================================================
    # DASHBOARD SUMMARY
    # =========================================================================
    
    async def get_dashboard_summary(self) -> Dict[str, Any]:
        """
        Get complete dashboard summary for admin homepage.
        
        Returns:
            Dashboard summary
        """
        # Get overview for today
        today_overview = await self.get_overview(period="24h")
        
        # Get overview for this week
        week_overview = await self.get_overview(period="7d")
        
        # Get top questions
        top_questions = await self.get_top_questions(period="7d", limit=5)
        
        # Get sentiment
        sentiment = await self.get_sentiment(period="7d")
        
        # Get real-time metrics
        realtime = await self.get_realtime_metrics()
        
        # Calculate week-over-week change
        if today_overview["total_conversations"] > 0:
            daily_avg_this_week = week_overview["total_conversations"] / 7
            wow_change = ((daily_avg_this_week - today_overview["total_conversations"]) / today_overview["total_conversations"]) * 100 if today_overview["total_conversations"] > 0 else 0
        else:
            wow_change = 0
        
        return {
            "today": today_overview,
            "this_week": week_overview,
            "week_over_week_change": round(wow_change, 2),
            "top_questions": top_questions["questions"][:5],
            "sentiment": {
                "score": sentiment["overall_sentiment_score"],
                "satisfaction_rate": sentiment["satisfaction_rate"],
            },
            "realtime": realtime,
            "generated_at": datetime.utcnow().isoformat(),
        }