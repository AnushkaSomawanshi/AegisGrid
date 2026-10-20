from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import uuid
from datetime import datetime, timezone

import aio_pika
import psycopg

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("aegisgrid.event-worker")

DATABASE_URL = os.getenv("DATABASE_URL")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5433")
POSTGRES_DB = os.getenv("POSTGRES_DB", "aegisgrid")
POSTGRES_USER = os.getenv("POSTGRES_USER", "aegisgrid")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "local-dev-only-change-me")
RABBITMQ_URL = os.getenv("RABBITMQ_URL")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = os.getenv("RABBITMQ_PORT", "5672")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "aegisgrid")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "local-dev-rabbitmq-only")
WORKER_NAME = os.getenv("WORKER_NAME", "event-worker")


def utcnow():
    return datetime.now(timezone.utc)


def database_url():
    return DATABASE_URL or (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )


def db_connect():
    return psycopg.connect(database_url(), connect_timeout=5)


def init_db():
    with db_connect() as conn:
        conn.execute("""
          CREATE TABLE IF NOT EXISTS broker_deliveries (
            id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, event_type TEXT NOT NULL,
            payload JSONB NOT NULL, consumed_at TIMESTAMPTZ NOT NULL DEFAULT now()
          )
        """)
        conn.execute("""
          CREATE TABLE IF NOT EXISTS worker_status (
            worker_name TEXT PRIMARY KEY, status TEXT NOT NULL,
            last_heartbeat TIMESTAMPTZ, processed_count BIGINT NOT NULL DEFAULT 0,
            error_count BIGINT NOT NULL DEFAULT 0, last_error TEXT
          )
        """)
        conn.execute(
            """INSERT INTO worker_status(worker_name,status,last_heartbeat)
               VALUES(%s,'STARTING',now())
               ON CONFLICT(worker_name) DO UPDATE SET status='STARTING',last_heartbeat=now(),last_error=NULL""",
            (WORKER_NAME,)
        )
        conn.commit()


def update_status(status: str, error: str | None = None):
    with db_connect() as conn:
        conn.execute(
            """INSERT INTO worker_status(worker_name,status,last_heartbeat,last_error)
               VALUES(%s,%s,now(),%s)
               ON CONFLICT(worker_name) DO UPDATE SET status=EXCLUDED.status,
                 last_heartbeat=now(),last_error=EXCLUDED.last_error""",
            (WORKER_NAME, status, error)
        )
        conn.commit()


async def heartbeat_loop():
    while True:
        try:
            await asyncio.to_thread(update_status, "READY", None)
        except Exception as exc:
            log.warning("Could not update worker heartbeat: %s", exc)
        await asyncio.sleep(5)


async def main():
    for attempt in range(20):
        try:
            await asyncio.to_thread(init_db)
            break
        except Exception as exc:
            if attempt == 19:
                raise
            log.warning("Database not ready yet (%s/20): %s", attempt + 1, exc)
            await asyncio.sleep(min(2 + attempt, 10))

    broker_url = RABBITMQ_URL or f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/"
    connection = await aio_pika.connect_robust(broker_url, client_properties={"connection_name": WORKER_NAME})
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=20)
    exchange = await channel.declare_exchange("aegisgrid.events", aio_pika.ExchangeType.TOPIC, durable=True)
    queue = await channel.declare_queue("aegisgrid.audit", durable=True)
    await queue.bind(exchange, routing_key="#")
    await asyncio.to_thread(update_status, "READY", None)
    log.info("Worker %s ready; queue=%s consumers=%s", WORKER_NAME, queue.name, queue.declaration_result.consumer_count)

    async def handle(message: aio_pika.abc.AbstractIncomingMessage):
        async with message.process(requeue=False):
            event = json.loads(message.body.decode("utf-8"))
            event_id = str(event.get("id") or message.message_id or uuid.uuid4())
            trace_id = str(event.get("trace_id") or message.correlation_id or "unknown")
            event_type = str(event.get("event_type") or message.routing_key or "unknown")
            with db_connect() as conn:
                cursor = conn.execute(
                    """INSERT INTO broker_deliveries(id,trace_id,event_type,payload)
                       VALUES(%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING""",
                    (event_id, trace_id, event_type, json.dumps(event))
                )
                if cursor.rowcount:
                    conn.execute(
                        """UPDATE worker_status SET processed_count=processed_count+1,
                           last_heartbeat=now(),status='READY',last_error=NULL WHERE worker_name=%s""",
                        (WORKER_NAME,)
                    )
                conn.commit()
            log.info("Consumed event=%s type=%s trace=%s route=%s", event_id, event_type, trace_id, message.routing_key)

    await queue.consume(handle)
    heartbeat = asyncio.create_task(heartbeat_loop())
    try:
        await asyncio.Event().wait()
    finally:
        heartbeat.cancel()
        await connection.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Worker shutdown requested")
    except Exception as exc:
        log.exception("Worker terminated unexpectedly: %s", exc)
        try:
            update_status("DEGRADED", str(exc)[:500])
        except Exception:
            pass
        raise
