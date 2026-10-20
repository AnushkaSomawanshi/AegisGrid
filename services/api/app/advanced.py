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
        offsets = parameters.get("offsets", [120, 40, -60, 200, 300])
        if (not isinstance(offsets, list) or not 2 <= len(offsets) <= 20
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or abs(v) > 86400000 for v in offsets)):
            raise HTTPException(422, "offsets must contain 2 to 20 finite numeric millisecond offsets within +/- 86400000")
        drift_rates = parameters.get("drift_rates_ms_per_s", [0] * len(offsets))
        if (not isinstance(drift_rates, list) or len(drift_rates) != len(offsets)
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or abs(v) > 1000 for v in drift_rates)):
            raise HTTPException(422, "drift_rates_ms_per_s must match offsets and contain rates within +/- 1000")
        elapsed_s = parameters.get("simulated_elapsed_s", 0)
        delay_ms = parameters.get("message_delay_ms", 0)
        if isinstance(elapsed_s, bool) or not isinstance(elapsed_s, (int, float)) or not 0 <= elapsed_s <= 3600:
            raise HTTPException(422, "simulated_elapsed_s must be between 0 and 3600 seconds")
        if isinstance(delay_ms, bool) or not isinstance(delay_ms, (int, float)) or not 0 <= delay_ms <= 60000:
            raise HTTPException(422, "message_delay_ms must be between 0 and 60000")
        excluded = parameters.get("unreachable_nodes", [])
        node_ids = ["C0"] + [f"N{i}" for i in range(1, len(offsets))]
        if not isinstance(excluded, list) or any(node not in node_ids for node in excluded):
            raise HTTPException(422, "unreachable_nodes must be a list of configured node IDs (C0, N1, ...)")
        excluded_set = set(excluded)
        if "C0" in excluded_set:
            raise HTTPException(422, "coordinator C0 must be online to initiate a Berkeley synchronization round")
        nodes = []
        for i, offset in enumerate(offsets):
            node_id = node_ids[i]
            drifted = round(float(offset) + float(drift_rates[i]) * float(elapsed_s), 2)
            nodes.append({"node": node_id, "initial_offset_ms": round(float(offset), 2),
                          "offset_ms": drifted, "drift_rate_ms_per_s": float(drift_rates[i]),
                          "reported_offset_ms": None, "adjustment_ms": 0.0,
                          "corrected_offset_ms": drifted, "status": "unreachable" if node_id in excluded_set else "waiting"})
        participants = [n for n in nodes if n["node"] not in excluded_set]
        if not participants:
            raise HTTPException(422, "at least one reachable clock is required for a synchronization round")
        trace = []
        def add(event: str, **fields: Any) -> None:
            trace.append({"step": len(trace) + 1, "event": event, **fields, "execution_mode": "simulation"})
        nodes[0]["reported_offset_ms"] = nodes[0]["offset_ms"]
        nodes[0]["status"] = "reported"
        # Keep the legacy node label for the existing workbench API contract while
        # exposing the explicit coordinator ID used by the detailed demonstration.
        add("clock.coordinator.sampled", node="node-1", node_id="C0",
            reported_offset_ms=nodes[0]["offset_ms"])
        for node in nodes:
            if node["node"] == "C0":
                continue
            if node["node"] in excluded_set:
                add("clock.poll.timeout", node=node["node"], timeout_ms=max(100, int(delay_ms) * 3),
                    decision="excluded-from-average", message_delay_ms=delay_ms)
            else:
                add("clock.poll.sent", coordinator="C0", node=node["node"], message_delay_ms=delay_ms)
                add("clock.reading.received", coordinator="C0", node=node["node"],
                    reported_offset_ms=node["offset_ms"], message_delay_ms=delay_ms)
                node["reported_offset_ms"] = node["offset_ms"]
                node["status"] = "reported"
        reported = [n for n in participants if n["reported_offset_ms"] is not None]
        if not reported:
            raise HTTPException(422, "no clock readings were received; synchronization round cannot complete")
        mean = round(sum(float(n["reported_offset_ms"]) for n in reported) / len(reported), 2)
        add("clock.average.computed", participants=[n["node"] for n in reported], excluded_nodes=sorted(excluded_set),
            reported_offsets_ms={n["node"]: n["reported_offset_ms"] for n in reported}, mean_offset_ms=mean,
            formula="sum(participating offsets) / participating node count")
        for node in nodes:
            if node["node"] in excluded_set or node["reported_offset_ms"] is None:
                continue
            adjustment = round(mean - float(node["reported_offset_ms"]), 2)
            node["adjustment_ms"] = adjustment
            add("clock.correction.sent", coordinator="C0", node=node["node"],
                adjustment_ms=adjustment, target_offset_ms=mean)
            node["corrected_offset_ms"] = mean
            node["status"] = "synchronized"
            add("clock.correction.applied", node=node["node"], adjustment_ms=adjustment,
                previous_offset_ms=node["offset_ms"], corrected_offset_ms=mean)
        initial_values = [float(n["offset_ms"]) for n in reported]
        final_values = [float(n["corrected_offset_ms"]) for n in reported]
        initial_spread = round(max(initial_values) - min(initial_values), 2)
        final_spread = round(max(final_values) - min(final_values), 2)
        add("clock.round.completed", participants=[n["node"] for n in reported],
            excluded_nodes=sorted(excluded_set), final_spread_ms=final_spread, status="completed")
        return trace, {"algorithm": "Berkeley-style average-offset model", "mean_offset_ms": mean,
                       "participants": len(reported), "participant_nodes": [n["node"] for n in reported],
                       "excluded_nodes": sorted(excluded_set), "nodes": nodes,
                       "initial_spread_ms": initial_spread, "final_spread_ms": final_spread,
                       "message_delay_ms": delay_ms, "simulated_elapsed_s": elapsed_s,
                       "status": "calculated", "execution_mode": "simulation",
                       "note": "Offsets and delays are synthetic. Delay is trace metadata, not a packet-level delay estimator."}
    if lab_id == "lamport":
        operations = parameters.get("operations", [
            {"process":"P1","kind":"local","label":"create incident","event_id":"E1"},
            {"process":"P1","kind":"send","label":"send dispatch request","message_id":"M1","to":"P2","event_id":"E2"},
            {"process":"P2","kind":"receive","label":"receive dispatch request","message_id":"M1","from":"P1","event_id":"E3"},
            {"process":"P2","kind":"local","label":"assign response unit","event_id":"E4"},
            {"process":"P3","kind":"local","label":"independent inventory refresh","event_id":"E5"},
        ])
        if not isinstance(operations, list) or not operations or len(operations) > 100:
            raise HTTPException(422, "operations must be a list of 1 to 100 events")

        clocks: dict[str, int] = {}
        last_event_by_process: dict[str, str] = {}
        sent_messages: dict[str, dict[str, Any]] = {}
        used_event_ids: set[str] = set()
        trace: list[dict[str, Any]] = []
        process_names: dict[str, str] = {}
        for index, operation in enumerate(operations):
            if not isinstance(operation, dict):
                raise HTTPException(422, "each operation must be an object")
            process = operation.get("process", "P1")
            kind = operation.get("kind", "local")
            if not isinstance(process, str) or not process.strip() or len(process) > 40:
                raise HTTPException(422, "process must be a non-empty string of at most 40 characters")
            if kind not in {"local", "send", "receive"}:
                raise HTTPException(422, "Lamport event kind must be local, send, or receive")
            process = process.strip()
            event_id = operation.get("event_id", f"E{index + 1}")
            if not isinstance(event_id, str) or not event_id.strip() or len(event_id) > 40 or event_id in used_event_ids:
                raise HTTPException(422, "event_id must be a unique non-empty string of at most 40 characters")
            event_id = event_id.strip()
            label = operation.get("label", kind.replace("_", " "))
            if not isinstance(label, str) or not label.strip() or len(label) > 160:
                raise HTTPException(422, "label must be a non-empty string of at most 160 characters")
            used_event_ids.add(event_id)
            process_names.setdefault(process, str(operation.get("process_name", process)))
            before = clocks.get(process, 0)
            previous_event = last_event_by_process.get(process)
            causal_predecessors = [previous_event] if previous_event else []
            item: dict[str, Any] = {
                "step": index + 1, "event_id": event_id, "process": process,
                "process_name": process_names[process], "event": kind, "label": label.strip(),
                "clock_before": before, "clock_after": before + 1,
                "causal_predecessors": causal_predecessors, "execution_mode": "simulation"
            }
            if kind == "receive":
                message_id = operation.get("message_id")
                if not isinstance(message_id, str) or not message_id.strip():
                    raise HTTPException(422, "receive events require a message_id that matches an earlier send")
                message_id = message_id.strip()
                sent = sent_messages.get(message_id)
                if sent is None:
                    raise HTTPException(422, f"receive event {event_id} references message {message_id!r} without an earlier send")
                expected_sender = operation.get("from")
                if expected_sender is not None and expected_sender != sent["sender"]:
                    raise HTTPException(422, f"receive event {event_id} sender does not match message {message_id!r}")
                expected_receiver = sent.get("receiver")
                if expected_receiver is not None and expected_receiver != process:
                    raise HTTPException(422, f"message {message_id!r} was sent to {expected_receiver!r}, not {process!r}")
                message_clock = sent["message_clock"]
                after = max(before, message_clock) + 1
                item.update({
                    "clock_before": before, "clock_after": after, "message_id": message_id,
                    "message_clock": message_clock, "sender": sent["sender"],
                    "calculation": f"max({before}, {message_clock}) + 1 = {after}",
                    "causal_predecessors": list(dict.fromkeys(causal_predecessors + [sent["event_id"]]))
                })
            elif kind == "send":
                message_id = operation.get("message_id", f"M{index + 1}")
                receiver = operation.get("to")
                if not isinstance(message_id, str) or not message_id.strip() or len(message_id) > 80:
                    raise HTTPException(422, "send events require a non-empty message_id of at most 80 characters")
                message_id = message_id.strip()
                if message_id in sent_messages:
                    raise HTTPException(422, f"message_id {message_id!r} is sent more than once; message IDs must be unique")
                if receiver is not None and (not isinstance(receiver, str) or not receiver.strip()):
                    raise HTTPException(422, "send event 'to' must be a non-empty process ID when supplied")
                after = before + 1
                item.update({
                    "clock_before": before, "clock_after": after, "message_id": message_id,
                    "message_clock": after, "receiver": receiver.strip() if isinstance(receiver, str) else None,
                    "calculation": f"{before} + 1 = {after}"
                })
                sent_messages[message_id] = {
                    "sender": process, "receiver": item["receiver"], "message_clock": after, "event_id": event_id
                }
            else:
                after = before + 1
                item["calculation"] = f"{before} + 1 = {after}"
            clocks[process] = after
            last_event_by_process[process] = event_id
            trace.append(item)

        # Include an explicit event-to-event relation list. A process-order edge and a
        # send-to-receive edge encode happens-before; the list order alone does not.
        edges = []
        for event in trace:
            for predecessor in event["causal_predecessors"]:
                relation = "message" if event.get("event") == "receive" and predecessor == next(
                    (sent["event_id"] for sent in sent_messages.values() if sent["event_id"] == predecessor), None
                ) and event.get("message_id") in sent_messages and sent_messages[event["message_id"]]["event_id"] == predecessor else "process-order"
                edges.append({"from": predecessor, "to": event["event_id"], "relation": relation})
        return trace, {
            "algorithm": "Lamport logical clock", "final_process_clocks": clocks,
            "processes": [{"process": key, "final_clock": value} for key, value in clocks.items()],
            "messages": [{"message_id": key, "sender": value["sender"], "receiver": value["receiver"],
                          "message_clock": value["message_clock"], "send_event_id": value["event_id"]}
                         for key, value in sent_messages.items()],
            "causal_edges": edges,
            "receive_rule": "max(local_clock, message_clock) + 1",
            "execution_mode": "simulation",
            "note": "Logical timestamps express causal ordering; they are not wall-clock time and do not order independent concurrent events."
        }
    if lab_id == "snapshot":
        processes = parameters.get("processes", ["P1", "P2", "P3"])
        initiator = parameters.get("initiator", "P1")
        scenario = str(parameters.get("scenario", ""))
        message_count = parameters.get("message_count", 1)
        if scenario == "empty":
            message_count = 0
        if scenario == "multiple":
            message_count = 2
        if not isinstance(processes, list) or not 2 <= len(processes) <= 10 or any(not isinstance(p, str) or not p.strip() or len(p) > 40 for p in processes) or len(set(processes)) != len(processes):
            raise HTTPException(422, "processes must contain 2 to 10 unique process IDs")
        processes = [p.strip() for p in processes]
        if initiator not in processes:
            raise HTTPException(422, "initiator must be a member of processes")
        if isinstance(message_count, bool) or not isinstance(message_count, int) or not 0 <= message_count <= 20:
            raise HTTPException(422, "message_count must be an integer between 0 and 20")
        if len(processes) < 3 and message_count:
            raise HTTPException(422, "in-transit message presets require at least three processes")
        channels = {f"{a}->{b}": {"channel": f"{a}->{b}", "from": a, "to": b,
                    "status": "not-recording", "messages": [], "started_at_step": None,
                    "closed_at_step": None} for a in processes for b in processes if a != b}
        process_states: dict[str, dict[str, Any]] = {}
        trace: list[dict[str, Any]] = []
        marker_sends: dict[tuple[str, str], int] = {}
        def add(event: str, **fields: Any) -> dict[str, Any]:
            item = {"step": len(trace) + 1, "event": event, "execution_mode": "simulation", **fields}
            trace.append(item)
            return item
        add("snapshot.started", process=initiator, detail=f"{initiator} initiates a new global snapshot.")
        process_states[initiator] = {"process": initiator, "state_label": "incident queue + dispatch cursor", "recorded_at_step": 1, "markers_received": 0}
        add("process.state_recorded", process=initiator, state_label=process_states[initiator]["state_label"],
            detail="Initiator records its local state before sending any marker.")
        for source in processes:
            if source != initiator:
                ch = channels[f"{source}->{initiator}"]
                ch["status"] = "recording"
                ch["started_at_step"] = len(trace) + 1
                add("channel.recording.started", process=initiator, channel=ch["channel"], sender=source,
                    receiver=initiator, detail="Initiator records each incoming channel after saving its local state.")
        for target in processes:
            if target == initiator:
                continue
            marker_sends[(initiator, target)] = len(trace) + 1
            add("marker.sent", process=initiator, sender=initiator, to=target, channel=f"{initiator}->{target}",
                message_id=f"MK-{initiator}-{target}", detail="Marker sent on outgoing channel.")
        # P3 sees the initiator marker first, opening P2 -> P3 recording before M1 is delivered.
        delivery_order = [p for p in processes if p != initiator]
        if len(processes) >= 3:
            delivery_order = [processes[2], processes[1]] + [p for p in processes if p not in {initiator, processes[2], processes[1]}]
        for target in delivery_order:
            source = initiator
            channel_name = f"{source}->{target}"
            add("marker.received", process=target, sender=source, channel=channel_name,
                message_id=f"MK-{source}-{target}", detail="First marker records this process's local state.")
            process_states[target] = {"process": target, "state_label": "resource queue + in-memory assignments" if target == "P2" else "inventory cache + pending updates",
                                      "recorded_at_step": len(trace), "markers_received": 1}
            add("process.state_recorded", process=target, state_label=process_states[target]["state_label"],
                detail="Local process state captured at the first marker.")
            for other in processes:
                if other == target:
                    continue
                ch = channels[f"{other}->{target}"]
                if other == source:
                    ch["status"] = "closed"
                    ch["started_at_step"] = len(trace) - 1
                    ch["closed_at_step"] = len(trace)
                else:
                    ch["status"] = "recording"
                    ch["started_at_step"] = len(trace) + 1
                    add("channel.recording.started", process=target, channel=ch["channel"], sender=other, receiver=target,
                        detail="Record application messages on this incoming channel until its marker arrives.")
            # On the P3 recording window, deliver app messages before the P2 marker.
            if target == processes[2] and message_count:
                for index in range(message_count):
                    message_id = f"M{index + 1}"
                    payload = "dispatch.updated #104" if index == 0 else f"inventory.delta #{104 + index}"
                    ch = channels[f"{processes[1]}->{target}"]
                    message = {"message_id": message_id, "from": processes[1], "to": target, "payload": payload,
                               "delivery_step": len(trace) + 1}
                    if ch["status"] == "recording":
                        ch["messages"].append(message)
                        add("channel.message_recorded", channel=ch["channel"], process=target, sender=processes[1],
                            message_id=message_id, message=payload, reason="Delivered after recording began and before the channel marker arrived.",
                            detail="Application message is included in this channel's recorded state.")
                    else:
                        add("application.message.delivered", channel=ch["channel"], process=target, sender=processes[1],
                            message_id=message_id, message=payload, reason="Channel was not recording at delivery.")
            # The newly captured process sends markers on every outgoing channel.
            for other in processes:
                if other == target:
                    continue
                marker_sends[(target, other)] = len(trace) + 1
                add("marker.sent", process=target, sender=target, to=other, channel=f"{target}->{other}",
                    message_id=f"MK-{target}-{other}", detail="First-marker rule: record local state, then send markers.")
        # Deliver all remaining markers; marker on a channel closes that channel's recording.
        for (source, target), sent_step in list(marker_sends.items()):
            if source == initiator and target in process_states and target != processes[2]:
                pass
            ch = channels[f"{source}->{target}"]
            if ch["status"] == "recording":
                add("marker.received", process=target, sender=source, channel=ch["channel"],
                    message_id=f"MK-{source}-{target}", detail="Marker ends recording for this directed channel.")
                ch["status"] = "closed"
                ch["closed_at_step"] = len(trace)
                add("channel.recording.closed", process=target, channel=ch["channel"],
                    captured_messages=len(ch["messages"]), detail="Channel state is complete; subsequent messages are not included.")
            elif ch["status"] == "not-recording":
                ch["status"] = "closed"
                ch["closed_at_step"] = len(trace) + 1
                add("marker.received", process=target, sender=source, channel=ch["channel"],
                    message_id=f"MK-{source}-{target}", detail="Marker arrived before recording was opened; channel state is empty.")
                add("channel.recording.closed", process=target, channel=ch["channel"], captured_messages=0,
                    detail="Channel state is empty for this snapshot.")
        captured = [message for ch in channels.values() for message in ch["messages"]]
        all_recorded = len(process_states) == len(processes)
        all_closed = all(ch["status"] == "closed" for ch in channels.values())
        consistent = all_recorded and all_closed
        add("snapshot.completed", process=initiator, process_count=len(process_states), channel_count=len(channels),
            captured_message_count=len(captured), consistent_cut=consistent,
            detail="Snapshot assembly checks every local process state and every directed channel state.")
        return trace, {"algorithm": "Chandy–Lamport-style global snapshot", "initiator": initiator, "processes": processes,
                       "process_states": process_states, "channel_states": list(channels.values()),
                       "process_states_recorded": len(process_states), "messages_in_transit_recorded": len(captured),
                       "captured_messages": captured, "consistent_cut": consistent,
                       "consistency_checks": {"consistent_cut": consistent, "all_processes_recorded": all_recorded,
                         "all_channels_closed": all_closed, "summary": "Every process state recorded and every directed channel recording closed." if consistent else "Snapshot incomplete."},
                       "execution_mode": "simulation",
                       "note": "Channel messages are derived from the deterministic send/delivery/marker schedule, not supplied as a pre-labelled final in-transit list."}
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
        try:
            misses = int(parameters.get("missed_beats", 3))
            threshold = int(parameters.get("threshold", 3))
        except (TypeError, ValueError):
            raise HTTPException(422, "missed_beats and threshold must be integers")
        if misses < 0 or misses > 100 or threshold < 1 or threshold > 100:
            raise HTTPException(422, "missed_beats must be 0..100 and threshold must be 1..100")
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
    parameters = {**body.parameters, "scenario": body.scenario} if body.lab_id == "snapshot" else body.parameters
    trace, result = _trace_for(body.lab_id, parameters)
    row = ExperimentRun(lab_id=body.lab_id, scenario=body.scenario, parameters=json.dumps(parameters),
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
