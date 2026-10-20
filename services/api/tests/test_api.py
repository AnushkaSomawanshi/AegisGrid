import os
os.environ["DATABASE_URL"] = "sqlite:///./test_aegisgrid.db"
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db

init_db()
client = TestClient(app)


def test_root_and_health():
    assert client.get("/").status_code == 200
    assert client.get("/health/live").json()["status"] == "alive"
    assert client.get("/health/ready").status_code == 200


def test_incident_create_list_update():
    response = client.post("/api/incidents", json={
        "title":"Test medical incident", "category":"Medical", "severity":"high",
        "location":"Zone Alpha", "description":"Automated test case"
    })
    assert response.status_code == 201
    incident_id = response.json()["incident"]["id"]
    assert client.get("/api/incidents").status_code == 200
    updated = client.patch(f"/api/incidents/{incident_id}", json={"status":"assigned"})
    assert updated.status_code == 200
    assert updated.json()["incident"]["status"] == "assigned"


def test_lab_endpoints():
    for lab in ["physical-clock","lamport","snapshot","vector","election","mutex","failure","messaging","stream","infrastructure"]:
        response = client.get(f"/api/labs/{lab}")
        assert response.status_code == 200, lab
        assert "concept" in response.json()


def test_event_ledger():
    emitted = client.post("/api/events/demo")
    assert emitted.status_code == 200
    response = client.get("/api/events")
    assert response.status_code == 200
    assert response.json()["count"] >= 1
    outbox = client.get("/api/outbox")
    assert outbox.status_code == 200
    assert any(item["event_record_id"] == emitted.json()["id"] for item in outbox.json()["items"])


def test_invalid_lab():
    assert client.get("/api/labs/not-a-lab").status_code == 404


def test_resource_inventory_and_reservation():
    seeded = client.post("/api/resources/demo-seed")
    assert seeded.status_code == 200
    available = next(r for r in seeded.json()["items"] if r["code"] == "MED-04")
    response = client.post("/api/reservations", json={
        "resource_id": available["id"], "requested_by": "test-dispatch"
    })
    assert response.status_code == 201
    assert response.json()["resource"]["status"] == "reserved"
    conflict = client.post("/api/reservations", json={
        "resource_id": available["id"], "requested_by": "second-dispatch"
    })
    assert conflict.status_code == 409
    reservation_id = response.json()["reservation"]["id"]
    released = client.post(f"/api/reservations/{reservation_id}/release")
    assert released.status_code == 200
    assert released.json()["reservation"]["status"] == "released"
    assert released.json()["resource"]["status"] == "available"


def test_stepwise_experiment_persists_trace_and_result():
    created = client.post("/api/experiments", json={
        "lab_id": "physical-clock", "scenario": "offset-baseline",
        "parameters": {"offsets": [-100, 0, 100]}
    })
    assert created.status_code == 201
    run = created.json()["run"]
    assert run["result"]["mean_offset_ms"] == 0
    first = client.post(f"/api/experiments/{run['id']}/step")
    assert first.status_code == 200
    assert first.json()["event"]["node"] == "node-1"
    assert first.json()["run"]["current_step"] == 1
    reset = client.post(f"/api/experiments/{run['id']}/reset")
    assert reset.json()["run"]["current_step"] == 0


def test_beacon_simulation_and_forensics():
    beacon = client.post("/api/beacons/simulate", json={
        "node_id": "node-test", "interval_ms": 500, "timeout_ms": 1000,
        "missed_beats": 3, "recover": True
    })
    assert beacon.status_code == 200
    assert beacon.json()["execution_mode"] == "simulation"
    assert beacon.json()["final_state"] == "healthy"
    incident = client.post("/api/incidents", json={
        "title": "Forensics test incident", "category": "Medical",
        "severity": "high", "location": "Zone test", "description": "trace test"
    })
    incident_id = incident.json()["incident"]["id"]
    report = client.get(f"/api/forensics/{incident_id}")
    assert report.status_code == 200
    assert report.json()["incident"]["id"] == incident_id
    assert len(report.json()["nodes"]) >= 1


def test_each_workbench_lab_creates_a_nonempty_trace():
    labs = ["physical-clock", "lamport", "snapshot", "vector", "election", "mutex", "beacon", "messaging", "stream", "scaling"]
    for lab_id in labs:
        response = client.post("/api/experiments", json={
            "lab_id": lab_id, "scenario": "acceptance-" + lab_id, "parameters": {}
        })
        assert response.status_code == 201, lab_id
        run = response.json()["run"]
        assert run["trace"], lab_id
        assert run["result"].get("execution_mode") in {"simulation", "workflow_template", "runbook"}, lab_id


def test_clock_lab_rejects_malformed_offsets():
    response = client.post("/api/experiments", json={
        "lab_id": "physical-clock", "scenario": "invalid", "parameters": {"offsets": []}
    })
    assert response.status_code == 422


def test_experiment_pause_resume_and_simulated_fault():
    created = client.post("/api/experiments", json={
        "lab_id": "lamport", "scenario": "pause-fault-resume", "parameters": {}
    }).json()["run"]
    run_id = created["id"]
    paused = client.post(f"/api/experiments/{run_id}/pause")
    assert paused.status_code == 200
    blocked = client.post(f"/api/experiments/{run_id}/step")
    assert blocked.status_code == 409
    resumed = client.post(f"/api/experiments/{run_id}/resume")
    assert resumed.status_code == 200
    injected = client.post(f"/api/experiments/{run_id}/inject-failure", json={
        "fault_type": "process-unavailable", "target": "P2"
    })
    assert injected.status_code == 200
    assert injected.json()["event"]["event"] == "fault.injected"
    assert injected.json()["run"]["result"]["injected_fault"]["execution_mode"] == "simulation"
