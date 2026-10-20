"""Small deterministic teaching models for common distributed-systems concepts."""
from __future__ import annotations
from typing import Any


def physical_clock_demo(offsets: list[int] | None = None) -> dict[str, Any]:
    offsets = offsets or [120, -35, 65, -10]
    coordinator = round(sum(offsets) / len(offsets))
    return {
        "concept": "Physical clock synchronization",
        "algorithm": "Berkeley-style averaging",
        "note": "Deterministic educational simulation; values are synthetic milliseconds, not host clock readings.",
        "nodes": [{"node": f"node-{i+1}", "offset_ms": offset, "adjustment_ms": coordinator-offset, "corrected_offset_ms": coordinator} for i, offset in enumerate(offsets)],
        "coordinator_offset_ms": coordinator,
        "steps": ["Coordinator polls node clock offsets", "Offsets are averaged", "Each node receives a relative adjustment", "Nodes converge on the simulated coordinator offset"],
    }


def lamport_demo() -> dict[str, Any]:
    events = [
        {"id":"A1","node":"node-1","event":"create incident","clock":1,"relation":"local"},
        {"id":"A2","node":"node-1","event":"publish dispatch request","clock":2,"relation":"send"},
        {"id":"B1","node":"node-2","event":"receive dispatch request","clock":3,"relation":"receive"},
        {"id":"B2","node":"node-2","event":"assign response unit","clock":4,"relation":"local"},
        {"id":"C1","node":"node-3","event":"refresh inventory","clock":1,"relation":"independent"},
    ]
    return {"concept":"Lamport logical clocks","note":"Synthetic trace. Clock order preserves happened-before but cannot establish causality for every pair.","events":events,"rules":["Increment local counter before each event","Send message with current counter","On receive: clock = max(local, received) + 1","If A happened-before B, then L(A) < L(B)"]}


def snapshot_demo() -> dict[str, Any]:
    return {"concept":"Global state snapshot","algorithm":"Chandy–Lamport-style teaching model","note":"Illustrative state only; no live distributed process is being snapshotted.","initiator":"node-1","process_states":[{"node":"node-1","state":"recorded","detail":"Initiator state captured"},{"node":"node-2","state":"recorded","detail":"Marker received; local state captured"},{"node":"node-3","state":"recorded","detail":"Marker received; local state captured"}],"channels":[{"from":"node-1","to":"node-2","state":"empty","messages":[]},{"from":"node-2","to":"node-3","state":"in-transit","messages":["dispatch.updated #104"]},{"from":"node-3","to":"node-1","state":"empty","messages":[]}],"steps":["Initiator records local state and sends markers","Each process records state on first marker","Messages received on channels before their marker are recorded as in-flight","Snapshot combines process states and channel states"]}


def vector_demo() -> dict[str, Any]:
    return {
        "concept":"Vector clocks",
        "note":"Synthetic event vectors; vector order is component-wise.",
        "events":[
            {"id":"A","node":"node-1","vector":[1,0,0]},
            {"id":"B","node":"node-1","vector":[2,0,0]},
            {"id":"C","node":"node-2","vector":[1,1,0]},
            {"id":"D","node":"node-3","vector":[0,0,1]},
        ],
        "comparisons":[
            {"a":"A","b":"B","relation":"A happened-before B"},
            {"a":"A","b":"C","relation":"A happened-before C in this model"},
            {"a":"B","b":"C","relation":"concurrent"},
            {"a":"C","b":"D","relation":"concurrent"},
        ],
        "rule":"V(a) < V(b) iff every component of V(a) is <= the matching component of V(b), and at least one is strictly smaller."
    }


def bully_demo(node_ids: list[int] | None = None, failed_id: int = 4) -> dict[str, Any]:
    node_ids = node_ids or [1,2,3,4,5]
    alive = [n for n in node_ids if n != failed_id]
    winner = max(alive) if alive else None
    return {"concept":"Leader election","algorithm":"Bully algorithm model","note":"Failure and election are simulated; no process is killed or elected in the runtime.","nodes":[{"id":n,"state":"failed" if n == failed_id else ("leader" if n == winner else "alive")} for n in node_ids],"election":[f"Node {min(alive) if alive else '?'} detects missing coordinator", "Election messages are sent to higher-ID nodes", f"Node {winner} wins because it is the highest available node" if winner else "No available node"],"leader":winner}


def mutex_demo() -> dict[str, Any]:
    requests = [{"node":"node-2","timestamp":7,"process_id":2},{"node":"node-1","timestamp":7,"process_id":1},{"node":"node-3","timestamp":9,"process_id":3}]
    ordered = sorted(requests, key=lambda r:(r["timestamp"],r["process_id"]))
    return {"concept":"Distributed mutual exclusion","algorithm":"Ricart–Agrawala request ordering","note":"Logical request ordering is simulated; this is not a lock protecting a shared production resource.","requests":requests,"grant_order":[r["node"] for r in ordered],"steps":["Requesting process multicasts a timestamped REQUEST","Peers compare requests by (timestamp, process ID)","Replies are deferred while a peer has priority","Critical section is entered after all required REPLY messages"]}


def failure_demo() -> dict[str, Any]:
    samples = [{"time":"12:00:00","node":"node-1","heartbeat":"received","missed":0},{"time":"12:00:01","node":"node-2","heartbeat":"received","missed":0},{"time":"12:00:02","node":"node-3","heartbeat":"missed","missed":1},{"time":"12:00:03","node":"node-3","heartbeat":"missed","missed":2},{"time":"12:00:04","node":"node-3","heartbeat":"suspected","missed":3}]
    return {"concept":"Heartbeat failure detection","note":"Synthetic heartbeat timeline; suspicion is not proof of failure.","threshold":3,"samples":samples,"interpretation":"At three consecutive misses, node-3 is marked suspected. Real systems trade detection speed against false positives during congestion or pauses."}


def stream_demo() -> dict[str, Any]:
    return {"concept":"Stream-oriented communication","transport":"WebSocket","note":"The frontend uses a periodic refresh fallback; this trace explains a WebSocket lifecycle and is not a captured live socket session.","lifecycle":["HTTP Upgrade request","101 Switching Protocols","Bidirectional text frames","Ping/Pong keepalive","Close frame"],"sample_events":[{"type":"incident.created","sequence":101},{"type":"unit.assigned","sequence":102},{"type":"incident.updated","sequence":103}]}


def concepts() -> list[dict[str, str]]:
    return [
        {"id":"physical-clock","title":"Physical clock sync","algorithm":"Berkeley-style averaging","mode":"Simulation"},
        {"id":"lamport","title":"Lamport logical clocks","algorithm":"Happened-before ordering","mode":"Simulation"},
        {"id":"snapshot","title":"Global snapshot","algorithm":"Chandy–Lamport-style model","mode":"Simulation"},
        {"id":"vector","title":"Vector clocks","algorithm":"Causality & concurrency","mode":"Simulation"},
        {"id":"election","title":"Leader election","algorithm":"Bully algorithm","mode":"Simulation"},
        {"id":"mutex","title":"Mutual exclusion","algorithm":"Ricart–Agrawala model","mode":"Simulation"},
        {"id":"failure","title":"Failure detection","algorithm":"Heartbeat / suspicion threshold","mode":"Simulation"},
        {"id":"messaging","title":"Message-oriented communication","algorithm":"RabbitMQ durable queue","mode":"Runtime-backed"},
        {"id":"stream","title":"Stream communication","algorithm":"WebSocket lifecycle","mode":"Illustrative trace"},
        {"id":"infrastructure","title":"Container orchestration","algorithm":"Docker Compose / Kubernetes","mode":"Runtime-backed when observed"},
    ]
