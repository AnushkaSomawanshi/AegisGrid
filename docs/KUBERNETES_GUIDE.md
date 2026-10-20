# Kubernetes Guide

The manifests in `infrastructure/kubernetes` describe the target local deployment, including a separate Event Worker Deployment. Review images, local image loading, storage and secret configuration before applying. These manifests have not been executed by GitHub's file-writing API.

## Verify cluster

```bash
kubectl config current-context
kubectl cluster-info
kubectl get nodes
```

## Apply

```bash
kubectl apply -f infrastructure/kubernetes/namespace.yaml
kubectl apply -f infrastructure/kubernetes/
kubectl get deployments,pods,services -n aegisgrid
kubectl get pods -n aegisgrid -w
```

## Self-healing experiment
1. Confirm the target Pod is managed by a Deployment.
2. Record desired and available replicas.
3. Delete one test Pod by its actual name.
4. Watch the replacement.
5. Verify it becomes Ready.
6. Measure request continuity and verify application data separately.

Do not claim complete deployment until app, PostgreSQL and RabbitMQ are reachable in-cluster. A local Docker Desktop cluster does not prove multi-machine high availability.

## Security
Use Secrets or an appropriate secret manager. Do not commit production credentials or place kubeconfig/cluster-admin tokens in frontend assets. The initial UI does not directly query the Kubernetes API.
