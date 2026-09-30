import asyncio
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

    async def _setup_queues(self) -> aio_pika.RobustQueue:
        """
        Declare Dead-Letter Exchange (DLX), Dead-Letter Queue (DLQ),
        and the main webhook queue configured with dead-letter routing.
        """
        # 1. Declare Dead-Letter Exchange (DLX)
        dlx = await self._channel.declare_exchange(
            settings.RABBITMQ_WEBHOOK_DLX,
            type=aio_pika.ExchangeType.DIRECT,
            durable=True,
        )

        # 2. Declare Dead-Letter Queue (DLQ) and bind to DLX
        dlq = await self._channel.declare_queue(
            settings.RABBITMQ_WEBHOOK_DLQ,
            durable=True,
        )
        await dlq.bind(dlx, routing_key=settings.RABBITMQ_WEBHOOK_DLQ)

        # 3. Declare Main Webhook Queue with DLX arguments
        queue_args = {
            "x-dead-letter-exchange": settings.RABBITMQ_WEBHOOK_DLX,
            "x-dead-letter-routing-key": settings.RABBITMQ_WEBHOOK_DLQ,
        }
        try:
            return await self._channel.declare_queue(
                settings.RABBITMQ_WEBHOOK_QUEUE,
                durable=True,
                arguments=queue_args,
            )
        except Exception as e:
            logger.warning(
                "rabbitmq_main_queue_declare_with_dlx_failed_falling_back",
                error=str(e),
            )
            # Reopen channel if closed due to 406 PRECONDITION_FAILED
            if self._channel.is_closed:
                self._channel = await self._connection.channel()
            return await self._channel.declare_queue(
                settings.RABBITMQ_WEBHOOK_QUEUE,
                durable=True,
            )

    async def connect(self):
        """Establish a connection to RabbitMQ and setup DLQ topology."""
        if self._connection and not self._connection.is_closed:
            return

        try:
            self._connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            self._channel = await self._connection.channel()
            masked_url = settings.rabbitmq_url.replace(
                settings.RABBITMQ_PASSWORD.get_secret_value(), "****"
            )
            logger.info("rabbitmq_connected", url=masked_url)

            # Ensure DLQ and main queue exist
            await self._setup_queues()
        except Exception as e:
            logger.error("rabbitmq_connection_failed", error=str(e))
            raise

    async def close(self):
        """Close the RabbitMQ connection."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("rabbitmq_connection_closed")

    async def publish_webhook_event(
        self,
        payload: dict,
        raw_body: bytes,
        signature: str | None,
        headers: dict | None = None,
    ):
        """Publish a webhook event to the queue."""
        if not self._channel or self._channel.is_closed:
            await self.connect()

        message_body = {
            "payload": payload,
            "raw_body": raw_body.decode('utf-8', errors='replace') if isinstance(raw_body, bytes) else (raw_body or ""),
            "signature": signature,
        }

        msg_headers = {"x-retry-count": 0}
        if headers:
            msg_headers.update(headers)

        message = aio_pika.Message(
            body=json.dumps(message_body).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            headers=msg_headers,
        )

        await self._channel.default_exchange.publish(
            message,
            routing_key=settings.RABBITMQ_WEBHOOK_QUEUE,
        )
        logger.info("rabbitmq_message_published", queue=settings.RABBITMQ_WEBHOOK_QUEUE)

    async def consume_webhook_events(self, callback: Callable[[dict, bytes, str | None], Awaitable[Any]]):
        """
        Consume messages from the queue and pass them to the callback.
        Enforces retry with exponential backoff and dead-letter routing to DLQ.
        """
        if not self._channel or self._channel.is_closed:
            await self.connect()

        queue = await self._setup_queues()
        await self._channel.set_qos(prefetch_count=10)

        logger.info(
            "rabbitmq_started_consuming",
            queue=settings.RABBITMQ_WEBHOOK_QUEUE,
            dlq=settings.RABBITMQ_WEBHOOK_DLQ,
            max_retries=settings.RABBITMQ_MAX_RETRIES,
        )

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                retry_count = int(message.headers.get("x-retry-count", 0)) if message.headers else 0
                try:
                    data = json.loads(message.body.decode("utf-8"))
                    payload = data.get("payload")
                    raw_body_str = data.get("raw_body")
                    raw_body = raw_body_str.encode('utf-8') if raw_body_str else b""
                    signature = data.get("signature")

                    logger.debug(
                        "rabbitmq_message_received",
                        queue=settings.RABBITMQ_WEBHOOK_QUEUE,
                        retry_count=retry_count,
                    )
                    await callback(payload, raw_body, signature)
                    await message.ack()
                    logger.debug("rabbitmq_message_acked", retry_count=retry_count)

                except Exception as e:
                    logger.error(
                        "rabbitmq_message_processing_failed",
                        error=str(e),
                        retry_count=retry_count,
                        max_retries=settings.RABBITMQ_MAX_RETRIES,
                        exc_info=True,
                    )

                    if retry_count < settings.RABBITMQ_MAX_RETRIES:
                        new_retry_count = retry_count + 1
                        backoff_seconds = settings.RABBITMQ_RETRY_BACKOFF_SECONDS * (2 ** retry_count)
                        logger.warning(
                            "rabbitmq_retrying_message",
                            attempt=new_retry_count,
                            max_retries=settings.RABBITMQ_MAX_RETRIES,
                            backoff_seconds=backoff_seconds,
                        )
                        await asyncio.sleep(min(backoff_seconds, 60))

                        # Republish with incremented retry count
                        new_headers = dict(message.headers or {})
                        new_headers["x-retry-count"] = new_retry_count
                        new_headers["x-last-error"] = str(e)[:255]

                        retry_message = aio_pika.Message(
                            body=message.body,
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            headers=new_headers,
                        )
                        await self._channel.default_exchange.publish(
                            retry_message,
                            routing_key=settings.RABBITMQ_WEBHOOK_QUEUE,
                        )
                        # Acknowledge original so it doesn't block or duplicate
                        await message.ack()
                    else:
                        # Max retries exceeded: Reject without requeue (routes to DLQ via DLX)
                        logger.critical(
                            "rabbitmq_message_exhausted_retries_routing_to_dlq",
                            queue=settings.RABBITMQ_WEBHOOK_QUEUE,
                            dlq=settings.RABBITMQ_WEBHOOK_DLQ,
                            total_retries=retry_count,
                            error=str(e),
                        )
                        await message.reject(requeue=False)


rabbitmq_service = RabbitMQService()
