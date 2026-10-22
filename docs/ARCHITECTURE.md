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
4. API commits the incident row to PostgreSQL.
5. The event recorder commits an `incident.created` ledger row and its outbox envelope together in a separate database transaction.
6. API attempts a fast-path publication to RabbitMQ and returns the persistence, broker and outbox outcomes separately.
7. If publication fails or is ambiguous, the independent outbox dispatcher retries pending rows; the worker consumes the message and records `worker.processed` after processing.
8. The dashboard can inspect incident state, event ledger and outbox state independently.

**Consistency boundary:** this teaching implementation does not make incident persistence, event/outbox recording and broker delivery one atomic operation. The incident row is committed before the event/outbox transaction, so failure between these operations can leave an incident without its expected event. The event ledger row and its outbox envelope are atomic with each other; the dispatcher retries pending publication; the consumer deduplicates stable event IDs before recording processing. These measures reduce lost-event risk after the outbox transaction, but they do not provide end-to-end exactly-once delivery. Validate each stage separately.

### Incident status transition

1. UI sends `PATCH /api/incidents/{incident_id}` with a constrained status.
2. API updates and commits the incident record.
3. The event recorder records the `incident.status_changed` ledger row and outbox envelope in a separate transaction, then attempts fast-path broker publication.
4. User inspects the incident state, event record, outbox status and worker processing evidence independently.

### Asynchronous broker flow

The API and outbox dispatcher publish persistent JSON envelopes to the durable `aegisgrid.events` queue. The dispatcher polls pending outbox rows and retries publication; the worker runs independently, uses `basic_qos(prefetch_count=1)`, records processed event IDs, and acknowledges only after the database processing record commits. Consumer processing exceptions are nacked/requeued.

The consumer includes event-ID deduplication, but this should not be described as complete exactly-once delivery: messages may be delivered more than once, and broker delivery, processing persistence, and acknowledgement are separate observable stages. Before production use, add and verify bounded retry/dead-letter policy, publisher confirms, poison-message handling, structured logs/metrics, and operational controls for pending/unacknowledged messages.

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
| `/api/overview` | GET | Incident metrics and recent event summary |
| `/api/incidents` | GET / POST | List incidents / create an incident |
| `/api/incidents/{incident_id}` | PATCH | Update a constrained incident status |
| `/api/events` | GET | Inspect event ledger rows |
| `/api/events/demo` | POST | Emit a demo event through the event/outbox path |
| `/api/outbox` | GET | Inspect pending/published outbox records |
| `/api/outbox/{outbox_id}/retry` | POST | Request a retry of an outbox record |
| `/api/deployment/status` | GET | Probe API/database and broker reachability; explicitly does not enumerate Pods/containers |
| `/api/deployment/verify-request` | POST | Verify a real API-to-database write path |
| `/api/resources` | GET / POST | List/create resource records |
| `/api/resources/demo-seed` | POST | Seed demonstration resources |
| `/api/reservations` | GET / POST | Inspect/create resource reservations |
| `/api/reservations/{reservation_id}/release` | POST | Release a reservation |
| `/api/experiments` | GET / POST | List/create persisted educational experiment runs |
| `/api/experiments/{run_id}` | GET | Inspect one experiment run |
| `/api/experiments/{run_id}/step` | POST | Advance a run by one step |
| `/api/experiments/{run_id}/pause` / `resume` | POST | Pause/resume a run |
| `/api/experiments/{run_id}/reset` | POST | Reset a run |
| `/api/experiments/{run_id}/inject-failure` | POST | Inject a supported lab failure scenario |
| `/api/beacons/simulate` | POST | Run a beacon protocol teaching simulation |
| `/api/forensics/{incident_id}` | GET | Retrieve the available incident forensic view |
| `/api/concepts` | GET | List lab catalog and model modes |
| `/api/labs/{lab_id}` | GET | Retrieve an educational model trace or runbook |
| `/ws/events`, `/ws/telemetry` | WebSocket | Demo event pong / telemetry stream endpoint |
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

## 9. Remaining production-oriented hardening

The repository already contains an outbox dispatcher, event-ID deduplication, backend tests, CI jobs, manifest validation, a Compose smoke test, and an optional API HPA manifest. Those capabilities should not be described as missing; their operational guarantees still need targeted tests.

Remaining work before production-like use:

1. Add publisher-confirm semantics and prove behavior during ambiguous broker failures.
2. Add bounded retries and dead-letter routing for poison messages; test retry exhaustion.
3. Introduce versioned event schemas and explicit schema-compatibility tests.
4. Add database migrations and consider structured JSON/JSONB payload storage.
5. Add authentication, authorization and rate limiting for incident/resource actions.
6. Add structured logs, metrics and trace/correlation IDs across API, outbox, broker and worker.
7. Apply NetworkPolicies, least-privilege ServiceAccounts, secure secret management and TLS where required.
8. Consider Pod disruption budgets and configure HPA only from measured/available metrics.
9. Extend CI with targeted integration, load and cluster-deployment tests where infrastructure is available.
10. Keep simulation evidence separate from actual runtime inventory and measured performance.
