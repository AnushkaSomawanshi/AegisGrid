#!/usr/bin/env python3
"""Measure Kubernetes replacement-Pod readiness after a controlled deletion.

This intentionally only operates in namespace aegisgrid and requires --confirm.
It measures replacement readiness, not zero-downtime or user-visible recovery.
"""
from __future__ import annotations
import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def kubectl(*args: str) -> dict:
    result = subprocess.run(["kubectl", *args], check=True, capture_output=True, text=True)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def ready_pods(selector: str, namespace: str) -> list[dict]:
    data = kubectl("get", "pods", "-n", namespace, "-l", selector, "-o", "json")
    ready = []
    for pod in data.get("items", []):
        conditions = pod.get("status", {}).get("conditions", [])
        if any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions):
            ready.append({"name": pod["metadata"]["name"], "uid": pod["metadata"]["uid"],
                          "ready_at": pod.get("status", {}).get("startTime")})
    return ready


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="aegisgrid")
    parser.add_argument("--selector", default="app=aegisgrid-api")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--confirm", action="store_true", help="confirm deleting one matching Pod")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    if args.namespace != "aegisgrid":
        parser.error("safety guard: this script only operates in namespace aegisgrid")
    if not args.confirm:
        parser.error("refusing to delete a Pod without --confirm")
    if args.timeout < 10 or args.timeout > 1800:
        parser.error("--timeout must be between 10 and 1800 seconds")
    before = ready_pods(args.selector, args.namespace)
    if not before:
        parser.error("no Ready Pods found for selector " + args.selector)
    victim = before[0]["name"]
    before_names = {p["name"] for p in before}
    injected_at = datetime.now(timezone.utc)
    started = time.monotonic()
    subprocess.run(["kubectl", "delete", "pod", victim, "-n", args.namespace, "--wait=false"], check=True)
    replacement = None
    while time.monotonic() - started < args.timeout:
        candidates = ready_pods(args.selector, args.namespace)
        replacement = next((p for p in candidates if p["name"] not in before_names), None)
        if replacement:
            break
        time.sleep(args.poll_seconds)
    elapsed = time.monotonic() - started
    report = {
        "measurement_type": "kubernetes_replacement_readiness",
        "namespace": args.namespace,
        "selector": args.selector,
        "deleted_pod": victim,
        "ready_pods_before": before,
        "failure_injected_at_utc": injected_at.isoformat(),
        "replacement_ready": replacement is not None,
        "replacement_pod": replacement,
        "replacement_ready_elapsed_seconds": round(elapsed, 3) if replacement else None,
        "timed_out": replacement is None,
        "timeout_seconds": args.timeout,
        "limitations": ["Measures replacement Pod readiness only, not request-level downtime.",
                        "Use a disposable development namespace and repeat at least three trials.",
                        "A pre-existing Ready replica may continue serving traffic during replacement."]
    }
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    return 0 if replacement else 2


if __name__ == "__main__":
    raise SystemExit(main())
