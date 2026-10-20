"""AegisGrid API gateway and concept lab endpoints."""
import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc
from .db import init_db, get_db, Incident, EventRecord, OutboxRecord
from .broker import publish_event
from . import labs
from .advanced import router as advanced_router

app = FastAPI(
    title="AegisGrid API",
    description="Distributed emergency-response coordination and educational distributed-systems labs.",
    version="1.0.0",
)
app.include_router(advanced_router)

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
    # Persist the event and its outbox envelope in the same SQL transaction.
    event = EventRecord(event_type=event_type, source=source, payload=json.dumps(payload, ensure_ascii=False))
    db.add(event)
    db.flush()
    correlation_id = str(payload.get("correlation_id") or payload.get("incident_id") or payload.get("id") or event.id)
    envelope = {**payload, "event_id": str(event.id), "correlation_id": correlation_id,
                "causation_id": payload.get("causation_id")}
    event.payload = json.dumps(envelope, ensure_ascii=False)
    outbox = OutboxRecord(event_record_id=event.id, event_id=str(event.id), event_type=event_type,
                          payload=json.dumps(envelope, ensure_ascii=False), status="pending")
    db.add(outbox)
    db.commit()
    db.refresh(event)
    db.refresh(outbox)
    # Fast-path publication reduces latency; a failed attempt remains in the outbox for retry.
    broker_result = publish_event(event_type, envelope, source)
    outbox.attempts += 1
    outbox.status = "published" if broker_result.get("delivery") == "published" else "pending"
    outbox.last_error = broker_result.get("detail", "") or ""
    if outbox.status == "published":
        outbox.published_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": event.id, "event_type": event.event_type, "source": source, "payload": payload,
            "created_at": event.created_at.isoformat(), "broker": broker_result.get("delivery", "not-configured"),
            "broker_detail": broker_result.get("detail"), "outbox_id": outbox.id,
            "outbox_status": outbox.status}


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
    try:
        db.query(Incident).limit(1).all()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database not ready: {str(exc)[:160]}")
    return {"status":"ready", "service":"api", "database":"reachable"}



@app.get("/api/deployment/status")
def deployment_status(db: Session = Depends(get_db)):
    """Return live dependency probes; never infer Docker container or Kubernetes pod state."""
    import socket
    checks = []
    try:
        db.query(Incident).limit(1).all()
        checks.append({"name":"PostgreSQL","kind":"database","status":"healthy","detail":"API successfully queried the configured database"})
    except Exception as exc:
        checks.append({"name":"PostgreSQL","kind":"database","status":"unavailable","detail":str(exc)[:160]})
    host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    try:
        with socket.create_connection((host, int(os.getenv("RABBITMQ_PORT", "5672"))), timeout=1.2):
            checks.append({"name":"RabbitMQ","kind":"broker","status":"reachable","detail":f"TCP connection to {host} succeeded; broker application health is not inferred from TCP alone"})
    except Exception as exc:
        checks.append({"name":"RabbitMQ","kind":"broker","status":"unavailable","detail":f"Cannot reach {host}: {str(exc)[:120]}"})
    role = os.getenv("AEGISGRID_ROLE", "api")
    return {
        "service":"AegisGrid API", "role":role, "status":"healthy" if checks[0]["status"] == "healthy" else "degraded",
        "deployment_target":os.getenv("AEGISGRID_DEPLOYMENT_TARGET", "compose-or-local"),
        "runtime_inventory":"not-connected",
        "runtime_inventory_note":"Container and pod counts are not available from this API process. Use the documented Docker/Kubernetes CLI or configure an explicit runtime adapter.",
        "checks":checks, "checked_at":datetime.now(timezone.utc).isoformat(),
        "architecture":[
            {"name":"Frontend","kind":"web","communication":"HTTP to API","declared_in_compose":True},
            {"name":"API","kind":"http-api","communication":"SQL to PostgreSQL; TCP/AMQP integration to RabbitMQ","declared_in_compose":True},
            {"name":"Worker","kind":"background-worker","communication":"Consumes broker work and persists results","declared_in_compose":True},
            {"name":"Outbox dispatcher","kind":"background-worker","communication":"Polls transactional outbox and publishes events","declared_in_compose":True},
            {"name":"PostgreSQL","kind":"database","communication":"SQL","declared_in_compose":True},
            {"name":"RabbitMQ","kind":"message-broker","communication":"AMQP","declared_in_compose":True}
        ]
    }


@app.post("/api/deployment/verify-request", status_code=201)
def deployment_verify_request(db: Session = Depends(get_db)):
    """Exercise the real API-to-database path using a uniquely labelled demo incident."""
    marker = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    item = Incident(title=f"Deployment verification {marker}", category="System", severity="low",
                    location="Local deployment lab", description="Generated by Deployment Studio to verify frontend -> API -> database connectivity.")
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"verified":True,"path":["Deployment Studio frontend","AegisGrid API","PostgreSQL"],"incident":{
        "id":item.id,"title":item.title,"status":item.status,"created_at":item.created_at.isoformat()},
        "note":"This verifies the live API/database path. Worker and broker processing must be checked separately in runtime logs."}

@app.get("/api/overview")
def overview(db: Session = Depends(get_db)):
    all_incidents = db.query(Incident).all()
    open_count = sum(i.status != "resolved" for i in all_incidents)
    critical = sum(i.severity == "critical" and i.status != "resolved" for i in all_incidents)
    recent_events = db.query(EventRecord).order_by(desc(EventRecord.id)).limit(8).all()
    broker_configured = bool(os.getenv("RABBITMQ_HOST"))
    return {
        "service":"AegisGrid Command Centre",
        "as_of":datetime.now(timezone.utc).isoformat(),
        "metrics":{"active_incidents":open_count,"critical_incidents":critical,"total_incidents":len(all_incidents),
                   "events_recorded":db.query(EventRecord).count()},
        "services":[{"name":"API gateway","state":"up","detail":"FastAPI endpoint responding","kind":"runtime"},
                    {"name":"PostgreSQL","state":"up","detail":"Reachable through readiness dependency","kind":"runtime"},
                    {"name":"RabbitMQ","state":"configured" if broker_configured else "not-configured",
                     "detail":"Configured; publication outcome is reported per event" if broker_configured else "RABBITMQ_HOST not configured","kind":"runtime"},
                    {"name":"Event worker","state":"configured" if broker_configured else "not-configured",
                     "detail":"Independent consumer; verify processing in worker logs and ledger" if broker_configured else "Worker/broker not configured","kind":"runtime"},
                    {"name":"Concept labs","state":"up","detail":"Deterministic educational model endpoints","kind":"application"}],
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



@app.get("/api/outbox")
def list_outbox(limit: int = 50, db: Session = Depends(get_db)):
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be between 1 and 200")
    rows = db.query(OutboxRecord).order_by(desc(OutboxRecord.id)).limit(limit).all()
    return {"items":[{"id":r.id,"event_record_id":r.event_record_id,"event_id":r.event_id,
        "event_type":r.event_type,"status":r.status,"attempts":r.attempts,"last_error":r.last_error,
        "created_at":r.created_at.isoformat(),"published_at":r.published_at.isoformat() if r.published_at else None}
        for r in rows],"count":len(rows)}

@app.post("/api/outbox/{outbox_id}/retry")
def retry_outbox(outbox_id: int, db: Session = Depends(get_db)):
    row = db.get(OutboxRecord, outbox_id)
    if row is None:
        raise HTTPException(404, "outbox record not found")
    if row.status == "published":
        return {"id":row.id,"status":row.status,"attempts":row.attempts,"detail":"already published"}
    try:
        payload = json.loads(row.payload)
    except json.JSONDecodeError:
        raise HTTPException(500, "outbox payload is invalid JSON")
    result = publish_event(row.event_type, payload, "outbox-retry")
    row.attempts += 1
    row.last_error = result.get("detail", "") or ""
    if result.get("delivery") == "published":
        row.status = "published"
        row.published_at = datetime.now(timezone.utc)
    else:
        row.status = "pending"
    db.commit()
    return {"id":row.id,"status":row.status,"attempts":row.attempts,"delivery":result.get("delivery"),
            "detail":row.last_error}

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



@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """Real WebSocket transport carrying explicitly synthetic, sequenced demo telemetry."""
    await websocket.accept()
    sequence = 0
    try:
        await websocket.send_json({"type":"connected","mode":"synthetic-demo","message":"Telemetry stream connected"})
        while True:
            frame = {"type":"telemetry","mode":"synthetic-demo","sequence":sequence,
                     "at":datetime.now(timezone.utc).isoformat(),
                     "load_pct":round(35 + ((sequence * 17) % 47), 1),
                     "queue_depth":(sequence * 7) % 23,
                     "node":"worker-demo-1"}
            await websocket.send_json(frame)
            sequence += 1
            try:
                command = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                if command == "close":
                    await websocket.close(code=1000)
                    return
                if command == "ping":
                    await websocket.send_json({"type":"pong","at":datetime.now(timezone.utc).isoformat()})
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        return

@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """A minimal live transport demo with a connection frame and timestamped pong responses."""
    await websocket.accept()
    try:
        await websocket.send_json({"type":"connected","message":"AegisGrid WebSocket connected","at":datetime.now(timezone.utc).isoformat()})
        while True:
            message = await websocket.receive_text()
            await websocket.send_json({"type":"pong","echo":message,"at":datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        return
