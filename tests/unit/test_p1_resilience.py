"""
Unit tests for P1 Resilience and Security (C-12: RabbitMQ DLQ/Retries & C-06: Qdrant API Key).
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pydantic import SecretStr

from app.core.config import Settings, Environment
from app.services.queue.rabbitmq_service import RabbitMQService
from app.services.vector.qdrant_store import QdrantVectorStore
from app.services.cache.redis_cache import cache_service, CacheNamespace, RedisCacheService


class FakeQueueIterator:
    def __init__(self, messages):
        self.messages = messages

    async def __aenter__(self):
        async def gen():
            for m in self.messages:
                yield m
        return gen()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class TestRabbitMQResilience:
    """Tests for C-12: RabbitMQ Dead-Letter Queue (DLQ) and Retry Mechanism."""

    @pytest.mark.asyncio
    async def test_setup_queues_declares_dlx_and_dlq(self):
        """Verify that DLX, DLQ, and main queue with DLX arguments are declared."""
        service = RabbitMQService()
        mock_channel = AsyncMock()
        service._channel = mock_channel

        mock_dlx = AsyncMock()
        mock_dlq = AsyncMock()
        mock_main_queue = AsyncMock()

        mock_channel.declare_exchange.return_value = mock_dlx
        mock_channel.declare_queue.side_effect = [mock_dlq, mock_main_queue]

        queue = await service._setup_queues()

        # Check DLX declaration
        mock_channel.declare_exchange.assert_called_once_with(
            "whatsapp_webhooks_dlx",
            type="direct",
            durable=True,
        )
        # Check DLQ declaration and binding
        mock_channel.declare_queue.assert_any_call("whatsapp_webhooks_dlq", durable=True)
        mock_dlq.bind.assert_called_once_with(mock_dlx, routing_key="whatsapp_webhooks_dlq")

        # Check main queue declaration with DLX arguments
        mock_channel.declare_queue.assert_any_call(
            "whatsapp_webhooks",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "whatsapp_webhooks_dlx",
                "x-dead-letter-routing-key": "whatsapp_webhooks_dlq",
            },
        )
        assert queue == mock_main_queue

    @pytest.mark.asyncio
    async def test_consume_webhook_events_acks_on_success(self):
        """Successful processing must acknowledge (ack) the message."""
        service = RabbitMQService()
        mock_channel = AsyncMock()
        mock_channel.is_closed = False
        service._channel = mock_channel
        service.connect = AsyncMock()

        # Fake incoming message
        payload = {"object": "whatsapp_business_account", "entry": []}
        msg_body = json.dumps({"payload": payload, "raw_body": "body", "signature": None}).encode()

        mock_msg = AsyncMock()
        mock_msg.body = msg_body
        mock_msg.headers = {"x-retry-count": 0}

        mock_queue = MagicMock()
        mock_queue.iterator.return_value = FakeQueueIterator([mock_msg])
        service._setup_queues = AsyncMock(return_value=mock_queue)

        mock_callback = AsyncMock()

        # Run consumer
        await service.consume_webhook_events(mock_callback)

        mock_callback.assert_called_once_with(payload, b"body", None)
        mock_msg.ack.assert_called_once()
        mock_msg.reject.assert_not_called()

    @pytest.mark.asyncio
    async def test_consume_webhook_events_retries_on_failure(self):
        """Processing error with retry_count < max_retries must republish with incremented count and ack original."""
        service = RabbitMQService()
        mock_channel = AsyncMock()
        mock_channel.is_closed = False
        mock_channel.default_exchange = AsyncMock()
        service._channel = mock_channel
        service.connect = AsyncMock()

        payload = {"object": "whatsapp_business_account"}
        msg_body = json.dumps({"payload": payload, "raw_body": "test", "signature": None}).encode()

        mock_msg = AsyncMock()
        mock_msg.body = msg_body
        mock_msg.headers = {"x-retry-count": 1}

        mock_queue = MagicMock()
        mock_queue.iterator.return_value = FakeQueueIterator([mock_msg])
        service._setup_queues = AsyncMock(return_value=mock_queue)

        mock_callback = AsyncMock(side_effect=Exception("Transient DB timeout"))

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await service.consume_webhook_events(mock_callback)
            mock_sleep.assert_called_once()

        # Republished with retry_count = 2
        mock_channel.default_exchange.publish.assert_called_once()
        published_msg = mock_channel.default_exchange.publish.call_args[0][0]
        assert published_msg.headers["x-retry-count"] == 2
        assert "Transient DB timeout" in published_msg.headers["x-last-error"]

        # Original message acked to clear inflight
        mock_msg.ack.assert_called_once()
        mock_msg.reject.assert_not_called()

    @pytest.mark.asyncio
    async def test_consume_webhook_events_sends_to_dlq_when_retries_exhausted(self):
        """When retries are exhausted (retry_count >= max_retries), message must be rejected with requeue=False (DLQ)."""
        service = RabbitMQService()
        mock_channel = AsyncMock()
        mock_channel.is_closed = False
        mock_channel.default_exchange = AsyncMock()
        service._channel = mock_channel
        service.connect = AsyncMock()

        payload = {"object": "whatsapp_business_account"}
        msg_body = json.dumps({"payload": payload, "raw_body": "test", "signature": None}).encode()

        mock_msg = AsyncMock()
        mock_msg.body = msg_body
        mock_msg.headers = {"x-retry-count": 3}  # max_retries = 3

        mock_queue = MagicMock()
        mock_queue.iterator.return_value = FakeQueueIterator([mock_msg])
        service._setup_queues = AsyncMock(return_value=mock_queue)

        mock_callback = AsyncMock(side_effect=Exception("Permanent parsing error"))

        await service.consume_webhook_events(mock_callback)

        # No republish attempt
        mock_channel.default_exchange.publish.assert_not_called()
        # Rejected with requeue=False (moves to DLQ)
        mock_msg.reject.assert_called_once_with(requeue=False)
        mock_msg.ack.assert_not_called()


class TestQdrantSecurity:
    """Tests for C-06: Qdrant API Key and Production Cloaking."""

    def test_qdrant_store_passes_api_key_to_client(self):
        """QdrantStore must pass configured QDRANT_API_KEY to QdrantClient."""
        store = QdrantVectorStore()
        with patch("app.services.vector.qdrant_store.settings.QDRANT_API_KEY", SecretStr("test-qdrant-key-32-chars-long!")):
            with patch("app.services.vector.qdrant_store.QdrantClient") as mock_qdrant_cls:
                store._client = None
                client = store._get_client()
                mock_qdrant_cls.assert_called_once_with(
                    url=store._url,
                    api_key="test-qdrant-key-32-chars-long!",
                    timeout=30.0,
                    prefer_grpc=False,
                )

    def test_production_config_rejects_missing_or_weak_qdrant_api_key(self):
        """Production environment must reject missing or default QDRANT_API_KEY."""
        with pytest.raises(ValueError, match="QDRANT_API_KEY must be set in production/staging"):
            Settings(
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
                QDRANT_API_KEY=None,
            )

        with pytest.raises(ValueError, match="QDRANT_API_KEY is insecure for production/staging"):
            Settings(
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
                QDRANT_API_KEY=SecretStr("password"),
            )

    def test_production_config_accepts_strong_qdrant_api_key(self):
        """Production environment must accept a valid strong QDRANT_API_KEY."""
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
            QDRANT_API_KEY=SecretStr("super-secure-qdrant-api-key-32-chars"),
        )
        assert settings_instance.QDRANT_API_KEY.get_secret_value() == "super-secure-qdrant-api-key-32-chars"


class TestIdempotencyRetry:
    """Tests for clear_whatsapp_processed helper for retry resilience."""

    @pytest.mark.asyncio
    async def test_clear_whatsapp_processed_clears_cache_entry(self):
        msg_id = "wamid.TEST_ID_12345"
        await cache_service.mark_whatsapp_processed(msg_id, ttl=60)
        assert await cache_service.is_whatsapp_processed(msg_id) is True

        cleared = await cache_service.clear_whatsapp_processed(msg_id)
        assert cleared is True
        assert await cache_service.is_whatsapp_processed(msg_id) is False

    @pytest.mark.asyncio
    async def test_redis_cache_service_clear_whatsapp_processed_calls_delete(self):
        real_service = RedisCacheService()
        real_service.delete = AsyncMock(return_value=1)
        result = await real_service.clear_whatsapp_processed("wamid.ABC123XYZ")
        assert result is True
        real_service.delete.assert_called_once_with(CacheNamespace.WHATSAPP_PROCESSED, "wamid.ABC123XYZ")
