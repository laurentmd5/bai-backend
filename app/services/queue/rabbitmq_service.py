import json
import aio_pika
from typing import Callable, Awaitable, Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

class RabbitMQService:
    def __init__(self):
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None

    async def connect(self):
        """Establish a connection to RabbitMQ."""
        if self._connection and not self._connection.is_closed:
            return

        try:
            self._connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            self._channel = await self._connection.channel()
            logger.info("rabbitmq_connected", url=settings.rabbitmq_url.replace(settings.RABBITMQ_PASSWORD.get_secret_value(), "****"))
            
            # Ensure queue exists
            await self._channel.declare_queue(
                settings.RABBITMQ_WEBHOOK_QUEUE,
                durable=True
            )
        except Exception as e:
            logger.error("rabbitmq_connection_failed", error=str(e))
            raise

    async def close(self):
        """Close the RabbitMQ connection."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("rabbitmq_connection_closed")

    async def publish_webhook_event(self, payload: dict, raw_body: bytes, signature: str | None):
        """Publish a webhook event to the queue."""
        if not self._channel or self._channel.is_closed:
            await self.connect()

        # We must decode raw_body to string to serialize it in JSON
        # signature can be None
        message_body = {
            "payload": payload,
            "raw_body": raw_body.decode('utf-8') if isinstance(raw_body, bytes) else raw_body,
            "signature": signature
        }

        message = aio_pika.Message(
            body=json.dumps(message_body).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )

        await self._channel.default_exchange.publish(
            message,
            routing_key=settings.RABBITMQ_WEBHOOK_QUEUE,
        )
        logger.info("rabbitmq_message_published", queue=settings.RABBITMQ_WEBHOOK_QUEUE)

    async def consume_webhook_events(self, callback: Callable[[dict, bytes, str | None], Awaitable[Any]]):
        """Consume messages from the queue and pass them to the callback."""
        if not self._channel or self._channel.is_closed:
            await self.connect()

        queue = await self._channel.declare_queue(
            settings.RABBITMQ_WEBHOOK_QUEUE,
            durable=True
        )

        await self._channel.set_qos(prefetch_count=10)

        logger.info("rabbitmq_started_consuming", queue=settings.RABBITMQ_WEBHOOK_QUEUE)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        data = json.loads(message.body.decode("utf-8"))
                        payload = data.get("payload")
                        raw_body_str = data.get("raw_body")
                        raw_body = raw_body_str.encode('utf-8') if raw_body_str else b""
                        signature = data.get("signature")
                        
                        logger.debug("rabbitmq_message_received", queue=settings.RABBITMQ_WEBHOOK_QUEUE)
                        await callback(payload, raw_body, signature)
                    except Exception as e:
                        logger.error("rabbitmq_message_processing_failed", error=str(e), exc_info=True)
                        # We could implement dead-letter queues here in the future
                        # For now, it will be discarded since we use message.process() which acks automatically on success or failure.

rabbitmq_service = RabbitMQService()
