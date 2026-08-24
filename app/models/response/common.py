"""
Common response models for Company Bot.
Includes error responses, health checks, pagination, and metrics.
"""

from typing import Optional, List, Dict, Any, Generic, TypeVar
from datetime import datetime
from pydantic import BaseModel, Field
from pydantic.generics import GenericModel

T = TypeVar('T')


class ErrorResponse(BaseModel):
    """
    Standardized error response following RFC 7807.
    """
    
    error: str = Field(
        ...,
        description="Human-readable error message"
    )
    
    code: str = Field(
        ...,
        description="Machine-readable error code"
    )
    
    details: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional error details"
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Error timestamp (UTC)"
    )
    
    path: Optional[str] = Field(
        None,
        description="Request path that caused the error"
    )
    
    request_id: Optional[str] = Field(
        None,
        description="Request ID for tracing"
    )
    
    status_code: Optional[int] = Field(
        None,
        description="HTTP status code"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "error": "Validation error",
                "code": "VALIDATION_ERROR",
                "details": {
                    "field": "message",
                    "reason": "Message too long (max 2000 characters)"
                },
                "timestamp": "2026-04-17T10:30:45Z",
                "path": "/api/v1/chat/message",
                "request_id": "req_abc123",
                "status_code": 400
            }
        }
    }


class ServiceHealthResponse(BaseModel):
    """
    Individual service health status.
    """
    
    status: str = Field(
        ...,
        description="Service status",
        examples=["healthy", "degraded", "unhealthy"]
    )
    
    latency_ms: Optional[float] = Field(
        None,
        description="Service latency in milliseconds"
    )
    
    error: Optional[str] = Field(
        None,
        description="Error message if unhealthy"
    )
    
    details: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional service-specific details"
    )


class HealthResponse(BaseModel):
    """
    Overall system health response.
    """
    
    status: str = Field(
        ...,
        description="Overall system status",
        examples=["healthy", "degraded", "unhealthy"]
    )
    
    version: str = Field(
        ...,
        description="Application version"
    )
    
    environment: str = Field(
        ...,
        description="Runtime environment"
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Health check timestamp"
    )
    
    services: Dict[str, ServiceHealthResponse] = Field(
        default_factory=dict,
        description="Individual service health statuses"
    )
    
    uptime_seconds: Optional[float] = Field(
        None,
        description="Application uptime in seconds"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "healthy",
                "version": "4.0.0",
                "environment": "production",
                "timestamp": "2026-04-17T10:30:45Z",
                "services": {
                    "database": {
                        "status": "healthy",
                        "latency_ms": 5.2,
                        "details": {
                            "pool_size": 20,
                            "checked_out": 2
                        }
                    },
                    "redis": {
                        "status": "healthy",
                        "latency_ms": 1.8,
                        "details": {
                            "used_memory": "128MB"
                        }
                    },
                    "qdrant": {
                        "status": "healthy",
                        "latency_ms": 3.4,
                        "details": {
                            "collection_size": 115
                        }
                    },
                    "gemini": {
                        "status": "healthy",
                        "latency_ms": 245.6
                    }
                },
                "uptime_seconds": 86400.0
            }
        }
    }


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic paginated response wrapper.
    """
    
    items: List[T] = Field(
        default_factory=list,
        description="List of items for current page"
    )
    
    total: int = Field(
        ...,
        description="Total number of items across all pages"
    )
    
    page: int = Field(
        ...,
        description="Current page number (1-indexed)"
    )
    
    page_size: int = Field(
        ...,
        description="Number of items per page"
    )
    
    pages: int = Field(
        ...,
        description="Total number of pages"
    )
    
    has_next: bool = Field(
        ...,
        description="Whether there is a next page"
    )
    
    has_previous: bool = Field(
        ...,
        description="Whether there is a previous page"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [],
                "total": 150,
                "page": 1,
                "page_size": 20,
                "pages": 8,
                "has_next": True,
                "has_previous": False
            }
        }
    }


class CacheStatsResponse(BaseModel):
    """
    Redis cache statistics.
    """
    
    keyspace_hits: int = Field(..., description="Total cache hits")
    
    keyspace_misses: int = Field(..., description="Total cache misses")
    
    hit_rate: float = Field(..., description="Cache hit rate percentage")
    
    total_commands_processed: int = Field(..., description="Total Redis commands")
    
    used_memory_human: str = Field(..., description="Human-readable memory usage")
    
    connected_clients: int = Field(..., description="Number of connected clients")
    
    evicted_keys: int = Field(..., description="Number of evicted keys")
    
    expired_keys: int = Field(..., description="Number of expired keys")
    
    rag_cache_size: Optional[int] = Field(None, description="RAG cache entries count")
    
    embedding_cache_size: Optional[int] = Field(None, description="Embedding cache entries count")
    
    session_cache_size: Optional[int] = Field(None, description="Session cache entries count")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "keyspace_hits": 15234,
                "keyspace_misses": 2156,
                "hit_rate": 87.6,
                "total_commands_processed": 25000,
                "used_memory_human": "128.5M",
                "connected_clients": 5,
                "evicted_keys": 0,
                "expired_keys": 120,
                "rag_cache_size": 450,
                "embedding_cache_size": 890,
                "session_cache_size": 120
            }
        }
    }


class MetricsResponse(BaseModel):
    """
    Application metrics for monitoring.
    """
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    requests_total: int = Field(..., description="Total requests processed")
    
    requests_per_minute: float = Field(..., description="Current request rate")
    
    error_rate: float = Field(..., description="Error rate percentage")
    
    avg_latency_ms: float = Field(..., description="Average response latency")
    
    p95_latency_ms: float = Field(..., description="95th percentile latency")
    
    p99_latency_ms: float = Field(..., description="99th percentile latency")
    
    active_sessions: int = Field(..., description="Active chat sessions")
    
    active_admin_sessions: int = Field(..., description="Active admin sessions")
    
    cache: CacheStatsResponse = Field(..., description="Cache statistics")
    
    database_pool: Dict[str, Any] = Field(..., description="Database pool statistics")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "timestamp": "2026-04-17T10:30:45Z",
                "requests_total": 125000,
                "requests_per_minute": 45.3,
                "error_rate": 0.12,
                "avg_latency_ms": 234.5,
                "p95_latency_ms": 1450.2,
                "p99_latency_ms": 3200.8,
                "active_sessions": 42,
                "active_admin_sessions": 3,
                "cache": {},
                "database_pool": {
                    "size": 20,
                    "checked_in": 15,
                    "checked_out": 5
                }
            }
        }
    }
