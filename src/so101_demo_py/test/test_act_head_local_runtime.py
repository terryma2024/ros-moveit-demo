"""Directed tests for the process-local stopped-demand runtime."""

import importlib.util


def test_local_runtime_is_a_real_component_api():
    spec = importlib.util.find_spec("so101_demo.adapters.act.head_local_runtime")
    assert spec is not None, "HeadLocalRuntime component module must exist"
    module = __import__("so101_demo.adapters.act.head_local_runtime", fromlist=["HeadLocalRuntime"])
    assert callable(getattr(module, "HeadLocalRuntime", None))


def test_runtime_exports_its_local_admission_and_stop_contract():
    spec = importlib.util.find_spec("so101_demo.adapters.act.head_local_runtime")
    assert spec is not None, "HeadLocalRuntime component module must exist"
    module = __import__("so101_demo.adapters.act.head_local_runtime", fromlist=["HeadLocalRuntime"])
    runtime = module.HeadLocalRuntime
    for name in ("dispatch_guard", "own_inventory", "fault", "stop", "close", "start"):
        assert callable(getattr(runtime, name, None)), name

