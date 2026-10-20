# API Reference

Base URL locally: `http://localhost:8000`. Interactive OpenAPI docs: `/docs`.

## Health

### GET /health/live
Returns process liveness.
```json
{"status":"alive","service":"api"}
```

### GET /health/ready
Queries the database as a readiness dependency. Returns HTTP 503 if the DB cannot be queried.
```json
{"status":"ready","service":"api","database":"reachable"}
```

## Incidents

### GET /api/incidents?limit=50
Returns newest incident records. Limit range: 1–200.

### POST /api/incidents
Request:
```json
{
  "title":"Medical assistance required",
  "category":"Medical",
  "severity":"critical",
  "location":"Sector 07",
  "description":"Training demonstration only"
}
```
Severity is one of low, medium, high, critical. Success returns HTTP 201 with the incident and event result. The broker outcome is a distinct field, so a persistent record does not imply a successful publish.

### PATCH /api/incidents/{id}
Request:
```json
{"status":"assigned"}
```
Status is one of open, assigned, responding, resolved. Returns 404 for an unknown ID.

## Events

### GET /api/events?limit=50
Returns event rows newest first with payload decoded as JSON.

### POST /api/events/demo
Creates a demo event and attempts publication through RabbitMQ. Response includes:
- `id`: event ledger row ID
- `event_type`, `source`, `payload`, `created_at`
- `broker`: published, failed, or local-only
- `broker_detail`: optional diagnosis text on non-success

A broker publication result is not the same thing as worker processing. Wait for/inspect a `worker.processed` record and consumer logs for evidence of processing.

## Distributed concept modules

### GET /api/concepts
Returns modules, protocol names and mode labels.

### GET /api/labs/{lab_id}
Lab IDs: physical-clock, lamport, snapshot, vector, election, mutex, failure, messaging, stream, infrastructure. Algorithm endpoints return deterministic synthetic model output. Messaging and infrastructure endpoints provide runtime checks/runbook information, not fabricated cluster telemetry.

## WebSocket

Connect to `ws://localhost:8000/ws/events`. The server first sends a connection notice. Send a text frame such as `ping`; the server responds with a timestamped pong and echoed value. Disconnect closes the connection. This is a transport example, not a general broadcast/event-tail implementation.

## Error conventions
- Pydantic validation errors use HTTP 422.
- Unknown lab IDs and unknown incident IDs return HTTP 404.
- Out-of-range list limits return HTTP 400.
- Readiness returns HTTP 503 when the database cannot be queried.


## Resource inventory and reservations

### GET /api/resources
Returns persisted resources, including type, availability, capacity, location and optional coordinates.

### POST /api/resources
Creates a resource. Example:
```json
{"code":"MED-12","name":"Mobile medical team 12","kind":"medical-unit","location":"Central district","capacity":1,"latitude":18.52,"longitude":73.85}
```
Resource codes are unique. Duplicate codes return HTTP 409.

### POST /api/resources/demo-seed
Idempotently creates four synthetic field-unit/facility records if their codes do not exist. Coordinates are sample Pune-area values, not live GPS.

### GET /api/reservations
Returns reservation history.

### POST /api/reservations
Example:
```json
{"resource_id":1,"incident_id":null,"requested_by":"command-desk"}
```
Reserves an available resource. Missing resources return 404; an unavailable resource returns 409. A conditional database update protects the available-to-reserved transition against concurrent requests on PostgreSQL.

### POST /api/reservations/{id}/release
Releases an active reservation and returns the resource to available. Releasing an unknown reservation returns 404; releasing an already released reservation returns 409.

## Transactional outbox and worker idempotency

### GET /api/outbox?limit=50
Returns outbox rows with stable event ID, status, attempt count, error detail and publication timestamp.

### POST /api/outbox/{id}/retry
Retries a pending message explicitly. Published rows are not published again by this endpoint. A publication confirmation can still be ambiguous if the network fails after the broker accepts the message; the consumer deduplicates by stable event ID.

The event ledger row and outbox envelope are committed in one SQL transaction. An independent dispatcher polls pending rows and retries them. Failed deliveries remain pending; exponential backoff and a configurable poison-message dead-letter threshold remain future work.

## Experiment workbench

### POST /api/experiments
Creates a saved trace and result:
```json
{"lab_id":"physical-clock","scenario":"offset-baseline","parameters":{"offsets":[-120,30,80,-10]}}
```
Allowed lab IDs: `physical-clock`, `lamport`, `snapshot`, `vector`, `election`, `mutex`, `beacon`, `messaging`, `stream`, `scaling`.

### GET /api/experiments?limit=50
Returns recent saved runs. Limit range: 1–200.

### GET /api/experiments/{id}
Loads a saved run, parameters, trace, result and cursor.

### POST /api/experiments/{id}/step
Executes the next trace entry by advancing the persisted cursor. A paused run returns HTTP 409.

### POST /api/experiments/{id}/pause and POST /api/experiments/{id}/resume
Pause/resume the saved educational trace cursor. These do not pause a real service.

### POST /api/experiments/{id}/reset
Resets the cursor to zero while retaining the original trace and parameters.

### POST /api/experiments/{id}/inject-failure
Request:
```json
{"fault_type":"process-unavailable","target":"P2"}
```
Allowed fault types are `process-unavailable`, `message-delay`, and `heartbeat-loss`. The event is inserted into the model trace and explicitly labelled simulation; it does not stop a process, container, or Pod.

## Beacon simulation

### POST /api/beacons/simulate
Example:
```json
{"node_id":"node-2","interval_ms":500,"timeout_ms":1000,"missed_beats":3,"recover":true}
```
Returns a synthetic heartbeat/miss/recovery trace and final state. This endpoint does not monitor actual network nodes.

## Incident forensics

### GET /api/forensics/{incident_id}
Returns the incident plus chronological event records whose persisted payload matches the incident ID. The resulting graph is a chronological reconstruction, **not a proof of distributed causality**, because full correlation/causation propagation across all services is not yet implemented.

## Runtime measurement utility

Run `python scripts/http_load_probe.py --url http://localhost:8000/health/live --requests 300 --concurrency 20 --output artifacts/api-baseline.json` to record real HTTP response samples. The script does not collect server CPU/memory, broker depth, or worker throughput; those must be measured separately.


## WebSocket telemetry stream

### WS /ws/telemetry
Opens a real WebSocket transport and sends a connected frame followed by monotonically sequenced synthetic telemetry frames approximately once per second. Frames include timestamp, sequence, demo node label, load sample and queue-depth sample. Values are deterministic demonstration data and must not be represented as live infrastructure telemetry.

The dashboard's **Telemetry stream** page connects to this endpoint and shows the received frames and observed sequence gaps. The client can disconnect/reconnect; sequence-gap counts are session-local and do not persist.
