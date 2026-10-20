# Docker Guide

## What runs
The Compose stack contains five independent services: frontend/Nginx, FastAPI API, event-worker consumer, PostgreSQL and RabbitMQ. Containers communicate through the Compose network using service names. Only the frontend/API and RabbitMQ management console are published to host ports by default; PostgreSQL and AMQP remain internal.

## Start the project
```bash
cp .env.example .env
# Change the local passwords in .env before sharing this environment.
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 api worker
```

Open:
- Dashboard: http://localhost:3000
- API OpenAPI: http://localhost:8000/docs
- RabbitMQ management: http://localhost:15672 (local credentials from .env)

The initial development default passwords are not production-safe. Do not bind this stack to an untrusted network without changing credentials and configuring appropriate access controls.

## Verify service-to-service communication
```bash
curl -fsS http://localhost:8000/health/ready
curl -fsS http://localhost:8000/api/overview
curl -X POST http://localhost:8000/api/events/demo
curl -fsS http://localhost:8000/api/events
docker compose logs --tail=100 worker rabbitmq
```

A successful event route response contains a broker outcome. After the worker processes the message, inspect the ledger for a `worker.processed` record. Do not treat a committed event or successful API response as proof the consumer completed its work.

## Scale independent consumers
```bash
docker compose up -d --scale worker=3
docker compose ps worker
docker compose logs --tail=100 worker
```

Worker replicas consume from the same durable queue. Do not scale PostgreSQL or RabbitMQ with this command. Stateful scale-out needs a separate replication, clustering and persistent-volume design.

## Test restart/persistence behavior
1. Create an incident and record its ID.
2. Restart only the API container: `docker compose restart api`.
3. Check readiness and query the incident again. PostgreSQL data should remain because the database uses a named volume.
4. Restart the worker and emit another event. Check logs and the event ledger.
5. For a fault-recovery experiment, stop a stateless worker, observe queue depth/consumer availability, then start it again.

Avoid deleting the PostgreSQL volume unless data reset is intended. `docker compose down -v` deletes the named database volume.

## Troubleshooting
- **Frontend loads but is in demo mode:** run `docker compose ps` and `docker compose logs api postgres rabbitmq`. Check readiness at port 8000.
- **Database authentication failure:** make sure all containers use the same POSTGRES_PASSWORD. A changed environment variable doesn't rotate credentials inside an already initialized database volume automatically.
- **RabbitMQ connection refused:** confirm the broker health check passed and credentials match. API/worker retry behavior and their logs should be inspected.
- **Worker has no records:** create a new event; verify the response's broker status and look at queue-ready/unacknowledged counts in RabbitMQ.
- **Port is in use:** change the host side of the Compose port mapping, keeping the container port unchanged.
- **Frontend build error:** remove local node_modules if testing outside Docker, run npm install, then npm run build.

## Compose files
- `docker-compose.yml`: application components, dependency checks, database volume and broker.
- `services/api/Dockerfile`: API/worker Python image.
- `frontend/Dockerfile`: multi-stage React build and Nginx runtime.
- `frontend/nginx.conf`: SPA fallback, API proxy and WebSocket upgrade proxy.

## Operational boundary
Compose health checks are a local-development convenience, not a proof of production-grade reliability. Back up important data, rotate secrets, restrict network exposure and test failure scenarios before using any non-demo environment.
