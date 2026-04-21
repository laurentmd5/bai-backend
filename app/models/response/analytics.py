"""
Analytics response models for BARROW.AI.
Serializes dashboard metrics, trends, and statistics.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class AnalyticsTopQuestion(BaseModel):
    """
    Top asked question with statistics.
    """
    
    question_preview: str = Field(..., description="Truncated question text")
    
    frequency: int = Field(..., description="Number of times asked")
    
    avg_confidence: Optional[float] = Field(None, description="Average confidence score")
    
    positive_feedback: int = Field(default=0, description="Positive feedback count")
    
    negative_feedback: int = Field(default=0, description="Negative feedback count")
    
    satisfaction_rate: Optional[float] = Field(
        None,
        description="Positive feedback percentage"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "question_preview": "What has NPP done for internet connectivity?",
                "frequency": 342,
                "avg_confidence": 0.92,
                "positive_feedback": 310,
                "negative_feedback": 12,
                "satisfaction_rate": 96.3
            }
        }
    }


class AnalyticsOverviewResponse(BaseModel):
    """
    Dashboard overview metrics.
    """
    
    period: str = Field(
        ...,
        description="Time period for metrics",
        examples=["24h", "7d", "30d"]
    )
    
    total_conversations: int = Field(..., description="Total conversations in period")
    
    total_messages: int = Field(..., description="Total messages in period")
    
    active_sessions: int = Field(..., description="Active sessions in period")
    
    unique_users: int = Field(..., description="Unique users in period")
    
    avg_confidence: Optional[float] = Field(None, description="Average confidence score")
    
    cache_hit_rate: float = Field(..., description="Cache hit percentage")
    
    fallback_rate: float = Field(..., description="Fallback trigger percentage")
    
    positive_feedback_rate: Optional[float] = Field(
        None,
        description="Positive feedback percentage"
    )
    
    avg_latency_ms: Optional[float] = Field(None, description="Average response latency")
    
    p95_latency_ms: Optional[float] = Field(None, description="95th percentile latency")
    
    by_channel: Dict[str, int] = Field(
        default_factory=dict,
        description="Message count by channel"
    )
    
    by_language: Dict[str, int] = Field(
        default_factory=dict,
        description="Message count by language"
    )
    
    top_questions: List[AnalyticsTopQuestion] = Field(
        default_factory=list,
        description="Top asked questions"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "period": "7d",
                "total_conversations": 5240,
                "total_messages": 5240,
                "active_sessions": 1820,
                "unique_users": 1650,
                "avg_confidence": 0.87,
                "cache_hit_rate": 42.5,
                "fallback_rate": 8.3,
                "positive_feedback_rate": 91.2,
                "avg_latency_ms": 234.5,
                "p95_latency_ms": 1450.2,
                "by_channel": {
                    "web": 3200,
                    "whatsapp": 2040
                },
                "by_language": {
                    "en": 4500,
                    "fr": 620,
                    "mandinka": 120
                },
                "top_questions": []
            }
        }
    }


class AnalyticsQuestionsResponse(BaseModel):
    """
    Top questions analytics.
    """
    
    period: str = Field(..., description="Time period")
    
    questions: List[AnalyticsTopQuestion] = Field(..., description="Top questions")
    
    total_unique_questions: int = Field(..., description="Total unique questions")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "period": "7d",
                "questions": [],
                "total_unique_questions": 1250
            }
        }
    }


class AnalyticsSentimentTrend(BaseModel):
    """
    Sentiment trend over time.
    """
    
    timestamp: datetime = Field(..., description="Time bucket")
    
    positive_count: int = Field(..., description="Positive feedback count")
    
    negative_count: int = Field(..., description="Negative feedback count")
    
    sentiment_score: float = Field(
        ...,
        description="Sentiment score (-1 to 1)"
    )


class AnalyticsSentimentResponse(BaseModel):
    """
    Sentiment analysis response.
    """
    
    period: str = Field(..., description="Time period")
    
    overall_sentiment_score: float = Field(..., description="Overall sentiment (-1 to 1)")
    
    positive_count: int = Field(..., description="Total positive feedback")
    
    negative_count: int = Field(..., description="Total negative feedback")
    
    neutral_count: int = Field(..., description="Total without feedback")
    
    satisfaction_rate: float = Field(..., description="Positive feedback percentage")
    
    trends: List[AnalyticsSentimentTrend] = Field(
        default_factory=list,
        description="Sentiment trends over time"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "period": "7d",
                "overall_sentiment_score": 0.82,
                "positive_count": 2150,
                "negative_count": 210,
                "neutral_count": 2880,
                "satisfaction_rate": 91.1,
                "trends": []
            }
        }
    }


class AnalyticsLatencyDistribution(BaseModel):
    """
    Latency distribution percentiles.
    """
    
    p50_ms: float = Field(..., description="50th percentile (median)")
    
    p90_ms: float = Field(..., description="90th percentile")
    
    p95_ms: float = Field(..., description="95th percentile")
    
    p99_ms: float = Field(..., description="99th percentile")
    
    min_ms: float = Field(..., description="Minimum latency")
    
    max_ms: float = Field(..., description="Maximum latency")
    
    avg_ms: float = Field(..., description="Average latency")


class AnalyticsLatencyResponse(BaseModel):
    """
    Latency analytics response.
    """
    
    period: str = Field(..., description="Time period")
    
    distribution: AnalyticsLatencyDistribution = Field(..., description="Latency distribution")
    
    by_channel: Dict[str, AnalyticsLatencyDistribution] = Field(
        default_factory=dict,
        description="Latency by channel"
    )
    
    cache_hit_latency: AnalyticsLatencyDistribution = Field(
        ...,
        description="Latency for cache hits"
    )
    
    cache_miss_latency: AnalyticsLatencyDistribution = Field(
        ...,
        description="Latency for cache misses"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "period": "7d",
                "distribution": {
                    "p50_ms": 234.5,
                    "p90_ms": 980.2,
                    "p95_ms": 1450.2,
                    "p99_ms": 3200.8,
                    "min_ms": 45.2,
                    "max_ms": 8900.1,
                    "avg_ms": 456.7
                },
                "by_channel": {},
                "cache_hit_latency": {
                    "p50_ms": 5.2,
                    "p90_ms": 8.5,
                    "p95_ms": 12.3,
                    "p99_ms": 25.6,
                    "min_ms": 1.2,
                    "max_ms": 45.2,
                    "avg_ms": 6.8
                },
                "cache_miss_latency": {
                    "p50_ms": 1243.5,
                    "p90_ms": 2450.2,
                    "p95_ms": 3120.5,
                    "p99_ms": 5200.8,
                    "min_ms": 234.5,
                    "max_ms": 8900.1,
                    "avg_ms": 1456.7
                }
            }
        }
    }


class AnalyticsDailyStatsResponse(BaseModel):
    """
    Daily statistics response.
    """
    
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    
    conversations: int = Field(..., description="Total conversations")
    
    unique_sessions: int = Field(..., description="Unique sessions")
    
    avg_confidence: Optional[float] = Field(None, description="Average confidence")
    
    cache_hit_rate: float = Field(..., description="Cache hit rate")
    
    fallback_count: int = Field(..., description="Fallback count")
    
    positive_feedback: int = Field(..., description="Positive feedback count")
    
    negative_feedback: int = Field(..., description="Negative feedback count")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "date": "2026-04-17",
                "conversations": 1240,
                "unique_sessions": 850,
                "avg_confidence": 0.88,
                "cache_hit_rate": 43.2,
                "fallback_count": 98,
                "positive_feedback": 520,
                "negative_feedback": 42
            }
        }
    }