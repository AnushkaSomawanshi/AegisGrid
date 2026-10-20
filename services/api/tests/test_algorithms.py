from app.main import ClockConfigure, clock_configure, clock_run, vector_compare, VectorAction, vector_event, state

def test_berkeley_average_with_all_nodes():
    clock_configure(ClockConfigure(offsets_ms=[200,-150,500,-300,100]))
    result = __import__("asyncio").run(clock_run())
    assert result["mean_offset_ms"] == 70

def test_berkeley_average_excludes_unavailable_node():
    clock_configure(ClockConfigure(offsets_ms=[200,-150,500,-300,100], available=[True,True,True,False,True]))
    result = __import__("asyncio").run(clock_run())
    assert result["mean_offset_ms"] == 162.5
    assert result["excluded"] == ["P4"]

def test_vector_comparison_detects_concurrency():
    result = vector_compare({"a":[1,0,2],"b":[0,2,1]})
    assert result["relation"] == "CONCURRENT"

def test_vector_comparison_detects_happens_before():
    result = vector_compare({"a":[1,0,1],"b":[1,2,1]})
    assert result["relation"] == "A_BEFORE_B"
