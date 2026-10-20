# Concept Demonstration Plan

Every lab should provide: (1) theory, assumptions and limitations, (2) topology/state view, (3) execution controls, (4) event trace, (5) calculated result or invariant, and (6) saved evidence and tests.

## 1. Physical clock synchronization / Berkeley-style coordinator
Display process offsets, participant availability, reference time, coordinator calculation, proposed corrections and before/after comparison. Worked offsets +200, -150, +500, -300, +100 ms average to +70 ms; excluding the fourth participant yields +162.5 ms. Label it a simulation; do not change the host clock.

## 2. Logical clocks / Lamport algorithm
Show process lanes and counters. Local event increments; sending increments and attaches timestamp; receiving applies max(local, message)+1. Persist each transition and expose message ID. Test all rules. Timestamp comparison alone does not prove causality.

## 3. Global state
Represent local process and channel state. A complete Chandy-Lamport implementation requires marker propagation and channel recording under algorithm assumptions. Do not call a simultaneous collection of objects a valid snapshot. Initial API is explicitly incomplete.

## 4. Vector clocks
Maintain fixed process set and vector component per process. Local event increments local component; send attaches vector; receive merges component-wise maximum then increments receiver component. Compare causal order/equality/concurrency.

## 5. Election algorithms
Identify a specific algorithm (e.g. Bully only if compatible with course requirement). Visualise IDs/priorities, messages, replies, coordinator announcement and failure/recovery. Initial endpoint is a simplified model, not yet full Bully protocol.

## 6. Mutual exclusion
Choose a course-compatible algorithm (e.g. Ricart-Agrawala). Visualise requests, timestamps, replies, deferred replies, entry/release and ownership timeline. Assert at most one owner. Initial API is a central teaching-model owner, not peer-to-peer Ricart-Agrawala.

## 7. Beacon protocol / failure detection
Visualise interval, last beacon, missed signals, timeout and suspected/recovered transitions. Confirm exact named protocol against course notes. Current endpoint has manual pause/resume, not a timer-driven detector.

## 8. Message-oriented communication
Use real RabbitMQ. Expose event ID, correlation ID, routing key, queue/consumer state, acknowledgements, retries and dead-letter flow. Initial API publishes to a durable topic exchange; consumer queues and inspectable delivery lifecycle remain to be completed.

## 9. Stream-oriented communication
Use a real WebSocket for continuous generated telemetry. Show connection state, sequence IDs and sample payloads. Payload values are simulated; the WebSocket transport is real. Recovery semantics, measured latency and missing-sample analysis remain to be added.

## 10. Event forensics / happened-before
Show process lanes, local-order edges, message edges and event inspector. The Forensics screen builds a graph from persisted ledger events and exposes an event-pair causal-path endpoint. It uses explicit message IDs and process identity when available. It does not infer causality from Lamport integers alone or treat missing paths as proof of concurrency if logs may be incomplete. Current local process ordering is a database insertion-order proxy; robust concurrent-write ordering needs per-process sequence numbers in the event schema.

## 11. Docker
Run full local stack using Compose. Inspect real containers, health and logs; demonstrate end-to-end incident and event flow. Do not expose Docker socket to frontend.

## 12. Kubernetes and self-healing
Deploy app workloads and dependencies, inspect Deployments/Pods/Services, scale a stateless service and delete one managed Pod. Record replacement and separately measure request continuity and persistence. Manifests require local image/config validation before claiming they work.

## 13. Scalability and fault tolerance
Use reproducible load workload and real request metrics; compare one replica with multiple replicas. Record throughput, latency, errors, resource use, queue depth and recovery time. Never invent measurements.
