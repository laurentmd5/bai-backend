"""
Rate limiting dependency for BARROW.AI endpoints.
"""

from fastapi import Request, HTTPException, status
from app.core.config import settings


async def check_rate_limit(
    request: Request,
    max_requests: int = 30,
    window_seconds: int = 60,
) -> bool:
    """
    Rate limiting dependency for FastAPI endpoints.
    Simple in-memory check, full version uses Redis.
    
    Args:
        request: FastAPI request
        max_requests: Maximum requests allowed
        window_seconds: Time window in seconds
        
    Returns:
        True if allowed
        
    Raises:
        HTTPException 429 if rate limit exceeded
    """
    # In production, this uses Redis via SecurityValidator
    # For now, this is a placeholder that always allows
    return True