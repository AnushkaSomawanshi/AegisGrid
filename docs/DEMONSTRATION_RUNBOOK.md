# AegisGrid demonstration runbook

This runbook describes how to start the repository, verify the Docker Compose stack, and optionally deploy the Kubernetes manifests. Run commands from the repository root. Treat demo incidents, the supplied reference map artwork, and protocol-lab traces as illustrative unless a screen explicitly shows API-backed evidence.

## 1. Prerequisites

- Git
- Docker Desktop with Docker Compose v2
- PowerShell on Windows
- Optional for Kubernetes: kubectl and a local Kubernetes cluster such as Docker Desktop Kubernetes, kind, or minikube
- Optional for editing/running frontend outside containers: Node.js 20+

## 2. Update the repository

```powershell
git switch main
git fetch origin
git pull --ff-only origin main
git status
```

If local edits exist, inspect and commit or stash them before switching branches. Do not reset or clean files you need.

## 3. Add the supplied operational map asset

Copy the exact supplied reference image into this path before building the frontend:

`frontend/public/assets/aegisgrid-operational-map.png`

Confirm it exists:

```powershell
Test-Path .\frontend\public\assets\aegisgrid-operational-map.png
```

The frontend build copies files under `frontend/public` to the static web root. The Command Centre displays this image as the sole visible map layer; Leaflet markers and demo routes are hidden on this view so they do not conflict with the embedded scenario labels. This static reference image is not a geospatial basemap and does not imply live GIS coordinates.

## 4. Start the Docker Compose stack

```powershell
docker compose config
docker compose build --no-cache
docker compose up -d
docker compose ps
```

Open:
- Frontend: http://localhost:3000
- FastAPI docs: http://localhost:8000/docs
- RabbitMQ management UI: http://localhost:15672

Inspect logs if a service is unhealthy:

```powershell
docker compose logs --tail=150
docker compose logs --tail=150 frontend
docker compose logs --tail=150 api
docker compose logs --tail=150 worker
```

Service names can differ by Compose file; use `docker compose ps` to check exact names. If frontend source or public assets changed, rebuild and recreate that service:

```powershell
docker compose build --no-cache frontend
docker compose up -d --force-recreate frontend
```

Verify the image URL in a browser:
http://localhost:3000/assets/aegisgrid-operational-map.png

Then hard-refresh the dashboard with Ctrl+Shift+R.

Stop without deleting data volumes:

```powershell
docker compose down
```

Do not add `--volumes` unless you intentionally want to delete persisted local database/broker data.

## 5. Kubernetes demonstration workflow

Kubernetes deployment manifests are under `infrastructure/kubernetes/`. Inspect the namespace, workload manifests, images, ports, secrets and storage assumptions before applying them.

Check cluster access:

```powershell
kubectl config current-context
kubectl get nodes
kubectl get namespaces
```

Apply the namespace and stack (review exact manifest filenames first):

```powershell
kubectl apply -f infrastructure/kubernetes/namespace.yaml
kubectl apply -f infrastructure/kubernetes/app-stack.yaml
kubectl get all -n aegisgrid
kubectl get pods -n aegisgrid -o wide
kubectl get events -n aegisgrid --sort-by=.lastTimestamp
```

If the cluster cannot access locally built images, build the images specified by the manifests and load them into kind/minikube, or use a registry accessible to the cluster. Do not assume the Compose-built image automatically exists inside every Kubernetes cluster.

Useful inspection commands:

```powershell
kubectl describe pods -n aegisgrid
kubectl logs -n aegisgrid deployment/<deployment-name> --all-containers=true --tail=100
kubectl get deployments,replicasets,pods,services -n aegisgrid
kubectl rollout status deployment/<deployment-name> -n aegisgrid
kubectl rollout history deployment/<deployment-name> -n aegisgrid
```

Replace placeholders with actual names from `kubectl get deployments -n aegisgrid`. Only scale a stateless deployment that supports multiple replicas and whose configuration/queue semantics allow it:

```powershell
kubectl scale deployment/<worker-deployment-name> --replicas=2 -n aegisgrid
kubectl get pods -n aegisgrid -w
```

For a controlled recovery demonstration, delete one non-stateful test pod and observe its replacement:

```powershell
kubectl delete pod <test-pod-name> -n aegisgrid
kubectl get pods -n aegisgrid -w
```

Do not delete database pods or persistent volumes as a casual recovery demo. Capture the before/after pod list, events, rollout status, and request/worker evidence. Clean up only after the demonstration:

```powershell
kubectl delete -f infrastructure/kubernetes/app-stack.yaml
kubectl delete -f infrastructure/kubernetes/namespace.yaml
```

## 6. Concepts and demonstrations

- **Physical clock synchronization (Berkeley-style model):** compare node clock offsets, calculate a coordinator estimate, and inspect bounded corrections. Synthetic offsets are not measured host clocks.
- **Lamport logical clocks:** increment before local/send events; on receive use max(local, received)+1. A lower timestamp is not by itself proof of causality.
- **Vector clocks:** compare vectors component-wise. Comparable vectors imply happened-before; incomparable vectors indicate concurrency in the model.
- **Global state snapshot (Chandy–Lamport-style):** inspect process-local state and messages in transit. A lab trace is not a production distributed snapshot.
- **Bully leader election:** simulate failure suspicion and highest-live-ID coordinator selection; outcome depends on model membership and failure assumptions.
- **Distributed mutual exclusion (Ricart–Agrawala-style):** inspect timestamped requests and permission ordering. The educational lab does not lock a real shared production resource.
- **Heartbeat failure detection:** vary missed-heartbeat thresholds and distinguish suspicion from proof of a crash.
- **Message-oriented communication (RabbitMQ):** follow producer, durable queue, worker delivery/acknowledgement, and recorded processing evidence. API acceptance alone does not prove worker completion.
- **Stream-oriented communication (WebSocket):** demonstrate upgrade, bidirectional messages, keepalive and disconnect behavior.
- **Docker and Kubernetes:** compare container startup/health and service wiring with Kubernetes desired replicas, readiness, scheduling, replacement and rollout behavior. A running container or Pod is not, by itself, proof of end-to-end application correctness.
- **Service topology and runtime diagnostics:** inspect the configured components and correlate dashboard state with logs, API responses and Kubernetes/Compose output.

## 7. Evidence checklist

For each demonstration, record:
1. Scenario and whether data is live API-backed or synthetic.
2. Commands used and environment/image versions.
3. API response or event/worker acknowledgement relevant to the claim.
4. `docker compose ps` or Kubernetes pod/deployment state before and after.
5. Logs/events and observed timing for recovery or message processing.
6. Known limitations. Do not present sample values, static map artwork, or protocol-lab simulation output as real emergency telemetry.
