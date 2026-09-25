"""A child SEARCH boundary owns reset, scene service and broker stop."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.adapters.act.task8_search_boundary import (
    Task8SearchBoundary, Task8SearchBoundaryError,
)
from so101_demo.core.task_geometry import load_task_geometry


def _geometry():
    return load_task_geometry(Path(__file__).parents[1] / "assets/common/geometry-manifest.yaml")


def _request():
    return {"session_id": "session-1", "attempt_id": "attempt-1", "scenario_id": "case-1",
            "deadline_ns": 9999999999999999999}


class _Node:
    def __init__(self):
        self.destroyed = False

    def destroy_node(self):
        self.destroyed = True


class _Broker:
    def __init__(self, *, stops=True):
        self.calls = []
        self.ownership = SimpleNamespace(state="RUNNING")
        self.driver = SimpleNamespace(stopped=lambda: stops)

    def stop_attempt(self, reason):
        self.calls.append(("stop", reason))

    def tick(self):
        self.calls.append(("tick",))
        if self.driver.stopped():
            self.ownership.state = "IDLE"


class _Reset:
    def __init__(self, broker):
        self.node = _Node()
        self.broker = broker
        self.sources = SimpleNamespace(session_id="session-1")
        self.receipt = None
        self.calls = []

    def begin(self, request):
        self.calls.append(("begin", dict(request)))
        self.receipt = SimpleNamespace(new_epoch=2)
        return {"session_id": request["session_id"], "attempt_id": request["attempt_id"],
                "reset_epoch": 2, "release_epoch": 0, "full_restart": False}

    def _guard(self, request):
        self.calls.append(("guard", dict(request)))


def _boundary(*, fail_segment=False, fail_scene=False, stops=True):
    broker = _Broker(stops=stops)
    reset = _Reset(broker)
    nodes = []
    adapters = []
    segments = []

    def node_factory():
        node = _Node()
        nodes.append(node)
        return node

    def scene_factory(node):
        assert node is nodes[-1] and node is not reset.node
        if fail_scene:
            raise RuntimeError("SCENE_CONSTRUCTION_FAILED")
        return SimpleNamespace(node=node)

    def adapter_factory(node, **kwargs):
        assert node is reset.node and kwargs["boundary"] is reset
        adapter = SimpleNamespace(operation_guard=lambda: reset._guard(_request()))
        adapters.append(adapter)
        return adapter

    def segment_factory(sources, adapter, scene, geometry, **kwargs):
        assert sources is reset.sources and adapter is adapters[-1]
        assert scene.node is nodes[-1] and geometry == _geometry()
        segment = SimpleNamespace(run=lambda request, *, reset_epoch: (
            (_ for _ in ()).throw(RuntimeError("SEARCH_FAILED")) if fail_segment else
            (dict(request), reset_epoch)
        ))
        segments.append(segment)
        return segment

    clock = [1.0]
    boundary = Task8SearchBoundary(
        reset, binding=object(), geometry=_geometry(), snapshot_root=Path("/owned/snapshot"),
        scene_node_factory=node_factory, scene_port_factory=scene_factory,
        adapter_factory=adapter_factory, segment_factory=segment_factory,
        max_source_wait_s=0.1, poll_interval_s=0.01, stop_timeout_s=0.05,
        monotonic=lambda: clock[0], sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    return boundary, broker, reset, nodes, adapters, segments


def test_one_begin_then_search_uses_separate_scene_node_and_returns_neutral_evidence():
    boundary, broker, reset, nodes, adapters, segments = _boundary()
    request = _request()
    assert boundary.begin(request)["full_restart"] is False
    assert boundary.search(request) == (request, 2)
    assert len(nodes) == len(adapters) == len(segments) == 1
    assert nodes[0].destroyed is True and broker.calls == []
    with pytest.raises(Task8SearchBoundaryError, match="TASK8_SEARCH_ALREADY_STARTED"):
        boundary.search(request)


def test_search_rejects_changed_attempt_before_any_scene_or_adapter_creation():
    boundary, broker, _, nodes, adapters, _ = _boundary()
    boundary.begin(_request())
    changed = dict(_request(), attempt_id="other")
    with pytest.raises(Task8SearchBoundaryError, match="TASK8_SEARCH_SCOPE_MISMATCH"):
        boundary.search(changed)
    assert not nodes and not adapters and not broker.calls


def test_invalid_reset_receipt_closes_broker_before_returning():
    boundary, broker, reset, _, _, _ = _boundary()
    reset.begin = lambda request: dict(
        session_id=request["session_id"], attempt_id=request["attempt_id"],
        reset_epoch=2, release_epoch=0, full_restart=True,
    )
    with pytest.raises(Task8SearchBoundaryError, match="TASK8_BEGIN_PROOF_INVALID"):
        boundary.begin(_request())
    assert broker.calls[0][0] == "stop" and broker.ownership.state == "IDLE"


@pytest.mark.parametrize("failure", ["scene", "segment"])
def test_search_failure_destroys_scene_node_and_stops_broker(failure):
    boundary, broker, _, nodes, _, _ = _boundary(
        fail_scene=failure == "scene", fail_segment=failure == "segment",
    )
    boundary.begin(_request())
    with pytest.raises(RuntimeError, match="SCENE_CONSTRUCTION_FAILED|SEARCH_FAILED"):
        boundary.search(_request())
    assert len(nodes) == 1 and nodes[0].destroyed is True
    assert broker.calls[0][0] == "stop" and broker.ownership.state == "IDLE"


def test_unconfirmed_broker_stop_overrides_search_failure():
    boundary, broker, _, nodes, _, _ = _boundary(fail_segment=True, stops=False)
    boundary.begin(_request())
    with pytest.raises(Task8SearchBoundaryError, match="TASK8_SEARCH_STOP_UNCONFIRMED"):
        boundary.search(_request())
    assert len(nodes) == 1 and nodes[0].destroyed is True
    assert broker.calls[0][0] == "stop"
