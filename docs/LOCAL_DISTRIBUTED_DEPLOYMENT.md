# Local Distributed Deployment Guide

This guide runs AegisGrid on one developer laptop using Docker Compose first and a local Kubernetes cluster second. This is a local development/academic setup, not a production security baseline.

## Architecture and request path

The existing Compose deployment already separates these processes:

- **Frontend** — Nginx-served React application on host port 3000; /api-proxy/ forwards requests to the API service.
- **API** — FastAPI on host port 8000; handles incidents and writes durable records to PostgreSQL.
- **Worker** — independent RabbitMQ consumer; processes event messages and persists results.
- **Outbox dispatcher** — independently polls the transactional outbox and publishes committed events to RabbitMQ.
- **PostgreSQL** — persistent incident, event, and outbox storage.
- **RabbitMQ** — message broker between the outbox dispatcher and worker.

The Deployment Studio's live request test creates a uniquely labelled low-severity verification incident through the API. That proves the HTTP/API-to-database path. The dependency panel separately probes the database query and RabbitMQ TCP reachability. A TCP connection is not proof of a successful AMQP publish/consume; verify that in worker and dispatcher logs.

## Docker Compose

From the repository root:

```bash
docker compose up -d --build
docker compose ps
```

Open the app at http://localhost:3000 and API docs at http://localhost:8000/docs.

Inspect actual runtime status and logs:

```bash
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 worker
docker compose logs --tail=100 outbox-dispatcher
docker compose logs --tail=100 rabbitmq
```

Demonstrate independent worker scaling:

```bash
docker compose up -d --scale worker=3
docker compose ps worker
```

Run the same incident/request workload before and after scaling. Record successful and failed requests, achieved throughput, p50/p95 latency, and the actual number of running worker containers. Scaling workers helps only work consumed from the shared broker; it does not scale the API or database. Do not assume linear performance improvement.

Shut down the stack:

```bash
docker compose down
```

Add -v only when intentionally deleting the local database volume.

## Kubernetes on a local cluster

Prerequisites: Docker, kubectl, and kind or Minikube. Build the images from the repository root:

```bash
docker build -t aegisgrid-api:local ./services/api
docker build -t aegisgrid-frontend:local ./frontend
```

For kind, create a local cluster if you do not already have one, then load the images:

```bash
kind create cluster --name aegisgrid
kind load docker-image aegisgrid-api:local --name aegisgrid
kind load docker-image aegisgrid-frontend:local --name aegisgrid
```

Apply the Kustomize resources:

```bash
kubectl apply -k deploy/kubernetes
kubectl get deployments,pods,services -n aegisgrid
kubectl rollout status deployment/aegisgrid-api -n aegisgrid
kubectl rollout status deployment/aegisgrid-frontend -n aegisgrid
kubectl port-forward service/aegisgrid-frontend 3000:80 -n aegisgrid
```

Then open http://localhost:3000. Keep the port-forward command running in its terminal. The API is reached through the frontend Nginx proxy and Kubernetes service DNS name api.

Scale the worker deployment and observe the actual replicas:

```bash
kubectl scale deployment/aegisgrid-worker --replicas=3 -n aegisgrid
kubectl rollout status deployment/aegisgrid-worker -n aegisgrid
kubectl get pods -n aegisgrid -l app=aegisgrid-worker -o wide
kubectl logs deployment/aegisgrid-worker -n aegisgrid --tail=100
```

Restore the baseline after the experiment:

```bash
kubectl scale deployment/aegisgrid-worker --replicas=1 -n aegisgrid
```

Remove the deployment when finished:

```bash
kubectl delete -k deploy/kubernetes
```

### Kubernetes configuration notes

- Manifests live in deploy/kubernetes/ and include the frontend, API, worker, outbox dispatcher, PostgreSQL StatefulSet/PVC, RabbitMQ, Services, ConfigMap, and a Kustomize-generated Secret.
- Secret values in the manifest generator are explicitly **development-only credentials**. Do not use them outside a local demo; provide real secrets via a secure deployment process for shared environments.
- The manifests use local image tags and IfNotPresent; build and load those images into the cluster before applying.
- PostgreSQL uses a 1 GiB PVC. A local cluster needs a working default StorageClass.
- API readiness depends on database readiness. The init containers wait for PostgreSQL and RabbitMQ TCP ports before starting the application processes.
- The API Deployment has one replica by default. Before scaling the API, verify database schema/startup behavior and ensure all replicas use the same configured database. Worker replicas are the safer first scaling demonstration.
- These manifests are for local teaching. They do not provide production TLS, external secret management, network policies, high-availability storage, or a highly available broker/database.

## Deployment Studio evidence semantics

The dashboard intentionally distinguishes:
1. **Live API/dependency probes** returned by /api/deployment/status.
2. **Verified request evidence** returned by POST /api/deployment/verify-request.
3. **Runtime inventory**, which is marked not connected until an explicit Docker/Kubernetes runtime adapter is configured.
4. **Command previews**, which do not imply that a scale or restart action has been applied.

For a project demonstration, capture the UI, docker compose ps or kubectl get pods, the verification incident, worker/outbox logs, and before/after benchmark results. Report measured values from the actual run, not target request rates or illustrative numbers.
