"""
Request logging middleware for Company Bot.
Logs all incoming requests with structured data.
"""

import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import get_logger, set_request_id

logger = get_logger(__name__)


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all requests and responses.
    
    Logs include:
    - Request ID for tracing
    - Method and path
    - Client IP
    - User agent
    - Response status
    - Duration
    """
    
    # Paths to exclude from logging
    EXCLUDED_PATHS = [
        "/health",
        "/metrics",
        "/favicon.ico",
    ]
    
    # Sensitive headers to redact
    SENSITIVE_HEADERS = [
        "authorization",
        "cookie",
        "x-api-key",
        "x-csrf-token",
    ]
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _should_log(self, path: str) -> bool:
        """Check if path should be logged."""
        for excluded in self.EXCLUDED_PATHS:
            if path.startswith(excluded):
                return False
        return True
    
    def _sanitize_headers(self, headers: dict) -> dict:
        """Redact sensitive headers."""
        sanitized = {}
        for key, value in headers.items():
            if key.lower() in self.SENSITIVE_HEADERS:
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = value
        return sanitized
    
    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """
        Process request and log details.
        
        Args:
            request: FastAPI request
            call_next: Next middleware in chain
            
        Returns:
            Response
        """
        # Generate request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        # BUG #2 FIX: Set request_id in module-level ContextVar for correlation across logs
        set_request_id(request_id)
        
        # Skip logging for excluded paths
        if not self._should_log(request.url.path):
            return await call_next(request)
        
        start_time = time.time()
        
        # Extract request details
        client_ip = self._get_client_ip(request)
        method = request.method
        path = request.url.path
        user_agent = request.headers.get("User-Agent", "unknown")
        
        # Log request
        logger.info(
            "request_started",
            request_id=request_id,
            method=method,
            path=path,
            client_ip=client_ip,
            user_agent=user_agent[:200] if user_agent else None,
        )
        
        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            logger.error(
                "request_failed",
                request_id=request_id,
                method=method,
                path=path,
                client_ip=client_ip,
                duration_ms=round(duration_ms, 2),
                error=str(e),
                exc_info=True,
            )
            raise
        
        duration_ms = (time.time() - start_time) * 1000
        
        # Log response
        logger.info(
            "request_completed",
            request_id=request_id,
            method=method,
            path=path,
            client_ip=client_ip,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
