"""
HTTP metrics middleware for Prometheus observability.
Tracks request count, latency, in-flight requests, and error rates with anti-cardinality protection.
"""

import re
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.core.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    http_requests_in_flight,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

UUID_REGEX = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
NUMERIC_REGEX = re.compile(r'/\d+(?=/|$)')


def normalize_endpoint_path(path: str) -> str:
    """
    Normalize dynamic URL paths to prevent Prometheus high-cardinality label explosion.
    Replaces UUIDs and numeric IDs with {id}.
    Example:
        /api/v1/admin/knowledge/detail/123e4567-e89b-12d3-a456-426614174000
        -> /api/v1/admin/knowledge/detail/{id}
    """
    if not path:
        return "/"
    # Strip query parameters if present
    clean_path = path.split("?")[0]
    # Replace UUIDs
    normalized = UUID_REGEX.sub("{id}", clean_path)
    # Replace numeric segments
    normalized = NUMERIC_REGEX.sub("/{id}", normalized)
    return normalized


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to collect HTTP metrics for Prometheus.
    Records request count, latency, in-flight count, and status codes.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process request and record metrics.
        """
        method = request.method
        path = request.url.path
        normalized_endpoint = normalize_endpoint_path(path)
        start_time = time.time()

        try:
            http_requests_in_flight.labels(method=method).inc()
        except Exception:
            pass

        try:
            response = await call_next(request)
            status = response.status_code
            
            # Record request metrics
            duration_seconds = time.time() - start_time
            http_requests_total.labels(
                method=method,
                endpoint=normalized_endpoint,
                status=status
            ).inc()
            http_request_duration_seconds.labels(
                method=method,
                endpoint=normalized_endpoint
            ).observe(duration_seconds)
            
            return response
            
        except Exception as e:
            # Record error as 500 status
            status = 500
            duration_seconds = time.time() - start_time
            
            http_requests_total.labels(
                method=method,
                endpoint=normalized_endpoint,
                status=status
            ).inc()
            http_request_duration_seconds.labels(
                method=method,
                endpoint=normalized_endpoint
            ).observe(duration_seconds)
            
            logger.error(
                "http_middleware_error",
                path=path,
                normalized_endpoint=normalized_endpoint,
                method=method,
                error=str(e)
            )
            raise
        finally:
            try:
                http_requests_in_flight.labels(method=method).dec()
            except Exception:
                pass

