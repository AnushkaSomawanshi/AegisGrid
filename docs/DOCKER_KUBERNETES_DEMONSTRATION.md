# Docker and Kubernetes Demonstration Runbook

This runbook is the repeatable practical demonstration for the Distributed Systems mini-project. It separates **what the repository defines**, **what the operator actually runs**, and **what must be measured**. Do not claim a deployment or performance result until the commands have been run and their output saved.

## 0. Safety and prerequisites

- Use a disposable development environment and synthetic data only.
- Docker Engine/Desktop with Compose v2 is required for the container demo.
- Kubernetes demo requires a working development cluster (kind, minikube, or Docker Desktop Kubernetes), `kubectl`, and a default StorageClass that can bind the PostgreSQL PVC.
- Local images must be available inside the selected cluster. For kind, run `kind load docker-image ...`; for minikube, use its image build/load workflow.
- Review `infrastructure/kubernetes/app-stack.yaml`. Replace placeholder Secret values before applying. The sample credentials are not production credentials.
- Verify the intended context before every Kubernetes command: `kubectl config current-context`.

## 1. Docker Compose: build and start all services

From the repository root:

```bash
cp .env.example .env
# Edit .env and set development-only values unique to your machine.
docker compose config
docker compose up -d --build
docker compose ps
```

Expected service set:
- `frontend`: React static bundle served by Nginx, host port 3000.
- `api`: FastAPI, host port 8000.
- `worker`: independent RabbitMQ consumer process.
- `postgres`: persistent SQL state in named volume `aegisgrid-db`.
- `rabbitmq`: durable queue and local management interface on port 15672.

Check readiness and interfaces:

```bash
curl -fsS http://localhost:8000/health/live
curl -fsS http://localhost:8000/health/ready
curl -fsS http://localhost:8000/api/overview
```

Open dashboard `http://localhost:3000`, API OpenAPI `http://localhost:8000/docs`, and local RabbitMQ management `http://localhost:15672`. The management interface should not be exposed to an untrusted network.

## 2. Demonstrate the practical application

### 2.1 Create an incident

```bash
curl -sS -X POST http://localhost:8000/api/incidents \
  -H 'Content-Type: application/json' \
  -d '{"title":"Demo medical response","category":"Medical","severity":"high","location":"Sector 07","description":"Synthetic mini-project test"}'
```

Record the returned incident ID and event ID. Confirm the incident appears in the dashboard and API:

```bash
curl -fsS http://localhost:8000/api/incidents
curl -fsS http://localhost:8000/api/events
```

### 2.2 Seed and reserve a field resource

```bash
curl -sS -X POST http://localhost:8000/api/resources/demo-seed
curl -fsS http://localhost:8000/api/resources
```

Use the returned ID for one available resource:

```bash
curl -sS -X POST http://localhost:8000/api/reservations \
  -H 'Content-Type: application/json' \
  -d '{"resource_id":1,"requested_by":"command-desk"}'
curl -fsS http://localhost:8000/api/reservations
```

Attempt a second reservation for the same resource. The API should return HTTP 409 because the resource is no longer available. This is a simple reservation guard, not a full multi-capacity allocation scheduler.

### 2.3 Verify broker and worker communication

```bash
curl -sS -X POST http://localhost:8000/api/events/demo
docker compose logs --tail=100 api worker rabbitmq
curl -fsS http://localhost:8000/api/events
```

Observe separately:
1. API event ledger row.
2. Broker publication result returned by the API.
3. Worker log indicating processing.
4. Worker-generated `worker.processed` event in the ledger.

A successful API response is not proof of worker completion. This version still needs a transactional outbox and consumer idempotency before it can promise stronger delivery semantics.

## 3. Detailed concept workbench

Open **Experiment workbench** in the dashboard:
1. Select a protocol and enter a scenario name.
2. Adjust clock offsets or beacon parameters where available.
3. Create the run. The API persists the run, parameters, trace and result.
4. Click **Step next** to advance the persisted cursor one event.
5. Inspect the event timeline and backend-computed result.
6. Use **Reset cursor** to replay the stored trace from the first event.
7. Reopen a previous run from Recent experiment runs.
8. Copy the run evidence JSON into the report.

These are stepwise, persisted educational traces. They do not yet constitute complete distributed protocol engines with pause/resume, arbitrary node failure at every transition, or live node telemetry. The messaging and stream traces explicitly do not prove live broker/stream delivery.

## 4. Record a real HTTP baseline

The standard-library load probe makes actual HTTP requests and writes a JSON report:

```bash
python scripts/http_load_probe.py \
  --url http://localhost:8000/health/live \
  --requests 300 --concurrency 20 \
  --output artifacts/api-baseline.json
```

Create the output directory first if using `artifacts/`:

```bash
mkdir -p artifacts
```

Repeat at least three times. Keep target endpoint, request count, concurrency, machine, commit, and environment identical when comparing. The script reports successful/failed HTTP attempts, throughput, and latency percentiles. It does **not** measure server CPU/memory, RabbitMQ queue depth or worker throughput; collect those separately. A health endpoint is a smoke/load probe, not a representative production workload.

## 5. Scale the Docker worker pool

The worker is stateless with respect to its own process memory and consumes a shared durable RabbitMQ queue. For a development demonstration:

```bash
docker compose up -d --scale worker=1
docker compose ps
# Generate a fixed batch of demo events and observe worker logs.
docker compose up -d --scale worker=2
docker compose ps
docker compose up -d --scale worker=3
docker compose ps
```

For each configuration record:
- Number of messages offered and number of `worker.processed` records observed.
- Time from first publication to last worker acknowledgement.
- Broker ready/unacknowledged message counts in the RabbitMQ management UI.
- API errors and duplicate processing attempts.
- Worker/API/PostgreSQL/RabbitMQ resource usage if a tool provides it.

Do not infer worker throughput from the dashboard's illustrative charts. Run the same workload at each replica count and repeat each trial.

## 6. Kubernetes: build images and prepare the cluster

Check context and nodes:

```bash
kubectl config current-context
kubectl get nodes
```

Build images from the repository root:

```bash
docker build -t aegisgrid-api:local ./services/api
docker build -t aegisgrid-frontend:local ./frontend
```

For kind, load images into the cluster (replace the cluster name if needed):

```bash
kind load docker-image aegisgrid-api:local
kind load docker-image aegisgrid-frontend:local
```

For minikube, either build using its Docker daemon or load the images using its image-loading command. Ensure the deployment's `imagePullPolicy: IfNotPresent` can find these images.

## 7. Apply Kubernetes resources

**Review and replace the Secret placeholders first.** For a local-only test, edit the Secret values in `app-stack.yaml` or create a separate local Secret with the same name. Do not commit real credentials.

```bash
kubectl apply -f infrastructure/kubernetes/namespace.yaml
kubectl apply -f infrastructure/kubernetes/app-stack.yaml
kubectl get pods,deploy,svc,pvc -n aegisgrid -w
```

Wait for readiness:

```bash
kubectl rollout status deployment/aegisgrid-api -n aegisgrid
kubectl rollout status deployment/aegisgrid-frontend -n aegisgrid
kubectl rollout status deployment/aegisgrid-worker -n aegisgrid
kubectl get pods -n aegisgrid -o wide
kubectl get events -n aegisgrid --sort-by=.lastTimestamp
```

The frontend NodePort is 30080 in the manifest. Access depends on cluster type (for example, use `minikube service aegisgrid-frontend -n aegisgrid` if applicable). The API is cluster-internal through Service `api:8000`; use `kubectl port-forward service/api 8000:8000 -n aegisgrid` for local API testing.

## 8. Kubernetes scaling demonstration

Scale the stateless API and consumer separately:

```bash
kubectl scale deployment/aegisgrid-api --replicas=3 -n aegisgrid
kubectl scale deployment/aegisgrid-worker --replicas=3 -n aegisgrid
kubectl rollout status deployment/aegisgrid-api -n aegisgrid
kubectl get deploy,pods -n aegisgrid -o wide
kubectl top pods -n aegisgrid
```

`kubectl top` requires Metrics Server. If it is unavailable, record that resource usage was not measured instead of fabricating it.

An optional CPU-based HorizontalPodAutoscaler is supplied separately:

```bash
kubectl apply -f infrastructure/kubernetes/api-hpa.yaml
kubectl get hpa -n aegisgrid
kubectl describe hpa aegisgrid-api -n aegisgrid
```

The HPA requires metrics-server and only targets the API Deployment. It is a demonstration policy, not evidence that autoscaling occurred; observe replica changes under a repeatable load before reporting a result.

## 9. Controlled self-healing demonstration

Only do this in your own disposable development namespace:

```bash
kubectl get pods -n aegisgrid -l app=aegisgrid-api
kubectl delete pod -n aegisgrid -l app=aegisgrid-api --wait=false
kubectl get pods -n aegisgrid -l app=aegisgrid-api -w
```

For a repeatable readiness-timing JSON record (guarded to namespace `aegisgrid` and requiring explicit confirmation):

```bash
python scripts/k8s_recovery_probe.py --namespace aegisgrid --selector app=aegisgrid-api --confirm --output artifacts/recovery-r1.json
```

The script deletes one matching Pod and measures how long until a new replacement Pod becomes Ready. It does not measure user-visible downtime; run a parallel request probe for that.

Record:
- Failure injection timestamp.
- Pod termination and replacement timestamps.
- Time until replacement Pod is Ready.
- Readiness requests that failed during recovery.
- Replica count before and after.
- Pod events and relevant API logs.

Repeat three times and report the median and range. A Deployment replaces Pods; it does not guarantee zero failed requests during termination or startup.

## 10. Inspect actual cluster/runtime state

```bash
kubectl get deploy,pods,svc,pvc -n aegisgrid
kubectl describe deployment aegisgrid-api -n aegisgrid
kubectl logs deployment/aegisgrid-api -n aegisgrid --tail=100
kubectl logs deployment/aegisgrid-worker -n aegisgrid --tail=100
kubectl get events -n aegisgrid --sort-by=.lastTimestamp
```

Docker equivalent:

```bash
docker compose ps
docker compose logs --tail=100 api worker postgres rabbitmq
docker stats --no-stream
```

The dashboard runtime page currently provides safe command runbooks. It does not execute host commands or directly query the Docker socket/Kubernetes API; results must be collected from the real CLI/runtime.

## 11. Teardown

Compose:

```bash
docker compose down
```

Kubernetes (only the project's dedicated namespace):

```bash
kubectl delete namespace aegisgrid
```

Deleting the namespace removes the PVC claim and can cause development data to be lost depending on the StorageClass reclaim policy. Export any evidence before teardown.

## 12. Final evidence checklist

- [ ] Compose services build and become healthy.
- [ ] Incident create/status update survives API restart.
- [ ] Resource seed/create works and duplicate reservation returns HTTP 409.
- [ ] API event, RabbitMQ publication, worker processing and worker ledger row are separately verified.
- [ ] At least one run from each lab family has its parameters, trace and result exported.
- [ ] Three baseline load reports and three scaled comparison runs are saved.
- [ ] Kubernetes deployments become Ready and the expected replica count is observed.
- [ ] A controlled stateless Pod replacement is timed and documented.
- [ ] All limitations, missing measurements and environment versions are recorded.
