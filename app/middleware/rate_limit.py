"""
Rate limiting middleware for BARROW.AI.
Provides IP-based and endpoint-based rate limiting.
"""

import time
from typing import Callable, Optional, Tuple
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.logging import get_logger
from app.services.cache.redis_cache import cache_service
from app.core.exceptions import RateLimitException

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using sliding window algorithm.
    
    Limits are configurable per endpoint pattern:
    - /api/v1/chat/* : 30 requests per minute
    - /api/v1/admin/* : 60 requests per minute
    - /api/v1/whatsapp/* : 10 requests per minute
    """
    
    # Endpoint-specific rate limits
    ENDPOINT_LIMITS = {
        "/api/v1/chat": {
            "max_requests": 30,
            "window_seconds": 60,
        },
        "/api/v1/admin/auth/login": {
            "max_requests": 5,
            "window_seconds": 60,
        },
        "/api/v1/admin": {
            "max_requests": 60,
            "window_seconds": 60,
        },
        "/api/v1/whatsapp/webhook": {
            "max_requests": 50,
            "window_seconds": 60,
        },
    }
    
    # Default rate limit
    DEFAULT_LIMIT = {
        "max_requests": 100,
        "window_seconds": 60,
    }
    
    # Paths exempt from rate limiting
    EXEMPT_PATHS = [
        "/health",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
    ]
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP from request headers.
        
        Args:
            request: FastAPI request
            
        Returns:
            Client IP address
        """
        # Check X-Forwarded-For header (behind proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Fallback to direct client
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _get_limit_for_path(self, path: str) -> Tuple[int, int]:
        """
        Get rate limit configuration for a path.
        
        Args:
            path: Request path
            
        Returns:
            Tuple of (max_requests, window_seconds)
        """
        for prefix, limit in self.ENDPOINT_LIMITS.items():
            if path.startswith(prefix):
                return limit["max_requests"], limit["window_seconds"]
        
        return self.DEFAULT_LIMIT["max_requests"], self.DEFAULT_LIMIT["window_seconds"]
    
    def _is_exempt(self, path: str) -> bool:
        """
        Check if path is exempt from rate limiting.
        
        Args:
            path: Request path
            
        Returns:
            True if exempt
        """
        for exempt_path in self.EXEMPT_PATHS:
            if path.startswith(exempt_path):
                return True
        return False
    
    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """
        Process request with rate limiting.
        
        Args:
            request: FastAPI request
            call_next: Next middleware in chain
            
        Returns:
            Response
        """
        path = request.url.path
        
        # Skip rate limiting for exempt paths
        if self._is_exempt(path):
            return await call_next(request)
        
        # Get client IP
        client_ip = self._get_client_ip(request)
        
        # Get rate limit for this path
        max_requests, window_seconds = self._get_limit_for_path(path)
        
        # Create rate limit key
        rate_limit_key = f"rl:path:{client_ip}:{path}"
        
        # Check rate limit
        allowed, remaining, reset_in = await self._check_rate_limit(
            key=rate_limit_key,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        
        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                ip=client_ip,
                path=path,
                max_requests=max_requests,
                window_seconds=window_seconds,
            )
            
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "code": "RATE_LIMIT_EXCEEDED",
                    "retry_after": reset_in,
                    "details": {
                        "max_requests": max_requests,
                        "window_seconds": window_seconds,
                    },
                },
                headers={
                    "Retry-After": str(reset_in),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(reset_in),
                },
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_in)
        
        return response
    
    async def _check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> Tuple[bool, int, int]:
        """
        Check if request is within rate limit using sliding window.
        
        Args:
            key: Rate limit key
            max_requests: Maximum allowed requests
            window_seconds: Time window in seconds
            
        Returns:
            Tuple of (allowed, remaining, reset_in_seconds)
        """
        current_time = time.time()
        window_start = current_time - window_seconds
        
        try:
            client = await cache_service._get_client()
            
            # Remove old entries
            await client.zremrangebyscore(key, 0, window_start)
            
            # Count current requests
            count = await client.zcard(key)
            
            if count >= max_requests:
                # Get oldest request timestamp
                oldest = await client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    reset_in = int(oldest[0][1] + window_seconds - current_time)
                    return False, 0, max(1, reset_in)
                return False, 0, window_seconds
            
            # Add current request
            await client.zadd(key, {str(current_time): current_time})
            await client.expire(key, window_seconds + 1)
            
            remaining = max_requests - count - 1
            
            return True, remaining, window_seconds
            
        except Exception as e:
            logger.error("rate_limit_check_failed", error=str(e))
            # Fail open - allow request
            return True, max_requests, window_seconds