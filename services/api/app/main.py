"""AegisGrid API gateway and concept lab endpoints."""
import json
import os
from datetime import datetime, timezone
from typing import Any
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc
from .db import init_db, get_db, Incident, EventRecord
from .broker import publish_event
from . import labs

app = FastAPI(
    title="AegisGrid API",
    description="Distributed emergency-response coordination and educational distributed-systems labs.",
    version="1.0.0",
)
origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup() -> None:
    init_db()


class IncidentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    category: str = Field(default="Medical", max_length=60)
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    location: str = Field(default="Control zone", max_length=180)
    description: str = Field(default="", max_length=3000)


class IncidentUpdate(BaseModel):
    status: str = Field(pattern="^(open|assigned|responding|resolved)$")


def record_event(db: Session, event_type: str, source: str, payload: dict[str, Any]) -> dict:
    event = EventRecord(event_type=event_type, source=source, payload=json.dumps(payload, ensure_ascii=False))
    db.add(event)
    db.commit()
    db.refresh(event)
    broker_result = publish_event(event_type, {"event_id": event.id, **payload}, source)
    return {"id": event.id, "event_type": event.event_type, "source": source, "payload": payload,
            "created_at": event.created_at.isoformat(), "broker": broker_result.get("delivery", "not-configured"),
            "broker_detail": broker_result.get("detail")}


def incident_dict(item: Incident) -> dict:
    return {"id": item.id, "title": item.title, "category": item.category, "severity": item.severity,
            "status": item.status, "location": item.location, "description": item.description,
            "created_at": item.created_at.isoformat()}


@app.get("/")
def root():
    return {"name":"AegisGrid API","version":"1.0.0","docs":"/docs","health":"/health/ready"}


@app.get("/health/live")
def liveness():
    return {"status":"alive", "service":"api"}


@app.get("/health/ready")
def readiness(db: Session = Depends(get_db)):
    # DB availability is part of readiness: traffic should not be routed to a pod without persistence.
    try:
        db.query(Incident).limit(1).all()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database not ready: {str(exc)[:160]}")
    return {"status":"ready", "service":"api", "database":"reachable"}


@app.get("/api/overview")
def overview(db: Session = Depends(get_db)):
    all_incidents = db.query(Incident).all()
    open_count = sum(i.status != "resolved" for i in all_incidents)
    critical = sum(i.severity == "critical" and i.status != "resolved" for i in all_incidents)
    recent_events = db.query(EventRecord).order_by(desc(EventRecord.id)).limit(8).all()
    return {
        "service":"AegisGrid Command Centre",
        "as_of":datetime.now(timezone.utc).isoformat(),
        "metrics":{"active_incidents":open_count,"critical_incidents":critical,"total_incidents":len(all_incidents),
                   "events_recorded":db.query(EventRecord).count()},
        "services":[{"name":"API gateway","state":"up","detail":"FastAPI endpoint responding","kind":"runtime"},
                    {"name":"PostgreSQL","state":"up","detail":"Reachable through readiness dependency","kind":"runtime"},
                    {"name":"RabbitMQ","state":"configured" if os.getenv("RABBITMQ_HOST") else "not-configured",
                     "detail":"Publish is checked per event; see event broker result","kind":"runtime"},
                    {"name":"Concept labs","state":"up","detail":"Deterministic simulation endpoints","kind":"application"}],
        "recent_events":[{"id":e.id,"event_type":e.event_type,"source":e.source,"payload":e.payload,"created_at":e.created_at.isoformat()} for e in recent_events]
    }


@app.get("/api/incidents")
def list_incidents(limit: int = 50, db: Session = Depends(get_db)):
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be between 1 and 200")
    rows = db.query(Incident).order_by(desc(Incident.id)).limit(limit).all()
    return {"items":[incident_dict(i) for i in rows], "count":len(rows)}


@app.post("/api/incidents", status_code=201)
def create_incident(body: IncidentCreate, db: Session = Depends(get_db)):
    item = Incident(title=body.title.strip(), category=body.category, severity=body.severity,
                    location=body.location.strip(), description=body.description, status="open")
    if not item.title:
        raise HTTPException(422, "title cannot be blank")
    db.add(item)
    db.commit()
    db.refresh(item)
    event = record_event(db, "incident.created", "api", incident_dict(item))
    return {"incident":incident_dict(item), "event":event}


@app.patch("/api/incidents/{incident_id}")
def update_incident(incident_id: int, body: IncidentUpdate, db: Session = Depends(get_db)):
    item = db.get(Incident, incident_id)
    if not item:
        raise HTTPException(404, "incident not found")
    item.status = body.status
    db.commit()
    db.refresh(item)
    event = record_event(db, "incident.status_changed", "api", incident_dict(item))
    return {"incident":incident_dict(item), "event":event}


@app.get("/api/events")
def events(limit: int = 50, db: Session = Depends(get_db)):
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be between 1 and 200")
    rows = db.query(EventRecord).order_by(desc(EventRecord.id)).limit(limit).all()
    items = []
    for e in rows:
        try:
            payload = json.loads(e.payload)
        except json.JSONDecodeError:
            payload = {"raw":e.payload}
        items.append({"id":e.id,"event_type":e.event_type,"source":e.source,"payload":payload,"created_at":e.created_at.isoformat()})
    return {"items":items,"count":len(items)}


@app.post("/api/events/demo")
def demo_event(db: Session = Depends(get_db)):
    return record_event(db, "dispatch.demo", "dashboard", {"message":"Demonstration event emitted from the command centre","sequence":db.query(EventRecord).count()+1})


@app.get("/api/concepts")
def concepts():
    return {"items":labs.concepts()}


@app.get("/api/labs/{lab_id}")
def get_lab(lab_id: str):
    handlers = {
        "physical-clock":labs.physical_clock_demo,
        "lamport":labs.lamport_demo,
        "snapshot":labs.snapshot_demo,
        "vector":labs.vector_demo,
        "election":labs.bully_demo,
        "mutex":labs.mutex_demo,
        "failure":labs.failure_demo,
        "stream":labs.stream_demo,
    }
    if lab_id == "messaging":
        return {"concept":"Message-oriented communication","technology":"RabbitMQ","note":"Runtime-backed publish test; emit a demo event to inspect publisher status in event ledger.","flow":["API validates command","API records event in PostgreSQL","API publishes durable message to aegisgrid.events","Independent worker consumes and records processing acknowledgement"],"runtime_configured":bool(os.getenv("RABBITMQ_HOST"))}
    if lab_id == "infrastructure":
        return {"concept":"Container orchestration","note":"This endpoint does not claim cluster state. Inspect Compose or Kubernetes directly for runtime-backed metrics.","docker_commands":["docker compose ps","docker compose logs --tail=100 api","docker compose up -d --scale worker=3"],"kubernetes_commands":["kubectl get deployments,pods,services -n aegisgrid","kubectl scale deployment/aegisgrid-api --replicas=3 -n aegisgrid","kubectl rollout status deployment/aegisgrid-api -n aegisgrid"]}
    handler = handlers.get(lab_id)
    if not handler:
        raise HTTPException(404, "unknown lab; see GET /api/concepts")
    return handler()


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """A small live transport demo. Clients receive a connection notice and timestamped heartbeats."""
    await websocket.accept()
    try:
        await websocket.send_json({"type":"connected","message":"AegisGrid WebSocket connected","at":datetime.now(timezone.utc).isoformat()})
        while True:
            # Respond to client text; client can send ping to receive pong. No false claim of DB tailing.
            message = await websocket.receive_text()
            await websocket.send_json({"type":"pong","echo":message,"at":datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        return
