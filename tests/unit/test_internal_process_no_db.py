"""
Unit tests for internal process endpoint bypass.
Verifies that webhooks without messages (delivery receipts/statuses)
do NOT trigger database session acquisition or ChatService initialization.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import create_app
from app.core.config import settings


STATUS_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "123456789",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "+221338000000",
                            "phone_number_id": "123456789"
                        },
                        "statuses": [
                            {
                                "id": "wamid.HBgLMjIx...",
                                "status": "read",
                                "timestamp": "1713340200",
                                "recipient_id": "221770000000"
                            }
                        ]
                    },
                    "field": "messages"
                }
            ]
        }
    ]
}


class TestInternalProcessBypass:
    """Test fast-fail bypass in /api/v1/internal/process-whatsapp."""

    @pytest.fixture
    def client(self):
        app = create_app()
        # Mock rag_service on app.state
        app.state.rag_service = MagicMock()
        return TestClient(app, raise_server_exceptions=False)

    def test_status_webhook_skips_db_session_acquisition(self, client):
        """Webhooks with only status updates must return ignored without calling get_session_context."""
        secret = settings.INTERNAL_API_SECRET.get_secret_value()
        
        with patch("app.api.v1.endpoints.internal.get_session_context") as mock_session_ctx:
            response = client.post(
                "/api/v1/internal/process-whatsapp",
                headers={
                    "X-Internal-Secret": secret,
                    "Content-Type": "application/json"
                },
                json={
                    "payload": STATUS_PAYLOAD,
                    "raw_body": "{}",
                    "signature": "sha256=test"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["result"]["status"] == "ignored"
            assert data["result"]["reason"] == "no_messages"
            
            # CRITICAL SRE ASSERTION: Database session was NEVER opened
            mock_session_ctx.assert_not_called()
