"""
Rate limiting middleware for BARROW.AI.
Provides IP-based and endpoint-based rate limiting.
"""

import time
import ipaddress
from typing import Callable, Optional, Tuple, List
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
    
    # SECURITY FLAIR #2 FIX: Trusted proxies list
    # Only these proxies can set X-Forwarded-For (prevents rate limit bypass)
    TRUSTED_PROXIES: List[str] = [
        "127.0.0.1",     # Localhost
        "::1",           # IPv6 localhost
        "10.0.0.0/8",    # Private network
        "172.16.0.0/12", # Private network
        "192.168.0.0/16", # Private network
    ]
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        # Precompile trusted proxy networks
        self._trusted_networks = [
            ipaddress.ip_network(cidr, strict=False)
            for cidr in self.TRUSTED_PROXIES
        ]
    
    def _get_client_ip(self, request: Request) -> str:
        """
        SECURITY FLAIR #2 FIX: Extract client IP with proxy validation.
        
        Validates X-Forwarded-For header against trusted proxies list
        to prevent rate limit bypass via header spoofing.
        
        Args:
            request: FastAPI request
            
        Returns:
            Client IP address
        """
        # Get immediate peer IP
        immediate_peer_ip = request.client.host if request.client else "unknown"
        
        # Check if immediate peer is a trusted proxy
        try:
            immediate_peer = ipaddress.ip_address(immediate_peer_ip)
            is_trusted_proxy = any(
                immediate_peer in network for network in self._trusted_networks
            )
        except ValueError:
            is_trusted_proxy = False
        
        # Only trust X-Forwarded-For if immediate peer is a trusted proxy
        if is_trusted_proxy:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                # Parse from right-to-left through proxy chain
                # E.g., "client_ip, proxy1, proxy2" -> take leftmost untrusted
                ips = [ip.strip() for ip in forwarded.split(",")]
                
                # Skip rightmost trusted proxies and return first untrusted IP
                for ip_str in reversed(ips):
                    try:
                        ip = ipaddress.ip_address(ip_str)
                        # If this IP is NOT in trusted list, use it
                        if not any(ip in network for network in self._trusted_networks):
                            logger.info(
                                "rate_limit_client_ip_extracted",
                                ip=ip_str,
                                forwarded_chain=forwarded,
                                trusted_proxy=True
                            )
                            return ip_str
                    except ValueError:
                        continue
        
        # Check X-Real-IP header (but only if from trusted proxy)
        if is_trusted_proxy:
            real_ip = request.headers.get("X-Real-IP")
            if real_ip:
                logger.info(
                    "rate_limit_client_ip_extracted",
                    ip=real_ip,
                    source="X-Real-IP",
                    trusted_proxy=True
                )
                return real_ip.strip()
        
        # Fallback to direct client or immediate peer
        logger.info(
            "rate_limit_client_ip_extracted",
            ip=immediate_peer_ip,
            source="direct_connection",
            trusted_proxy=is_trusted_proxy
        )
        return immediate_peer_ip
    
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