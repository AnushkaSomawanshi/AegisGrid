# Concept Demonstrations

This workbook describes what each AegisGrid demonstration does and what its evidence means. Distributed-protocol labs are deterministic simulations unless the page explicitly identifies a runtime-backed operation.

## 1. Physical clock synchronization — detailed Berkeley-style demonstration

### What the page demonstrates

The Physical Clock Synchronization page is an interactive experiment workspace backed by the persisted `POST /api/experiments` and `POST /api/experiments/{id}/step` APIs. The frontend displays configuration, clock state, the backend-generated event ledger, calculation audit, execution progress and JSON evidence export. The clock model is synthetic; it does not read or modify the host operating system clock.

### Configure a round

- Configure 2–20 node offsets in milliseconds. `C0` is the coordinator and `N1...` are followers.
- Configure per-node drift in milliseconds per simulated second.
- Advance a synthetic elapsed duration to apply drift to the input offset.
- Set a message-delay value for trace metadata.
- Mark nodes unreachable to demonstrate timeout and participant exclusion.
- Give the run a scenario label and create a persisted experiment.

For a node (i), the simulated offset at the poll point is:

`offset_i = initial_offset_i + drift_rate_i × simulated_elapsed_seconds`

Message delay is deliberately labelled as timing metadata. This version does not infer offset from network round-trip timestamps or emulate packet delivery, asymmetry or jitter.

### Execution phases

The backend creates a chronological trace containing these event families:

1. `clock.poll.sent` — coordinator sends a poll to a reachable follower.
2. `clock.reading.received` — coordinator receives that follower's configured synthetic offset.
3. `clock.poll.timeout` — an unreachable node is excluded from the sample set.
4. `clock.coordinator.sampled` — the coordinator contributes its own reading when available.
5. `clock.average.computed` — the backend records the participant list, excluded list, readings and computed mean.
6. `clock.correction.sent` — the coordinator assigns a relative correction to a participating node.
7. `clock.correction.applied` — the model records the node's corrected offset.
8. `clock.round.completed` — final participant set and final spread are recorded.

Use **Next event** to advance one persisted event, **Run to completion** to execute the remaining trace, **Reset trace** to reset the persisted cursor, and **Export JSON** to download the run configuration, result and executed trace.

### Coordinator calculation and invariants

Only nodes with a reported reading participate in the average:

`mean_offset = sum(reported_offset_i) / participant_count`

Each participating node receives:

`correction_i = mean_offset - reported_offset_i`

After ideal correction, every participating node's model offset equals the mean. The mean does not have to be zero because Berkeley-style averaging targets the group's estimated average, not necessarily UTC. Unreachable nodes remain unchanged and are not included in the final participating-node spread. A round with no reachable readings is rejected instead of reporting a false success.

The result includes the per-node initial offset, drifted offset, reported offset, correction, corrected offset and status, plus participant/excluded-node lists, initial spread and final spread. The UI's calculation table is rendered from this backend result, not from a hard-coded worked example.

### Worked baseline

With offsets `[120, 40, -60, 200, 300]` ms and zero drift, the mean is `120 ms`. Corrections are `[0, +80, +180, -80, -180]` ms for `[C0, N1, N2, N3, N4]`. The initial spread is `360 ms`; the ideal simulated final spread is `0 ms`. This baseline is also covered by the backend tests.

### Limitations displayed intentionally

- These are synthetic offsets, not physical clock readings.
- Drift is a configurable arithmetic offset applied at a chosen synthetic elapsed time, not a continuously ticking oscillator.
- Delay is recorded in the trace but is not used to estimate network-adjusted clock offsets.
- The simulation assumes ideal correction application; it does not model correction slew, oscillator uncertainty, asymmetric latency, outlier rejection or coordinator crash recovery.
- The demonstration is for education and testing, not time-service or production clock discipline.

## 2. Lamport logical clocks

### Rules
- Before each local event, increment the process counter.
- A sent message carries the sender's current logical clock.
- On receive, set the counter to max(local_counter, received_timestamp) + 1.
- If event A happened-before event B, then L(A) < L(B).

The converse does not necessarily hold: a lower scalar timestamp does not prove that one event caused another.

### Demonstration
The model shows a local incident event, a message send, a receive and a unit assignment on different processes. It also shows an independent inventory refresh event to prompt discussion about concurrent actions.

### Discussion
Lamport clocks make a consistent ordering possible but do not fully encode causality. If the ordering of all independent events matters, use a tie-breaker or a richer causal representation.

## 3. Global state snapshot — Chandy–Lamport-style model

### Objective
Capture a consistent cut of a distributed computation by recording each process's local state and each communication channel's in-flight messages.

### Simplified marker flow
1. The initiator records its local state and sends marker messages.
2. A process records its local state when it receives its first marker.
3. It records messages on a channel until the marker for that channel arrives.
4. The snapshot combines process state with channel state.

### Dashboard observation
The trace contains three process-local states and a message in transit between node-2 and node-3. Ask why simply collecting three process states without channel messages can create an inconsistent picture.

This dashboard response is a teaching example, not a real snapshot from the running API, database, broker or Kubernetes workloads.

## 4. Vector clocks

### Comparison
Given vectors A and B, A happened-before B when every component of A is less than or equal to the corresponding component of B, and at least one component is strictly lower. If neither vector dominates the other, the events are concurrent in the vector-clock model.

### Demonstration
The sample uses three components [P1, P2, P3]. It highlights a pair where one vector dominates another and pairs where vectors are incomparable.

### Discussion
Vector clocks can express concurrency that scalar Lamport clocks cannot distinguish. Their metadata grows with the number of participants and dynamic membership requires a carefully designed representation.

## 5. Leader election — Bully algorithm model

### Concept
In a simplified Bully algorithm, a process that suspects the coordinator starts an election. Processes with higher IDs can respond and start their own elections. The highest-ID live process eventually announces itself as coordinator, assuming membership and failure detection behave as expected.

### Demonstration
The model marks node 4 unavailable and shows node 5 becoming leader because it has the highest live identifier.

### Discussion
This is not a production leader-election protocol. A live service can appear failed during a network partition, and naive elections can cause split-brain behavior if there is no quorum/fencing mechanism. The lab doesn't kill containers or change a real cluster leader.

## 6. Distributed mutual exclusion — Ricart–Agrawala model

### Concept
A process multicasts a timestamped REQUEST. Peers compare request priority using logical timestamp and process ID as a tie-breaker. A process can enter its critical section once it has received all required REPLY messages; peers that have a higher-priority local request defer their responses.

### Demonstration
The dashboard orders three requests. Two have equal timestamps, so process ID establishes a deterministic order.

### Discussion
This model is for understanding the protocol and its assumptions. It is not a distributed lock protecting AegisGrid database or infrastructure state. Message loss and crashed participants can prevent progress without additional recovery design.

## 7. Heartbeat failure detection

### Concept
A monitor receives periodic heartbeats and increments a missed count when one is not received. At the configured threshold it marks the process as suspected.

### Key distinction
**Suspected is not the same as proven failed.** A slow process, long garbage-collection pause, congested network or dropped packet may cause false suspicion. Lower thresholds detect faster but risk false positives; higher thresholds delay detection.

### Demonstration
The synthetic trace shows node-3 missing three consecutive heartbeats. The chart is an explanatory timeline, not monitoring data from real containers.

## 8. Message-oriented communication — RabbitMQ

### End-to-end walkthrough
1. Create an incident or request a demo event.
2. Confirm the incident/event record through the API.
3. Inspect the API response's broker result (published, failed, or local-only).
4. Inspect the RabbitMQ queue/management UI and publisher/consumer logs.
5. Inspect worker.processed records in the event ledger after the independent worker commits processing.
6. Compare each milestone. A database commit is not proof of queue publication; a publish attempt is not proof of worker processing.

### Current design boundaries
The queue is durable and messages use persistent delivery mode. The worker acknowledges after the database record commits and requeues on an exception. At-least-once delivery means duplicates are possible, so production consumers must be idempotent. For stronger atomicity between database and broker, use a transactional outbox and publisher-confirm workflow.

## 9. Stream-oriented communication — WebSocket

The endpoint /ws/events accepts a connection, sends a connection notice, receives text frames and responds with timestamped pong frames. Connect using a WebSocket client after starting the stack.

The UI also displays an illustrative lifecycle: HTTP Upgrade, switching-protocols response, bidirectional frames, Ping/Pong, close. The sample frame rows are explanatory, not a captured live socket stream. This endpoint does not currently broadcast event-ledger changes to every browser client.

Discuss reconnect/backoff, heartbeats, flow control, backpressure, authorization and what should happen when a client is slower than the producer.

## 10. Docker and Kubernetes

### Docker Compose
Compose defines separate processes for frontend, API, event worker, PostgreSQL and RabbitMQ. Health-based depends_on improves startup ordering, but applications still need reconnect handling because dependencies can fail after startup.

Useful evidence:
- docker compose ps
- docker compose logs --tail=100 api worker postgres rabbitmq
- docker compose up -d --scale worker=3
- Event throughput and processing records before and after scaling.

### Kubernetes
Kubernetes manifests define Deployments and Services for frontend, API, PostgreSQL, RabbitMQ and the independent worker. The API uses readiness/liveness probes; PostgreSQL has a PVC for local persistent storage.

Useful evidence:
- kubectl get deployments,pods,services -n aegisgrid
- kubectl rollout status deployment/aegisgrid-api -n aegisgrid
- kubectl scale deployment/aegisgrid-worker --replicas=3 -n aegisgrid
- kubectl get pods -n aegisgrid -w
- After deleting one development Pod, observe controller replacement and confirm readiness.

These commands are runbook instructions, not results produced by the dashboard. Image loading, local cluster networking, storage classes and secret values may need adjustment for the selected cluster.

## 11. Scalability and controlled failure experiment

### Baseline
Record deployment/environment, image tag, CPU/memory, current worker count, test request count, concurrency and duration.

### Load and scaling
Run the same fixed workload at one, two and three worker replicas. Record successful messages per second, p50 and p95 latency, HTTP errors/timeouts, RabbitMQ ready/unacknowledged messages, worker processing delay, CPU and memory.

### Recovery
Delete/restart one stateless Pod/container in a development-only environment. Measure time until a replacement is ready and completes a health or message-processing operation. Repeat to understand variability.

### Interpretation
Do not assume linear scaling. The database can become the bottleneck because each consumed message creates a new ledger row. The broker can also constrain throughput. A useful result reports the workload and environment, raw measurements, repeat count, variability and bottleneck hypotheses.

## 12. Demonstration rubric

For each lab, present:
1. The problem and assumptions.
2. The protocol/model rule.
3. Input trace and derived output.
4. The invariant or expected behavior.
5. A failure case or counterexample.
6. The limitation and distinction between simulation and actual runtime evidence.
