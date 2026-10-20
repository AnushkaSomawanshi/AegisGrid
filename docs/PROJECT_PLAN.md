# AegisGrid Project Plan

## Project objective
Design, develop and demonstrate a small distributed application using containerization and orchestration. The application must show scalability, inter-service communication, persistent state and inspectable distributed-systems concepts in a professional dashboard.

## Stakeholders and usage
- Operator persona: creates/updates a sample incident and follows its event trace.
- Student/demo presenter: demonstrates protocol models and explains assumptions/limits.
- Developer/operator: starts the service stack, inspects logs/health, scales stateless workloads and records fault-recovery evidence.

The platform is educational only; it must not be represented as a live emergency dispatch service.

## Functional requirements
- FR-01: Dashboard offers overview metrics, incident response, event ledger, service topology, labs, scale plan and runtime runbooks.
- FR-02: User can create incidents with title, category, severity, location and description.
- FR-03: User can transition incident status among open, assigned, responding and resolved.
- FR-04: API persists incidents and event records when configured with PostgreSQL.
- FR-05: API attempts publication of event messages to durable RabbitMQ queue and exposes delivery outcome.
- FR-06: Independent consumer processes messages and records a processing acknowledgement.
- FR-07: API exposes health, overview, incident, event and concept endpoints.
- FR-08: WebSocket endpoint demonstrates bidirectional request/reply frames.
- FR-09: Concept laboratory explains ten required topics and labels simulations.
- FR-10: Docker Compose builds and starts the application components.
- FR-11: Kubernetes manifests describe application workloads, services, probes and persistent database storage.
- FR-12: Documentation covers architecture, algorithms, deployment, scaling, testing and demo sequence.

## Non-functional requirements
- NFR-01: Component boundaries and container configurations remain easy to inspect.
- NFR-02: API request payloads are validated and error cases return meaningful status codes.
- NFR-03: UI is responsive and demonstrates backend-unavailable state honestly.
- NFR-04: No runtime command or cluster-admin credential is exposed to browser code.
- NFR-05: Samples are labelled as synthetic, and performance results are not invented.
- NFR-06: Service health reports distinguish liveness, readiness, broker delivery and worker processing.
- NFR-07: Tests and build checks can run in CI.

## Architecture choice rationale
- React + TypeScript supports a strongly typed, stateful dashboard and a component-driven interface.
- FastAPI makes API contracts and validation accessible through OpenAPI docs.
- PostgreSQL provides persistent incident and event state.
- RabbitMQ illustrates durable message-oriented integration and producer/consumer separation.
- A separate worker process demonstrates independent scaling and acknowledgement behavior.
- Compose reduces local setup friction; Kubernetes manifests demonstrate declarative deployment and self-healing.
- Algorithm labs are functions in one API service initially rather than artificial microservices for every protocol. This preserves simple testability and keeps each protocol simulation separate from infrastructure management.

## Milestones
1. Repository foundation and project plan.
2. API models, incident routes and event ledger.
3. RabbitMQ publisher and independent worker.
4. Dashboard navigation, incident actions and ledger inspection.
5. Concept lab outputs and teaching notes.
6. Container builds and Compose orchestration.
7. Kubernetes namespace/deployments/services/PVC/probes.
8. Tests, CI, guides and live demo walkthrough.
9. Run experiments in an actual environment and attach captured results.

## Acceptance criteria
- A clean checkout can build through Compose without manually creating source files.
- API readiness returns success only when its DB dependency can be queried.
- Incident creation persists an incident and event with the configured DB.
- Broker publication outcome is not conflated with worker processing.
- At least one event can be followed from API event to worker processing record when broker/worker are available.
- Concept labs return inspectable traces and include an explicit simulation limitation.
- Dashboard can navigate all major views and clearly indicate demo/offline conditions.
- Kubernetes manifest applies in a configured local cluster after image availability and secrets are set.
- Scaling/recovery claims are supported by measurements captured from that runtime.
- Documentation includes explicit next steps for production hardening.

## Known risks
- Database transaction and broker publication are not atomic in this baseline.
- Duplicate RabbitMQ delivery may produce duplicate worker records.
- The sample WebSocket is an echo/pong demo, not a full event push service.
- Local Kubernetes image loading, storage and networking vary by cluster.
- Static example chart data can be mistaken for measured telemetry if labels are ignored.
- Credentials in the base Kubernetes Secret are placeholders and must be replaced.
- The project lacks auth, transactional outbox, dead-letter queue and formal migration handling.

## Evaluation evidence checklist
- [ ] Compose build and service list
- [ ] API health and OpenAPI screenshots
- [ ] Incident create/status transition plus database-backed event
- [ ] API broker result and worker acknowledgement/log
- [ ] One screenshot per concept lab with a short invariant explanation
- [ ] Kubernetes deployment/Pod readiness output
- [ ] Before/after replica scaling evidence
- [ ] Controlled failure recovery time and raw observations
- [ ] Repeated throughput/latency measurements and environment description
