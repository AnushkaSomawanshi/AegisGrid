# AegisGrid Live Demo Script (8–12 minutes)

## 1. Set expectations (30 seconds)
Introduce AegisGrid as an academic distributed emergency response and resource coordination platform. It combines a real containerized application architecture with deterministic models for algorithms. Clarify that it is not connected to real emergency systems and sample chart values are illustrative.

## 2. Start with architecture (1 minute)
Open Service Topology and explain:
- React frontend for operator workflow.
- FastAPI gateway validates commands and exposes REST/WebSocket endpoints.
- PostgreSQL persists incidents and event records.
- RabbitMQ carries durable asynchronous messages.
- Independent worker consumes messages and records processing acknowledgements.
Explain synchronous HTTP/database traffic versus asynchronous broker/worker communication.

## 3. Create an incident (1 minute)
Open Incident Response, create a medical or infrastructure demo incident, and set severity. Confirm its initial state, then update the status to assigned/responding/resolved. The UI should announce when changes are session-only because API is disconnected; for a full demo, start Compose and confirm API connectivity first.

## 4. Follow the event (1 minute)
Open Event Ledger and expand the latest incident event. Point out event type, source, timestamp and payload. Emit a demo event, inspect the API broker result if using API docs, then inspect worker logs and a worker.processed event. Make the distinction among persistence, publish, and processing explicit.

## 5. Explain time and causality (2 minutes)
- Physical clock sync: use signed corrections to explain clock offsets and the limitations of simple averaging.
- Lamport clock: show the send/receive relationship; explain that scalar order does not prove causality.
- Vector clocks: compare one dominating pair and one incomparable pair.
- Snapshot: point out the in-transit channel message and consistent-cut principle.

## 6. Explain coordination and failure (2 minutes)
- Bully election: highest live ID wins in the model; note failure detection and split-brain limitations.
- Ricart–Agrawala: timestamp plus process ID determines request order; this is not a real lock.
- Heartbeat failure: a threshold triggers suspicion, not certainty; delayed packets can create false positives.

## 7. Demonstrate scaling (2 minutes)
Open Scale & Resilience and show that the replica planner is explicitly illustrative. In the terminal run `docker compose up -d --scale worker=3`. Inspect `docker compose ps`, emit repeatable events, and observe actual worker logs/ledger records. For Kubernetes, show deployment/Pod state and one controlled Pod-recovery test from a development cluster.

Do not state a throughput improvement unless it has been measured from the same workload at each replica count.

## 8. Close with engineering trade-offs (1 minute)
Discuss why a broker decouples publishers from consumers, why persistence is separate from delivery, and why the current project needs a transactional outbox, idempotency, retry/dead-letter policy, authentication, secure secrets and observability before production use.
