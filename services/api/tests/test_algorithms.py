import asyncio

from app.main import (
    ClockConfigure, EventAction, beacon_pause, beacons_tick, clock_configure,
    clock_run, init_beacons, init_election, init_mutex, init_snapshot,
    mutex_release, mutex_request, run_bully_election, snapshot_start,
    snapshot_step, state, vector_compare,
)


def test_berkeley_average_with_all_nodes():
    clock_configure(ClockConfigure(offsets_ms=[200, -150, 500, -300, 100]))
    result = asyncio.run(clock_run())
    assert result["mean_offset_ms"] == 70


def test_berkeley_average_excludes_unavailable_node():
    clock_configure(ClockConfigure(offsets_ms=[200, -150, 500, -300, 100], available=[True, True, True, False, True]))
    result = asyncio.run(clock_run())
    assert result["mean_offset_ms"] == 162.5
    assert result["excluded"] == ["P4"]


def test_vector_comparison_detects_concurrency():
    result = vector_compare({"a": [1, 0, 2], "b": [0, 2, 1]})
    assert result["relation"] == "CONCURRENT"


def test_vector_comparison_detects_happens_before():
    result = vector_compare({"a": [1, 0, 1], "b": [1, 2, 1]})
    assert result["relation"] == "A_BEFORE_B"


def test_global_snapshot_processes_marker_queue_to_consistent_snapshot():
    state["global_snapshot"] = init_snapshot()
    result = asyncio.run(snapshot_start(EventAction(process_id="P1")))
    for _ in range(10):
        if not result["marker_queue"]:
            break
        result = asyncio.run(snapshot_step())
    assert result["snapshot_complete"] is True
    assert all(p["recorded"] for p in result["processes"].values())
    assert result["consistency"]["consistent"] is True


def test_bully_election_selects_highest_available_process():
    lab = init_election()
    lab["nodes"][4]["available"] = False
    result = run_bully_election(lab, "P2")
    assert result["coordinator"] == "P4"
    kinds = {event["kind"] for event in result["events"]}
    assert "ELECTION" in kinds
    assert "OK" in kinds
    assert "COORDINATOR" in kinds


def test_mutual_exclusion_hands_resource_to_waiter_on_release():
    state["mutual_exclusion"] = init_mutex()
    first = asyncio.run(mutex_request("P1"))
    assert first["owner"] == "P1"
    second = asyncio.run(mutex_request("P2"))
    assert second["owner"] == "P1"
    assert next(n for n in second["nodes"] if n["id"] == "P2")["state"] == "REQUESTING"
    released = asyncio.run(mutex_release("P1"))
    assert released["owner"] == "P2"
    assert released["safety_ok"] is True


def test_beacon_detector_moves_from_suspected_to_unavailable_after_ticks():
    state["beacons"] = init_beacons()
    asyncio.run(beacon_pause("P1"))
    result = None
    for _ in range(6):
        result = asyncio.run(beacons_tick())
    node = next(n for n in result["nodes"] if n["id"] == "P1")
    assert node["status"] == "UNAVAILABLE"
