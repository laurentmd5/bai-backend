"""
Unit tests for Worker HTTP Delegation (Solution 3).
Tests authentication of the internal endpoint and the lightweight worker delegation logic.
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import httpx

from app.main import create_app
from app.core.config import settings
from worker import process_webhook_task


@pytest.fixture
def app():
    """Create test application."""
    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestInternalEndpoint:
    """Tests for the internal inter-service endpoint."""

    def test_internal_endpoint_rejects_missing_secret(self, client):
        """Requests without the X-Internal-Secret header must be rejected with 403."""
        response = client.post(
            "/api/v1/internal/process-whatsapp",
            json={"payload": {"test": "event"}, "raw_body": "test", "signature": None}
        )
        assert response.status_code == 403
        assert "Unauthorized" in response.text

    def test_internal_endpoint_rejects_invalid_secret(self, client):
        """Requests with wrong secret must be rejected with 403."""
        response = client.post(
            "/api/v1/internal/process-whatsapp",
            headers={"X-Internal-Secret": "wrong-secret-token"},
            json={"payload": {"test": "event"}, "raw_body": "test", "signature": None}
        )
        assert response.status_code == 403

    def test_internal_endpoint_accepts_valid_secret(self, client):
        """Requests with valid secret proceed to RAG/WhatsApp processing."""
        valid_secret = settings.INTERNAL_API_SECRET.get_secret_value()
        
        # When RAG service is not initialized in raw test app, it returns 503 Service Unavailable (which proves auth passed)
        response = client.post(
            "/api/v1/internal/process-whatsapp",
            headers={"X-Internal-Secret": valid_secret},
            json={"payload": {"test": "event"}, "raw_body": "test", "signature": None}
        )
        # Auth succeeded: either 200 (if rag ready) or 503 (if rag state is empty in test)
        assert response.status_code in (200, 503)


class TestWorkerDelegation:
    """Tests for worker process_webhook_task HTTP delegation."""

    @pytest.mark.asyncio
    async def test_process_webhook_task_sends_http_post(self):
        """Verify that worker sends an authenticated HTTP request to backend."""
        fake_payload = {"entry": [{"changes": [{"value": {"messages": [{"text": {"body": "hello"}}]}}]}]}
        fake_raw_body = b'{"entry": []}'
        fake_sig = "sha256=abcdef"

        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await process_webhook_task(
                payload=fake_payload,
                raw_body=fake_raw_body,
                signature=fake_sig
            )

            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args.kwargs
            assert "headers" in call_kwargs
            assert call_kwargs["headers"]["X-Internal-Secret"] == settings.INTERNAL_API_SECRET.get_secret_value()
            assert call_kwargs["json"]["payload"] == fake_payload
            assert call_kwargs["json"]["signature"] == fake_sig
