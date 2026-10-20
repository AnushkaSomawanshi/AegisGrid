#!/usr/bin/env python3
"""Small standard-library HTTP load probe that records actual API response timings.

Example:
  python scripts/http_load_probe.py --url http://localhost:8000/health/live --requests 300 --concurrency 20
It does not generate synthetic metrics; every sample comes from a real HTTP response attempt.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction))))
    return round(ordered[index], 3)


def request_once(url: str, timeout: float) -> dict:
    started = time.perf_counter()
    status = None
    error = None
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            status = response.status
            response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        error = str(exc)[:200]
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {"status": status, "latency_ms": round(elapsed_ms, 3), "error": error}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000/health/live")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    if args.requests < 1 or args.requests > 100000:
        parser.error("--requests must be between 1 and 100000")
    if args.concurrency < 1 or args.concurrency > 500:
        parser.error("--concurrency must be between 1 and 500")
    start_wall = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        samples = list(pool.map(lambda _: request_once(args.url, args.timeout), range(args.requests)))
    duration = time.perf_counter() - started
    latencies = [item["latency_ms"] for item in samples]
    successes = sum(1 for item in samples if item["status"] is not None and 200 <= item["status"] < 400)
    failures = len(samples) - successes
    report = {
        "measurement_type": "real_http_probe",
        "started_at_utc": start_wall,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_url": args.url,
        "requests_offered": args.requests,
        "concurrency": args.concurrency,
        "duration_seconds": round(duration, 3),
        "successful_responses": successes,
        "failed_responses": failures,
        "throughput_successful_responses_per_second": round(successes / duration, 3) if duration else None,
        "latency_ms": {
            "min": round(min(latencies), 3) if latencies else None,
            "mean": round(statistics.mean(latencies), 3) if latencies else None,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "max": round(max(latencies), 3) if latencies else None,
        },
        "status_counts": {str(code): sum(1 for item in samples if item["status"] == code) for code in sorted({item["status"] for item in samples if item["status"] is not None})},
        "sample_errors": [item["error"] for item in samples if item["error"]][:10],
        "limitations": ["Single-client HTTP probe; not a full capacity benchmark.", "Repeat at least three times and keep environment/workload fixed.", "No server CPU/memory or broker queue metrics are collected by this script."]
    }
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
