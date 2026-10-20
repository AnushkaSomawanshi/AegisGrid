# Docker Compose Guide

## Start
From the repository root:

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 worker
```

Frontend: http://localhost:3000. API docs: http://localhost:8000/docs. RabbitMQ management: http://localhost:15672. The independent `worker` service consumes broker events and persists delivery records. PostgreSQL host port is 5433 to reduce conflict with local PostgreSQL.

## Diagnose

```bash
docker compose ps
docker compose logs --tail=150 postgres
docker compose logs --tail=150 rabbitmq
docker compose logs --tail=150 api
```

Container creation alone does not imply readiness.

## Stop

```bash
docker compose down
```

Avoid `docker compose down -v` unless intentionally deleting the named development database volume.

## Safety
The current web screen displays API health and runtime instructions; it does not claim live Docker daemon inspection. Never expose the Docker socket directly to browser code.
