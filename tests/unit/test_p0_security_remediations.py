"""
Unit tests for P0 security remediations (C-01, C-02, C-03, C-04, C-10).
"""

import hmac
import hashlib
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import create_app
from app.core.config import Settings, Environment
from app.api.v1.endpoints.whatsapp import verify_whatsapp_signature
from app.services.validation.security_validator import InMemorySlidingWindowRateLimiter, SecurityValidator
from app.api.v1.endpoints.admin.auth import InMemoryLockoutTracker, _check_lockout, _record_failure, _clear_failures
from app.services.queue.rabbitmq_service import rabbitmq_service
from fastapi import HTTPException
from pydantic import SecretStr


class TestWhatsAppSignatureVerification:
    """Test suite for C-03: WhatsApp webhook HMAC-SHA256 signature verification."""

    def test_verify_signature_valid(self):
        body = b'{"object": "whatsapp_business_account"}'
        secret = "test-secret-key-12345"
        expected_hash = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        sig = f"sha256={expected_hash}"

        with patch("app.api.v1.endpoints.whatsapp.settings.WHATSAPP_APP_SECRET", SecretStr(secret)):
            assert verify_whatsapp_signature(body, sig) is True

    def test_verify_signature_invalid_hash(self):
        body = b'{"object": "whatsapp_business_account"}'
        secret = "test-secret-key-12345"
        sig = "sha256=invalid_hash_value_that_does_not_match"

        with patch("app.api.v1.endpoints.whatsapp.settings.WHATSAPP_APP_SECRET", SecretStr(secret)):
            assert verify_whatsapp_signature(body, sig) is False

    def test_verify_signature_tampered_body(self):
        body = b'{"object": "whatsapp_business_account"}'
        tampered_body = b'{"object": "whatsapp_business_account", "extra": "data"}'
        secret = "test-secret-key-12345"
        expected_hash = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        sig = f"sha256={expected_hash}"

        with patch("app.api.v1.endpoints.whatsapp.settings.WHATSAPP_APP_SECRET", SecretStr(secret)):
            assert verify_whatsapp_signature(tampered_body, sig) is False

    def test_verify_signature_missing_prefix(self):
        body = b'{"test": 1}'
        secret = "test-secret"
        valid_hash = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with patch("app.api.v1.endpoints.whatsapp.settings.WHATSAPP_APP_SECRET", SecretStr(secret)):
            assert verify_whatsapp_signature(body, valid_hash) is False  # Missing 'sha256='
            assert verify_whatsapp_signature(body, None) is False

    def test_endpoint_rejects_missing_signature_in_production(self):
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        payload = {"object": "whatsapp_business_account", "entry": []}

        with patch("app.api.v1.endpoints.whatsapp.settings.ENVIRONMENT", Environment.PRODUCTION):
            response = client.post("/api/v1/whatsapp/webhook", json=payload)
            assert response.status_code == 401
            assert "unauthorized" in response.json()["status"]

    def test_endpoint_rejects_invalid_signature(self):
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        payload = {"object": "whatsapp_business_account", "entry": []}

        headers = {"X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000"}
        response = client.post("/api/v1/whatsapp/webhook", json=payload, headers=headers)
        assert response.status_code == 401


class TestProductionSecretsEnforcement:
    """Test suite for C-02: Enforcing secure production secrets."""

    def test_rejects_insecure_internal_secret_in_production(self):
        with pytest.raises(ValueError, match="INTERNAL_API_SECRET is insecure for production/staging"):
            Settings(
                ENVIRONMENT=Environment.PRODUCTION,
                INTERNAL_API_SECRET=SecretStr("internal-secret-token-for-worker-delegation"),
                JWT_SECRET=SecretStr("strong-jwt-secret-minimum-32-chars-long!"),
                JWT_REFRESH_SECRET=SecretStr("strong-refresh-secret-minimum-32-chars-long!"),
                ENCRYPTION_KEY=SecretStr("YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE="),
                CSRF_SECRET=SecretStr("strong-csrf-secret-minimum-32-chars-long!"),
                POSTGRES_PASSWORD=SecretStr("postgres_pass_123456"),
                REDIS_PASSWORD=SecretStr("redis_pass_123456"),
                RABBITMQ_PASSWORD=SecretStr("rabbit_pass_123456"),
                GEMINI_API_KEY=SecretStr("gemini_key_123456"),
                WHATSAPP_ACCESS_TOKEN=SecretStr("wa_token_123456"),
                WHATSAPP_VERIFY_TOKEN=SecretStr("wa_verify_123456"),
                WHATSAPP_PHONE_NUMBER_ID="123456789",
                WHATSAPP_APP_SECRET=SecretStr("wa_secret_123456"),
            )

    def test_accepts_strong_secrets_in_production(self):
        settings_instance = Settings(
            ENVIRONMENT=Environment.PRODUCTION,
            INTERNAL_API_SECRET=SecretStr("super-secure-production-internal-token-32-chars"),
            JWT_SECRET=SecretStr("strong-jwt-secret-minimum-32-chars-long!"),
            JWT_REFRESH_SECRET=SecretStr("strong-refresh-secret-minimum-32-chars-long!"),
            ENCRYPTION_KEY=SecretStr("YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE="),
            CSRF_SECRET=SecretStr("strong-csrf-secret-minimum-32-chars-long!"),
            POSTGRES_PASSWORD=SecretStr("postgres_pass_123456"),
            REDIS_PASSWORD=SecretStr("redis_pass_123456"),
            RABBITMQ_PASSWORD=SecretStr("rabbit_pass_123456"),
            GEMINI_API_KEY=SecretStr("gemini_key_123456"),
            WHATSAPP_ACCESS_TOKEN=SecretStr("wa_token_123456"),
            WHATSAPP_VERIFY_TOKEN=SecretStr("wa_verify_123456"),
            WHATSAPP_PHONE_NUMBER_ID="123456789",
            WHATSAPP_APP_SECRET=SecretStr("wa_secret_123456"),
        )
        assert settings_instance.INTERNAL_API_SECRET.get_secret_value() == "super-secure-production-internal-token-32-chars"


class TestRateLimiterAndLockoutFallback:
    """Test suite for C-04: In-memory fallback for rate limiting and login lockout."""

    def test_in_memory_rate_limiter_sliding_window(self):
        limiter = InMemorySlidingWindowRateLimiter(max_keys=100)
        # Limit to 3 requests per 60 seconds
        key = "test:ip:1.2.3.4"
        assert limiter.check(key, max_requests=3, window_seconds=60)[0] is True
        assert limiter.check(key, max_requests=3, window_seconds=60)[0] is True
        assert limiter.check(key, max_requests=3, window_seconds=60)[0] is True
        # 4th request must be rejected
        allowed, remaining, reset_in = limiter.check(key, max_requests=3, window_seconds=60)
        assert allowed is False
        assert remaining == 0
        assert reset_in > 0

    @pytest.mark.asyncio
    async def test_security_validator_falls_back_when_redis_fails(self):
        validator = SecurityValidator()
        mock_broken_cache = MagicMock()
        mock_broken_cache._get_client = AsyncMock(side_effect=ConnectionError("Redis down"))
        with patch("app.services.validation.security_validator.cache_service", mock_broken_cache):
            # Must NOT raise, and must enforce rate limit via fallback
            key = "fallback:test"
            assert (await validator.check_rate_limit(key, max_requests=2, window_seconds=60))[0] is True
            assert (await validator.check_rate_limit(key, max_requests=2, window_seconds=60))[0] is True
            # 3rd request blocked
            assert (await validator.check_rate_limit(key, max_requests=2, window_seconds=60))[0] is False

    def test_in_memory_lockout_tracker_locks_out_after_failures(self):
        tracker = InMemoryLockoutTracker()
        ip = "192.168.1.100"
        for _ in range(4):
            tracker.record_failure(ip, max_failures=5, failures_ttl=60, lockout_ttl=60)
            assert tracker.check_lockout(ip) is None

        # 5th failure triggers lockout
        tracker.record_failure(ip, max_failures=5, failures_ttl=60, lockout_ttl=60)
        remaining = tracker.check_lockout(ip)
        assert remaining is not None
        assert remaining > 0

        # Clearing failures unlocks
        tracker.clear_failures(ip)
        assert tracker.check_lockout(ip) is None


class TestInternalEndpointSecurity:
    """Test suite for C-10: Masking exception details in internal endpoints."""

    def test_internal_error_does_not_leak_exception(self):
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        
        secret = "test-secret"
        with patch("app.api.v1.endpoints.internal.settings.INTERNAL_API_SECRET", SecretStr(secret)):
            # Force RAG service to be set so it reaches the processing block
            app.state.rag_service = MagicMock()
            
            with patch("app.api.v1.endpoints.internal.WhatsAppService.process_webhook", side_effect=Exception("Database password leak: postgres://admin:supersecret@db:5432")):
                response = client.post(
                    "/api/v1/internal/process-whatsapp",
                    headers={"X-Internal-Secret": secret},
                    json={"payload": {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [{"id": "1"}]}}]}]}}
                )
                assert response.status_code == 500
                detail = response.json().get("detail", "")
                assert "supersecret" not in detail
                assert "postgres://" not in detail
                assert "Database password leak" not in detail
                assert detail == "An internal error occurred during processing."
