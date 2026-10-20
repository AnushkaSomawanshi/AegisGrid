from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import aio_pika
import psycopg
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5433")
POSTGRES_DB = os.getenv("POSTGRES_DB", "aegisgrid")
POSTGRES_USER = os.getenv("POSTGRES_USER", "aegisgrid")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "local-dev-only-change-me")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://aegisgrid:local-dev-rabbitmq-only@localhost:5672/")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

db_lock = asyncio.Lock()
broker_connection: aio_pika.RobustConnection | None = None
broker_channel: aio_pika.abc.AbstractRobustChannel | None = None
subscribers: set[WebSocket] = set()
state: dict[str, Any] = {
    "clock_sync": None, "lamport": None, "global_snapshot": None,
    "vector": None, "election": None, "mutual_exclusion": None,
    "beacons": None, "experiments": [], "events": []
}

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

def connect_db():
    url = DATABASE_URL or (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    return psycopg.connect(url, row_factory=dict_row, connect_timeout=3)

def init_db():
    with connect_db() as conn:
        conn.execute("""
          CREATE TABLE IF NOT EXISTS incidents (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
            severity TEXT NOT NULL, status TEXT NOT NULL, location TEXT NOT NULL,
            description TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
          )
        """)
        conn.execute("""
          CREATE TABLE IF NOT EXISTS event_ledger (
            id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, service TEXT NOT NULL,
            event_type TEXT NOT NULL, payload JSONB NOT NULL,
            happened_at TIMESTAMPTZ NOT NULL DEFAULT now()
          )
        """)
        conn.execute("""
          CREATE TABLE IF NOT EXISTS experiment_runs (
            id TEXT PRIMARY KEY, concept TEXT NOT NULL, scenario TEXT NOT NULL,
            result JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
          )
        """)
        conn.commit()

async def publish_event(event_type: str, payload: dict[str, Any], trace_id: str | None = None):
    event = {
        "id": str(uuid.uuid4()), "trace_id": trace_id or str(uuid.uuid4()),
        "event_type": event_type, "source": "aegisgrid-api",
        "occurred_at": utcnow(), "payload": payload
    }
    try:
        if broker_channel:
            exchange = await broker_channel.declare_exchange("aegisgrid.events", aio_pika.ExchangeType.TOPIC, durable=True)
            message = aio_pika.Message(
                body=json.dumps(event).encode(),
                content_type="application/json",
                message_id=event["id"],
                correlation_id=event["trace_id"],
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )
            await exchange.publish(message, routing_key=event_type.lower().replace(".", "_"))
            event["broker_status"] = "published"
        else:
            event["broker_status"] = "unavailable"
    except Exception as exc:
        event["broker_status"] = "error"
        event["broker_error"] = str(exc)
    try:
        with connect_db() as conn:
            conn.execute(
                "INSERT INTO event_ledger(id,trace_id,service,event_type,payload) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING",
                (event["id"], event["trace_id"], event["source"], event_type, json.dumps(event))
            )
            conn.commit()
    except Exception:
        pass
    await broadcast({"type": "event", "data": event})
    return event

async def broadcast(message: dict[str, Any]):
    dead = []
    for ws in list(subscribers):
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        subscribers.discard(ws)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global broker_connection, broker_channel
    for attempt in range(8):
        try:
            await asyncio.to_thread(init_db)
            break
        except Exception:
            if attempt == 7:
                raise
            await asyncio.sleep(1 + attempt)
    try:
        broker_connection = await aio_pika.connect_robust(RABBITMQ_URL, timeout=4)
        broker_channel = await broker_connection.channel()
    except Exception:
        broker_connection = None
        broker_channel = None
    yield
    if broker_connection:
        await broker_connection.close()

app = FastAPI(title="AegisGrid API", version="0.1.0", description="Emergency response APIs and educational distributed-systems labs.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

class IncidentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    category: str = Field(default="General", max_length=60)
    severity: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    location: str = Field(default="Unspecified", max_length=240)
    description: str = Field(default="", max_length=2000)

class EventAction(BaseModel):
    process_id: str = "P1"
    target_id: str | None = None
    message: str | None = None
    value: str | None = None

class ClockConfigure(BaseModel):
    offsets_ms: list[float] = Field(default_factory=lambda: [200,-150,500,-300,100], min_length=2, max_length=20)
    available: list[bool] | None = None

class VectorAction(BaseModel):
    process_id: str
    target_id: str | None = None
    event_type: str = Field(pattern="^(local|send|receive)$")
    message_id: str | None = None

class ExperimentRequest(BaseModel):
    scenario: str = "worked-example"
    parameters: dict[str, Any] = Field(default_factory=dict)

@app.get("/health/live")
def health_live():
    return {"status":"alive","service":"aegisgrid-api","time":utcnow()}

@app.get("/health/ready")
def health_ready():
    try:
        with connect_db() as conn:
            conn.execute("SELECT 1")
        db = True
    except Exception:
        db = False
    return {"status":"ready" if db else "degraded","database":db,"rabbitmq":broker_channel is not None}

@app.get("/api/overview")
def overview():
    try:
        with connect_db() as conn:
            rows = conn.execute("SELECT severity,status,count(*) AS count FROM incidents GROUP BY severity,status").fetchall()
            recent = conn.execute("SELECT * FROM incidents ORDER BY created_at DESC LIMIT 8").fetchall()
            event_count = conn.execute("SELECT count(*) AS count FROM event_ledger").fetchone()["count"]
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}")
    incidents = [dict(row) for row in recent]
    for row in incidents:
        for key in ("created_at","updated_at"):
            row[key] = row[key].isoformat() if row.get(key) else None
    return {
      "service":"AegisGrid","mode":"demo","incident_summary":rows,
      "recent_incidents":incidents,"event_count":event_count,
      "services":[
        {"name":"API Gateway","status":"healthy"},
        {"name":"PostgreSQL","status":"healthy"},
        {"name":"RabbitMQ","status":"healthy" if broker_channel else "degraded"}
      ]
    }

@app.get("/api/incidents")
def list_incidents():
    with connect_db() as conn:
        rows = conn.execute("SELECT * FROM incidents ORDER BY created_at DESC LIMIT 200").fetchall()
    out=[]
    for row in rows:
        item=dict(row)
        for key in ("created_at","updated_at"):
            item[key]=item[key].isoformat() if item.get(key) else None
        out.append(item)
    return out

@app.post("/api/incidents", status_code=201)
async def create_incident(body: IncidentCreate):
    inc_id = "INC-" + uuid.uuid4().hex[:8].upper()
    now = datetime.now(timezone.utc)
    with connect_db() as conn:
        row=conn.execute(
          """INSERT INTO incidents(id,title,category,severity,status,location,description,created_at,updated_at)
             VALUES(%s,%s,%s,%s,'OPEN',%s,%s,%s,%s) RETURNING *""",
          (inc_id,body.title,body.category,body.severity,body.location,body.description,now,now)
        ).fetchone()
        conn.commit()
    result=dict(row)
    result["created_at"]=result["created_at"].isoformat()
    result["updated_at"]=result["updated_at"].isoformat()
    event=await publish_event("Incident.Created", result, inc_id)
    await broadcast({"type":"incident.created","data":result})
    return {"incident":result,"event":event}

@app.patch("/api/incidents/{incident_id}/status")
async def update_incident_status(incident_id: str, body: dict[str,str]):
    status=body.get("status","")
    if status not in {"OPEN","ACKNOWLEDGED","ASSIGNED","IN_PROGRESS","RESOLVED"}:
        raise HTTPException(422,"Unsupported incident status")
    with connect_db() as conn:
        row=conn.execute("UPDATE incidents SET status=%s,updated_at=now() WHERE id=%s RETURNING *",(status,incident_id)).fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404,"Incident not found")
    result=dict(row)
    for key in ("created_at","updated_at"):
        result[key]=result[key].isoformat()
    await publish_event("Incident.StatusChanged",result,incident_id)
    return result

@app.get("/api/events")
def get_events(limit: int=100):
    limit=max(1,min(limit,500))
    with connect_db() as conn:
        rows=conn.execute("SELECT * FROM event_ledger ORDER BY happened_at DESC LIMIT %s",(limit,)).fetchall()
    out=[]
    for row in rows:
        item=dict(row)
        item["happened_at"]=item["happened_at"].isoformat()
        out.append(item)
    return out

@app.websocket("/ws/events")
async def event_stream(ws: WebSocket):
    await ws.accept()
    subscribers.add(ws)
    try:
        await ws.send_json({"type":"connection","data":{"status":"connected","time":utcnow()}})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        subscribers.discard(ws)

# ---------- Clock synchronization ----------
@app.post("/api/labs/clock-sync/configure")
def clock_configure(body: ClockConfigure):
    available=body.available or [True]*len(body.offsets_ms)
    if len(available)!=len(body.offsets_ms):
        raise HTTPException(422,"available must have one flag per clock")
    state["clock_sync"]={"nodes":[{"id":f"P{i+1}","offset_ms":offset,"available":available[i]} for i,offset in enumerate(body.offsets_ms)],"history":[]}
    return state["clock_sync"]

@app.get("/api/labs/clock-sync")
def clock_state():
    if state["clock_sync"] is None:
        clock_configure(ClockConfigure())
    return state["clock_sync"]

@app.post("/api/labs/clock-sync/run")
async def clock_run():
    current=state["clock_sync"]
    if current is None:
        clock_configure(ClockConfigure())
        current=state["clock_sync"]
    active=[n for n in current["nodes"] if n["available"]]
    if not active:
        raise HTTPException(409,"At least one clock must participate")
    mean=sum(n["offset_ms"] for n in active)/len(active)
    corrections=[{"process":n["id"],"old_offset_ms":n["offset_ms"],"target_offset_ms":mean,"correction_ms":mean-n["offset_ms"]} for n in active]
    result={"algorithm":"Berkeley-style average-offset model","participants":[n["id"] for n in active],"excluded":[n["id"] for n in current["nodes"] if not n["available"]],"mean_offset_ms":round(mean,4),"corrections":corrections,"note":"Educational simulation; operating-system clocks are not changed."}
    current["history"].append({"at":utcnow(),"result":result})
    await publish_event("Lab.ClockSync.Completed",result)
    return result

# ---------- Lamport clocks ----------
def init_lamport():
    return {"clocks":{"P1":0,"P2":0,"P3":0},"events":[],"messages":{}}
@app.get("/api/labs/lamport")
def lamport_state():
    if state["lamport"] is None: state["lamport"]=init_lamport()
    return state["lamport"]
@app.post("/api/labs/lamport/local")
async def lamport_local(body: EventAction):
    lab=state["lamport"] or init_lamport()
    pid=body.process_id
    lab["clocks"].setdefault(pid,0)
    lab["clocks"][pid]+=1
    event={"id":str(uuid.uuid4()),"process_id":pid,"kind":"local","clock":lab["clocks"][pid],"at":utcnow(),"description":body.message or "Local event"}
    lab["events"].append(event); state["lamport"]=lab
    await publish_event("Lab.Lamport.LocalEvent",event)
    return {"state":lab,"event":event}
@app.post("/api/labs/lamport/send")
async def lamport_send(body: EventAction):
    if not body.target_id: raise HTTPException(422,"target_id required")
    lab=state["lamport"] or init_lamport(); pid=body.process_id
    lab["clocks"].setdefault(pid,0); lab["clocks"][pid]+=1
    mid=str(uuid.uuid4())
    msg={"id":mid,"from":pid,"to":body.target_id,"clock":lab["clocks"][pid],"payload":body.message or "event","sent_at":utcnow()}
    lab["messages"][mid]=msg
    lab["events"].append({"id":str(uuid.uuid4()),"process_id":pid,"kind":"send","message_id":mid,"clock":lab["clocks"][pid],"at":utcnow()})
    state["lamport"]=lab
    await publish_event("Lab.Lamport.MessageSent",msg)
    return {"state":lab,"message":msg}
@app.post("/api/labs/lamport/receive/{message_id}")
async def lamport_receive(message_id: str, body: EventAction):
    lab=state["lamport"] or init_lamport()
    msg=lab["messages"].get(message_id)
    if not msg: raise HTTPException(404,"Message not found")
    pid=body.process_id; lab["clocks"].setdefault(pid,0)
    lab["clocks"][pid]=max(lab["clocks"][pid],msg["clock"])+1
    event={"id":str(uuid.uuid4()),"process_id":pid,"kind":"receive","message_id":message_id,"clock":lab["clocks"][pid],"at":utcnow()}
    lab["events"].append(event); state["lamport"]=lab
    await publish_event("Lab.Lamport.MessageReceived",event)
    return {"state":lab,"event":event}

# ---------- Vector clocks ----------
def init_vector():
    pids=["P1","P2","P3","P4","P5"]
    return {"processes":pids,"vectors":{p:[0]*len(pids) for p in pids},"events":[],"messages":{}}
@app.get("/api/labs/vector")
def vector_state():
    if state["vector"] is None: state["vector"]=init_vector()
    return state["vector"]
@app.post("/api/labs/vector/event")
async def vector_event(body: VectorAction):
    lab=state["vector"] or init_vector()
    if body.process_id not in lab["processes"]: raise HTTPException(422,"Unknown process; reset or configure the five-process model")
    pid=body.process_id; idx=lab["processes"].index(pid); vec=lab["vectors"][pid]
    if body.event_type=="local":
        vec[idx]+=1
        event={"id":str(uuid.uuid4()),"process_id":pid,"kind":"local","vector":vec.copy(),"at":utcnow()}
    elif body.event_type=="send":
        if not body.target_id or body.target_id not in lab["processes"]: raise HTTPException(422,"Valid target_id required")
        vec[idx]+=1; mid=str(uuid.uuid4())
        msg={"id":mid,"from":pid,"to":body.target_id,"vector":vec.copy(),"at":utcnow()}
        lab["messages"][mid]=msg
        event={"id":str(uuid.uuid4()),"process_id":pid,"kind":"send","message_id":mid,"vector":vec.copy(),"at":utcnow()}
    else:
        msg=lab["messages"].get(body.message_id or "")
        if not msg or msg["to"]!=pid: raise HTTPException(404,"Matching message for this receiver not found")
        vec[:]=[max(a,b) for a,b in zip(vec,msg["vector"])]
        vec[idx]+=1
        event={"id":str(uuid.uuid4()),"process_id":pid,"kind":"receive","message_id":msg["id"],"vector":vec.copy(),"at":utcnow()}
    lab["events"].append(event); state["vector"]=lab
    await publish_event("Lab.Vector.Event",event)
    return {"state":lab,"event":event}
@app.post("/api/labs/vector/compare")
def vector_compare(body: dict[str,list[int]]):
    a,b=body.get("a"),body.get("b")
    if not isinstance(a,list) or not isinstance(b,list) or len(a)!=len(b) or not a: raise HTTPException(422,"a and b must be equal-length vectors")
    a_le_b=all(x<=y for x,y in zip(a,b)); b_le_a=all(y<=x for x,y in zip(a,b))
    if a==b: relation="EQUAL"
    elif a_le_b: relation="A_BEFORE_B"
    elif b_le_a: relation="B_BEFORE_A"
    else: relation="CONCURRENT"
    return {"a":a,"b":b,"relation":relation,"explanation":{"A_BEFORE_B":"Every component of A is <= B and at least one is smaller.","B_BEFORE_A":"Every component of B is <= A and at least one is smaller.","CONCURRENT":"Neither vector is component-wise <= the other.","EQUAL":"The vectors are identical."}[relation]}

# ---------- Global snapshot teaching model ----------
@app.get("/api/labs/global-snapshot")
def snapshot_state():
    if state["global_snapshot"] is None:
        state["global_snapshot"]={"processes":{"P1":{"balance":10,"recorded":False},"P2":{"balance":10,"recorded":False},"P3":{"balance":10,"recorded":False}},"channels":[{"from":"P1","to":"P2","messages":[]},{"from":"P2","to":"P3","messages":[]},{"from":"P3","to":"P1","messages":[]}],"events":[],"status":"READY","note":"Educational snapshot model; full marker/channel recording will be expanded in the next implementation milestone."}
    return state["global_snapshot"]
@app.post("/api/labs/global-snapshot/start")
async def snapshot_start():
    lab=snapshot_state()
    for proc in lab["processes"].values(): proc["recorded"]=True
    lab["status"]="RECORDED"
    lab["events"].append({"id":str(uuid.uuid4()),"kind":"snapshot.recorded","at":utcnow()})
    await publish_event("Lab.GlobalSnapshot.Recorded",{"processes":lab["processes"],"channels":lab["channels"]})
    return lab

# ---------- Election lab (Bully algorithm model) ----------
def init_election():
    return {"nodes":[{"id":f"P{i}","priority":i,"available":True} for i in range(1,6)],"coordinator":"P5","events":[]}
@app.get("/api/labs/election")
def election_state():
    if state["election"] is None: state["election"]=init_election()
    return state["election"]
@app.post("/api/labs/election/fail/{process_id}")
async def election_fail(process_id: str):
    lab=state["election"] or init_election()
    node=next((n for n in lab["nodes"] if n["id"]==process_id),None)
    if not node: raise HTTPException(404,"Process not found")
    node["available"]=False
    lab["events"].append({"kind":"process.failed","process_id":process_id,"at":utcnow()})
    if lab["coordinator"]==process_id:
        candidates=[n for n in lab["nodes"] if n["available"] and n["priority"]>node["priority"]]
        if not candidates:
            candidates=[n for n in lab["nodes"] if n["available"]]
        if candidates:
            winner=max(candidates,key=lambda n:n["priority"])
            lab["coordinator"]=winner["id"]
            lab["events"].extend([
              {"kind":"election.started","initiator":next((n["id"] for n in lab["nodes"] if n["available"]),None),"at":utcnow()},
              {"kind":"coordinator.announced","process_id":winner["id"],"priority":winner["priority"],"at":utcnow()}
            ])
    state["election"]=lab
    await publish_event("Lab.Election.StateChanged",lab)
    return lab

# ---------- Mutual exclusion (Ricart–Agrawala-style teaching model) ----------
def init_mutex():
    return {"nodes":[{"id":f"P{i}","state":"RELEASED","request_ts":None,"permissions":[]} for i in range(1,6)],"owner":None,"events":[],"safety_ok":True}
@app.get("/api/labs/mutual-exclusion")
def mutex_state():
    if state["mutual_exclusion"] is None: state["mutual_exclusion"]=init_mutex()
    return state["mutual_exclusion"]
@app.post("/api/labs/mutual-exclusion/request/{process_id}")
async def mutex_request(process_id: str):
    lab=state["mutual_exclusion"] or init_mutex()
    node=next((n for n in lab["nodes"] if n["id"]==process_id),None)
    if not node: raise HTTPException(404,"Process not found")
    if lab["owner"] and lab["owner"]!=process_id:
        node["state"]="WAITING"
        lab["events"].append({"kind":"request.deferred","process_id":process_id,"owner":lab["owner"],"at":utcnow()})
    else:
        lab["owner"]=process_id; node["state"]="IN_CRITICAL_SECTION"
        node["permissions"]=[n["id"] for n in lab["nodes"] if n["id"]!=process_id]
        lab["events"].append({"kind":"resource.granted","process_id":process_id,"at":utcnow()})
    lab["safety_ok"]=sum(n["state"]=="IN_CRITICAL_SECTION" for n in lab["nodes"])<=1
    state["mutual_exclusion"]=lab
    await publish_event("Lab.MutualExclusion.Request",{"process_id":process_id,"owner":lab["owner"]})
    return lab
@app.post("/api/labs/mutual-exclusion/release/{process_id}")
async def mutex_release(process_id: str):
    lab=state["mutual_exclusion"] or init_mutex()
    if lab["owner"]!=process_id: raise HTTPException(409,"Only the current owner can release the resource")
    node=next(n for n in lab["nodes"] if n["id"]==process_id)
    node["state"]="RELEASED"; lab["owner"]=None
    waiting=next((n for n in lab["nodes"] if n["state"]=="WAITING"),None)
    if waiting:
        waiting["state"]="IN_CRITICAL_SECTION"; lab["owner"]=waiting["id"]
        lab["events"].append({"kind":"resource.granted","process_id":waiting["id"],"at":utcnow()})
    lab["events"].append({"kind":"resource.released","process_id":process_id,"at":utcnow()})
    lab["safety_ok"]=sum(n["state"]=="IN_CRITICAL_SECTION" for n in lab["nodes"])<=1
    state["mutual_exclusion"]=lab
    await publish_event("Lab.MutualExclusion.Release",{"process_id":process_id,"owner":lab["owner"]})
    return lab

# ---------- Beacon / timeout failure detector ----------
@app.get("/api/labs/beacons")
def beacons_state():
    if state["beacons"] is None:
        state["beacons"]={"interval_ms":1000,"timeout_ms":3000,"nodes":[{"id":f"P{i}","enabled":True,"last_beacon_at":utcnow(),"missed":0,"status":"HEALTHY"} for i in range(1,6)],"events":[]}
    return state["beacons"]
@app.post("/api/labs/beacons/{process_id}/pause")
async def beacon_pause(process_id: str):
    lab=beacons_state()
    node=next((n for n in lab["nodes"] if n["id"]==process_id),None)
    if not node: raise HTTPException(404,"Process not found")
    node["enabled"]=False; node["status"]="SUSPECTED"
    lab["events"].append({"kind":"beacon.paused","process_id":process_id,"at":utcnow()})
    await publish_event("Lab.Beacon.StateChanged",{"process_id":process_id,"status":node["status"]})
    return lab
@app.post("/api/labs/beacons/{process_id}/resume")
async def beacon_resume(process_id: str):
    lab=beacons_state()
    node=next((n for n in lab["nodes"] if n["id"]==process_id),None)
    if not node: raise HTTPException(404,"Process not found")
    node["enabled"]=True; node["status"]="HEALTHY"; node["missed"]=0; node["last_beacon_at"]=utcnow()
    lab["events"].append({"kind":"beacon.resumed","process_id":process_id,"at":utcnow()})
    await publish_event("Lab.Beacon.StateChanged",{"process_id":process_id,"status":node["status"]})
    return lab

@app.get("/api/labs")
def labs_index():
    return [
      {"id":"clock-sync","name":"Physical Clock Synchronization","status":"IMPLEMENTED","mode":"simulation","endpoint":"/api/labs/clock-sync"},
      {"id":"lamport","name":"Logical Clocks and Lamport Algorithm","status":"IMPLEMENTED","mode":"simulation","endpoint":"/api/labs/lamport"},
      {"id":"global-snapshot","name":"Global State Snapshot","status":"FOUNDATION","mode":"educational-model","endpoint":"/api/labs/global-snapshot"},
      {"id":"vector","name":"Vector Clocks and Causality","status":"IMPLEMENTED","mode":"simulation","endpoint":"/api/labs/vector"},
      {"id":"election","name":"Leader Election","status":"FOUNDATION","mode":"educational-model","endpoint":"/api/labs/election"},
      {"id":"mutual-exclusion","name":"Mutual Exclusion","status":"FOUNDATION","mode":"educational-model","endpoint":"/api/labs/mutual-exclusion"},
      {"id":"beacons","name":"Beacon Failure Detection","status":"FOUNDATION","mode":"educational-model","endpoint":"/api/labs/beacons"},
      {"id":"messaging","name":"Message-Oriented Communication","status":"BROKER-INTEGRATION","mode":"rabbitmq","endpoint":"/api/events"},
      {"id":"streaming","name":"Stream-Oriented Communication","status":"IMPLEMENTED","mode":"websocket","endpoint":"/ws/events"},
      {"id":"infrastructure","name":"Docker and Kubernetes","status":"DOCUMENTED","mode":"runtime-observation","endpoint":"/health/ready"}
    ]

@app.get("/api/experiments")
def list_experiments():
    return state["experiments"][-100:]
@app.post("/api/experiments")
async def save_experiment(body: ExperimentRequest):
    run={"id":str(uuid.uuid4()),"scenario":body.scenario,"parameters":body.parameters,"created_at":utcnow(),"status":"RECORDED"}
    state["experiments"].append(run)
    with connect_db() as conn:
        conn.execute("INSERT INTO experiment_runs(id,concept,scenario,result) VALUES(%s,%s,%s,%s)",(run["id"],"general",body.scenario,json.dumps(run)))
        conn.commit()
    return run
