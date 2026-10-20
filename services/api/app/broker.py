"""RabbitMQ publisher. Failed broker delivery is surfaced, never silently called successful."""
import json
import os
from datetime import datetime, timezone


def publish_event(event_type: str, payload: dict, source: str = "api") -> dict:
    message = {
        "event_type": event_type,
        "source": source,
        "payload": payload,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    host = os.getenv("RABBITMQ_HOST")
    if not host:
        return {**message, "delivery": "local-only", "detail": "RABBITMQ_HOST not configured"}
    try:
        import pika
        credentials = pika.PlainCredentials(
            os.getenv("RABBITMQ_USER", "guest"),
            os.getenv("RABBITMQ_PASSWORD", "guest"),
        )
        params = pika.ConnectionParameters(
            host=host,
            port=int(os.getenv("RABBITMQ_PORT", "5672")),
            credentials=credentials,
            connection_attempts=2,
            retry_delay=1,
            socket_timeout=3,
        )
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.queue_declare(queue="aegisgrid.events", durable=True)
        channel.confirm_delivery()
        channel.basic_publish(
            exchange="",
            routing_key="aegisgrid.events",
            mandatory=True,
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
        )
        connection.close()
        return {**message, "delivery": "published"}
    except Exception as exc:
        return {**message, "delivery": "failed", "detail": str(exc)[:240]}
