"""Directed tests for the shared-original local ROS observer."""

import importlib.util


def test_local_observer_is_a_real_component_api():
    spec = importlib.util.find_spec("so101_demo.adapters.act.head_local_observer")
    assert spec is not None, "HeadLocalObserver component module must exist"
    module = __import__("so101_demo.adapters.act.head_local_observer", fromlist=["HeadLocalObserver"])
    assert callable(getattr(module, "HeadLocalObserver", None))


def test_observer_exports_original_and_action_response_boundaries():
    spec = importlib.util.find_spec("so101_demo.adapters.act.head_local_observer")
    assert spec is not None, "HeadLocalObserver component module must exist"
    module = __import__("so101_demo.adapters.act.head_local_observer", fromlist=["HeadLocalObserver"])
    observer = module.HeadLocalObserver
    for name in ("observe_original", "request_results", "request_cancel_all", "close"):
        assert callable(getattr(observer, name, None)), name
