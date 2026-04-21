"""
Database configuration module for BARROW.AI backend.
Provides async SQLAlchemy engine, session management, and connection pooling.
Implements clean architecture principles with proper separation of concerns.
"""

from typing import AsyncGenerator, Optional, Callable, Any
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine,
    AsyncConnection
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError, OperationalError, DisconnectionError

from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import BarrowAIException, ErrorCode

logger = get_logger(__name__)

# SQLAlchemy declarative base for all ORM models
Base = declarative_base()

# Global engine and session factory
_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker] = None
_is_initialized: bool = False
_init_lock = asyncio.Lock()


class DatabaseError(BarrowAIException):
    """Database-specific exception."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            code=ErrorCode.INTERNAL_ERROR,
            status_code=500,
            details={"original_error": str(original_error)} if original_error else None
        )
        self.original_error = original_error


class ConnectionPoolExhaustedError(DatabaseError):
    """Raised when connection pool is exhausted."""
    
    def __init__(self, pool_size: int, overflow: int):
        super().__init__(
            message=f"Connection pool exhausted (size={pool_size}, overflow={overflow})"
        )


async def init_database() -> None:
    """
    Initialize the database engine and session factory.
    Thread-safe initialization with proper connection pool configuration.
    """
    global _engine, _async_session_factory, _is_initialized
    
    async with _init_lock:
        if _is_initialized:
            logger.info("database_already_initialized")
            return
        
        try:
            # Convert PostgreSQL URL to asyncpg format
            database_url = settings.database_url
            
            logger.info(
                "initializing_database",
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                database=settings.POSTGRES_DB,
                pool_size=settings.DATABASE_POOL_SIZE,
                max_overflow=settings.DATABASE_MAX_OVERFLOW
            )
            
            # Create async engine with optimized settings
            _engine = create_async_engine(
                database_url,
                echo=settings.DATABASE_ECHO,
                pool_size=settings.DATABASE_POOL_SIZE,
                max_overflow=settings.DATABASE_MAX_OVERFLOW,
                poolclass=QueuePool,
                pool_pre_ping=True,  # Verify connections before use
                pool_recycle=3600,   # Recycle connections after 1 hour
                pool_timeout=30,     # Wait up to 30 seconds for connection
                connect_args={
                    "server_settings": {
                        "application_name": settings.APP_NAME,
                        "timezone": "UTC",
                        "statement_timeout": "30000",  # 30 seconds
                        "idle_in_transaction_session_timeout": "60000",  # 60 seconds
                    },
                    "command_timeout": 30,
                },
            )
            
            # Add engine event listeners
            _setup_engine_event_listeners(_engine)
            
            # Create session factory
            _async_session_factory = async_sessionmaker(
                _engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False,
            )
            
            # Test connection
            await _test_connection()
            
            _is_initialized = True
            logger.info("database_initialized_successfully")
            
        except Exception as e:
            logger.error("database_initialization_failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to initialize database: {str(e)}", e)


def _setup_engine_event_listeners(engine: AsyncEngine) -> None:
    """
    Setup SQLAlchemy engine event listeners for monitoring and debugging.
    """
    
    @event.listens_for(engine.sync_engine, "connect")
    def receive_connect(dbapi_connection, connection_record):
        """Called when a connection is created."""
        logger.debug(
            "database_connection_created",
            connection_id=id(dbapi_connection)
        )
    
    @event.listens_for(engine.sync_engine, "close")
    def receive_close(dbapi_connection, connection_record):
        """Called when a connection is closed."""
        logger.debug(
            "database_connection_closed",
            connection_id=id(dbapi_connection)
        )
    
    @event.listens_for(engine.sync_engine, "checkout")
    def receive_checkout(dbapi_connection, connection_record, connection_proxy):
        """Called when a connection is checked out from the pool."""
        logger.debug(
            "database_connection_checked_out",
            connection_id=id(dbapi_connection),
            pool_size=engine.pool.size(),
            checked_in=engine.pool.checkedin()
        )
    
    @event.listens_for(engine.sync_engine, "checkin")
    def receive_checkin(dbapi_connection, connection_record):
        """Called when a connection is returned to the pool."""
        logger.debug(
            "database_connection_checked_in",
            connection_id=id(dbapi_connection)
        )


async def _test_connection() -> None:
    """Test database connection and log server version."""
    try:
        async with _engine.connect() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            logger.info("database_connection_test_successful", postgres_version=version)
            
            # Check extensions
            result = await conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname IN ('uuid-ossp', 'pgcrypto')")
            )
            extensions = [row[0] for row in result.fetchall()]
            logger.info("database_extensions_available", extensions=extensions)
            
    except Exception as e:
        logger.error("database_connection_test_failed", error=str(e))
        raise


async def close_database() -> None:
    """
    Close database engine and release all connections.
    Should be called during application shutdown.
    """
    global _engine, _async_session_factory, _is_initialized
    
    if _engine:
        logger.info("closing_database_connections")
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        _is_initialized = False
        logger.info("database_connections_closed")


def get_engine() -> AsyncEngine:
    """
    Get the database engine.
    
    Returns:
        AsyncEngine: SQLAlchemy async engine
        
    Raises:
        DatabaseError: If database is not initialized
    """
    if not _is_initialized or not _engine:
        raise DatabaseError("Database not initialized. Call init_database() first.")
    return _engine


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for obtaining a database session.
    Session is automatically closed after request processing.
    
    Yields:
        AsyncSession: Database session
        
    Example:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            ...
    """
    if not _is_initialized or not _async_session_factory:
        await init_database()
    
    async with _async_session_factory() as session:
        try:
            yield session
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error("database_session_error", error=str(e))
            raise DatabaseError(f"Database operation failed: {str(e)}", e)
        except Exception as e:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for obtaining a database session outside FastAPI dependency.
    
    Yields:
        AsyncSession: Database session
        
    Example:
        async with get_session_context() as session:
            result = await session.execute(...)
    """
    if not _is_initialized or not _async_session_factory:
        await init_database()
    
    async with _async_session_factory() as session:
        try:
            yield session
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error("database_session_error", error=str(e))
            raise DatabaseError(f"Database operation failed: {str(e)}", e)
        except Exception as e:
            await session.rollback()
            raise
        finally:
            await session.close()


async def execute_with_retry(
    operation: Callable[[AsyncSession], Any],
    max_retries: int = 3,
    retry_delay: float = 1.0
) -> Any:
    """
    Execute a database operation with automatic retry on connection errors.
    
    Args:
        operation: Async function that takes a session and returns a result
        max_retries: Maximum number of retry attempts
        retry_delay: Base delay between retries (exponential backoff)
        
    Returns:
        Any: Result of the operation
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            async with get_session_context() as session:
                result = await operation(session)
                await session.commit()
                return result
                
        except (OperationalError, DisconnectionError) as e:
            last_error = e
            wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
            
            logger.warning(
                "database_operation_retry",
                attempt=attempt + 1,
                max_retries=max_retries,
                wait_seconds=wait_time,
                error=str(e)
            )
            
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
            else:
                raise DatabaseError(f"Operation failed after {max_retries} attempts", e)
        
        except SQLAlchemyError as e:
            raise DatabaseError(f"Database operation failed: {str(e)}", e)


async def check_database_health() -> dict:
    """
    Check database health for monitoring endpoints.
    
    Returns:
        dict: Health status with metrics
    """
    try:
        async with get_session_context() as session:
            start_time = datetime.utcnow()
            
            # Execute simple query
            result = await session.execute(text("SELECT 1"))
            await result.scalar()
            
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Get pool statistics
            if _engine:
                pool = _engine.pool
                pool_stats = {
                    "size": pool.size(),
                    "checked_in": pool.checkedin(),
                    "checked_out": pool.checkedout(),
                    "overflow": pool.overflow(),
                }
            else:
                pool_stats = {"status": "not_initialized"}
            
            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "pool": pool_stats,
                "initialized": _is_initialized,
            }
            
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e),
            "initialized": _is_initialized,
        }


class TransactionContext:
    """
    Context manager for explicit transaction control.
    
    Example:
        async with TransactionContext(session) as tx:
            await tx.execute(...)
            await tx.commit()
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self._committed = False
        self._rolled_back = False
    
    async def __aenter__(self) -> "TransactionContext":
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()
            return False
        
        if not self._committed and not self._rolled_back:
            await self.commit()
        
        return False
    
    async def commit(self) -> None:
        """Commit the transaction."""
        await self.session.commit()
        self._committed = True
        logger.debug("transaction_committed")
    
    async def rollback(self) -> None:
        """Rollback the transaction."""
        await self.session.rollback()
        self._rolled_back = True
        logger.debug("transaction_rolled_back")
    
    async def execute(self, statement, params=None):
        """Execute a statement within the transaction."""
        return await self.session.execute(statement, params)


# SQLAlchemy model mixins for common columns
class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""
    
    created_at: datetime
    updated_at: datetime


class SoftDeleteMixin:
    """Mixin for soft delete functionality."""
    
    deleted_at: Optional[datetime]
    is_deleted: bool
    
    def soft_delete(self) -> None:
        """Mark the record as deleted."""
        self.deleted_at = datetime.utcnow()
        self.is_deleted = True
    
    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.deleted_at = None
        self.is_deleted = False


def setup_database_hooks(app):
    """
    Setup FastAPI application lifespan hooks for database.
    
    Args:
        app: FastAPI application instance
    """
    @app.on_event("startup")
    async def startup_database():
        """Initialize database on application startup."""
        await init_database()
    
    @app.on_event("shutdown")
    async def shutdown_database():
        """Close database connections on application shutdown."""
        await close_database()