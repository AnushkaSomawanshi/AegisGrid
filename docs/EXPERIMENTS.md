# Experiments and Evidence

Each experiment should record run ID, scenario, parameters, code version, start/end time, outputs, pass/fail checks, event trace and caveats.

## Core tests
- Clock average and excluded participant.
- Lamport local/send/receive rules.
- Vector causal ordering and concurrency.
- Snapshot consistency and channel-state rules after full algorithm implementation.
- Election state machine across failures after complete protocol implementation.
- Mutual-exclusion safety under competing requests.
- Beacon timeout and recovery after timer-driven implementation.
- RabbitMQ publication and consumer idempotency.
- WebSocket connect/disconnect and streaming sequence handling.
- Compose health and end-to-end incident workflow.
- Kubernetes replica scaling, Pod replacement and request continuity.
- Scalability baseline versus multiple replicas.

## Interpretation
Report measured performance only. Label simulations. Distinguish Pod replacement from service availability, suspicion from confirmed failure, and timestamp order from causal order.
