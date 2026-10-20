"""Background outbox dispatcher: retries pending event envelopes with bounded polling delay.

The consumer is idempotent by stable event_id, so an ambiguous publisher confirmation may
lead to redelivery without duplicating worker side effects.
"""
import json
import os
import time
from datetime import datetime, timezone
from sqlalchemy import asc
from .db import SessionLocal, OutboxRecord
from .broker import publish_event

POLL_SECONDS = max(1, int(os.getenv("OUTBOX_POLL_SECONDS", "3")))
BATCH_SIZE = max(1, min(100, int(os.getenv("OUTBOX_BATCH_SIZE", "25"))))


def dispatch_once() -> int:
    db = SessionLocal()
    sent = 0
    try:
        pending = db.query(OutboxRecord).filter(OutboxRecord.status == "pending").order_by(asc(OutboxRecord.id)).limit(BATCH_SIZE).all()
        for row in pending:
            try:
                payload = json.loads(row.payload)
            except json.JSONDecodeError:
                row.status = "dead-letter"
                row.last_error = "invalid outbox JSON; automatic retry stopped"
                continue
            result = publish_event(row.event_type, payload, "outbox-dispatcher")
            row.attempts += 1
            row.last_error = result.get("detail", "") or ""
            if result.get("delivery") == "published":
                row.status = "published"
                row.published_at = datetime.now(timezone.utc)
                sent += 1
            # Failures remain pending and are retried on a later poll. A future production
            # version should add exponential backoff and a configurable dead-letter threshold.
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return sent


def main() -> None:
    print(f"[outbox-dispatcher] polling pending events every {POLL_SECONDS}s", flush=True)
    while True:
        try:
            count = dispatch_once()
            if count:
                print(f"[outbox-dispatcher] confirmed {count} publication(s)", flush=True)
        except Exception as exc:
            print(f"[outbox-dispatcher] dispatch cycle failed: {exc}", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
