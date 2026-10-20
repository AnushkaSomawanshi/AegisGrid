"""Independent RabbitMQ consumer with idempotent event-ID handling."""
import hashlib
import json
import os
import time
from datetime import datetime, timezone
import pika
from sqlalchemy.exc import IntegrityError
from .db import SessionLocal, EventRecord, ProcessedMessage


def main() -> None:
    host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    credentials = pika.PlainCredentials(os.getenv("RABBITMQ_USER", "aegisgrid"), os.getenv("RABBITMQ_PASSWORD", "aegisgrid_dev"))
    params = pika.ConnectionParameters(host=host, port=int(os.getenv("RABBITMQ_PORT", "5672")), credentials=credentials,
                                       heartbeat=30, blocked_connection_timeout=20)
    while True:
        try:
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue="aegisgrid.events", durable=True)
            channel.basic_qos(prefetch_count=1)
            print(f"[worker] connected to RabbitMQ at {host}; waiting for events", flush=True)

            def handle(ch, method, properties, body):
                try:
                    event = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    print(f"[worker] invalid message; reject without requeue: {exc}", flush=True)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    return
                nested = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                event_id = str(nested.get("event_id") or event.get("event_id") or hashlib.sha256(body).hexdigest())
                event_type = str(event.get("event_type", "unknown"))
                db = SessionLocal()
                try:
                    existing = db.query(ProcessedMessage).filter(ProcessedMessage.event_id == event_id).first()
                    if existing is not None:
                        print(f"[worker] duplicate {event_id}; already processed, acknowledging", flush=True)
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                        return
                    db.add(ProcessedMessage(event_id=event_id, event_type=event_type))
                    db.add(EventRecord(event_type="worker.processed", source="worker",
                                       payload=json.dumps({"event_id": event_id, "original_event_type": event_type,
                                                           "original_source": event.get("source", "unknown"),
                                                           "worker_status": "acknowledged",
                                                           "original_payload": nested}, ensure_ascii=False)))
                    db.commit()
                    print(f"[worker] processed event {event_id} ({event_type})", flush=True)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except IntegrityError:
                    db.rollback()
                    # A competing consumer may have committed this event between SELECT and INSERT.
                    existing = db.query(ProcessedMessage).filter(ProcessedMessage.event_id == event_id).first()
                    if existing is not None:
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                        print(f"[worker] concurrent duplicate {event_id}; acknowledged", flush=True)
                    else:
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                except Exception as exc:
                    db.rollback()
                    print(f"[worker] processing failed for {event_id}: {exc}", flush=True)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                finally:
                    db.close()
            channel.basic_consume(queue="aegisgrid.events", on_message_callback=handle)
            channel.start_consuming()
        except Exception as exc:
            print(f"[worker] broker unavailable ({exc}); retrying in 4s", flush=True)
            time.sleep(4)


if __name__ == "__main__":
    main()
