"""The Planning Scene capabilities the full nine-phase case needs, and what they refuse without.

`detach_moveit` must leave the cup detached in the PLANNING scene before the physical release, and the repository's own
rule is that the postcondition is read back rather than inferred. These tests use a stub scene, so what is substituted
is the MoveIt session; the read-back rule and the refusals are production code.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from so101_demo.adapters.act.pick_place_search_boundary import (  # noqa: E402
    PickPlaceSearchBoundary, PickPlaceSearchBoundaryError,
)
from so101_demo.adapters.act.pick_place_search_port import (  # noqa: E402
    PickPlaceSearchPhasePort, PickPlaceSearchPortError,
)

REQUEST = {"session_id": "session-1", "attempt_id": "attempt-1"}


class _Scene:
    def __init__(self, *, attached=True, detaches=True):
        self._attached = attached
        self._detaches = detaches
        self.detach_calls = 0

    def is_attached(self):
        return self._attached

    def detach(self):
        self.detach_calls += 1
        if self._detaches:
            self._attached = False


def _boundary(scene):
    return SimpleNamespace(planning_scene=scene) if scene is not None else SimpleNamespace()


def _call(boundary, name, request=REQUEST):
    return getattr(PickPlaceSearchBoundary, name)(boundary, request)


def _bound(scene):
    """A stub self carrying the REAL methods, because detach_moveit reads its postcondition through the other one."""

    from types import MethodType

    boundary = _boundary(scene)
    for name in ("planning_attached", "detach_moveit"):
        setattr(boundary, name, MethodType(getattr(PickPlaceSearchBoundary, name), boundary))
    return boundary


def test_planning_attached_reads_the_scene_and_detach_moveit_reads_it_back():
    scene = _Scene(attached=True)
    boundary = _bound(scene)
    assert _call(boundary, "planning_attached") is True
    assert _call(boundary, "detach_moveit") is True
    assert scene.detach_calls == 1
    assert _call(boundary, "planning_attached") is False, "detached means detached, read back"


def test_a_detach_that_does_not_detach_is_refused_by_name():
    """The failure that matters: the call returns, the scene still holds the cup."""

    boundary = _bound(_Scene(attached=True, detaches=False))
    with pytest.raises(PickPlaceSearchBoundaryError, match="planning scene still attached"):
        _call(boundary, "detach_moveit")


def test_each_missing_piece_refuses_by_name():
    with pytest.raises(PickPlaceSearchBoundaryError, match="planning_scene.is_attached"):
        _call(_boundary(None), "planning_attached")
    with pytest.raises(PickPlaceSearchBoundaryError, match="planning_scene.detach"):
        _call(_boundary(SimpleNamespace(is_attached=lambda: True)), "detach_moveit")


def test_a_scene_that_answers_with_a_non_boolean_is_refused():
    boundary = _boundary(SimpleNamespace(is_attached=lambda: "yes"))
    with pytest.raises(PickPlaceSearchBoundaryError, match="planning_scene.is_attached"):
        _call(boundary, "planning_attached")


def test_the_port_delegates_and_refuses_when_the_boundary_cannot():
    from types import MethodType

    def _port(boundary):
        stub = SimpleNamespace(boundary=boundary)
        for name in ("_boundary_capability", "detach_moveit", "planning_attached"):
            setattr(stub, name, MethodType(getattr(PickPlaceSearchPhasePort, name), stub))
        return stub

    port = _port(SimpleNamespace(detach_moveit=lambda request: True, planning_attached=lambda request: False))
    assert port.detach_moveit(REQUEST) is True
    assert port.planning_attached(REQUEST) is False

    with pytest.raises(PickPlaceSearchPortError, match="boundary.planning_attached"):
        _port(SimpleNamespace()).planning_attached(REQUEST)
