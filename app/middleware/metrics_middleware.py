"""
HTTP metrics middleware for Prometheus observability.
Tracks request count, latency, and error rates.
"""

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.core.metrics import http_requests_total, http_request_duration_seconds
from app.core.logging import get_logger

logger = get_logger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to collect HTTP metrics for Prometheus.
    Records request count, latency, and status codes.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process request and record metrics.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler
            
        Returns:
            HTTP response
        """
        method = request.method
        path = request.url.path
        start_time = time.time()

        try:
            response = await call_next(request)
            status = response.status_code
            
            # Record request metrics
            duration_seconds = time.time() - start_time
            http_requests_total.labels(
                method=method,
                endpoint=path,
                status=status
            ).inc()
            http_request_duration_seconds.labels(
                method=method,
                endpoint=path
            ).observe(duration_seconds)
            
            return response
            
        except Exception as e:
            # Record error as 500 status
            status = 500
            duration_seconds = time.time() - start_time
            
            http_requests_total.labels(
                method=method,
                endpoint=path,
                status=status
            ).inc()
            http_request_duration_seconds.labels(
                method=method,
                endpoint=path
            ).observe(duration_seconds)
            
            logger.error(
                "http_middleware_error",
                path=path,
                method=method,
                error=str(e)
            )
            raise
