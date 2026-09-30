"""
Unit tests for WhatsApp webhook edge filtering.
Verifies that delivery receipts (sent, delivered, read) without user messages
are acknowledged immediately with 200 OK and NEVER published to RabbitMQ.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.queue.rabbitmq_service import rabbitmq_service


STATUS_UPDATE_PAYLOAD = {
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
                                "status": "delivered",
                                "timestamp": "1713340200",
                                "recipient_id": "221770000000",
                                "conversation": {
                                    "id": "conv_123",
                                    "origin": {"type": "user_initiated"}
                                },
                                "pricing": {
                                    "billable": True,
                                    "pricing_model": "CBP",
                                    "category": "service"
                                }
                            }
                        ]
                    },
                    "field": "messages"
                }
            ]
        }
    ]
}

MESSAGE_PAYLOAD = {
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
                        "contacts": [
                            {
                                "profile": {"name": "Moussa Diop"},
                                "wa_id": "221770000000"
                            }
                        ],
                        "messages": [
                            {
                                "from": "221770000000",
                                "id": "wamid.HBgLMjIx...",
                                "timestamp": "1713340200",
                                "text": {"body": "Bonjour, je cherche un devis"},
                                "type": "text"
                            }
                        ]
                    },
                    "field": "messages"
                }
            ]
        }
    ]
}


class TestWhatsAppWebhookFiltering:
    """Test edge filtering on WhatsApp webhook endpoint."""

    @pytest.fixture
    def client(self):
        app = create_app()
        return TestClient(app, raise_server_exceptions=False)

    def test_status_update_is_filtered_and_not_sent_to_rabbitmq(self, client):
        """Status updates (delivered/read/sent) must return 200 and NOT hit RabbitMQ."""
        with patch.object(rabbitmq_service, "publish_webhook_event", new_callable=AsyncMock) as mock_publish:
            response = client.post(
                "/api/v1/whatsapp/webhook",
                json=STATUS_UPDATE_PAYLOAD,
                headers={"Content-Type": "application/json"}
            )
            assert response.status_code == 200
            assert response.json() == {"status": "ignored_status"}
            mock_publish.assert_not_called()

    def test_real_message_is_published_to_rabbitmq(self, client):
        """Real incoming message must return 200 and be published to RabbitMQ."""
        with patch.object(rabbitmq_service, "publish_webhook_event", new_callable=AsyncMock) as mock_publish:
            response = client.post(
                "/api/v1/whatsapp/webhook",
                json=MESSAGE_PAYLOAD,
                headers={"Content-Type": "application/json"}
            )
            assert response.status_code == 200
            assert response.json() == {"status": "received"}
            mock_publish.assert_called_once()
