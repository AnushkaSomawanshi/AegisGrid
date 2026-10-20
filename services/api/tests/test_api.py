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


def test_telemetry_websocket_emits_sequenced_synthetic_frames():
    with client.websocket_connect("/ws/telemetry") as websocket:
        connected = websocket.receive_json()
        first = websocket.receive_json()
        second = websocket.receive_json()
        assert connected["type"] == "connected"
        assert connected["mode"] == "synthetic-demo"
        assert first["sequence"] == 0
        assert second["sequence"] == 1
        assert first["type"] == "telemetry"


def test_protocol_models_compute_results_from_parameters():
    lamport = client.post("/api/experiments", json={
        "lab_id": "lamport", "scenario": "receive-rule",
        "parameters": {"operations": [
            {"process":"P1","kind":"send","message_id":"m"},
            {"process":"P2","kind":"receive","message_id":"m","message_clock":1}
        ]}
    }).json()["run"]
    assert lamport["trace"][1]["clock_after"] == 2
    assert lamport["result"]["final_process_clocks"]["P2"] == 2

    election = client.post("/api/experiments", json={
        "lab_id": "election", "scenario": "coordinator-failure",
        "parameters": {"node_ids":[1,2,3,4,5],"failed_node":4}
    }).json()["run"]
    assert election["result"]["elected_coordinator"] == 5
    assert any(event.get("kind") == "COORDINATOR" and event.get("node") == 5 for event in election["trace"])

    mutex = client.post("/api/experiments", json={
        "lab_id": "mutex", "scenario": "tie-break",
        "parameters": {"requests":[
            {"process":"P2","timestamp":1,"process_id":2},
            {"process":"P1","timestamp":1,"process_id":1}
        ]}
    }).json()["run"]
    assert mutex["result"]["grant_order"] == ["P1", "P2"]
    assert mutex["result"]["max_simultaneous_owners"] == 1


def test_snapshot_model_records_markers_and_in_transit_messages():
    run = client.post("/api/experiments", json={
        "lab_id": "snapshot", "scenario": "three-process-snapshot",
        "parameters": {
            "processes": ["P1", "P2", "P3"], "initiator": "P1",
            "messages_in_transit": [{"from":"P2","to":"P3","message":"m7"}]
        }
    }).json()["run"]
    assert run["result"]["consistent_cut"] is True
    assert run["result"]["process_states_recorded"] == 3
    assert run["result"]["messages_in_transit_recorded"] == 1
    assert any(event["event"] == "marker.received" for event in run["trace"])


def test_outbox_dispatcher_module_is_importable_and_runs_a_poll_cycle():
    from app.outbox_dispatcher import dispatch_once
    result = dispatch_once()
    assert isinstance(result, int)


def test_berkeley_clock_trace_exposes_poll_aggregate_and_corrections():
    response = client.post("/api/experiments", json={
        "lab_id": "physical-clock", "scenario": "detailed-five-node-round",
        "parameters": {"offsets": [120, 40, -60, 200, 300],
                       "drift_rates_ms_per_s": [0, 0, 0, 0, 0],
                       "simulated_elapsed_s": 10, "message_delay_ms": 20}
    })
    assert response.status_code == 201
    run = response.json()["run"]
    result = run["result"]
    assert result["mean_offset_ms"] == 120
    assert result["participants"] == 5
    assert result["initial_spread_ms"] == 360
    assert result["final_spread_ms"] == 0
    assert {event["event"] for event in run["trace"]} >= {
        "clock.poll.sent", "clock.reading.received", "clock.average.computed",
        "clock.correction.sent", "clock.correction.applied", "clock.round.completed"
    }
    by_node = {node["node"]: node for node in result["nodes"]}
    assert by_node["N1"]["adjustment_ms"] == 80
    assert by_node["N2"]["adjustment_ms"] == 180
    assert all(node["corrected_offset_ms"] == 120 for node in result["nodes"])


def test_berkeley_clock_excludes_unreachable_node_and_applies_drift():
    response = client.post("/api/experiments", json={
        "lab_id": "physical-clock", "scenario": "drift-and-timeout",
        "parameters": {"offsets": [100, 0, 200], "drift_rates_ms_per_s": [1, 2, -1],
                       "simulated_elapsed_s": 10, "message_delay_ms": 50,
                       "unreachable_nodes": ["N2"]}
    })
    assert response.status_code == 201
    run = response.json()["run"]
    result = run["result"]
    assert result["mean_offset_ms"] == 65
    assert result["excluded_nodes"] == ["N2"]
    assert result["participants"] == 2
    assert result["nodes"][0]["offset_ms"] == 110
    assert result["nodes"][1]["offset_ms"] == 20
    assert result["nodes"][2]["status"] == "unreachable"
    assert result["nodes"][2]["corrected_offset_ms"] == 190
    timeout = next(event for event in run["trace"] if event["event"] == "clock.poll.timeout")
    assert timeout["node"] == "N2"


def test_berkeley_clock_rejects_invalid_drift_and_all_unreachable():
    invalid_drift = client.post("/api/experiments", json={
        "lab_id": "physical-clock", "scenario": "invalid-drift",
        "parameters": {"offsets": [0, 10], "drift_rates_ms_per_s": [0]}
    })
    assert invalid_drift.status_code == 422
    no_participants = client.post("/api/experiments", json={
        "lab_id": "physical-clock", "scenario": "all-offline",
        "parameters": {"offsets": [0, 10], "unreachable_nodes": ["C0", "N1"]}
    })
    assert no_participants.status_code == 422


def test_lamport_demo_derives_message_timestamp_and_causal_edges():
    response = client.post("/api/experiments", json={
        "lab_id": "lamport", "scenario": "detailed-incident-dispatch",
        "parameters": {"operations": [
            {"process":"P1","kind":"local","label":"create incident","event_id":"E1"},
            {"process":"P1","kind":"send","label":"send dispatch request","message_id":"M1","to":"P2","event_id":"E2"},
            {"process":"P2","kind":"receive","label":"receive dispatch request","message_id":"M1","from":"P1","event_id":"E3"},
            {"process":"P2","kind":"local","label":"assign unit","event_id":"E4"},
            {"process":"P3","kind":"local","label":"independent refresh","event_id":"E5"}
        ]}
    })
    assert response.status_code == 201
    run = response.json()["run"]
    trace = run["trace"]
    assert [(e["event_id"], e["clock_before"], e["clock_after"]) for e in trace] == [
        ("E1", 0, 1), ("E2", 1, 2), ("E3", 0, 3), ("E4", 3, 4), ("E5", 0, 1)
    ]
    assert trace[1]["message_clock"] == 2
    assert trace[2]["message_clock"] == 2
    assert trace[2]["calculation"] == "max(0, 2) + 1 = 3"
    assert trace[2]["causal_predecessors"] == ["E2"]
    assert trace[3]["causal_predecessors"] == ["E3"]
    assert trace[4]["causal_predecessors"] == []
    assert {"from":"E2","to":"E3","relation":"message"} in run["result"]["causal_edges"]


def test_lamport_receive_uses_max_rule_when_local_clock_is_ahead():
    response = client.post("/api/experiments", json={
        "lab_id": "lamport", "scenario": "local-clock-ahead",
        "parameters": {"operations": [
            {"process":"P2","kind":"local","label":"local 1"},
            {"process":"P2","kind":"local","label":"local 2"},
            {"process":"P2","kind":"local","label":"local 3"},
            {"process":"P1","kind":"send","message_id":"M1","to":"P2"},
            {"process":"P2","kind":"receive","message_id":"M1"}
        ]}
    })
    assert response.status_code == 201
    trace = response.json()["run"]["trace"]
    assert trace[-1]["clock_before"] == 3
    assert trace[-1]["message_clock"] == 1
    assert trace[-1]["clock_after"] == 4
    assert trace[-1]["calculation"] == "max(3, 1) + 1 = 4"


def test_lamport_rejects_unknown_duplicate_and_mismatched_messages():
    unknown = client.post("/api/experiments", json={
        "lab_id":"lamport","scenario":"bad-receive",
        "parameters":{"operations":[{"process":"P2","kind":"receive","message_id":"missing"}]}
    })
    assert unknown.status_code == 422
    duplicate = client.post("/api/experiments", json={
        "lab_id":"lamport","scenario":"duplicate-message",
        "parameters":{"operations":[
            {"process":"P1","kind":"send","message_id":"M1"},
            {"process":"P1","kind":"send","message_id":"M1"}
        ]}
    })
    assert duplicate.status_code == 422
    mismatch = client.post("/api/experiments", json={
        "lab_id":"lamport","scenario":"wrong-recipient",
        "parameters":{"operations":[
            {"process":"P1","kind":"send","message_id":"M1","to":"P3"},
            {"process":"P2","kind":"receive","message_id":"M1"}
        ]}
    })
    assert mismatch.status_code == 422


def test_lamport_default_scenario_has_detailed_event_audit():
    run = client.post("/api/experiments", json={
        "lab_id":"lamport","scenario":"default-detailed"
    }).json()["run"]
    assert [event["clock_after"] for event in run["trace"]] == [1, 2, 3, 4, 1]
    assert run["result"]["final_process_clocks"] == {"P1": 2, "P2": 4, "P3": 1}
    assert len(run["result"]["causal_edges"]) == 3


def test_snapshot_default_derives_in_transit_message_from_recording_window():
    response = client.post('/api/experiments', json={'lab_id':'snapshot','scenario':'in-transit'})
    assert response.status_code == 201
    run = response.json()['run']
    trace = run['trace']
    recorded = next(e for e in trace if e['event'] == 'channel.message_recorded')
    assert recorded['channel'] == 'P2->P3'
    assert recorded['message_id'] == 'M1'
    started = next(e['step'] for e in trace if e['event'] == 'channel.recording.started' and e['channel'] == 'P2->P3')
    closed = next(e['step'] for e in trace if e['event'] == 'channel.recording.closed' and e['channel'] == 'P2->P3')
    assert started < recorded['step'] < closed
    assert run['result']['consistent_cut'] is True


def test_snapshot_empty_and_multiple_message_presets():
    empty = client.post('/api/experiments', json={'lab_id':'snapshot','scenario':'empty'}).json()['run']
    assert empty['result']['captured_messages'] == []
    multiple = client.post('/api/experiments', json={'lab_id':'snapshot','scenario':'multiple'}).json()['run']
    assert [m['message_id'] for m in multiple['result']['captured_messages']] == ['M1', 'M2']
    assert all(c['status'] == 'closed' for c in multiple['result']['channel_states'])


def test_vector_clock_default_trace_calculates_all_vectors():
    response = client.post('/api/experiments', json={'lab_id':'vector','scenario':'basic-causality'})
    assert response.status_code == 201
    run = response.json()['run']
    assert [event['vector_after'] for event in run['trace']] == [
        [1,0,0], [2,0,0], [2,1,0], [2,2,0],
        [0,0,1], [2,3,0], [2,3,2], [3,0,0]
    ]
    receive = run['trace'][2]
    assert receive['message_vector'] == [2,0,0]
    assert receive['merge_vector'] == [2,0,0]
    assert receive['calculation'].endswith('[2, 1, 0]')
    assert run['result']['final_process_vectors'] == {'P1':[3,0,0],'P2':[2,3,0],'P3':[2,3,2]}


def test_vector_clock_identifies_concurrent_events():
    run = client.post('/api/experiments', json={'lab_id':'vector','scenario':'basic-causality'}).json()['run']
    pair = next(c for c in run['result']['event_comparisons'] if c['a']=='E4' and c['b']=='E5')
    assert pair['relation'] == 'concurrent'
    assert any({c['a'],c['b']} == {'E4','E5'} for c in run['result']['concurrent_pairs'])


def test_vector_clock_multi_hop_propagates_causal_history():
    run = client.post('/api/experiments', json={'lab_id':'vector','scenario':'multi-hop'}).json()['run']
    assert run['trace'][2]['vector_after'] == [2,1,0]
    assert run['trace'][4]['vector_after'] == [2,2,1]
    assert {'from':'E2','to':'E3','relation':'message'} in run['result']['causal_edges']
    assert {'from':'E4','to':'E5','relation':'message'} in run['result']['causal_edges']


def test_vector_clock_rejects_unknown_and_wrong_recipient_messages():
    unknown = client.post('/api/experiments', json={'lab_id':'vector','parameters':{'operations':[
        {'process':'P2','kind':'receive','message_id':'missing','event_id':'E1'}
    ]}})
    assert unknown.status_code == 422
    wrong = client.post('/api/experiments', json={'lab_id':'vector','parameters':{'operations':[
        {'process':'P1','kind':'send','message_id':'M1','to':'P2','event_id':'E1'},
        {'process':'P3','kind':'receive','message_id':'M1','event_id':'E2'}
    ]}})
    assert wrong.status_code == 422
