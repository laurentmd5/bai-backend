"""
Pytest configuration and fixtures for BARROW.AI tests.
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import AsyncGenerator, Generator, Optional, List, Dict
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
import pyotp
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Add app to path
app_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(app_root))

# Set test environment BEFORE importing app
os.environ["ENVIRONMENT"] = "development"
os.environ["DEBUG"] = "true"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-testing"
os.environ["ENCRYPTION_KEY"] = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE="  # base64 (exactly 32 bytes)
os.environ["POSTGRES_PASSWORD"] = "test"
os.environ["REDIS_PASSWORD"] = "test"
os.environ["GEMINI_API_KEY"] = "test"
os.environ["WHATSAPP_ACCESS_TOKEN"] = "test"
os.environ["WHATSAPP_WEBHOOK_VERIFY_TOKEN"] = "test"
os.environ["WHATSAPP_BUSINESS_ACCOUNT_ID"] = "test"
os.environ["WHATSAPP_PHONE_NUMBER_ID"] = "test"

from app.main import create_app
from app.core.database import get_session, init_database, close_database
from app.core.redis_client import init_redis, close_redis
from app.models.domain.admin import AdminUser
from app.repositories.admin_repository import AdminRepository
from app.services.admin_service import AdminService
from app.core.security import hash_password, create_jwt_token, generate_totp_secret


# ===== REDIS MOCKING =====
# Mock Redis for tests to avoid connection timeouts
import unittest.mock as mock

# Patch Redis init/close before any app is created
original_init_redis = init_redis
original_close_redis = close_redis

async def mock_init_redis():
    """Mock Redis initialization for tests."""
    pass

async def mock_close_redis():
    """Mock Redis shutdown for tests."""
    pass

# Apply patches globally
import app.core.redis_client
app.core.redis_client.init_redis = mock_init_redis
app.core.redis_client.close_redis = mock_close_redis

# Also patch the cache service to work without Redis
from app.services.cache.redis_cache import cache_service

class MockCacheService:
    """Mock cache service that stores in memory."""
    def __init__(self):
        self._cache = {}
    
    async def get(self, key: str) -> Optional[str]:
        return self._cache.get(key)
    
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        self._cache[key] = value
        return True
    
    async def delete(self, key: str) -> int:
        if key in self._cache:
            del self._cache[key]
            return 1
        return 0
    
    async def exists(self, key: str) -> bool:
        return key in self._cache
    
    async def increment(self, key: str, amount: int = 1) -> int:
        current = int(self._cache.get(key, 0))
        current += amount
        self._cache[key] = str(current)
        return current
    
    async def get_range(self, key: str, start: int, stop: int) -> List[Dict]:
        """Get time range for sliding window."""
        import time
        current_time = time.time()
        return []
    
    async def remove_old_entries(self, key: str, older_than: int) -> int:
        """Remove old entries from sliding window."""
        return 0

# Replace cache service with mock
import app.services.cache.redis_cache
_original_cache = app.services.cache.redis_cache.cache_service
app.services.cache.redis_cache.cache_service = MockCacheService()


# ===== SESSION FIXTURES =====

@pytest.fixture(scope="session")
def test_env():
    """Configure test environment variables."""
    yield
    # Cleanup after all tests


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ===== DATABASE FIXTURES =====

@pytest_asyncio.fixture
async def async_engine():
    """Create in-memory SQLite database for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    
    # Create tables
    from app.models.domain import AdminUser, Conversation, KnowledgeDocument, Session, AuditLog
    async with engine.begin() as conn:
        await conn.run_sync(AdminUser.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session_factory(async_engine):
    """Create async session factory."""
    factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return factory


@pytest_asyncio.fixture
async def db_session(async_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Get database session for test."""
    async with async_session_factory() as session:
        yield session
        await session.rollback()


# ===== APPLICATION FIXTURES =====

@pytest.fixture(scope="function")
def app():
    """Create FastAPI app for testing."""
    app = create_app()
    return app


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for FastAPI app."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sync_client(app):
    """Create sync HTTP client for FastAPI app."""
    return TestClient(app)


# ===== AUTHENTICATION FIXTURES =====

@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession):
    """Create a test admin user."""
    admin = AdminUser(
        id=uuid4(),
        email="admin@test.com",
        full_name="Test Admin",
        password_hash=hash_password("AdminTest123!"),
        role="SUPERADMIN",
        is_active=True,
        two_factor_enabled=False,
    )
    db_session.add(admin)
    await db_session.commit()
    return admin


@pytest_asyncio.fixture
async def test_regular_admin(db_session: AsyncSession):
    """Create a test regular admin user."""
    admin = AdminUser(
        id=uuid4(),
        email="regular@test.com",
        full_name="Regular Admin",
        password_hash=hash_password("RegularTest123!"),
        role="ADMIN",
        is_active=True,
        two_factor_enabled=False,
    )
    db_session.add(admin)
    await db_session.commit()
    return admin


@pytest_asyncio.fixture
async def test_auditor(db_session: AsyncSession):
    """Create a test auditor user."""
    auditor = AdminUser(
        id=uuid4(),
        email="auditor@test.com",
        full_name="Test Auditor",
        password_hash=hash_password("AuditorTest123!"),
        role="AUDITOR",
        is_active=True,
        two_factor_enabled=False,
    )
    db_session.add(auditor)
    await db_session.commit()
    return auditor


@pytest_asyncio.fixture
async def test_viewer(db_session: AsyncSession):
    """Create a test viewer user."""
    viewer = AdminUser(
        id=uuid4(),
        email="viewer@test.com",
        full_name="Test Viewer",
        password_hash=hash_password("ViewerTest123!"),
        role="VIEWER",
        is_active=True,
        two_factor_enabled=False,
    )
    db_session.add(viewer)
    await db_session.commit()
    return viewer


@pytest.fixture
def admin_token(test_admin):
    """Create JWT token for test admin."""
    return create_jwt_token(
        {
            "sub": str(test_admin.id),
            "email": test_admin.email,
            "role": test_admin.role,
            "full_name": test_admin.full_name,
            "session_id": str(uuid4()),
        },
        "access"
    )


@pytest.fixture
def regular_admin_token(test_regular_admin):
    """Create JWT token for regular admin."""
    return create_jwt_token(
        {
            "sub": str(test_regular_admin.id),
            "email": test_regular_admin.email,
            "role": test_regular_admin.role,
            "full_name": test_regular_admin.full_name,
            "session_id": str(uuid4()),
        },
        "access"
    )


@pytest.fixture
def auditor_token(test_auditor):
    """Create JWT token for auditor."""
    return create_jwt_token(
        {
            "sub": str(test_auditor.id),
            "email": test_auditor.email,
            "role": test_auditor.role,
            "full_name": test_auditor.full_name,
            "session_id": str(uuid4()),
        },
        "access"
    )


@pytest.fixture
def admin_headers(admin_token):
    """Get headers with admin token."""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


@pytest.fixture
def regular_admin_headers(regular_admin_token):
    """Get headers with regular admin token."""
    return {
        "Authorization": f"Bearer {regular_admin_token}",
        "Content-Type": "application/json",
    }


@pytest.fixture
def auditor_headers(auditor_token):
    """Get headers with auditor token."""
    return {
        "Authorization": f"Bearer {auditor_token}",
        "Content-Type": "application/json",
    }


# ===== UTILITY FIXTURES =====

@pytest.fixture
def test_data():
    """Provide common test data."""
    return {
        "admin_email": "admin@test.com",
        "admin_password": "AdminTest123!",
        "regular_email": "regular@test.com",
        "regular_password": "RegularTest123!",
        "new_user_email": "newuser@test.com",
        "new_user_password": "NewUser123!",
        "new_user_name": "New User",
    }


@pytest.fixture
def invalid_token():
    """Provide an invalid JWT token."""
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.invalid"


@pytest.fixture
def expired_token():
    """Create an expired JWT token."""
    data = {
        "sub": str(uuid4()),
        "email": "test@test.com",
        "exp": datetime.utcnow() - timedelta(hours=1),
    }
    return create_jwt_token(data, "access")


# ===== CLEANUP FIXTURES =====

@pytest.fixture(autouse=True)
def setup_test_env(test_env):
    """Auto-use test environment for all tests."""
    pass
