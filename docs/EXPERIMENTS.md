# Scalability and Resilience Experiments

## Research questions
1. Does increasing event-worker replicas improve sustained message-processing throughput for a fixed workload?
2. Does consumer scaling increase database contention or simply move the bottleneck to PostgreSQL/RabbitMQ?
3. How long does an orchestrator take to return a stateless workload to ready state after a controlled Pod/container failure?
4. Which signal distinguishes API liveness, API readiness, broker publication and actual worker processing?

## Experiment hygiene
Use a local disposable environment with no real emergency data. Record date/time, OS, CPU/memory, Docker/Kubernetes versions, image tag or digest, branch/commit, broker/database versions and network details. Warm up first, repeat each run at least three times, and keep the input workload identical across comparisons.

Do not use the dashboard's synthetic performance curves as results. Capture raw measurements from the actual API, broker and runtime.

## A. Message throughput scaling

### Fixed workload
- Create a known batch of test messages (e.g. 300 to 1,000) through the demo event endpoint at a controlled rate.
- Record start time and message count.
- Ensure no old messages remain in the queue or count them as backlog.
- Run worker replicas at 1, then 2, then 3.
- Repeat runs and avoid changing the number of producers or database setup during comparison.

### Compose commands
```bash
docker compose up -d --scale worker=1
docker compose ps
docker compose logs -f worker
docker compose up -d --scale worker=2
docker compose up -d --scale worker=3
```

### Measurements to record
- Time from test start to last processing acknowledgement.
- Successfully processed events per second.
- Ready and unacknowledged queue counts over time.
- Number of event records and worker.processed records.
- Duplicate or failed processing attempts.
- API response time and HTTP error count.
- CPU/memory for worker, API, database and broker if measurements are available.

Throughput = successfully processed test messages / elapsed seconds. Keep units and test workload explicit.

## B. API request behavior
Call the health endpoint with a fixed number and concurrency of requests. Repeat before and after changing API replicas. Record p50/p95 latency, requests per second, timeouts and 5xx responses. Use an external load tool (e.g. hey, wrk or k6) if available and describe its parameters. A shell loop is suitable as a connectivity smoke test but is not a rigorous benchmark.

## C. Pod recovery
1. Capture a list of Pods and current readiness.
2. Send periodic readiness requests and record successful/failed responses.
3. Delete one stateless API or frontend Pod in a disposable namespace.
4. Record deletion, scheduling, container start, readiness and first successful request timestamps.
5. Verify replacement count and check pod events/logs.
6. Repeat and report median/range rather than one lucky run.

## D. Failure semantics matrix

| Failure | Expected observation | Required evidence |
|---|---|---|
| API process down | Liveness endpoint unavailable; service endpoint stops sending traffic once endpoints/readiness update | curl output, pod status/events |
| PostgreSQL unavailable | API readiness returns 503 or pod fails readiness, depending on startup state | API log and health endpoint |
| RabbitMQ unavailable | Event response indicates publisher failure; event record may still exist | API response, broker logs, event ledger |
| Worker stopped | Messages can remain ready in broker queue; no new worker processing records | Broker queue counts, worker logs |
| One stateless Pod deleted | Controller attempts to recreate it and return replica count | Deployment/Pod watch and events |
| Network slowdown | Latency rises or requests time out; missed heartbeats may cause suspicion | Load results, logs and synthetic lab discussion |

## E. Recording template

Copy this table to your report and fill using actual readings:

| Run | Worker replicas | Messages offered | Processed | Elapsed seconds | Throughput msg/s | API p95 ms | Queue max | Error/duplicate count |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A1 | 1 | | | | | | | |
| A2 | 2 | | | | | | | |
| A3 | 3 | | | | | | | |

Recovery measurements:

| Trial | Workload | Failure timestamp | Ready timestamp | Recovery seconds | Errors during recovery |
|---|---|---|---|---:|---|
| R1 | API replica | | | | |
| R2 | Frontend replica | | | | |
| R3 | Worker replica | | | | |

## F. Interpretation checklist
- Was throughput increased proportionally or did the improvement flatten?
- Did database connections, inserts or broker queue depth become the bottleneck?
- Did error rate or p95 latency get worse while average throughput improved?
- Were API and worker records duplicates-safe?
- Did Kubernetes replace the Pod, and when did it become Ready?
- Is the result reproducible and is the environment documented?
- Are conclusions limited to this workload and development environment?
