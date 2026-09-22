"""
CSRF (Cross-Site Request Forgery) Protection Middleware for Company Bot.

Implements double-submit cookie pattern with SameSite cookie attribute.

How it works:
1. GET requests (safe) don't need CSRF validation
2. POST/PUT/DELETE/PATCH requests require X-CSRF-Token header
3. The header value must match the csrf_token cookie value
4. Browser automatically includes cookies in requests (SameSite protection)
"""

import json
import os
import secrets
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

from app.core.logging import get_logger

_SECURE_COOKIE = os.environ.get("ENVIRONMENT", "production") == "production"

logger = get_logger(__name__)

# Methods that should be protected from CSRF
PROTECTED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

# Endpoints that are excluded from CSRF validation
# (e.g., webhook endpoints, public APIs without authentication)
EXEMPT_PATHS = {
    "/health",
    "/admin/health",
    "/metrics",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/api/v1/whatsapp/webhook",     # WhatsApp webhook uses signature validation instead
    "/api/v1/internal/process-whatsapp", # Internal inter-service endpoint (uses X-Internal-Secret)
    # Auth endpoints are exempt: no session exists yet before login
    "/api/v1/admin/auth/login",
    "/api/v1/admin/auth/verify-2fa",
    "/api/v1/admin/auth/refresh",
    "/api/v1/admin/auth/csrf-token",
}



class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware using double-submit cookie pattern.
    
    Security measures:
    - Tokens are URL-safe random 32-byte strings
    - Tokens are httponly=False (JS can read them)
    - Cookies have SameSite=Strict (browser prevents cross-site submission)
    - Validation on all state-changing operations (POST/PUT/DELETE/PATCH)
    
    The double-submit pattern works because:
    1. Malicious sites can't read cookies from other domains (same-origin policy)
    2. Cross-site requests can't read from the response to know the token value
    3. SameSite=Strict prevents the browser from sending cookies in cross-site requests
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request and validate CSRF token if necessary.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler
            
        Returns:
            Response from downstream handler
        """
        # Skip CSRF validation for safe methods and exempt paths
        if request.method not in PROTECTED_METHODS:
            return await call_next(request)
        
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)
        
        # For protected methods, validate CSRF token
        csrf_token_header = request.headers.get("X-CSRF-Token")
        csrf_token_cookie = request.cookies.get("csrf_token")
        
        if not csrf_token_header or not csrf_token_cookie:
            logger.warning(
                "csrf_validation_failed_missing_token",
                path=request.url.path,
                method=request.method,
                has_header=bool(csrf_token_header),
                has_cookie=bool(csrf_token_cookie),
                client_ip=request.client.host if request.client else None,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid", "code": "CSRF_MISSING"}
            )

        # Validate tokens match
        if csrf_token_header != csrf_token_cookie:
            logger.warning(
                "csrf_validation_failed_token_mismatch",
                path=request.url.path,
                method=request.method,
                client_ip=request.client.host if request.client else None,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token validation failed", "code": "CSRF_MISMATCH"}
            )
        
        logger.debug(
            "csrf_validation_passed",
            path=request.url.path,
            method=request.method,
        )
        
        # Token valid, proceed to handler
        return await call_next(request)


async def generate_csrf_token() -> str:
    """
    Generate a new CSRF token.
    
    Uses secrets.token_urlsafe() for cryptographically secure random bytes
    that are URL-safe (suitable for cookies and HTTP headers).
    
    Returns:
        URL-safe 32-byte random token as string
    """
    return secrets.token_urlsafe(32)


def add_csrf_cookie(response: Response, token: str) -> Response:
    """
    Add CSRF token cookie to response.
    
    Cookie settings:
    - httponly=False: Allows JavaScript to read the token (needed for double-submit)
    - secure=True: Only sent over HTTPS (set to False for local development)
    - samesite='Strict': Prevents browser from sending in cross-site requests
    - max_age=3600: Token expires after 1 hour
    
    Args:
        response: Response to add cookie to
        token: CSRF token value
        
    Returns:
        Modified response with cookie
    """
    response.set_cookie(
        key="csrf_token",
        value=token,
        httponly=False,  # JS needs to read this
        secure=_SECURE_COOKIE,  # HTTPS only in production; False in dev/test
        samesite="Strict",  # Prevent cross-site cookie submission
        max_age=3600,  # 1 hour expiration
    )
    return response

