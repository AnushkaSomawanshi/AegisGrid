"""Independent RabbitMQ consumer service."""
import json
import os
import time
from datetime import datetime, timezone
from .db import SessionLocal, init_db, EventRecord


def main() -> None:
    init_db()
    host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    import pika
    credentials = pika.PlainCredentials(os.getenv("RABBITMQ_USER", "aegisgrid"), os.getenv("RABBITMQ_PASSWORD", "aegisgrid_dev"))
    params = pika.ConnectionParameters(host=host, port=int(os.getenv("RABBITMQ_PORT","5672")), credentials=credentials,
                                       heartbeat=30, blocked_connection_timeout=20)
    while True:
        try:
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue="aegisgrid.events", durable=True)
            channel.basic_qos(prefetch_count=1)
            print(f"[worker] connected to RabbitMQ at {host}; waiting for events", flush=True)

            def handle(ch, method, properties, body):
                event = json.loads(body.decode("utf-8"))
                db = SessionLocal()
                try:
                    record = EventRecord(event_type="worker.processed", source="worker",
                                         payload=json.dumps({"original_event_type":event.get("event_type"),
                                                             "original_source":event.get("source"),
                                                             "worker_status":"acknowledged",
                                                             "original_payload":event.get("payload",{})}))
                    db.add(record)
                    db.commit()
                    print(f"[worker] processed {event.get('event_type')} -> ledger row {record.id}", flush=True)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as exc:
                    db.rollback()
                    print(f"[worker] processing failed: {exc}", flush=True)
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
