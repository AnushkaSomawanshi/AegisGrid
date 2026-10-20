#!/usr/bin/env python3
"""Static structural validation for Compose and Kubernetes manifests."""
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_documents(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        docs = [doc for doc in yaml.safe_load_all(handle) if doc is not None]
    if not docs:
        raise ValueError(f"{path.relative_to(ROOT)} contains no YAML documents")
    return docs


def main() -> int:
    errors: list[str] = []
    compose = load_documents(ROOT / "docker-compose.yml")[0]
    services = compose.get("services", {})
    expected_services = {"frontend", "api", "worker", "outbox-dispatcher", "postgres", "rabbitmq"}
    missing = expected_services - set(services)
    if missing:
        errors.append("Compose missing services: " + ", ".join(sorted(missing)))
    if "aegisgrid-db" not in compose.get("volumes", {}):
        errors.append("Compose must define persistent volume aegisgrid-db")

    namespace_docs = load_documents(ROOT / "infrastructure/kubernetes/namespace.yaml")
    stack_docs = load_documents(ROOT / "infrastructure/kubernetes/app-stack.yaml")
    hpa_docs = load_documents(ROOT / "infrastructure/kubernetes/api-hpa.yaml")
    all_docs = namespace_docs + stack_docs + hpa_docs
    kinds = [doc.get("kind") for doc in all_docs]
    if "Namespace" not in kinds or "PersistentVolumeClaim" not in kinds:
        errors.append("Kubernetes manifest set must include Namespace and PersistentVolumeClaim")
    deployments = {doc.get("metadata", {}).get("name") for doc in all_docs if doc.get("kind") == "Deployment"}
    expected_deployments = {"aegisgrid-api", "aegisgrid-frontend", "aegisgrid-worker",
                            "aegisgrid-outbox-dispatcher", "aegisgrid-postgres", "aegisgrid-rabbitmq"}
    missing_deployments = expected_deployments - deployments
    if missing_deployments:
        errors.append("Kubernetes missing Deployments: " + ", ".join(sorted(missing_deployments)))
    hpa = next((doc for doc in hpa_docs if doc.get("kind") == "HorizontalPodAutoscaler"), None)
    if not hpa or hpa.get("spec", {}).get("scaleTargetRef", {}).get("name") != "aegisgrid-api":
        errors.append("Optional HPA must target aegisgrid-api")

    if errors:
        print("\n".join("ERROR: " + error for error in errors), file=sys.stderr)
        return 1
    print("Manifest validation passed: Compose services, Kubernetes workloads, PVC and optional API HPA are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
