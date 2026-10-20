# Kubernetes Guide

## Objective
Run the actual AegisGrid frontend, API, worker, PostgreSQL and RabbitMQ workloads in the dedicated `aegisgrid` namespace. The manifest uses Deployments and Services; PostgreSQL has a persistent volume claim. This is a learning deployment, not a hardened production topology.

## Preflight
Requirements:
- A development Kubernetes cluster such as kind, minikube or Docker Desktop Kubernetes.
- kubectl configured to the intended cluster/context.
- Build tools able to create local API and frontend images.
- A cluster storage class that can satisfy the database PVC.

Check context and nodes before applying:
```bash
kubectl config current-context
kubectl get nodes
```

Build images:
```bash
docker build -t aegisgrid-api:local ./services/api
docker build -t aegisgrid-frontend:local ./frontend
```

For kind, load images into the cluster with `kind load docker-image aegisgrid-api:local aegisgrid-frontend:local`. For minikube, build into its daemon or load images. Image visibility is a common cause of ImagePullBackOff.

## Secrets
The checked-in Kubernetes Secret uses obvious development placeholder values. Replace them before applying to any shared cluster. Never commit live credentials to Git. For an actual shared deployment, use the cluster's secret manager or a secure external secret mechanism; base64-encoding a Secret does not encrypt it at rest by itself.

Update:
- POSTGRES_PASSWORD in `infrastructure/kubernetes/app-stack.yaml`
- RABBITMQ_PASSWORD in the same file
- CORS_ORIGINS and image references when exposing the frontend elsewhere

Keep API/worker database credentials and RabbitMQ credentials aligned with the database and broker pods. If a database has already initialized a persistent volume using an older password, changing the Secret alone may not rotate the database user password.

## Apply and inspect
```bash
kubectl apply -f infrastructure/kubernetes/namespace.yaml
kubectl apply -f infrastructure/kubernetes/app-stack.yaml
kubectl get deployments,pods,services,pvc -n aegisgrid
kubectl rollout status deployment/aegisgrid-api -n aegisgrid
kubectl rollout status deployment/aegisgrid-frontend -n aegisgrid
kubectl logs deployment/aegisgrid-api -n aegisgrid --tail=100
kubectl logs deployment/aegisgrid-worker -n aegisgrid --tail=100
```

The frontend NodePort is 30080. The API Service is internal on port 8000. Accessing the dashboard should use the node address and NodePort supported by your local cluster.

## Scale the stateless workloads
```bash
kubectl scale deployment/aegisgrid-api --replicas=3 -n aegisgrid
kubectl scale deployment/aegisgrid-frontend --replicas=3 -n aegisgrid
kubectl scale deployment/aegisgrid-worker --replicas=3 -n aegisgrid
kubectl get pods -n aegisgrid -w
```

The API deployment's readiness probe queries the database-backed readiness endpoint. Frontend readiness checks HTTP. The worker consumes a shared queue. Do not scale PostgreSQL or RabbitMQ by simply increasing replicas: their current manifests are singleton workloads and do not implement database replication or RabbitMQ clustering.

## Demonstrate recovery
Use a disposable development cluster:
```bash
kubectl get pods -n aegisgrid -o wide
kubectl delete pod <one-aegisgrid-api-pod-name> -n aegisgrid
kubectl get pods -n aegisgrid -w
kubectl rollout status deployment/aegisgrid-api -n aegisgrid
kubectl get events -n aegisgrid --sort-by=.lastTimestamp
```

Record the deletion time, replacement Pod creation time, readiness time, and a successful API request after recovery. Don't claim recovery performance until you have observed it.

## Security and production gaps
- Use a private image registry, pinned digests, image scanning and pull secrets as needed.
- Replace development credentials and use secure Secret management.
- Configure NetworkPolicies, resource quotas and least-privilege ServiceAccounts.
- Add PodDisruptionBudgets, HPA only after metrics are available, and topology spread/anti-affinity where appropriate.
- Use proper PostgreSQL and RabbitMQ operators or managed services for durability/HA.
- Configure TLS, ingress, authentication, observability and backups.
- Review all manifests with `kubectl diff -f infrastructure/kubernetes/` before changing a running environment.

The Kubernetes runtime panel documents commands; it does not remotely execute kubectl or invent cluster telemetry.
