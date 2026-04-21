"""
Redis client module for BARROW.AI backend.
Provides async Redis connection pooling, health checks, and comprehensive caching utilities.
Implements connection retry logic, circuit breaker pattern, and graceful degradation.
"""

import asyncio
import json
from typing import Optional, Any, Union, List, Dict, Set, Tuple
from datetime import timedelta
from contextlib import asynccontextmanager
from enum import Enum

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import (
    RedisError,
    ConnectionError,
    TimeoutError,
    ResponseError,
    AuthenticationError,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import BarrowAIException, ErrorCode

logger = get_logger(__name__)

# Global Redis client and connection pool
_redis_client: Optional[Redis] = None
_redis_pool: Optional[ConnectionPool] = None
_is_initialized: bool = False
_init_lock = asyncio.Lock()


CIRCUIT_BREAKER_REDIS_KEY = "circuit_breaker:redis"
CIRCUIT_BREAKER_THRESHOLD: int = 5
CIRCUIT_BREAKER_TIMEOUT_SECONDS: int = 30


class RedisErrorCode(str, Enum):
    """Redis-specific error codes."""
    CONNECTION_FAILED = "REDIS_CONNECTION_FAILED"
    AUTHENTICATION_FAILED = "REDIS_AUTHENTICATION_FAILED"
    TIMEOUT = "REDIS_TIMEOUT"
    CIRCUIT_OPEN = "REDIS_CIRCUIT_OPEN"
    SERIALIZATION_FAILED = "REDIS_SERIALIZATION_FAILED"
    OPERATION_FAILED = "REDIS_OPERATION_FAILED"


class RedisException(BarrowAIException):
    """Redis-specific exception with circuit breaker awareness."""
    
    def __init__(
        self,
        message: str,
        code: RedisErrorCode,
        original_error: Optional[Exception] = None
    ):
        super().__init__(
            message=message,
            code=ErrorCode.INTERNAL_ERROR,
            status_code=503,
            details={
                "redis_code": code.value,
                "original_error": str(original_error) if original_error else None
            }
        )
        self.redis_code = code
        self.original_error = original_error


class CircuitBreakerOpenException(RedisException):
    """Raised when circuit breaker is open."""
    
    def __init__(self):
        super().__init__(
            message="Redis circuit breaker is open - service temporarily unavailable",
            code=RedisErrorCode.CIRCUIT_OPEN
        )


def _reset_circuit_breaker() -> None:
    """Reset circuit breaker after successful operation."""
    global _circuit_breaker_open, _circuit_breaker_failures, _circuit_breaker_last_failure
    _circuit_breaker_open = False
    _circuit_breaker_failures = 0
    _circuit_breaker_last_failure = None
    logger.info("redis_circuit_breaker_reset")


def _record_circuit_breaker_failure() -> None:
    """Record a failure and potentially open circuit breaker."""
    global _circuit_breaker_open, _circuit_breaker_failures, _circuit_breaker_last_failure
    import time
    
    _circuit_breaker_failures += 1
    _circuit_breaker_last_failure = time.time()
    
    if _circuit_breaker_failures >= CIRCUIT_BREAKER_THRESHOLD:
        _circuit_breaker_open = True
        logger.error(
            "redis_circuit_breaker_opened",
            failures=_circuit_breaker_failures,
            threshold=CIRCUIT_BREAKER_THRESHOLD
        )


def _should_attempt_circuit_breaker() -> bool:
    """Check if circuit breaker allows an attempt."""
    global _circuit_breaker_open, _circuit_breaker_last_failure
    import time
    
    if not _circuit_breaker_open:
        return True
    
    if _circuit_breaker_last_failure is None:
        return True
    
    elapsed = time.time() - _circuit_breaker_last_failure
    if elapsed >= CIRCUIT_BREAKER_TIMEOUT_SECONDS:
        logger.info("redis_circuit_breaker_half_open")
        _circuit_breaker_open = False
        return True
    
    return False


async def init_redis() -> None:
    """
    Initialize Redis connection pool and client.
    Thread-safe initialization with retry logic and health check.
    """
    global _redis_client, _redis_pool, _is_initialized
    
    async with _init_lock:
        if _is_initialized and _redis_client:
            logger.info("redis_already_initialized")
            return
        
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                logger.info(
                    "initializing_redis",
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=settings.REDIS_DB,
                    max_connections=settings.REDIS_MAX_CONNECTIONS,
                    attempt=attempt + 1
                )
                
                # Create connection pool with optimized settings
                _redis_pool = aioredis.ConnectionPool.from_url(
                    settings.redis_url,
                    max_connections=settings.REDIS_MAX_CONNECTIONS,
                    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                    health_check_interval=30,
                    retry_on_timeout=True,
                    decode_responses=True,
                )
                
                # Create Redis client
                _redis_client = aioredis.Redis(
                    connection_pool=_redis_pool,
                    decode_responses=True,
                )
                
                # Test connection
                await _redis_client.ping()
                
                # Get server info
                info = await _redis_client.info("server")
                logger.info(
                    "redis_connected_successfully",
                    redis_version=info.get("redis_version"),
                    maxmemory=info.get("maxmemory_human"),
                )
                
                _is_initialized = True
                _reset_circuit_breaker()
                return
                
            except AuthenticationError as e:
                logger.error("redis_authentication_failed", error=str(e))
                raise RedisException(
                    "Redis authentication failed - check REDIS_PASSWORD",
                    RedisErrorCode.AUTHENTICATION_FAILED,
                    e
                )
            except (ConnectionError, TimeoutError) as e:
                logger.warning(
                    "redis_connection_failed",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e)
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                else:
                    _record_circuit_breaker_failure()
                    raise RedisException(
                        f"Failed to connect to Redis after {max_retries} attempts",
                        RedisErrorCode.CONNECTION_FAILED,
                        e
                    )
            except RedisError as e:
                logger.error("redis_initialization_failed", error=str(e))
                raise RedisException(
                    f"Redis initialization failed: {str(e)}",
                    RedisErrorCode.OPERATION_FAILED,
                    e
                )


async def close_redis() -> None:
    """
    Close Redis connections and release resources.
    Should be called during application shutdown.
    """
    global _redis_client, _redis_pool, _is_initialized
    
    if _redis_client:
        try:
            logger.info("closing_redis_connections")
            await _redis_client.aclose()
        except Exception as e:
            logger.warning("redis_close_error", error=str(e))
        finally:
            _redis_client = None
            _redis_pool = None
            _is_initialized = False
            logger.info("redis_connections_closed")


async def get_redis() -> Redis:
    """
    Get Redis client instance.
    Lazy initialization if not already initialized.
    
    Returns:
        Redis: Redis client instance
        
    Raises:
        RedisException: If Redis is unavailable
        CircuitBreakerOpenException: If circuit breaker is open
    """
    global _is_initialized, _redis_client
    
    if not _should_attempt_circuit_breaker():
        raise CircuitBreakerOpenException()
    
    if not _is_initialized or not _redis_client:
        await init_redis()
    
    return _redis_client


async def execute_redis_operation(
    operation_name: str,
    operation: callable,
    fallback_value: Any = None,
    allow_circuit_breaker: bool = True
) -> Any:
    """
    Execute a Redis operation with circuit breaker and error handling.
    
    Args:
        operation_name: Name of operation for logging
        operation: Async callable that takes Redis client and returns result
        fallback_value: Value to return if operation fails
        allow_circuit_breaker: Whether to respect circuit breaker
        
    Returns:
        Result of operation or fallback_value on failure
    """
    if allow_circuit_breaker and not _should_attempt_circuit_breaker():
        logger.warning(
            "redis_operation_skipped_circuit_open",
            operation=operation_name
        )
        return fallback_value
    
    try:
        client = await get_redis()
        result = await operation(client)
        _reset_circuit_breaker()
        return result
        
    except CircuitBreakerOpenException:
        logger.warning(
            "redis_operation_circuit_open",
            operation=operation_name
        )
        return fallback_value
        
    except (ConnectionError, TimeoutError) as e:
        _record_circuit_breaker_failure()
        logger.error(
            "redis_operation_connection_error",
            operation=operation_name,
            error=str(e)
        )
        return fallback_value
        
    except RedisError as e:
        logger.error(
            "redis_operation_failed",
            operation=operation_name,
            error=str(e)
        )
        return fallback_value
        
    except Exception as e:
        logger.error(
            "redis_operation_unexpected_error",
            operation=operation_name,
            error=str(e),
            exc_info=True
        )
        return fallback_value


async def check_redis_health() -> dict:
    """
    Check Redis health for monitoring endpoints.
    
    Returns:
        dict: Health status with metrics
    """
    try:
        if not _should_attempt_circuit_breaker():
            return {
                "status": "degraded",
                "circuit_breaker": "open",
                "initialized": _is_initialized,
            }
        
        client = await get_redis()
        start_time = asyncio.get_event_loop().time()
        
        # Test connection
        await client.ping()
        
        latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        
        # Get memory info
        info = await client.info("memory")
        
        # Get pool stats
        if _redis_pool:
            pool_stats = {
                "max_connections": _redis_pool.max_connections,
                "in_use": len(_redis_pool._in_use_connections) if hasattr(_redis_pool, '_in_use_connections') else -1,
                "available": len(_redis_pool._available_connections) if hasattr(_redis_pool, '_available_connections') else -1,
            }
        else:
            pool_stats = {"status": "not_initialized"}
        
        _reset_circuit_breaker()
        
        return {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2),
            "used_memory_human": info.get("used_memory_human"),
            "used_memory_peak_human": info.get("used_memory_peak_human"),
            "mem_fragmentation_ratio": info.get("mem_fragmentation_ratio"),
            "pool": pool_stats,
            "initialized": _is_initialized,
            "circuit_breaker": "closed",
        }
        
    except CircuitBreakerOpenException:
        return {
            "status": "degraded",
            "circuit_breaker": "open",
            "initialized": _is_initialized,
        }
    except Exception as e:
        _record_circuit_breaker_failure()
        return {
            "status": "unhealthy",
            "error": str(e),
            "initialized": _is_initialized,
            "circuit_breaker": "closed" if not _circuit_breaker_open else "open",
        }


def setup_redis_hooks(app):
    """
    Setup FastAPI application lifespan hooks for Redis.
    
    Args:
        app: FastAPI application instance
    """
    @app.on_event("startup")
    async def startup_redis():
        """Initialize Redis on application startup."""
        try:
            await init_redis()
        except Exception as e:
            logger.error("redis_startup_failed", error=str(e))
            # Don't raise - allow application to start in degraded mode
    
    @app.on_event("shutdown")
    async def shutdown_redis():
        """Close Redis connections on application shutdown."""
        await close_redis()