"""SEARCH uses advancing physics and independent Planning Scene readback."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

from so101_demo.adapters.act.pick_place_readback import PickPlaceReadbackError
from so101_demo.adapters.act.pick_place_search_segment import PickPlaceSearchError, PickPlaceSearchSegment
from so101_demo.core.task_geometry import load_task_geometry
from so101_demo.ports.planning_scene import SceneCommandReceipt


def _geometry():
    return load_task_geometry(
        Path(__file__).parents[1] / "assets/common/geometry-manifest.yaml",
    )


def _raw(step, *, x=-0.08, fingertips=()):
    world = SimpleNamespace(
        simulation_session_id="session-1", reset_epoch=2,
        simulation_step=step, simulation_time_s=float(step), paused=False,
        object_state=SimpleNamespace(
            body="plastic_cup", position_world=(x, -0.28, 0.165),
            orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
        ),
        left_fingertip_contacts=tuple(fingertips), right_fingertip_contacts=(),
    )
    return {
        "world": world,
        "scene": {"simulation_session_id": "session-1", "reset_epoch": 2,
                  "simulation_step": step, "paused": False},
        "contact": {"simulation_session_id": "session-1", "reset_epoch": 2,
                    "physics_step": step},
    }


def _locked():
    return {"found": True, "status": "TARGET_LOCKED", "bearing_rad": 0.0,
            "frame_id": "head_camera_frame", "ray_origin_frame_id": "head_camera_frame",
            "neck_yaw_rad": 0.1, "confidence": 0.9, "timestamp": 2.0,
            "attempt_id": "attempt-1"}


def _request():
    return {"session_id": "session-1", "attempt_id": "attempt-1",
            "deadline_ns": time.monotonic_ns() + 5_000_000_000}


class _Sources:
    def __init__(self, *rows):
        self.rows = deque(rows)
        self.cursors = []

    def capture(self, attempt_id, *, after_step):
        assert attempt_id == "attempt-1"
        self.cursors.append(after_step)
        row = self.rows.popleft() if self.rows else PickPlaceReadbackError("SOURCE_STEP_NOT_ADVANCED")
        if isinstance(row, BaseException):
            raise row
        assert row["world"].simulation_step > after_step
        return row


class _Scene:
    def __init__(self, *, fail_readback=False):
        self.applied = []
        self.observed = []
        self.fail_readback = fail_readback

    def apply_task_scene(self, geometry):
        self.applied.append(geometry)
        return SceneCommandReceipt("mujoco", "APPLY", True, None, {"applied": True})

    def observe_task_scene(self, geometry, *, expected_cup_attachment):
        assert expected_cup_attachment is None
        self.observed.append(geometry)
        if self.fail_readback:
            return SceneCommandReceipt("mujoco", "READ_BACK", False,
                                       "SCENE_READBACK_MISMATCH", {})
        return SceneCommandReceipt("mujoco", "READ_BACK", True, None,
                                   {"world_ids": ["pedestal", "plastic_cup", "table"],
                                    "attached_ids": [], "mismatches": []})


class _Adapter:
    def __init__(self, *decisions, stop_confirmed=True):
        self.decisions = deque(decisions)
        self.ticks = 0
        self.stops = 0
        self.stop_confirmed = stop_confirmed
        self.neck_port = SimpleNamespace(stop_and_confirm=self.stop_and_confirm)

    def tick(self, *, safe_observe):
        assert safe_observe is True
        self.ticks += 1
        return self.decisions.popleft()

    def stop_and_confirm(self):
        self.stops += 1
        return self.stop_confirmed


def _segment(sources, adapter, scene, *, guard=lambda: None, clock=None):
    clock = [10.0] if clock is None else clock
    return PickPlaceSearchSegment(
        sources, adapter, scene, _geometry(), operation_guard=guard,
        max_source_wait_s=0.05, poll_interval_s=0.01,
        monotonic=lambda: clock[0], sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )


def test_search_waits_for_new_steps_then_reads_back_final_physical_cup_pose():
    sources = _Sources(_raw(1), PickPlaceReadbackError("SOURCE_STEP_NOT_ADVANCED"),
                       _raw(2), _raw(3, x=-0.079))
    adapter = _Adapter({"status": "INPUT_PENDING", "stop": True}, _locked())
    scene = _Scene()
    observation = _segment(sources, adapter, scene).run(_request(), reset_epoch=2)
    assert sources.cursors == [0, 1, 1, 2]
    assert adapter.ticks == 2 and adapter.stops == 1
    assert [value.object("plastic_cup").pose.values[0] for value in scene.applied] == [-0.08, -0.079]
    assert len(scene.observed) == 2
    assert observation.search_result == _locked()
    assert observation.physical_readback["world"].simulation_step == 3
    assert observation.planning_scene.phase == "READ_BACK"


def test_search_scene_readback_failure_stops_before_neck_tick():
    adapter, scene = _Adapter(_locked()), _Scene(fail_readback=True)
    with pytest.raises(PickPlaceSearchError, match="SEARCH_SCENE_READBACK_FAILED"):
        _segment(_Sources(_raw(1)), adapter, scene).run(_request(), reset_epoch=2)
    assert adapter.ticks == 0 and adapter.stops == 1


def test_search_missing_new_step_times_out_and_confirms_stop():
    adapter = _Adapter({"status": "INPUT_PENDING", "stop": True})
    with pytest.raises(PickPlaceSearchError, match="SEARCH_SOURCE_TIMEOUT"):
        _segment(_Sources(_raw(1)), adapter, _Scene()).run(_request(), reset_epoch=2)
    assert adapter.ticks == 1 and adapter.stops == 1


def test_search_fingertip_contact_fails_before_neck_tick():
    adapter = _Adapter(_locked())
    with pytest.raises(PickPlaceSearchError, match="SEARCH_CONTACT_UNSAFE"):
        _segment(_Sources(_raw(1, fingertips=(object(),))), adapter, _Scene()).run(
            _request(), reset_epoch=2,
        )
    assert adapter.ticks == 0 and adapter.stops == 1


def test_search_stop_uncertainty_overrides_scene_failure():
    adapter = _Adapter(_locked(), stop_confirmed=False)
    with pytest.raises(PickPlaceSearchError, match="SEARCH_STOP_UNCONFIRMED"):
        _segment(_Sources(_raw(1)), adapter, _Scene(fail_readback=True)).run(
            _request(), reset_epoch=2,
        )
    assert adapter.stops == 1


def test_ros_source_wrapper_passes_step_cursor_to_physical_readback():
    from so101_demo.adapters.act.task8_sources import Task8RosEvidence

    calls = []
    source = object.__new__(Task8RosEvidence)
    source.session_id = "session-1"
    source.reset_epoch = 2
    source.readback = SimpleNamespace(capture=lambda *args, **kwargs: (
        calls.append((args, kwargs)) or {"accepted": True}
    ))
    assert source.capture("attempt-1", after_step=7) == {"accepted": True}
    assert calls == [(("session-1", "attempt-1", 2), {"after_step": 7})]
