"""
Pytest configuration and fixtures for BARROW.AI tests.
"""

import os
import sys
from pathlib import Path

import pytest


# Add app to path
app_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(app_root))

# Set test environment
os.environ["ENVIRONMENT"] = "development"
os.environ["DEBUG"] = "true"
os.environ["LOG_LEVEL"] = "DEBUG"


@pytest.fixture(scope="session")
def test_env():
    """Configure test environment."""
    os.environ["POSTGRES_PASSWORD"] = "test"
    os.environ["REDIS_PASSWORD"] = "test"
    os.environ["GEMINI_API_KEY"] = "test"
    os.environ["WHATSAPP_ACCESS_TOKEN"] = "test"
    yield
    # Cleanup


@pytest.fixture(autouse=True)
def setup_test_env(test_env):
    """Auto-use test environment for all tests."""
    pass
