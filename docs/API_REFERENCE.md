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
