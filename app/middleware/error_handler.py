"""
Error handling middleware for BARROW.AI.
Provides consistent error responses across the application.
"""

from typing import Callable, Union
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp

from app.core.logging import get_logger
from app.core.exceptions import (
    BarrowAIException,
    ValidationException,
    AuthenticationException,
    AuthorizationException,
    RateLimitException,
    NotFoundException,
    HostileContentException,
    PromptInjectionException,
    LLMException,
    LLMTimeoutException,
    LLMUnavailableException,
    DatabaseError,
    RedisException,
    QdrantException,
    WhatsAppException,
)
from app.models.response.common import ErrorResponse

logger = get_logger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle exceptions and return consistent error responses.
    
    Maps various exception types to appropriate HTTP status codes and error formats.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """
        Process request and handle exceptions.
        
        Args:
            request: FastAPI request
            call_next: Next middleware in chain
            
        Returns:
            Response or error response
        """
        try:
            return await call_next(request)
            
        except Exception as e:
            return self._handle_exception(request, e)
    
    def _handle_exception(self, request: Request, exc: Exception) -> JSONResponse:
        """
        Map exception to appropriate error response.
        
        Args:
            request: FastAPI request
            exc: Exception that occurred
            
        Returns:
            JSONResponse with error details
        """
        request_id = getattr(request.state, "request_id", None)
        
        # BarrowAI custom exceptions
        if isinstance(exc, BarrowAIException):
            return self._create_error_response(
                status_code=exc.status_code,
                error=exc.message,
                code=exc.code.value if hasattr(exc.code, 'value') else str(exc.code),
                request_id=request_id,
                details=exc.details,
            )
        
        # Specific BarrowAI exceptions
        if isinstance(exc, HostileContentException):
            logger.warning("hostile_content_blocked", request_id=request_id)
            return self._create_error_response(
                status_code=400,
                error="Invalid message content",
                code="HOSTILE_CONTENT",
                request_id=request_id,
            )
        
        if isinstance(exc, PromptInjectionException):
            logger.warning("prompt_injection_blocked", request_id=request_id)
            return self._create_error_response(
                status_code=400,
                error="Invalid message content",
                code="PROMPT_INJECTION",
                request_id=request_id,
            )
        
        if isinstance(exc, LLMTimeoutException):
            logger.error("llm_timeout", request_id=request_id, timeout=exc.timeout_seconds)
            return self._create_error_response(
                status_code=503,
                error="AI service temporarily unavailable",
                code="LLM_TIMEOUT",
                request_id=request_id,
                details={"timeout_seconds": exc.timeout_seconds},
            )
        
        if isinstance(exc, LLMUnavailableException):
            logger.error("llm_unavailable", request_id=request_id)
            return self._create_error_response(
                status_code=503,
                error="AI service temporarily unavailable",
                code="LLM_UNAVAILABLE",
                request_id=request_id,
            )
        
        if isinstance(exc, RateLimitException):
            return self._create_error_response(
                status_code=429,
                error="Rate limit exceeded",
                code="RATE_LIMIT_EXCEEDED",
                request_id=request_id,
                details={"retry_after": exc.retry_after},
                headers={"Retry-After": str(exc.retry_after)},
            )
        
        if isinstance(exc, NotFoundException):
            return self._create_error_response(
                status_code=404,
                error=exc.message,
                code="NOT_FOUND",
                request_id=request_id,
                details=exc.details,
            )
        
        if isinstance(exc, AuthenticationException):
            return self._create_error_response(
                status_code=401,
                error=exc.message,
                code=exc.code.value if hasattr(exc.code, 'value') else "UNAUTHORIZED",
                request_id=request_id,
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if isinstance(exc, AuthorizationException):
            return self._create_error_response(
                status_code=403,
                error=exc.message,
                code="FORBIDDEN",
                request_id=request_id,
            )
        
        # FastAPI/Starlette exceptions
        if isinstance(exc, RequestValidationError):
            logger.warning("validation_error", request_id=request_id, errors=str(exc.errors()))
            return self._create_error_response(
                status_code=400,
                error="Validation error",
                code="VALIDATION_ERROR",
                request_id=request_id,
                details={"errors": exc.errors()},
            )
        
        if isinstance(exc, StarletteHTTPException):
            return self._create_error_response(
                status_code=exc.status_code,
                error=exc.detail,
                code="HTTP_ERROR",
                request_id=request_id,
            )
        
        # Database and service exceptions
        if isinstance(exc, DatabaseError):
            logger.error("database_error", request_id=request_id, error=str(exc))
            return self._create_error_response(
                status_code=503,
                error="Database service unavailable",
                code="DATABASE_ERROR",
                request_id=request_id,
            )
        
        if isinstance(exc, RedisException):
            logger.error("redis_error", request_id=request_id, error=str(exc))
            return self._create_error_response(
                status_code=503,
                error="Cache service unavailable",
                code="REDIS_ERROR",
                request_id=request_id,
            )
        
        if isinstance(exc, QdrantException):
            logger.error("qdrant_error", request_id=request_id, error=str(exc))
            return self._create_error_response(
                status_code=503,
                error="Vector search service unavailable",
                code="VECTOR_STORE_ERROR",
                request_id=request_id,
            )
        
        if isinstance(exc, WhatsAppException):
            logger.error("whatsapp_error", request_id=request_id, error=str(exc))
            return self._create_error_response(
                status_code=503,
                error="WhatsApp service error",
                code="WHATSAPP_ERROR",
                request_id=request_id,
            )
        
        # Unknown exceptions
        logger.error(
            "unhandled_exception",
            request_id=request_id,
            error=str(exc),
            exc_info=True,
        )
        
        return self._create_error_response(
            status_code=500,
            error="An unexpected error occurred",
            code="INTERNAL_ERROR",
            request_id=request_id,
        )
    
    def _create_error_response(
        self,
        status_code: int,
        error: str,
        code: str,
        request_id: str = None,
        details: dict = None,
        headers: dict = None,
    ) -> JSONResponse:
        """
        Create a standardized error response.
        
        Args:
            status_code: HTTP status code
            error: Human-readable error message
            code: Machine-readable error code
            request_id: Request ID for tracing
            details: Additional error details
            headers: Additional response headers
            
        Returns:
            JSONResponse with error
        """
        from datetime import datetime
        
        response_content = {
            "error": error,
            "code": code,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        if request_id:
            response_content["request_id"] = request_id
        
        if details:
            response_content["details"] = details
        
        response_headers = headers or {}
        
        return JSONResponse(
            status_code=status_code,
            content=response_content,
            headers=response_headers,
        )