# AegisGrid Architecture

## 1. Purpose

AegisGrid is an academic distributed emergency-response coordination application. Incident intake and status transitions create persistent event records. An independent outbox dispatcher retries pending envelopes and an independent worker consumes asynchronously published messages. Event and outbox records commit in one SQL transaction; stable event IDs are deduplicated by the consumer. A concept laboratory exposes distributed-systems protocols as deterministic teaching models.

The platform demonstrates containerization, service boundaries, persistence, synchronous calls, asynchronous event delivery, scaling and recovery workflows. It is not a real emergency-dispatch system.

## 2. Component model

| Component | Technology | Responsibility | Communication |
|---|---|---|---|
| Frontend | React, TypeScript, Vite, Nginx | Command centre, incident forms, event ledger, concept labs, runbooks | HTTP and WebSocket through API proxy |
| API gateway | FastAPI, SQLAlchemy | Input validation, REST endpoints, event creation, health checks, lab handlers | HTTP to DB; AMQP publish to RabbitMQ |
| Persistence | PostgreSQL | Incident state and event ledger | SQL over internal Compose/Kubernetes network |
| Broker | RabbitMQ | Durable `aegisgrid.events` queue | AMQP |
| Worker | Python + pika | Independently consume event messages and append processing acknowledgement records | AMQP and PostgreSQL |
| Concept modules | Python functions mounted in API | Deterministic protocol demonstrations | Local API call; no side effects on cluster |
| Orchestrator | Docker Compose / Kubernetes | Container lifecycle, service discovery, restart, replica management and readiness probes | Container/network/runtime APIs |

## 3. Request and event flows

### Incident creation

1. User submits a validated incident form from the frontend.
2. Frontend sends `POST /api-proxy/incidents`, Nginx forwards it to the API's `/api/incidents`.
3. FastAPI validates title, severity, category, location and description.
4. API persists the incident in PostgreSQL.
5. API appends an `incident.created` record to the event ledger.
6. API attempts to publish a durable JSON message to RabbitMQ. The API response includes the broker outcome separately from database persistence.
7. The event worker consumes the message and appends `worker.processed` to the ledger.
8. The dashboard can query incident state and event traces independently.

**Important consistency caveat:** incident creation and the event ledger commit are separate database transactions in the current teaching implementation, and RabbitMQ publish is separate from the database commit. A failure between steps may create partial outcomes. The production-grade extension would use a transactional outbox, idempotent event IDs, retry policy and dead-letter queue.

### Incident status transition

1. UI sends `PATCH /api/incidents/{id}` with a constrained status.
2. API updates the incident record.
3. API creates an `incident.status_changed` ledger event and attempts broker publication.
4. User inspects the state and event result independently.

### Asynchronous broker flow

The API declares the durable `aegisgrid.events` queue and publishes persistent JSON messages. A separate worker deployment uses `basic_qos(prefetch_count=1)`, acknowledges after the database processing record commits, and nacks/requeues on consumer processing exceptions.

The sample worker is intentionally simple. Production extensions should consider duplicate delivery, poison messages, bounded retries, dead-letter routing, consumer idempotency, publisher confirms, and observability for unacknowledged messages.

### WebSocket flow

`/ws/events` is a minimal bidirectional demonstration endpoint: it sends an initial connection notice, accepts text frames and responds with a timestamped pong. It does not claim to tail the event ledger or broadcast globally. Nginx includes a WebSocket upgrade proxy.

## 4. Persistence model

### `incidents`

- `id`: generated integer primary key
- `title`: incident title
- `category`: response category
- `severity`: low, medium, high or critical
- `status`: open, assigned, responding or resolved
- `location`: human-readable location label
- `description`: response context
- `created_at`: UTC timestamp

### `event_records`

- `id`: generated integer primary key
- `event_type`: domain event label
- `source`: source component
- `payload`: JSON encoded as text for portability
- `created_at`: UTC timestamp

The ledger is append-oriented but is not cryptographically immutable. The worker creates `worker.processed` records for messages it successfully consumes. A production event store should store structured JSON/JSONB, trace IDs, schema versions, event IDs, delivery attempts and correlation/causation IDs.

## 5. API surface

| Endpoint | Verb | Purpose |
|---|---|---|
| `/` | GET | API identity and docs links |
| `/health/live` | GET | Process liveness |
| `/health/ready` | GET | Readiness including database reachability |
| `/api/overview` | GET | Incident metrics, service indicators and recent events |
| `/api/incidents` | GET | List incident records |
| `/api/incidents` | POST | Create an incident |
| `/api/incidents/{id}` | PATCH | Update a constrained incident status |
| `/api/events` | GET | List event ledger rows |
| `/api/events/demo` | POST | Emit a demo event |
| `/api/concepts` | GET | List labs and model modes |
| `/api/labs/{lab_id}` | GET | Get an educational model trace or operations runbook |
| `/ws/events` | WebSocket | Text echo/pong stream example |
| `/docs` | GET | OpenAPI Swagger UI |

## 6. Health and failure semantics

- Liveness only indicates the API process responds.
- Readiness asks whether the database can be queried, so an API without persistence is not considered ready.
- RabbitMQ publisher status is reported on event responses, not inferred from API liveness.
- Worker processing is separate from publish confirmation. Check worker logs and `worker.processed` events.
- Frontend banner displays sample data if API connection fails. Sample charts are illustrative, not runtime measurements.
- Concept models explicitly identify synthetic traces and avoid claiming to read or alter live services.

## 7. Scaling boundaries

Stateless API/frontend/worker processes are horizontal scaling candidates. Each worker replica competes for messages from the same durable queue. PostgreSQL and RabbitMQ use persistent state and require their own availability and storage design; do not blindly scale these singleton workloads as if they were stateless replicas.

A useful experiment compares worker replica counts while recording total messages, processing time, queue depth, throughput, errors and resource usage. The result may be limited by database writes or broker capacity rather than worker CPU alone.

## 8. Security assumptions

- Intended for local, development and academic use.
- `.env` is ignored by Git. `.env.example` contains placeholders only.
- Kubernetes manifest Secret values are development placeholders and must be changed before deployment.
- Do not expose PostgreSQL, AMQP or Kubernetes admin APIs publicly.
- Never mount the Docker socket into the dashboard or hand cluster credentials to browser code.
- Add authentication, authorization, rate limiting, TLS, input audit policy and secret management before shared use.

## 9. Future production-oriented hardening

1. Transactional outbox with background publisher and publisher confirms.
2. Idempotency keys and versioned event schemas.
3. Consumer retry limit and dead-letter queue.
4. Database migrations and structured PostgreSQL JSONB fields.
5. Authentication and role-based access for incident actions.
6. Metrics endpoint, request IDs, structured logs and distributed traces.
7. NetworkPolicies, least-privilege ServiceAccounts, secret management and TLS in Kubernetes.
8. Pod disruption budgets and HPA based on measured metrics.
9. Integration/load tests and CI build/test pipeline.
10. Real runtime collection kept separate from simulation endpoints.
