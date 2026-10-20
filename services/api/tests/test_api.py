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
    assert client.post("/api/events/demo").status_code == 200
    response = client.get("/api/events")
    assert response.status_code == 200
    assert response.json()["count"] >= 1


def test_invalid_lab():
    assert client.get("/api/labs/not-a-lab").status_code == 404
