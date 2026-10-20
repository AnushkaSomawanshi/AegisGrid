# AegisGrid Architecture

## Context
AegisGrid combines an emergency-response application with an educational distributed-systems laboratory. The UI distinguishes durable application records, algorithm simulations and verified infrastructure telemetry.

## Initial service boundaries
- **Frontend**: React/TypeScript command centre, algorithm labs and operations views.
- **API**: FastAPI application API, educational algorithm endpoints, event ledger and WebSocket broadcast endpoint.
- **PostgreSQL**: persisted incidents, experiment records and event ledger.
- **RabbitMQ**: durable topic exchange used for application event publication.

Algorithm labs currently live as modules inside the API process. They are not all independently deployed services. This keeps the first iteration manageable; extract a module into a service when that boundary provides a real benefit.

## Event flow
1. Client submits an incident to the API.
2. API validates and persists it.
3. API attempts publication through RabbitMQ.
4. API records event metadata and broadcasts to connected WebSocket clients.
5. Dashboard refreshes persisted state.

The initial database insert and broker publication do not use a transactional outbox. Add an outbox and independently running consumer before claiming exactly-once effects or robust event publication guarantees.

## Protocol scope
Clock synchronization, Lamport clocks and vector clocks are educational models. Global snapshot now models marker queues and channel recording; election traces Bully-style ELECTION/OK/COORDINATOR messages; mutual exclusion models Ricart–Agrawala-style request/reply/deferred-reply transitions; beacon timeout state advances through deterministic ticks. These remain educational simulations in one API process, not a multi-process distributed protocol deployment.

## Security boundary
Never expose Docker socket access or Kubernetes credentials to the browser. Infrastructure actions need an authorised backend with least-privilege access and explicit operator confirmation.
