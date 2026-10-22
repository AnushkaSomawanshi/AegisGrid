#!/usr/bin/env python3
"""Static structural checks for AegisGrid Compose and Kubernetes manifests.

This validator checks repository consistency only. It does not prove that images
build, a cluster accepts the manifests, or live services become healthy.
"""
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_documents(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        docs = [doc for doc in yaml.safe_load_all(handle) if doc is not None]
    if not docs:
        raise ValueError(f"{path.relative_to(ROOT)} contains no YAML documents")
    if any(not isinstance(doc, dict) for doc in docs):
        raise ValueError(f"{path.relative_to(ROOT)} contains a non-object YAML document")
    return docs


def named_resources(documents: list[dict], kind: str) -> dict[str, dict]:
    return {
        doc.get("metadata", {}).get("name", ""): doc
        for doc in documents
        if doc.get("kind") == kind
    }


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    # Docker Compose: required service topology and persistence.
    compose = load_documents(ROOT / "docker-compose.yml")[0]
    services = compose.get("services", {})
    expected_services = {"frontend", "api", "worker", "outbox-dispatcher", "postgres", "rabbitmq"}
    missing = expected_services - set(services)
    if missing:
        errors.append("Compose missing services: " + ", ".join(sorted(missing)))

    if "aegisgrid-db" not in compose.get("volumes", {}):
        errors.append("Compose must define persistent volume aegisgrid-db")
    elif "aegisgrid-db" not in services.get("postgres", {}).get("volumes", []).__str__():
        # Keep this readable while supporting both short and long Compose volume syntax.
        postgres_volumes = services.get("postgres", {}).get("volumes", [])
        if not any(
            (entry == "aegisgrid-db:/var/lib/postgresql/data")
            or (isinstance(entry, dict) and entry.get("source") == "aegisgrid-db")
            for entry in postgres_volumes
        ):
            errors.append("Compose PostgreSQL service must mount aegisgrid-db at its data directory")

    for service_name in ("api", "postgres", "rabbitmq"):
        if service_name in services and not services[service_name].get("healthcheck"):
            errors.append(f"Compose service '{service_name}' must declare a healthcheck")

    api_dependencies = services.get("api", {}).get("depends_on", {})
    for dependency in ("postgres", "rabbitmq"):
        dependency_config = api_dependencies.get(dependency, {}) if isinstance(api_dependencies, dict) else {}
        if dependency in services and dependency_config.get("condition") != "service_healthy":
            errors.append(f"Compose API must wait for healthy '{dependency}'")

    frontend_dependencies = services.get("frontend", {}).get("depends_on", {})
    if isinstance(frontend_dependencies, dict) and "api" in services:
        if frontend_dependencies.get("api", {}).get("condition") != "service_healthy":
            errors.append("Compose frontend must wait for API health")

    # Main Kubernetes deployment set.
    namespace_docs = load_documents(ROOT / "infrastructure/kubernetes/namespace.yaml")
    stack_docs = load_documents(ROOT / "infrastructure/kubernetes/app-stack.yaml")
    hpa_docs = load_documents(ROOT / "infrastructure/kubernetes/api-hpa.yaml")
    all_docs = namespace_docs + stack_docs + hpa_docs
    kinds = {doc.get("kind") for doc in all_docs}
    if "Namespace" not in kinds or "PersistentVolumeClaim" not in kinds:
        errors.append("Kubernetes manifest set must include Namespace and PersistentVolumeClaim")

    deployments = named_resources(all_docs, "Deployment")
    expected_deployments = {
        "aegisgrid-api", "aegisgrid-frontend", "aegisgrid-worker",
        "aegisgrid-outbox-dispatcher", "aegisgrid-postgres", "aegisgrid-rabbitmq",
    }
    missing_deployments = expected_deployments - set(deployments)
    if missing_deployments:
        errors.append("Kubernetes missing Deployments: " + ", ".join(sorted(missing_deployments)))

    services_k8s = named_resources(all_docs, "Service")
    for service_name, service in services_k8s.items():
        selector = service.get("spec", {}).get("selector", {})
        if not selector:
            errors.append(f"Kubernetes Service '{service_name}' has no selector")
            continue
        matching = [
            deployment for deployment in deployments.values()
            if all(deployment.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {}).get(key) == value
                   for key, value in selector.items())
        ]
        if not matching:
            errors.append(f"Kubernetes Service '{service_name}' selector matches no Deployment pod labels")

    for deployment_name in ("aegisgrid-api", "aegisgrid-frontend"):
        deployment = deployments.get(deployment_name)
        if not deployment:
            continue
        containers = deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        if not containers:
            errors.append(f"Kubernetes Deployment '{deployment_name}' has no containers")
            continue
        container = containers[0]
        if not container.get("image"):
            errors.append(f"Kubernetes Deployment '{deployment_name}' container has no image")
        for probe in ("readinessProbe", "livenessProbe"):
            if probe not in container:
                errors.append(f"Kubernetes Deployment '{deployment_name}' is missing {probe}")

    hpa = next((doc for doc in hpa_docs if doc.get("kind") == "HorizontalPodAutoscaler"), None)
    if not hpa or hpa.get("spec", {}).get("scaleTargetRef", {}).get("name") != "aegisgrid-api":
        errors.append("Optional HPA must target aegisgrid-api")

    # The Kustomize target is intentionally maintained as a separate local-cluster
    # profile. Check its declared resources and required workloads for drift.
    deploy_root = ROOT / "deploy/kubernetes"
    try:
        kustomization = load_documents(deploy_root / "kustomization.yaml")[0]
        declared = kustomization.get("resources", [])
        if not declared:
            errors.append("Local Kustomize profile must declare resources")
        local_docs = []
        for resource in declared:
            resource_path = (deploy_root / resource).resolve()
            if not resource_path.is_relative_to(deploy_root.resolve()):
                errors.append(f"Kustomize resource escapes deploy/kubernetes: {resource}")
                continue
            if not resource_path.is_file():
                errors.append(f"Kustomize resource missing: deploy/kubernetes/{resource}")
                continue
            local_docs.extend(load_documents(resource_path))

        local_kinds = {doc.get("kind") for doc in local_docs}
        if not {"Namespace", "ConfigMap", "StatefulSet", "Deployment", "Service"}.issubset(local_kinds):
            errors.append("Local Kustomize set must include Namespace, ConfigMap, StatefulSet, Deployment and Service")
        local_deployments = set(named_resources(local_docs, "Deployment"))
        local_expected = {
            "aegisgrid-api", "aegisgrid-frontend", "aegisgrid-worker",
            "aegisgrid-outbox-dispatcher", "rabbitmq",
        }
        if not local_expected.issubset(local_deployments):
            errors.append("Local Kustomize set is missing Deployments: " + ", ".join(sorted(local_expected - local_deployments)))
        local_statefulsets = set(named_resources(local_docs, "StatefulSet"))
        if "postgres" not in local_statefulsets:
            errors.append("Local Kustomize set must include the PostgreSQL StatefulSet")

        if "secretGenerator" in kustomization:
            literal_values = " ".join(kustomization.get("secretGenerator", [{}])[0].get("literals", []))
            if "dev_only" in literal_values or "aegisgrid_dev" in literal_values:
                warnings.append(
                    "Local Kustomize secretGenerator contains development-only credentials; "
                    "replace it with an external secret workflow before shared or production use."
                )
    except (OSError, ValueError, yaml.YAMLError, TypeError) as exc:
        errors.append(f"Local Kustomize manifest validation failed: {exc}")

    if warnings:
        print("\n".join("WARNING: " + warning for warning in warnings), file=sys.stderr)
    if errors:
        print("\n".join("ERROR: " + error for error in errors), file=sys.stderr)
        return 1
    print(
        "Static manifest validation passed: Compose topology, Kubernetes workloads, "
        "service selectors, probes, persistence and HPA target are structurally present."
    )
    print("Note: this check does not replace docker compose config/build, cluster deployment, or runtime smoke tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
