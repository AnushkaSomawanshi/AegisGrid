# AegisGrid — PC Setup and Release Acceptance

This guide is the operator-facing entry point for running AegisGrid on a personal computer. It separates Docker Compose (the normal local launch path) from optional Kubernetes validation.

## 1. What “ready” means

AegisGrid is an academic distributed-systems application. The running application stack includes a React/Nginx frontend, FastAPI API, PostgreSQL database, RabbitMQ broker, event worker and outbox dispatcher. The concept labs are educational simulations; their traces and illustrative charts are not observations from real machines. This project is not a real emergency-dispatch system.

| Acceptance level | Meaning | Required evidence |
|---|---|---|
| Source/configuration | Files and manifests exist | Repository review |
| Automated CI | Configured jobs pass | Successful Actions run for the exact `main` commit |
| Local runtime | Application works on this PC | Commands, API responses and browser checks |
| Kubernetes runtime | A selected profile deploys on a real dev cluster | Ready Pods, bound PVC, working endpoint and measured recovery/scaling |
| Production readiness | Security, retry/DLQ, HA, migrations and observability verified | Separate production review; not implied by the levels above |

Do not mark a higher level complete because a lower level passed.

## 2. PC prerequisites

For the normal local demo:
- Git
- Docker Desktop (Windows/macOS) or Docker Engine + Docker Compose v2 (Linux)
- A terminal (PowerShell/Windows Terminal, macOS Terminal or Linux shell)

For source-level checks, install Python 3.12 and Node.js 20. For optional Kubernetes work, install `kubectl` and configure a disposable development cluster such as kind, minikube or Docker Desktop Kubernetes.

Verify tools at the repository root (the folder containing `docker-compose.yml`):

```bash
git status --short
docker --version
docker compose version
```

## 3. Start the complete local stack

Create the local environment file:

```bash
cp .env.example .env
```

PowerShell alternative:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and change the development passwords before sharing this machine or network. Sample values are for local learning only.

Validate and start the six services:

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

| Service | Responsibility | Local access |
|---|---|---|
| `frontend` | Dashboard served by Nginx | http://localhost:3000 |
| `api` | FastAPI routes and health checks | http://localhost:8000/docs |
| `postgres` | Persistent application state | Internal network |
| `rabbitmq` | Asynchronous event broker | http://localhost:15672 |
| `worker` | Consumes events and records processing | Internal service |
| `outbox-dispatcher` | Retries pending outbox publication | Internal service |

Wait for readiness:

```bash
curl -fsS http://localhost:8000/health/live
curl -fsS http://localhost:8000/health/ready
curl -fsS http://localhost:8000/api/overview
```

Then open http://localhost:3000. OpenAPI is at http://localhost:8000/docs. Do not expose RabbitMQ management to an untrusted network.

If any check fails:

```bash
docker compose ps
docker compose logs --tail=200 api postgres rabbitmq worker outbox-dispatcher frontend
```

Fix the underlying issue and retry `docker compose up -d --build`. Do not delete the database volume as an initial troubleshooting step: it contains local persisted data.

## 4. Verify application workflows

### Incident and persistence

```bash
curl -fsS http://localhost:8000/api/incidents
curl -fsS http://localhost:8000/api/events
curl -sS -X POST http://localhost:8000/api/incidents \
  -H 'Content-Type: application/json' \
  -d '{"title":"PC acceptance test","category":"Medical","severity":"high","location":"Demo Sector 1","description":"Synthetic local smoke test"}'
```

Record the returned incident ID. Confirm it appears in `GET /api/incidents` and in the dashboard.

### Resource and experiment APIs

```bash
curl -sS -X POST http://localhost:8000/api/resources/demo-seed
curl -fsS http://localhost:8000/api/resources
curl -fsS http://localhost:8000/api/experiments
curl -fsS http://localhost:8000/api/outbox
```

Use the dashboard's Resources & units and Experiment workbench pages as well. Check API responses and persisted state, not just visual changes.

### RabbitMQ-to-worker evidence

```bash
curl -sS -X POST http://localhost:8000/api/events/demo
curl -fsS 'http://localhost:8000/api/events?limit=100'
docker compose logs --tail=100 api outbox-dispatcher worker rabbitmq
```

Find the new demo event, its broker/outbox status and the corresponding `worker.processed` ledger entry. These are separate stages: a successful API request alone is not proof of consumer processing.

### Persistence across API restart

Record the ID of a created incident/resource, then:

```bash
docker compose restart api
curl -fsS http://localhost:8000/health/ready
curl -fsS http://localhost:8000/api/incidents
```

Confirm the saved object remains. This verifies persistence across an API restart, not disaster recovery for the database itself.

## 5. Run code checks

Run from the repository root:

```bash
python -m pip install pyyaml
python scripts/validate_manifests.py
python -m pip install -r services/api/requirements.txt
(cd services/api && pytest -q)
(cd frontend && npm install && npm run build)
```

PowerShell does not support POSIX `(cd dir && command)` subshell syntax. Run the tests/build this way instead:

```powershell
python -m pip install pyyaml
python scripts/validate_manifests.py
python -m pip install -r services/api/requirements.txt
Push-Location services/api
pytest -q
Pop-Location
Push-Location frontend
npm install
npm run build
Pop-Location
```

Check the [GitHub Actions page](https://github.com/AnushkaSomawanshi/AegisGrid/actions) for a successful run associated with the exact `main` commit you are evaluating. A previous commit's green CI is not evidence for a later commit.

## 6. Optional Kubernetes validation

Kubernetes is not required just to run the Compose demo. Do not apply both repository Kubernetes profiles together.

- Canonical application stack: `infrastructure/kubernetes/namespace.yaml` and `infrastructure/kubernetes/app-stack.yaml`.
- Separate laptop-local Kustomize profile: `deploy/kubernetes/kustomization.yaml`.

Choose one profile and record which one. Read [Kubernetes Guide](KUBERNETES_GUIDE.md) and [Docker/Kubernetes Demonstration Runbook](DOCKER_KUBERNETES_DEMONSTRATION.md) before applying resources.

### Preflight and images

```bash
kubectl config current-context
kubectl get nodes
docker build -t aegisgrid-api:local ./services/api
docker build -t aegisgrid-frontend:local ./frontend
```

Review and replace placeholder Secret values in `infrastructure/kubernetes/app-stack.yaml` through a local development-only process. Never commit real credentials. For kind, load the local images:

```bash
kind load docker-image aegisgrid-api:local aegisgrid-frontend:local
```

Minikube has its own image-loading workflow. Ensure the selected cluster can access the images before applying.

### Apply and inspect

```bash
kubectl apply -f infrastructure/kubernetes/namespace.yaml
kubectl apply -f infrastructure/kubernetes/app-stack.yaml
kubectl get deployments,pods,services,pvc -n aegisgrid -o wide
kubectl rollout status deployment/aegisgrid-api -n aegisgrid --timeout=180s
kubectl rollout status deployment/aegisgrid-frontend -n aegisgrid --timeout=180s
kubectl rollout status deployment/aegisgrid-worker -n aegisgrid --timeout=180s
kubectl get pvc -n aegisgrid
kubectl get events -n aegisgrid --sort-by=.lastTimestamp
```

If a workload is not Ready, inspect `kubectl describe pod`, logs and namespace events before retrying. A Pending PVC often indicates a missing/default StorageClass; ImagePullBackOff means the cluster cannot access the requested image. Do not claim a successful deployment until actual Pods are Ready and the endpoint responds.

Port-forward in separate terminals:

```bash
kubectl port-forward service/api 8000:8000 -n aegisgrid
kubectl port-forward service/aegisgrid-frontend 3000:80 -n aegisgrid
```

Then test `http://localhost:8000/health/ready` and `http://localhost:3000`.

### Persistence, recovery and scaling

In a disposable development cluster, create a test incident and note its ID before restarting a Pod:

```bash
kubectl get pods -n aegisgrid -o wide
kubectl delete pod -n aegisgrid -l app=aegisgrid-api
kubectl rollout status deployment/aegisgrid-api -n aegisgrid --timeout=180s
kubectl get pods,pvc -n aegisgrid
```

After the replacement is Ready, confirm the incident still exists and the API responds. Pod replacement does not guarantee zero downtime.

Scale a stateless deployment only after baseline readiness:

```bash
kubectl scale deployment/aegisgrid-api --replicas=3 -n aegisgrid
kubectl rollout status deployment/aegisgrid-api -n aegisgrid --timeout=180s
kubectl get deployment aegisgrid-api -n aegisgrid
kubectl get pods -n aegisgrid -o wide
```

Record desired and ready replica counts. The optional HPA needs Metrics Server and working CPU metrics; the presence of an HPA object is not proof autoscaling happened. Do not scale PostgreSQL or RabbitMQ by simply increasing replicas: these manifests do not provide database replication or broker clustering. Never run destructive recovery tests in a shared/production context.

## 7. Evidence checklist

Create an evidence folder locally:

```bash
mkdir -p artifacts/acceptance
```

For every result, record date/time, OS, Docker version, Git SHA, selected Kubernetes profile/context where applicable, exact commands, exit status and relevant output. Do not commit secrets, local environment files or sensitive logs.

| Gate | Pass criteria | Status before your run |
|---|---|---|
| CI | All required jobs pass on the exact current `main` SHA | Must check Actions |
| Manifest validation | Validator exits 0 | Not run by this guide |
| Backend tests | `pytest -q` exits 0 | Not run by this guide |
| Frontend build | `npm run build` exits 0 | Not run by this guide |
| Compose | Six services running; API readiness passes | Not run by this guide |
| UI/API smoke | Dashboard loads; incident/resource/experiment APIs respond | Not run by this guide |
| Broker-to-worker | New event has worker-processing evidence | Not run by this guide |
| Persistence | Test row survives API restart | Not run by this guide |
| Kubernetes | One profile applies; Pods Ready; PVC Bound | Optional; must be tested on a cluster |
| Recovery | Pod replacement ready and endpoint responds | Optional; measure in disposable cluster |
| Scale | Actual ready replicas match requested count | Optional; measure on a cluster |
| Performance | Fixed workload, repeated trials and raw measurements captured | Separate measured experiment |

## 8. Quick troubleshooting

| Symptom | First diagnostic |
|---|---|
| Docker cannot connect | Start Docker Desktop/Engine; run `docker info` |
| API unhealthy | `docker compose logs --tail=200 api postgres rabbitmq` |
| Frontend loads but API fails | Check API readiness and Nginx/API proxy logs |
| Worker processing missing | Inspect publish response, outbox rows, RabbitMQ and worker logs separately |
| Data disappeared | Verify `docker compose down -v` was not run; it removes named volumes |
| Kubernetes image pull fails | Load locally built images into the selected cluster |
| PVC Pending | Inspect StorageClass and PVC events |
| HPA metrics unknown | Check Metrics Server and resource metrics |

## 9. Limitations and completion statement

This is not certified production software. The outbox and event-ID deduplication improve recovery but do not constitute end-to-end exactly-once delivery. Remaining production-oriented work includes bounded retries/dead-letter handling, event schema versioning, authentication/authorization, secret management/TLS/network policies, observability, database migrations and suitable high availability for stateful services. Not every concept page is a full distributed protocol engine; educational traces remain simulations.

**Documentation does not mark results as passed.** Completion requires a green CI run for the current commit, actual local PC execution evidence and—if Kubernetes deployment is being claimed—results from an actual development cluster.
