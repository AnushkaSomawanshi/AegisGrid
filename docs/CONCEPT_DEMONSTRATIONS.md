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

## 3. Global state snapshot — Chandy–Lamport-style execution studio

### Detailed UI

The dedicated Global State Capture Studio is a dark, responsive operations dashboard rather than a theory-heavy article. It presents capture metrics, logical process cards, directed-channel recording status, a selectable event ledger, a payload inspector, process-state and channel-state ledgers, and assembled JSON evidence.

### Default execution schedule

1. P1 (Incident & Dispatch) starts the snapshot, records its local state, then sends markers.
2. P3 (Inventory & Monitoring) receives P1's marker first, records local state and opens recording on incoming channels other than P1 → P3.
3. M1, `dispatch.updated #104`, is delivered from P2 to P3 while P2 → P3 is recording. The engine captures it because delivery occurs after recording starts and before P2's marker arrives.
4. P2 records its local state after receiving the first marker and propagates markers.
5. A marker on each recorded incoming channel closes that channel's recording window.
6. Snapshot completion checks that every process state is recorded and every directed channel recording is closed.

### Controls and evidence

- Presets: message in transit, empty channel, multiple in-flight messages, and delayed-marker illustration.
- Start creates a persisted run; Next event executes one event; Run to completion advances the cursor; Pause/Resume and Reset use the existing experiment API.
- Visible process/channel state is derived from executed events rather than presented as if future events already happened.
- Export JSON saves run configuration, executed trace and evidence.
- Results include process states, directed channel states, message IDs/payloads, recording start/close steps, captured messages and consistency checks.

### Invariants and limitations

- The initiator records local state before sending markers.
- A non-initiator records local state on its first marker.
- Captured messages fall after recording begins and before the channel's closing marker.
- The final snapshot is complete only when every modeled process state is recorded and every channel recording is closed.
- This is a deterministic teaching simulation, not a live snapshot of the API, database, RabbitMQ or Kubernetes.
- Channel capture is derived from modeled event order; callers do not provide a pre-labelled final in-transit message list.

## 4. Vector clocks — execution studio

### Page design

The dedicated Vector Clock Execution Studio is a responsive, dark operations dashboard rather than a theory page. It contains execution metrics, three process cards with vector components, directed message cards with send timestamps, an event ledger, a calculation inspector, an event-comparison workbench, a causal-edge ledger and a final JSON evidence panel.

### Process identities and component order

The teaching scenario uses a fixed component order `[P1, P2, P3]`:
- P1 — Incident & Dispatch
- P2 — Resource Coordination
- P3 — Inventory & Monitoring

All process vectors begin at `[0, 0, 0]`. A vector shown on the page is reconstructed from the executed trace up to the persisted execution cursor. A future event can be inspected without advancing its process clock.

### Default event schedule

| Event | Process | Operation | Resulting vector |
|---|---|---|---|
| E1 | P1 | Create incident | `[1, 0, 0]` |
| E2 | P1 | Send M1 to P2 | `[2, 0, 0]` |
| E3 | P2 | Receive M1 | `[2, 1, 0]` |
| E4 | P2 | Allocate response unit | `[2, 2, 0]` |
| E5 | P3 | Independent inventory check | `[0, 0, 1]` |
| E6 | P2 | Send M2 to P3 | `[2, 3, 0]` |
| E7 | P3 | Receive M2 | `[2, 3, 2]` |
| E8 | P1 | Independent dispatch update | `[3, 0, 0]` |

These vectors are calculated by the backend from the ordered event schedule. They are not hard-coded frontend display values.

### Execution rules

- **Local event:** increment the component for the process executing the event.
- **Send:** increment the sender's component and attach a copy of the resulting vector to the message.
- **Receive:** merge the local and message vectors component-wise using the maximum, then increment the receiver's component.
- **Causality:** add process-order edges and message send-to-receive edges. The list position alone is not treated as proof of causality.
- **Comparison:** A strictly dominates B when all components of A are less than or equal to B and at least one is lower. The reverse relation is tested symmetrically. Incomparable vectors are concurrent; equal vectors are reported separately.

### Presets and controls

- Basic message exchange: local events, send timestamps and receive merge.
- Independent processes: three processes without message exchange.
- Multi-hop causality: propagate a causal history from P1 through P2 to P3.
- Concurrent updates: compare causally related events with an independent process event.
- Create a persisted run, advance one event, run the trace, pause/resume, reset the cursor and export JSON.
- Select any two executed events in the comparison workbench to view their vectors and relation.
- Inspect the event calculation, message timestamp, component-wise merge, resulting vector and causal predecessors.

### Evidence and tests

The result includes final process vectors, message IDs, sender/receiver, send-event references, attached message vectors, causal edges, pairwise event comparisons and concurrent pairs. Backend tests cover the default vector trace, receive merge, independent concurrency, multi-hop causal propagation, unknown messages and wrong-recipient delivery.

### Limitations

This is a deterministic teaching simulation. Process names are logical identities and do not claim to be deployed AegisGrid service processes. Vector timestamps are not wall-clock timestamps, and the page does not instrument live network messages or runtime state. The first version uses a fixed three-process component order; dynamic membership and vector compression are outside its scope.

## 5. Leader election — detailed Bully Algorithm Execution Studio

The dedicated leader-election page is an operations dashboard, not a theory article. It shows five process cards (P1 API Gateway, P2 Incident Service, P3 Resource Coordinator, P4 Inventory Service, P5 Cluster Coordinator), node availability, current per-node coordinator view, election state, a message ledger, step-by-step event timeline, message inspector, progress metrics, consistency checks and JSON export.

### Default demonstration: P5 fails and P4 wins

1. P5 becomes unavailable and P2 detects a simulated coordinator heartbeat timeout.
2. P2 starts an election, sends ELECTION to higher-ID nodes P3, P4 and P5.
3. Active P3 and P4 respond OK; failed P5 does not respond and produces a timeout event.
4. P3 and P4 initiate their own higher-priority elections. P4 receives no response from P5.
5. P4 becomes coordinator and sends COORDINATOR messages to P1, P2 and P3.
6. Recipients update their own coordinator views on receiving the announcement. The final state has exactly one coordinator and all active nodes agree on P4.

Every ELECTION, OK, COORDINATOR, simulated timeout, node transition and leader-view change is recorded in the persisted trace. A higher node that responds starts its own election; a lower node receiving OK waits rather than claiming leadership. Failed processes never send messages.

### Presets

- Coordinator failure: P5 failed, P2 initiates, P4 wins.
- Lowest initiator: P5 failed, P1 initiates, P4 wins.
- Multiple failures: P4 and P5 failed, P2 initiates, P3 wins.
- Coordinator recovery: P5 rejoins while P4 is coordinator; P5 runs an election and announces itself.

### Controls and evidence

Use Start election, Next event, Run all, Pause, Resume, Reset and Export evidence. The page reconstructs current node states from executed events only; selecting a pending event opens its inspector but does not apply its state changes. The result includes message sender/receiver/type/step, per-event node snapshots, failed and active membership, initiator, elected coordinator, and checks for highest-active winner, no sends from failed nodes, higher-only ELECTION requests, agreement and exactly one coordinator.

### Scope and limitations

This is a deterministic five-node educational simulation, not an instrumented live election. Timeouts are logical scheduled events, not elapsed wall-clock timers. It does not implement unreliable transport, network partitions, quorum, fencing or production-grade split-brain prevention. Real distributed deployments must not infer safety from this simplified model.

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


## 13. Lamport logical clocks — execution studio

The Lamport clock page is an event-by-event execution studio rather than a theory-only article. Its incident-dispatch scenario models three logical processes: P1 (Incident & Dispatch), P2 (Resource Coordination) and P3 (Inventory & Monitoring). These are simulation identities, not a claim that these are separate deployed services.

### Default trace

| Event | Process | Operation | Clock update | Meaning |
|---|---|---|---|---|
| E1 | P1 | Create incident | 0 → 1 | Local event increments P1 |
| E2 | P1 | Send M1 to P2 | 1 → 2 | The sent message carries timestamp 2 |
| E3 | P2 | Receive M1 | max(0, 2) + 1 = 3 | The receive is causally after E2 |
| E4 | P2 | Assign response unit | 3 → 4 | Local event follows the receive |
| E5 | P3 | Independent inventory refresh | 0 → 1 | Independent of E1–E4 in this scenario |

The ledger records event ID, process, event type, previous clock, message timestamp when applicable, resulting clock, calculation, and causal predecessors. The causality view uses process-order edges and message send-to-receive edges. The visible row order is only the trace presentation order; it must not be interpreted as proof that E5 happened before or after another process's event.

### Interactive controls and scenarios

- Create a persisted run, step one event at a time, run the remaining trace, pause/resume, reset the cursor and export the run evidence as JSON.
- Presets cover incident dispatch, a receive with a higher incoming timestamp, independent processes and multiple messages.
- The scenario editor accepts a bounded JSON event list. Local and send events increment the process clock by one. A receive derives its message timestamp from an earlier send with the same message ID and computes `max(local_clock, message_clock) + 1`; the timestamp is not trusted from a manually entered receive field.
- The backend rejects unknown receive message IDs, duplicate send IDs, duplicate event IDs and receiver/sender mismatches when routing metadata is provided.
- Run history and step state use the existing experiment API and persistence lifecycle.

### Interpretation and limits

Lamport timestamps can establish a consistent direction for causally related events but cannot prove that two unrelated events are concurrent in real time, and a scalar timestamp does not fully identify concurrency. This is a deterministic teaching simulation: it does not instrument the actual API, database, worker or broker, and it does not claim wall-clock timestamps or live distributed-process behavior.


## Message-Oriented and Stream-Oriented Communication — Execution Studio

The Message and Stream concepts open a shared Communication Execution Studio built around the AegisGrid incident-response workflow: P1 creates incident INC-104, P2 dispatches a response unit, and P3 publishes inventory/telemetry updates. This page is a deterministic simulation and does not claim that its generated events were delivered through live RabbitMQ or a production socket.

### Message-oriented mode

The trace models a discrete application envelope with a stable message ID, sender, receiver, queue acceptance, delivery attempt, acknowledgement, and business processing. The delivery-retry scenario demonstrates a transient delivery failure and retry with the same ID; consumers must be idempotent where at-least-once delivery is possible. Broker acceptance, consumer receipt, acknowledgement and business completion are distinct states.

### Stream-oriented mode

The trace models ordered bytes, sequence numbers, byte offsets, buffer occupancy, consumer lag, and application-frame decoding. Transport chunk boundaries are not treated as message boundaries. The interruption scenario shows a partial transfer, reconnect, and resume offset; the slow-consumer scenario records buffer/lag evidence. A production stream protocol would require real framing, offset, and reconnection semantics appropriate to its transport.

### UI controls and evidence

The dedicated page offers message-only, stream-only and comparison views; shared incident, telemetry, and mixed workloads; normal, slow-consumer, interruption, and delivery-retry presets; producer/consumer rate and buffer-capacity controls; step/run/pause/resume/reset; an event timeline and inspector; current transport counters; and JSON evidence export. Values are intended to be derived from the event trace, with pending events distinguished from executed events.

### Validation and limitations

The API validates workload, scenario, producer/consumer rates, and buffer capacity. Tests cover message retry and acknowledgement evidence, stream byte/buffer/reconnect evidence, and invalid configuration. The experiment remains explicitly marked as deterministic simulation; live broker/socket verification and real performance measurements are outside this demo.


## Local Distributed Deployment Studio

The Deployment Studio complements the protocol labs with a practical containerized deployment of the AegisGrid incident-response application. The existing Docker Compose stack separates the frontend, FastAPI API, RabbitMQ worker, transactional outbox dispatcher, PostgreSQL, and RabbitMQ. The local Kubernetes resources are maintained under `deploy/kubernetes/`.

The UI includes:
- A topology view of the services declared by the existing deployment.
- Live API-side PostgreSQL query and RabbitMQ TCP reachability probes from `GET /api/deployment/status`.
- A verification action that creates a uniquely labelled low-severity incident via `POST /api/deployment/verify-request`, exercising the real frontend-to-API-to-database path.
- Docker Compose and Kubernetes command previews, including worker scaling.
- Exportable evidence that distinguishes actual probes from unconnected runtime inventory and unapplied command previews.

The deployment lab explicitly does not claim to know host Docker container or Kubernetes pod counts. Those values must be inspected using Docker/Kubernetes tooling until an explicit runtime adapter is configured. RabbitMQ TCP reachability is not proof of message publish/consume; the worker and dispatcher logs provide additional evidence.

See [Local Distributed Deployment Guide](LOCAL_DISTRIBUTED_DEPLOYMENT.md) for startup, scaling, inspection, and cleanup instructions. Kubernetes manifests use local development credentials and are not a production security configuration.


## 11. Dedicated protocol simulation workspaces

The mutual-exclusion and heartbeat labs use a dedicated full-width workspace rather than the permanent ten-item catalog layout. The remaining concepts continue to use the existing workbench. The dedicated pages intentionally prioritise configuration, live model state, event-by-event execution, an event inspector and run evidence over explanatory theory cards.

### Distributed mutual exclusion

- Model: Ricart–Agrawala educational simulation with three processes, or two for the explicit timestamp tie-break scenario.
- Configure: scenario preset, per-process logical request timestamps, and scenario name.
- Execute: create persisted run, step one event at a time, run to completion, pause/resume and reset the event cursor.
- Inspect: request creation and multicast, request receive, tuple comparison `(Lamport timestamp, process ID)`, immediate or deferred REPLY, permission completion, critical-section entry, the protected application operation, exit, and released deferred replies.
- Evidence: full event trace, per-process clocks/state, reply sets and deferred queues, total entry order, final simulated application record and safety checks.
- Invariant: no process enters before all required peer replies have been recorded; at most one owner may be in the critical section. The application record in the trace is an illustrative in-memory object, not a production database lock.
- Limitation: the model is a deterministic teaching scheduler, not a crash-tolerant implementation of the protocol. It does not claim progress under process failure, lost replies or partitions.

### Heartbeat / beacon failure detection

- Configure: target node, heartbeat interval, timeout, network delay, loss percentage, process-crash / partition / delayed-delivery / recovery scenario, missed heartbeat count and whether to include a recovery event.
- Observe: initial heartbeat receipt, expected heartbeat arrivals, dropped or delayed signals, timeout crossings, suspicion decisions, and recovery.
- Inspect: event time in simulated milliseconds, last successfully received heartbeat, elapsed time since receipt, actual process state known to the simulator, observer's belief, decision reason and fault mode.
- Evidence: configured parameters, complete event trace, final actual and observed states, timeout-based detection time, missed-signal count and false-suspicion flag.
- Correctness: timeout suspicion is not proof of crash. A healthy process behind a partition or slow network can be suspected. The simulation labels actual state separately from what the observer can infer.
- Limitation: packet-loss percentage is converted into a deterministic pattern for repeatability; it is not a random network model or a claim about measured infrastructure.

### Validation checklist

1. Create and step a simultaneous-request scenario; ensure each process state reflects the event cursor, not the final state prematurely.
2. Verify same-timestamp requests use process ID as the deterministic secondary key.
3. Verify every critical-section entry has a complete reply set, and no trace contains concurrent owners.
4. Run a crash scenario with recovery disabled: actual state remains crashed and observer state reflects the timeout result.
5. Run a partition scenario: actual process remains running while the observer can become suspected.
6. Run a delayed heartbeat scenario where delivery crosses the timeout; suspicion is recorded before the late receipt clears it.
7. Reset a persisted run and verify the next event repeats exactly.
8. Treat CI and local builds as the source of test status; UI status badges alone are not execution evidence.


## Critical Resource Control Room — mutual exclusion page redesign

The Mutual Exclusion navigation item now opens a resource-centric execution workspace instead of the generic experiment workbench. The underlying `/api/experiments` and `/api/experiments/{run_id}/step` APIs remain authoritative for generated trace data and persisted run state.

### Page structure

1. **Resource identity and boundary:** identifies the teaching fixture as Recovery Slot R-01, capacity one, linked to example incident INC-1042. The page explicitly states that this is simulation data and does not lock or mutate a live dispatch resource.
2. **Scenario selector:** competing resource claims, equal timestamps/tie-break, deferred permission, and delayed delivery. The selected scenario is passed in experiment parameters so the backend creates the corresponding trace preset.
3. **Execution controls:** create a persisted run, advance one event, run the remaining trace, reset the cursor, and export a JSON evidence bundle.
4. **Process topology:** three named logical participants, resource ownership indicator, and a note that the backend event ledger—not decorative arrows—is authoritative for message direction and order. The tie-break preset models two processes as defined by the backend.
5. **Safety evidence:** displays relevant boolean/numeric/string result fields and the full backend result JSON. Missing checks are not represented as passing.
6. **Message timeline and inspector:** future events remain visibly pending and cannot be selected as executed. Selecting an executed event shows exact recorded fields, including timestamps, sender/target, message type, request ordering key, process snapshots and application state when present.
7. **Protected-operation walkthrough:** explains sample incident acknowledgement, unit assignment and reservation as modeled operations, without claiming they are live application mutations.
8. **Correctness boundary:** explains that Ricart–Agrawala assumptions do not provide arbitrary crash/partition tolerance and recommends database-enforced atomic claims or consensus-backed leases with fencing for production ownership.

### Data and execution contract

- The UI creates a `mutex` experiment and passes `scenario` inside `parameters`, matching the backend mutex trace builder.
- Step controls consume the returned persisted run and use `current_step` to distinguish executed events from pending events.
- The owner badge is reconstructed from executed critical-section entry/exit and resource-owner events, rather than from the future final result.
- JSON export contains run configuration, backend result, run metadata, and the trace prefix that has actually executed.
- API errors are surfaced to the user; failed requests are not presented as successful runs.
- The interface includes responsive layouts for tablet/mobile widths.

### Manual validation checklist

1. Open Distributed Runtime → Mutual exclusion and confirm the Critical Resource Control Room page is shown.
2. Create the competing-claims run and verify a persisted run ID and pending event list appear.
3. Advance one event at a time; confirm the executed cursor and inspector update while later events remain pending.
4. Run to completion; compare final result checks against trace entry/reply/exit events.
5. Choose equal timestamps and verify the backend trace records the process-ID tie-break.
6. Choose deferred permission and inspect `reply.deferred`, blocked request, later deferred reply delivery and entry ordering.
7. Reset and verify the cursor returns to the beginning; create a new run if the API rejects reset for that run state.
8. Export JSON and confirm it contains only the executed trace prefix plus complete run/result metadata.
9. Run `npm run build` in `frontend` and the backend test suite in the documented environment before merging.

**Validation status:** this change was authored through the GitHub repository API. A local frontend build and backend test execution were not available in this authoring session; CI and reviewer verification are still required.


## Beacon Protocol Control Room — interactive heartbeat suspicion demonstration

The Distributed Runtime navigation item **Heartbeat suspicion** now opens a dedicated Beacon Protocol Control Room. The mutual-exclusion page remains separate and is not changed by this route. The page uses the existing persisted `beacon` experiment model in `POST /api/experiments` and the event-by-event execution endpoint `POST /api/experiments/{id}/step`.

### What the user sees

1. **Incident context:** a teaching fixture for incident `INC-1042` connects beacon monitoring to dispatch-worker communication health. The page explicitly says the experiment is simulated.
2. **Fault-mode selector:** worker crash, network partition, delayed beacons, and intermittent loss/recovery. The selected mode is sent to the backend as `fault_mode`.
3. **Detector configuration:** worker ID, beacon interval, suspicion timeout, number of expected missed beats, simulated network delay, packet-loss percentage, and an optional recovery phase.
4. **Run controls:** create a persisted run, advance one event, run to completion, pause/resume the persisted run, clear the displayed run, and export evidence JSON.
5. **Response topology:** Incident Coordinator, monitored Dispatch Worker, and Resource Allocator with current observer classification. The diagram is conceptual; the backend trace is authoritative.
6. **Detector evidence:** accepted beacon count, missed-slot count, silence age, first suspicion timestamp, current observed state, and backend final classification.
7. **Event timeline and inspector:** executed events are selectable; pending events are disabled. Each selected event exposes backend fields such as simulated timestamp, last receive time, elapsed silence, actual process state, observer state and decision reason when present.
8. **Operational consequence:** the page illustrates a simulated assignment-review flag when suspicion has occurred. It never claims that a live dispatch unit was reassigned.
9. **Correctness boundary:** the page explains that timeout-based suspicion cannot distinguish a process crash from delayed communication or a network partition on its own.

### Existing backend model reused

The backend `_trace_for("beacon", parameters)` model already produces deterministic events including `heartbeat.received`, `heartbeat.missed`, `failure.suspected`, and `heartbeat.recovered`. The UI sends supported parameters to that model rather than generating its own event order. The event cursor controls what is considered executed in the presentation.

### Manual validation checklist

1. Open Distributed Runtime → Heartbeat suspicion and confirm Beacon Protocol Control Room appears.
2. Create a worker-crash run with interval 1000 ms and timeout 3000 ms; advance events and inspect the first `failure.suspected` event.
3. Run the network-partition scenario and confirm the page describes observer suspicion without asserting that the worker process crashed.
4. Run the delayed-beacon scenario with delay greater than the timeout and inspect both suspicion and subsequent received-beacon events.
5. Run the recovery scenario and verify the trace includes recovery evidence and the final observer classification.
6. Confirm pending events cannot be inspected before the cursor reaches them.
7. Pause/resume a run, clear the displayed run, and export the JSON evidence bundle.
8. Verify the Mutual Exclusion navigation item still opens the separate Critical Resource Control Room.
9. Run frontend production build, backend tests, and Docker Compose smoke tests before merging.

**Validation status:** changes were authored through the GitHub repository API. A local frontend build and backend test execution were not available during authoring; merge only after CI and reviewer checks pass.


## Communication Control Room — communication chapter workspace

The Messaging navigation item now opens a dedicated Communication Control Room. It presents the existing message-oriented and stream-oriented experiment studio inside a polished transport catalogue. The Mutual Exclusion and Beacon Protocol Control Rooms remain separate routes and separate demonstrations.

### UI areas

1. **Communication header:** AegisGrid distributed-systems context, incident teaching fixture, and a clear boundary between simulation evidence and runtime evidence.
2. **Transport catalogue:** separate cards for Remote Procedure Call (RPC), message-oriented communication, stream-oriented communication, P2P messaging and WebRTC. Existing message and stream labs are identified as interactive experiments. RPC, P2P and WebRTC are explicitly marked as not yet verified/implemented as dedicated transports rather than presented as functional demos.
3. **Existing experiment studio:** reuses the current `CommunicationDemo` component and its persisted experiment endpoints for deterministic messaging and stream traces, step execution, pause/resume/reset and JSON export.
4. **Runtime evidence note:** explains that deterministic traces do not prove that a user action passed through Docker, RabbitMQ or a live WebSocket. This avoids presenting simulated events as real runtime observations.
5. **Responsive layout:** transport cards adapt from five columns to tablet and mobile layouts.

### Runtime-backed demonstration target

The intended next stage is to correlate one frontend dispatch action through the actual configured service path: API request/response, database/outbox record, publisher result, broker routing/delivery evidence, worker processing and acknowledgement where available. Each stage needs its own evidence; API success must not be treated as proof of worker processing.

Required instrumentation for that stage includes correlation-ID propagation, structured service logs, and a restricted backend log-evidence endpoint. The browser must not access the Docker socket directly. Until that instrumentation is implemented and verified, the UI labels the existing message/stream labs as deterministic simulations and shows Docker correlation as a requirement rather than claiming live logs.

### Transport-specific correctness requirements

- **RPC:** show the actual invocation and response; label HTTP request-response accurately unless a dedicated RPC protocol such as gRPC is implemented.
- **Message-oriented:** distinguish created, published, consumed, processed and acknowledged states.
- **Stream-oriented:** show connection lifecycle and ordered frames/bytes only where a real stream transport exists; simulation traces remain labelled.
- **P2P:** only claim direct peer communication when an actual peer transport is established; otherwise identify relay/signalling paths accurately.
- **WebRTC:** keep signalling (SDP/ICE exchange) distinct from the peer data path and report browser connection/data-channel evidence only after implementation.

### Manual validation checklist

1. Open Messaging in the main navigation and verify the Communication Control Room shell and five transport cards.
2. Confirm message-oriented and stream-oriented experiments still use the existing experiment API and can create, step, pause/resume/reset and export a trace.
3. Verify that RPC, P2P and WebRTC cards do not claim runtime support until their transport implementations exist.
4. Verify the existing Stream Telemetry navigation and the Mutual Exclusion and Beacon Protocol pages remain available independently.
5. Run the frontend production build, backend test suite and Docker Compose smoke tests before merging.
6. For a later runtime-backed phase, verify correlation IDs across producer, outbox, broker and consumer logs before marking any stage as runtime-verified.

**Validation status:** authored through the GitHub repository API. Local build and test execution were not available in this authoring session; CI and reviewer verification are required.
