"""
Custom exception classes for BARROW.AI backend.
Provides structured error handling across the application.
"""

from typing import Optional, Dict, Any
from enum import Enum


class ErrorCode(str, Enum):
    """Standardized error codes for API responses."""
    
    # General errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    
    # Chat errors
    MESSAGE_TOO_LONG = "MESSAGE_TOO_LONG"
    INVALID_SESSION = "INVALID_SESSION"
    HOSTILE_CONTENT = "HOSTILE_CONTENT"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    
    # RAG errors
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    VECTOR_SEARCH_FAILED = "VECTOR_SEARCH_FAILED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    
    # LLM errors
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_QUOTA_EXCEEDED = "LLM_QUOTA_EXCEEDED"
    
    # Auth errors
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    TWO_FACTOR_REQUIRED = "TWO_FACTOR_REQUIRED"
    INVALID_2FA_CODE = "INVALID_2FA_CODE"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    
    # WhatsApp errors
    WHATSAPP_SEND_FAILED = "WHATSAPP_SEND_FAILED"
    WHATSAPP_WEBHOOK_INVALID = "WHATSAPP_WEBHOOK_INVALID"
    
    # Knowledge base errors
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    INDEXING_FAILED = "INDEXING_FAILED"
    DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"


class BarrowAIException(Exception):
    """Base exception class for BARROW.AI application."""
    
    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationException(BarrowAIException):
    """Raised when input validation fails."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
            details=details
        )


class AuthenticationException(BarrowAIException):
    """Raised when authentication fails."""
    
    def __init__(self, message: str, code: ErrorCode = ErrorCode.INVALID_CREDENTIALS):
        super().__init__(
            message=message,
            code=code,
            status_code=401
        )


class AuthorizationException(BarrowAIException):
    """Raised when user lacks required permissions."""
    
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            code=ErrorCode.FORBIDDEN,
            status_code=403
        )


class RateLimitException(BarrowAIException):
    """Raised when rate limit is exceeded."""
    
    def __init__(self, retry_after: int):
        super().__init__(
            message="Rate limit exceeded",
            code=ErrorCode.RATE_LIMIT_EXCEEDED,
            status_code=429,
            details={"retry_after": retry_after}
        )
        self.retry_after = retry_after


class NotFoundException(BarrowAIException):
    """Raised when a resource is not found."""
    
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} not found: {identifier}",
            code=ErrorCode.NOT_FOUND,
            status_code=404,
            details={"resource": resource, "identifier": identifier}
        )


class HostileContentException(BarrowAIException):
    """Raised when hostile or inappropriate content is detected."""
    
    def __init__(self, message: str = "Inappropriate content detected"):
        super().__init__(
            message=message,
            code=ErrorCode.HOSTILE_CONTENT,
            status_code=400
        )


class PromptInjectionException(BarrowAIException):
    """Raised when prompt injection attempt is detected."""
    
    def __init__(self):
        super().__init__(
            message="Invalid message content",
            code=ErrorCode.PROMPT_INJECTION,
            status_code=400
        )


class LLMException(BarrowAIException):
    """Base exception for LLM-related errors."""
    pass


class LLMTimeoutException(LLMException):
    """Raised when LLM API times out."""
    
    def __init__(self, timeout_seconds: int):
        super().__init__(
            message=f"LLM request timed out after {timeout_seconds} seconds",
            code=ErrorCode.LLM_TIMEOUT,
            status_code=503,
            details={"timeout_seconds": timeout_seconds}
        )


class LLMUnavailableException(LLMException):
    """Raised when LLM service is unavailable."""
    
    def __init__(self, reason: str = "Service unavailable"):
        super().__init__(
            message=f"LLM service unavailable: {reason}",
            code=ErrorCode.LLM_UNAVAILABLE,
            status_code=503,
            details={"reason": reason}
        )


class LowConfidenceException(BarrowAIException):
    """Raised when RAG confidence is below threshold."""
    
    def __init__(self, score: float, threshold: float):
        super().__init__(
            message=f"Confidence score {score:.2f} below threshold {threshold:.2f}",
            code=ErrorCode.LOW_CONFIDENCE,
            status_code=200,  # Not an error, just fallback
            details={"score": score, "threshold": threshold}
        )


class AccountLockedException(AuthenticationException):
    """Raised when admin account is locked due to failed attempts."""
    
    def __init__(self, locked_until: str):
        super().__init__(
            message=f"Account locked until {locked_until}",
            code=ErrorCode.ACCOUNT_LOCKED
        )
        self.locked_until = locked_until


class TwoFactorRequiredException(AuthenticationException):
    """Raised when 2FA verification is required."""
    
    def __init__(self, session_token: str):
        super().__init__(
            message="2FA verification required",
            code=ErrorCode.TWO_FACTOR_REQUIRED
        )
        self.session_token = session_token


class DatabaseError(BarrowAIException):
    """Raised when a database operation fails."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code=ErrorCode.INTERNAL_ERROR,
            status_code=500,
            details=details
        )

class RedisException(BarrowAIException):
    """Raised when a Redis operation fails."""

    def __init__(self, message: str, code: Optional[str] = None, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            code=ErrorCode.INTERNAL_ERROR,
            status_code=503,
            details={"redis_code": code, "original_error": str(original_error)} if original_error else None
        )


class QdrantException(BarrowAIException):
    """Raised when a Qdrant operation fails."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            code=ErrorCode.VECTOR_SEARCH_FAILED,
            status_code=503,
            details={"original_error": str(original_error)} if original_error else None
        )


class WhatsAppException(BarrowAIException):
    """Raised when a WhatsApp operation fails."""

    def __init__(self, message: str, code: Optional[int] = None, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            code=ErrorCode.WHATSAPP_SEND_FAILED,
            status_code=503,
            details={"whatsapp_code": code, "original_error": str(original_error)} if original_error else None
        )