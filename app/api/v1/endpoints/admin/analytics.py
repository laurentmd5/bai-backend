"""
Admin analytics endpoints for BARROW.AI.
"""

from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Query, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.analytics_service import AnalyticsService
from app.api.dependencies.auth import get_current_admin, require_admin
from app.api.dependencies.services import get_analytics_service
from app.models.response.analytics import (
    AnalyticsOverviewResponse,
    AnalyticsQuestionsResponse,
    AnalyticsSentimentResponse,
    AnalyticsLatencyResponse,
    AnalyticsDailyStatsResponse,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["Admin Analytics"])


@router.get("/overview", response_model=AnalyticsOverviewResponse)
async def get_overview(
    period: str = Query("7d", regex="^(24h|7d|30d|90d|1y)$"),
    current_admin: dict = Depends(get_current_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsOverviewResponse:
    """
    Get dashboard overview metrics.
    
    Period options: 24h, 7d, 30d, 90d, 1y
    """
    overview = await analytics_service.get_overview(period=period)
    return AnalyticsOverviewResponse(**overview)


@router.get("/trends")
async def get_trends(
    period: str = Query("30d", regex="^(24h|7d|30d|90d|1y)$"),
    granularity: str = Query("day", regex="^(hour|day|week|month)$"),
    current_admin: dict = Depends(get_current_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> JSONResponse:
    """
    Get conversation trends over time.
    """
    trends = await analytics_service.get_trends(period=period, granularity=granularity)
    return JSONResponse(content=trends)


@router.get("/sentiment", response_model=AnalyticsSentimentResponse)
async def get_sentiment(
    period: str = Query("7d", regex="^(24h|7d|30d|90d)$"),
    current_admin: dict = Depends(get_current_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsSentimentResponse:
    """
    Get sentiment analysis metrics.
    """
    sentiment = await analytics_service.get_sentiment(period=period)
    return AnalyticsSentimentResponse(**sentiment)


@router.get("/latency", response_model=AnalyticsLatencyResponse)
async def get_latency(
    period: str = Query("7d", regex="^(24h|7d|30d|90d)$"),
    current_admin: dict = Depends(get_current_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsLatencyResponse:
    """
    Get latency analytics.
    """
    latency = await analytics_service.get_latency_analytics(period=period)
    return AnalyticsLatencyResponse(**latency)


@router.get("/questions", response_model=AnalyticsQuestionsResponse)
async def get_top_questions(
    period: str = Query("7d", regex="^(24h|7d|30d|90d)$"),
    limit: int = Query(20, ge=1, le=100),
    channel: Optional[str] = Query(None, regex="^(web|whatsapp)$"),
    current_admin: dict = Depends(get_current_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsQuestionsResponse:
    """
    Get most frequently asked questions.
    """
    questions = await analytics_service.get_top_questions(
        period=period,
        limit=limit,
        channel=channel,
    )
    return AnalyticsQuestionsResponse(**questions)


@router.get("/sessions")
async def get_session_analytics(
    period: str = Query("7d", regex="^(24h|7d|30d)$"),
    current_admin: dict = Depends(get_current_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> JSONResponse:
    """
    Get session-based analytics.
    """
    sessions = await analytics_service.get_session_analytics(period=period)
    return JSONResponse(content=sessions)


@router.get("/knowledge")
async def get_knowledge_analytics(
    current_admin: dict = Depends(get_current_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> JSONResponse:
    """
    Get knowledge base usage analytics.
    """
    knowledge = await analytics_service.get_knowledge_analytics()
    return JSONResponse(content=knowledge)


@router.get("/cache")
async def get_cache_analytics(
    period: str = Query("7d", regex="^(24h|7d|30d)$"),
    current_admin: dict = Depends(get_current_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> JSONResponse:
    """
    Get cache performance analytics.
    """
    cache = await analytics_service.get_cache_analytics(period=period)
    return JSONResponse(content=cache)


@router.get("/dashboard")
async def get_dashboard_summary(
    current_admin: dict = Depends(get_current_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> JSONResponse:
    """
    Get complete dashboard summary.
    """
    summary = await analytics_service.get_dashboard_summary()
    return JSONResponse(content=summary)


@router.get("/realtime")
async def get_realtime_metrics(
    current_admin: dict = Depends(get_current_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> JSONResponse:
    """
    Get real-time metrics.
    """
    metrics = await analytics_service.get_realtime_metrics()
    return JSONResponse(content=metrics)


@router.get("/export/conversations")
async def export_conversations(
    start_date: Optional[str] = Query(None, description="ISO 8601 date"),
    end_date: Optional[str] = Query(None, description="ISO 8601 date"),
    channel: Optional[str] = Query(None, regex="^(web|whatsapp)$"),
    format: str = Query("csv", regex="^(csv|json)$"),
    current_admin: dict = Depends(require_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> JSONResponse:
    """
    Export conversations data.
    Requires admin or superadmin role.
    """
    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None
    
    export = await analytics_service.export_conversations(
        start_date=start,
        end_date=end,
        channel=channel,
        format=format,
    )
    
    return JSONResponse(content=export)


@router.get("/export/report")
async def export_analytics_report(
    period: str = Query("30d", regex="^(7d|30d|90d|1y)$"),
    format: str = Query("json", regex="^(json|pdf)$"),
    current_admin: dict = Depends(require_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> JSONResponse:
    """
    Generate comprehensive analytics report.
    Requires admin or superadmin role.
    """
    report = await analytics_service.export_analytics_report(
        period=period,
        format=format,
    )
    
    return JSONResponse(content=report)