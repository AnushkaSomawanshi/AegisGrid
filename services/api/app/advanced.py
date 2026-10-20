"""Report-aligned resource, experiment, beacon and incident-forensics APIs.

Protocol traces are explicit educational simulations. Resource/incident persistence and
experiment-run history are database-backed when the configured database is available.
"""
import json
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, update
from sqlalchemy.orm import Session
from .db import get_db, Resource, Reservation, Incident, EventRecord, ExperimentRun

router = APIRouter(prefix="/api", tags=["advanced demonstrations"])

def now() -> datetime:
    return datetime.now(timezone.utc)

def resource_dict(r: Resource) -> dict[str, Any]:
    return {"id": r.id, "code": r.code, "name": r.name, "kind": r.kind, "status": r.status,
            "location": r.location, "capacity": r.capacity, "latitude": r.latitude,
            "longitude": r.longitude, "created_at": r.created_at.isoformat()}

class ResourceCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=140)
    kind: str = Field(default="unit", max_length=40)
    location: str = Field(default="Control zone", max_length=180)
    capacity: int = Field(default=1, ge=1, le=10000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

class ReservationCreate(BaseModel):
    resource_id: int
    incident_id: int | None = None
    requested_by: str = Field(min_length=2, max_length=100)

class ExperimentCreate(BaseModel):
    lab_id: str = Field(pattern=r"^(physical-clock|lamport|snapshot|vector|election|mutex|beacon|messaging|stream|scaling)$")
    scenario: str = Field(default="default", max_length=120)
    parameters: dict[str, Any] = Field(default_factory=dict)


class FaultInjection(BaseModel):
    fault_type: str = Field(default="process-unavailable", pattern=r"^(process-unavailable|message-delay|heartbeat-loss)$")
    target: str = Field(default="node-2", min_length=1, max_length=80)

@router.post("/experiments/{run_id}/pause")
def pause_experiment(run_id: int, db: Session = Depends(get_db)):
    row = db.get(ExperimentRun, run_id)
    if row is None:
        raise HTTPException(404, "experiment run not found")
    if row.status == "completed":
        raise HTTPException(409, "completed run cannot be paused")
    row.status = "paused"
    row.updated_at = now()
    db.commit()
    db.refresh(row)
    return {"run":experiment_dict(row)}

@router.post("/experiments/{run_id}/resume")
def resume_experiment(run_id: int, db: Session = Depends(get_db)):
    row = db.get(ExperimentRun, run_id)
    if row is None:
        raise HTTPException(404, "experiment run not found")
    if row.status == "completed":
        raise HTTPException(409, "completed run cannot be resumed")
    row.status = "running" if row.current_step > 0 else "ready"
    row.updated_at = now()
    db.commit()
    db.refresh(row)
    return {"run":experiment_dict(row)}

@router.post("/experiments/{run_id}/inject-failure")
def inject_experiment_failure(run_id: int, body: FaultInjection, db: Session = Depends(get_db)):
    row = db.get(ExperimentRun, run_id)
    if row is None:
        raise HTTPException(404, "experiment run not found")
    if row.status == "completed":
        raise HTTPException(409, "completed run cannot accept another injected event; reset it first")
    trace = json.loads(row.trace)
    event = {"step":row.current_step + 1,"event":"fault.injected","fault_type":body.fault_type,
             "target":body.target,"execution_mode":"simulation",
             "note":"Injected into the educational trace; no real process or infrastructure was stopped."}
    trace.insert(row.current_step, event)
    for index, item in enumerate(trace):
        item["step"] = index + 1
    row.trace = json.dumps(trace)
    result = json.loads(row.result)
    result["injected_fault"] = {"fault_type":body.fault_type,"target":body.target,"execution_mode":"simulation"}
    row.result = json.dumps(result)
    row.status = "running"
    row.updated_at = now()
    db.commit()
    db.refresh(row)
    return {"run":experiment_dict(row),"event":event}

class BeaconRequest(BaseModel):
    node_id: str = Field(default="node-2", min_length=1, max_length=80)
    interval_ms: int = Field(default=1000, ge=100, le=60000)
    timeout_ms: int = Field(default=3000, ge=100, le=180000)
    missed_beats: int = Field(default=0, ge=0, le=100)
    recover: bool = True

def _trace_for(lab_id: str, parameters: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build a deterministic trace for the named model; never label it as live telemetry."""
    if lab_id == "physical-clock":
        offsets = parameters.get("offsets", [-120, 30, 80, -10])
        if not isinstance(offsets, list) or not offsets or len(offsets) > 20 or any(not isinstance(v, (int, float)) for v in offsets):
            raise HTTPException(422, "offsets must be a non-empty list of at most 20 numbers")
        mean = round(sum(offsets) / len(offsets), 2)
        trace = [{"step": i+1, "event": "clock.sampled", "node": f"node-{i+1}", "offset_ms": value,
                  "adjustment_ms": round(mean-value, 2), "model_value_ms": round(value+mean-value, 2)}
                 for i, value in enumerate(offsets)]
        return trace, {"algorithm": "Berkeley-style average-offset model", "mean_offset_ms": mean,
                       "participants": len(offsets), "status": "calculated", "execution_mode": "simulation"}
    if lab_id == "lamport":
        operations = parameters.get("operations", [
            {"process":"P1","kind":"local","label":"create incident"},
            {"process":"P1","kind":"send","label":"send dispatch request","message_id":"m1"},
            {"process":"P2","kind":"receive","label":"receive dispatch request","message_id":"m1","message_clock":2},
            {"process":"P2","kind":"local","label":"assign response unit"},
            {"process":"P3","kind":"local","label":"independent inventory refresh"},
        ])
        if not isinstance(operations, list) or not operations or len(operations) > 100:
            raise HTTPException(422, "operations must be a list of 1 to 100 events")
        clocks: dict[str, int] = {}
        trace = []
        for index, operation in enumerate(operations):
            if not isinstance(operation, dict):
                raise HTTPException(422, "each operation must be an object")
            process = str(operation.get("process", "P1"))
            kind = str(operation.get("kind", "local"))
            if kind not in {"local", "send", "receive"}:
                raise HTTPException(422, "Lamport event kind must be local, send, or receive")
            before = clocks.get(process, 0)
            if kind == "receive":
                message_clock = int(operation.get("message_clock", 0))
                after = max(before, message_clock) + 1
            else:
                message_clock = None
                after = before + 1
            clocks[process] = after
            item = {"step":index+1,"process":process,"event":kind,"label":str(operation.get("label", kind)),
                    "clock_before":before,"clock_after":after}
            if message_clock is not None:
                item["message_clock"] = message_clock
            if kind == "send":
                item["message_id"] = str(operation.get("message_id", "m"+str(index+1)))
            trace.append(item)
        return trace, {"algorithm":"Lamport logical clock","final_process_clocks":clocks,
                       "receive_rule":"max(local_clock, message_clock) + 1","execution_mode":"simulation"}
    if lab_id == "snapshot":
        processes = parameters.get("processes", ["P1", "P2", "P3"])
        initiator = str(parameters.get("initiator", "P1"))
        messages = parameters.get("messages_in_transit", [{"from":"P2","to":"P3","message":"dispatch.updated #104"}])
        if not isinstance(processes, list) or len(processes) < 2 or len(processes) > 10 or len(set(processes)) != len(processes):
            raise HTTPException(422, "processes must contain 2 to 10 unique process IDs")
        processes = [str(p) for p in processes]
        if initiator not in processes:
            raise HTTPException(422, "initiator must be a member of processes")
        if not isinstance(messages, list) or len(messages) > 100:
            raise HTTPException(422, "messages_in_transit must be a list of at most 100 messages")
        trace = [{"step":1,"event":"process.state_recorded","process":initiator,"detail":"Initiator records its local state"}]
        for target in processes:
            if target != initiator:
                trace.append({"step":len(trace)+1,"event":"marker.sent","process":initiator,"to":target,"channel":initiator+"->"+target})
        for target in processes:
            if target == initiator:
                continue
            trace.append({"step":len(trace)+1,"event":"marker.received","process":target,"from":initiator,
                          "detail":"First marker records local state"})
            trace.append({"step":len(trace)+1,"event":"process.state_recorded","process":target,"detail":"Local state captured"})
            for destination in processes:
                if destination != target:
                    trace.append({"step":len(trace)+1,"event":"marker.sent","process":target,"to":destination,
                                  "channel":target+"->"+destination})
        captured = []
        for message in messages:
            if not isinstance(message, dict) or str(message.get("from")) not in processes or str(message.get("to")) not in processes:
                raise HTTPException(422, "each in-transit message must use process IDs from the scenario")
            captured.append({"from":str(message["from"]),"to":str(message["to"]),"message":str(message.get("message","sample message"))})
            trace.append({"step":len(trace)+1,"event":"channel.message_recorded","channel":str(message["from"])+"->"+str(message["to"]),
                          "message":str(message.get("message","sample message"))})
        for target in processes:
            if target != initiator:
                trace.append({"step":len(trace)+1,"event":"channel.recording.closed","process":target,
                              "detail":"Marker arrived on each recorded incoming channel"})
        return trace, {"algorithm":"Chandy–Lamport teaching model","initiator":initiator,"processes":processes,
                       "process_states_recorded":len(processes),"messages_in_transit_recorded":len(captured),
                       "captured_messages":captured,"consistent_cut":True,"execution_mode":"simulation"}
    if lab_id == "vector":
        trace = []
        p1 = [1, 0, 0]
        trace.append({"step":1,"event":"local","process":"P1","vector":p1.copy()})
        p1[0] += 1
        message_vector = p1.copy()
        trace.append({"step":2,"event":"send","process":"P1","message_id":"m1","vector":p1.copy()})
        p2 = [0, 0, 0]
        p2 = [max(p2[i], message_vector[i]) for i in range(3)]
        p2[1] += 1
        trace.append({"step":3,"event":"receive","process":"P2","message_vector":message_vector,"vector":p2.copy()})
        p3 = [0, 0, 1]
        trace.append({"step":4,"event":"local","process":"P3","vector":p3.copy()})
        def vector_relation(left: list[int], right: list[int]) -> str:
            left_le = all(a <= b for a, b in zip(left, right))
            right_le = all(b <= a for a, b in zip(left, right))
            if left_le and left != right:
                return "happened-before"
            if right_le and left != right:
                return "happened-after"
            return "equal" if left == right else "concurrent"
        return trace, {"algorithm":"Vector clocks","send_receive_relation":vector_relation(message_vector, p2),
                       "P2_vs_P3":vector_relation(p2, p3),"execution_mode":"simulation"}
    if lab_id == "election":
        node_ids = parameters.get("node_ids", [1, 2, 3, 4, 5])
        failed_raw = parameters.get("failed_node", 4)
        if not isinstance(node_ids, list) or not node_ids or len(node_ids) > 50 or any(not isinstance(n, int) for n in node_ids):
            raise HTTPException(422, "node_ids must be a non-empty list of up to 50 integer IDs")
        if len(set(node_ids)) != len(node_ids):
            raise HTTPException(422, "node_ids must be unique")
        failed_id = int(failed_raw) if str(failed_raw).isdigit() else failed_raw
        alive = sorted([n for n in node_ids if n != failed_id])
        trace = [{"step":1,"event":"heartbeat.missed","node":str(failed_id),"state":"suspected"}]
        lower = [n for n in alive if isinstance(n, int) and isinstance(failed_id, int) and n < failed_id]
        candidate = max(lower) if lower else (max(alive) if alive else None)
        winner = max(alive) if alive else None
        if candidate is not None:
            trace.append({"step":2,"event":"election.started","node":candidate,"detail":"candidate detects coordinator failure"})
            higher = [n for n in alive if isinstance(n, int) and n > candidate]
            for offset, node in enumerate(higher):
                trace.append({"step":len(trace)+1,"event":"election.message","from":candidate,"to":node,"kind":"ELECTION"})
                trace.append({"step":len(trace)+1,"event":"election.ok","from":node,"to":candidate,"kind":"OK"})
        if winner is not None:
            trace.append({"step":len(trace)+1,"event":"coordinator.announced","node":winner,"kind":"COORDINATOR"})
        return trace, {"algorithm":"Bully election model","failed_node":failed_id,"alive_nodes":alive,
                       "elected_coordinator":winner,"execution_mode":"simulation"}
    if lab_id == "mutex":
        requests = parameters.get("requests", [
            {"process":"P1","timestamp":1,"process_id":1},
            {"process":"P2","timestamp":1,"process_id":2},
            {"process":"P3","timestamp":3,"process_id":3},
        ])
        if not isinstance(requests, list) or not requests or len(requests) > 50:
            raise HTTPException(422, "requests must be a non-empty list of up to 50 requests")
        try:
            ordered = sorted(requests, key=lambda r:(int(r["timestamp"]), int(r["process_id"])))
        except (KeyError, TypeError, ValueError):
            raise HTTPException(422, "each request needs integer timestamp and process_id")
        trace = []
        for index, request in enumerate(requests):
            trace.append({"step":len(trace)+1,"event":"request.multicast","process":str(request.get("process", "P"+str(index+1))),
                          "timestamp":int(request["timestamp"]),"process_id":int(request["process_id"])})
        owner_history = []
        for request in ordered:
            process = str(request.get("process", "P"+str(request["process_id"])))
            trace.append({"step":len(trace)+1,"event":"permission.granted","process":process,
                          "ordering_key":[int(request["timestamp"]), int(request["process_id"])]})
            trace.append({"step":len(trace)+1,"event":"critical-section.enter","process":process,"owner":process})
            owner_history.append(process)
            trace.append({"step":len(trace)+1,"event":"critical-section.exit","process":process,"owner":None})
        return trace, {"algorithm":"Ricart–Agrawala request-order model","grant_order":[str(r.get("process", "P"+str(r["process_id"]))) for r in ordered],
                       "single_owner_invariant":True,"max_simultaneous_owners":1,
                       "note":"This trace serializes critical-section ownership; it is not a lock on an external production resource.",
                       "execution_mode":"simulation"}
    if lab_id == "beacon":
        misses = int(parameters.get("missed_beats", 3))
        threshold = int(parameters.get("threshold", 3))
        trace = [{"step":i+1,"event":"heartbeat.missed","node":"node-2","miss_count":i+1,
                  "state":"suspected" if i+1 < threshold else "unavailable"}
                 for i in range(min(misses, 100))]
        trace.append({"step":len(trace)+1,"event":"heartbeat.recovered","node":"node-2","state":"healthy"})
        return trace, {"algorithm":"Heartbeat suspicion model","threshold":threshold,"missed_beats":misses,
                       "final_state":"healthy","execution_mode":"simulation"}
    if lab_id == "messaging":
        trace = [
            {"step":1,"event":"api.accepted","detail":"API validates event envelope"},
            {"step":2,"event":"database.recorded","detail":"Event ledger write committed"},
            {"step":3,"event":"broker.published","detail":"RabbitMQ publication must be separately verified in runtime"},
            {"step":4,"event":"worker.processed","detail":"Worker ledger record must be separately verified"},
        ]
        return trace, {"algorithm":"Message-oriented communication","delivery_guarantee":"at-least-once is possible; consumer must be idempotent",
                       "execution_mode":"workflow_template","runtime_verified":False}
    if lab_id == "stream":
        trace = [
            {"step":1,"event":"websocket.connected","sequence":1},
            {"step":2,"event":"telemetry.frame","sequence":2},
            {"step":3,"event":"telemetry.frame","sequence":3},
            {"step":4,"event":"websocket.disconnected","sequence":4},
            {"step":5,"event":"websocket.reconnected","sequence":5},
        ]
        return trace, {"algorithm":"Stream lifecycle","sequence_gap_detection":"demonstration trace only",
                       "execution_mode":"simulation","runtime_verified":False}
    trace = [
        {"step":1,"event":"baseline.configured","replicas":1,"measurement":"not-run"},
        {"step":2,"event":"scaled.configured","replicas":3,"measurement":"not-run"},
        {"step":3,"event":"measurement.required","detail":"Run the documented load harness; no metrics are fabricated."},
    ]
    return trace, {"algorithm":"Scalability experiment template","baseline_replicas":1,"scaled_replicas":3,
                   "measurements_collected":False,"execution_mode":"runbook"}

@router.get("/resources")
def list_resources(db: Session = Depends(get_db)):
    rows = db.query(Resource).order_by(Resource.kind, Resource.code).all()
    return {"items":[resource_dict(r) for r in rows], "count":len(rows)}

@router.post("/resources", status_code=201)
def create_resource(body: ResourceCreate, db: Session = Depends(get_db)):
    if db.query(Resource).filter(Resource.code == body.code).first():
        raise HTTPException(409, "resource code already exists")
    row = Resource(**body.model_dump(), status="available")
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"resource":resource_dict(row)}

@router.post("/resources/demo-seed")
def seed_resources(db: Session = Depends(get_db)):
    samples = [
        {"code":"MED-04","name":"Mobile medical team 04","kind":"medical-unit","location":"Riverside Sector 07","capacity":1,"latitude":18.5204,"longitude":73.8567},
        {"code":"FIRE-02","name":"Fire response team 02","kind":"fire-unit","location":"Central access","capacity":1,"latitude":18.5310,"longitude":73.8440},
        {"code":"HOSP-01","name":"Central care facility","kind":"hospital","location":"Central district","capacity":24,"latitude":18.5167,"longitude":73.8500},
        {"code":"SUP-09","name":"Supply vehicle 09","kind":"supply","location":"East logistics yard","capacity":8,"latitude":18.5350,"longitude":73.8700},
    ]
    created = []
    for item in samples:
        row = db.query(Resource).filter(Resource.code == item["code"]).first()
        if row is None:
            row = Resource(**item, status="available")
            db.add(row)
            created.append(item["code"])
    db.commit()
    return {"created":created,"items":[resource_dict(r) for r in db.query(Resource).order_by(Resource.code).all()],
            "mode":"persisted-demo-seed"}

@router.post("/reservations", status_code=201)
def reserve_resource(body: ReservationCreate, db: Session = Depends(get_db)):
    resource = db.get(Resource, body.resource_id)
    if resource is None:
        raise HTTPException(404, "resource not found")
    if resource.status != "available":
        raise HTTPException(409, "resource is not available")
    if body.incident_id is not None and db.get(Incident, body.incident_id) is None:
        raise HTTPException(404, "incident not found")
    # Conditional UPDATE is atomic on PostgreSQL: only one concurrent caller can
    # transition a given resource from available to reserved.
    changed = db.execute(update(Resource).where(Resource.id == body.resource_id, Resource.status == "available").values(status="reserved"))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "resource was reserved by another request")
    row = Reservation(resource_id=resource.id, incident_id=body.incident_id,
                      requested_by=body.requested_by.strip(), status="reserved")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.refresh(resource)
    return {"reservation":{"id":row.id,"resource_id":row.resource_id,"incident_id":row.incident_id,
            "requested_by":row.requested_by,"status":row.status,"created_at":row.created_at.isoformat()},
            "resource":resource_dict(resource)}


@router.post("/reservations/{reservation_id}/release")
def release_reservation(reservation_id: int, db: Session = Depends(get_db)):
    row = db.get(Reservation, reservation_id)
    if row is None:
        raise HTTPException(404, "reservation not found")
    if row.status != "reserved":
        raise HTTPException(409, "reservation is not active")
    resource = db.get(Resource, row.resource_id)
    row.status = "released"
    if resource is not None:
        resource.status = "available"
    db.commit()
    db.refresh(row)
    return {"reservation":{"id":row.id,"resource_id":row.resource_id,"incident_id":row.incident_id,
            "requested_by":row.requested_by,"status":row.status,"created_at":row.created_at.isoformat()},
            "resource":resource_dict(resource) if resource else None}

@router.get("/reservations")
def list_reservations(db: Session = Depends(get_db)):
    rows = db.query(Reservation).order_by(desc(Reservation.id)).limit(200).all()
    return {"items":[{"id":r.id,"resource_id":r.resource_id,"incident_id":r.incident_id,
            "requested_by":r.requested_by,"status":r.status,"created_at":r.created_at.isoformat()} for r in rows],
            "count":len(rows)}

@router.post("/experiments", status_code=201)
def create_experiment(body: ExperimentCreate, db: Session = Depends(get_db)):
    trace, result = _trace_for(body.lab_id, body.parameters)
    row = ExperimentRun(lab_id=body.lab_id, scenario=body.scenario, parameters=json.dumps(body.parameters),
                        trace=json.dumps(trace), result=json.dumps(result), status="ready", current_step=0)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"run":experiment_dict(row)}

def experiment_dict(row: ExperimentRun) -> dict[str, Any]:
    return {"id":row.id,"lab_id":row.lab_id,"scenario":row.scenario,"parameters":json.loads(row.parameters),
            "trace":json.loads(row.trace),"result":json.loads(row.result),"status":row.status,
            "current_step":row.current_step,"created_at":row.created_at.isoformat(),"updated_at":row.updated_at.isoformat()}

@router.get("/experiments")
def list_experiments(limit: int = 50, db: Session = Depends(get_db)):
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be between 1 and 200")
    rows = db.query(ExperimentRun).order_by(desc(ExperimentRun.id)).limit(limit).all()
    return {"items":[experiment_dict(r) for r in rows],"count":len(rows)}

@router.get("/experiments/{run_id}")
def get_experiment(run_id: int, db: Session = Depends(get_db)):
    row = db.get(ExperimentRun, run_id)
    if row is None:
        raise HTTPException(404, "experiment run not found")
    return {"run":experiment_dict(row)}

@router.post("/experiments/{run_id}/step")
def step_experiment(run_id: int, db: Session = Depends(get_db)):
    row = db.get(ExperimentRun, run_id)
    if row is None:
        raise HTTPException(404, "experiment run not found")
    if row.status == "paused":
        raise HTTPException(409, "run is paused; resume it before stepping")
    trace = json.loads(row.trace)
    if row.current_step >= len(trace):
        row.status = "completed"
        row.updated_at = now()
        db.commit()
        return {"run":experiment_dict(row),"event":None}
    event = trace[row.current_step]
    row.current_step += 1
    row.status = "completed" if row.current_step >= len(trace) else "running"
    row.updated_at = now()
    db.commit()
    db.refresh(row)
    return {"run":experiment_dict(row),"event":event}

@router.post("/experiments/{run_id}/reset")
def reset_experiment(run_id: int, db: Session = Depends(get_db)):
    row = db.get(ExperimentRun, run_id)
    if row is None:
        raise HTTPException(404, "experiment run not found")
    row.current_step = 0
    row.status = "ready"
    row.updated_at = now()
    db.commit()
    db.refresh(row)
    return {"run":experiment_dict(row)}

@router.post("/beacons/simulate")
def simulate_beacons(body: BeaconRequest):
    state = "healthy"
    trace = [{"at_ms":0,"event":"heartbeat.received","node":body.node_id,"misses":0,"state":"healthy"}]
    for miss in range(1, body.missed_beats + 1):
        elapsed = miss * body.interval_ms
        state = "unavailable" if elapsed >= body.timeout_ms else "suspected"
        trace.append({"at_ms":elapsed,"event":"heartbeat.missed","node":body.node_id,"misses":miss,"state":state})
    if body.recover:
        trace.append({"at_ms":(body.missed_beats+1)*body.interval_ms,"event":"heartbeat.received","node":body.node_id,"misses":0,"state":"healthy"})
        state = "healthy"
    return {"node_id":body.node_id,"interval_ms":body.interval_ms,"timeout_ms":body.timeout_ms,
            "execution_mode":"simulation","final_state":state,"trace":trace}

@router.get("/forensics/{incident_id}")
def incident_forensics(incident_id: int, db: Session = Depends(get_db)):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    rows = db.query(EventRecord).order_by(EventRecord.id.asc()).all()
    matches = []
    for event in rows:
        try:
            payload = json.loads(event.payload)
        except json.JSONDecodeError:
            payload = {}
        if payload.get("id") == incident_id or payload.get("incident_id") == incident_id or payload.get("correlation_id") == str(incident_id) or payload.get("incident", {}).get("id") == incident_id:
            matches.append({"id":event.id,"event_type":event.event_type,"source":event.source,
                            "payload":payload,"created_at":event.created_at.isoformat()})
    nodes = [{"id":f"incident-{incident.id}","kind":"incident","label":incident.title}]
    nodes.extend({"id":f"event-{e['id']}","kind":"event","label":e["event_type"]} for e in matches)
    edges = [{"from":nodes[i]["id"],"to":nodes[i+1]["id"],"relation":"observed-after"} for i in range(len(nodes)-1)]
    return {"incident":{"id":incident.id,"title":incident.title,"status":incident.status},
            "nodes":nodes,"edges":edges,"events":matches,
            "note":"Chronological reconstruction from persisted matching payloads; this is not a proof of distributed causality until correlation/causation IDs are propagated."}
