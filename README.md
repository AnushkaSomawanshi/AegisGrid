# AegisGrid

**Distributed Emergency Response & Resource Coordination Platform**

AegisGrid is an academic distributed-systems mini-project. It combines an emergency-response command centre with interactive labs for physical clock synchronization, Lamport clocks, global snapshots, vector clocks, election, mutual exclusion, beacon failure detection, message-oriented communication, stream-oriented communication, Docker and Kubernetes.

> The initial repository foundation is being built incrementally. Every lab must distinguish deterministic educational simulations from observations of real services and infrastructure. Do not describe a module as production-grade or fully verified until its tests and deployment checks have been run.

## Project goals

- Demonstrate a practical application backed by independently running services.
- Demonstrate inter-service communication using HTTP and RabbitMQ.
- Persist incidents and event traces in PostgreSQL.
- Make each required distributed-systems concept inspectable through a dedicated UI.
- Run the development stack with Docker Compose.
- Deploy the actual application workloads to Kubernetes and measure scaling/recovery.
- Keep the demo honest: simulated clocks/protocols are labeled as simulations; Docker/Kubernetes state should come from actual runtime APIs.

## Initial stack

- Frontend: React + TypeScript + Vite
- API: Python + FastAPI
- Broker: RabbitMQ
- Persistence: PostgreSQL
- Containerization: Docker Compose
- Orchestration: Kubernetes manifests
- Tests: pytest and frontend build checks

## Quick start

Requirements: Docker Desktop with Compose v2.

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 api
```

Open the frontend at http://localhost:3000 and API docs at http://localhost:8000/docs.

Run backend tests locally:

```bash
python -m pip install -r services/api/requirements.txt
pytest -q
```

Run frontend build locally:

```bash
cd frontend
npm install
npm run build
```

## Services

| Service | Purpose |
|---|---|
| frontend | Command Centre and concept-lab UI |
| api | FastAPI gateway, incidents, experiment APIs and event ledger |
| postgres | Persistent application records |
| rabbitmq | Asynchronous event broker |

Algorithm labs are initially implemented as isolated API modules so they can be tested independently without creating an unnecessary microservice for each algorithm. Later milestones can extract services where the boundary provides a real benefit.

## Concept labs

1. Physical clock synchronization and Berkeley-style coordinator
2. Logical clocks and Lamport message ordering
3. Global state snapshot (Chandy–Lamport-style educational model)
4. Vector clocks and causality/concurrency
5. Leader election (Bully algorithm model)
6. Distributed mutual exclusion (Ricart–Agrawala model)
7. Beacon/heartbeat failure detection
8. Message-oriented communication with RabbitMQ
9. Stream-oriented communication using WebSockets
10. Event forensics and causal path inspection
11. Docker operations and service diagnostics
12. Kubernetes workload state, scaling and managed-Pod recovery
13. Scalability and controlled failure experiments

## Kubernetes

Manifests live under `infrastructure/kubernetes/`. The Kubernetes deployment is intended to run the application services, not merely an unrelated demo Pod. Before a local deployment, review the manifests and configure secrets safely.

```bash
kubectl apply -f infrastructure/kubernetes/namespace.yaml
kubectl apply -f infrastructure/kubernetes/
kubectl get deployments,pods,services -n aegisgrid
```

The initial manifests may require adaptation for your local image build and cluster. Do not commit real credentials. See `docs/KUBERNETES_GUIDE.md`.

## Documentation

- `docs/ARCHITECTURE.md`
- `docs/CONCEPT_DEMONSTRATIONS.md`
- `docs/DOCKER_GUIDE.md`
- `docs/KUBERNETES_GUIDE.md`
- `docs/EXPERIMENTS.md`

## Safety and academic integrity

- Clock, election, mutual-exclusion and snapshot labs are deterministic educational models unless specifically documented otherwise.
- Infrastructure actions must only target the intended development namespace/Compose project.
- Do not expose the Docker socket, Kubernetes credentials, or unrestricted infrastructure administration to the browser.
- Actual test/build/deployment status must be reported only after the command has run successfully.
