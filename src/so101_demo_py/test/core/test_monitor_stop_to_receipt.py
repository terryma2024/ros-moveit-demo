"""C4: a terminal stop raised by the real monitor ends in a manifest the worker can verify.

The path under test: per-step latch -> real `_motion_monitor` -> TeacherStop -> terminal transition (R9.2) -> the real
`_capture_failure_evidence` -> the dynamic manifest contract. Nothing here constructs `failure_boundary_state` by hand.
"""
import pytest

from so101_demo.core.domain import ActionStatus, Failure, FailureCategory, State
from so101_demo.core.workflow import resolve_transition
from so101_demo.ros.teacher_stop import TeacherStop
from test_teacher_moveit_execution import evidence, make_adapter, no_snapshot
from test_per_step_cup_safety import CupSafetyLimits, FORCE_LIMIT, COMPRESSION_LIMIT, chunk, sample, watch
from test_dynamic_manifest_semantics import DONE_TRACE, event, manifest, validate


def test_a_monitor_stop_in_move_above_place_yields_a_verifiable_manifest(tmp_path):
    adapter = make_adapter(tmp_path)
    plugin = watch(state=State.MOVE_ABOVE_PLACE)
    plugin.clock = adapter._monotonic
    plugin.arm()
    adapter._physics_hazard_watch = plugin
    adapter._safety_state = State.MOVE_ABOVE_PLACE
    no_snapshot(adapter)
    monitor = adapter._motion_monitor(State.MOVE_ABOVE_PLACE)
    monitor()
    plugin.accept_chunk(chunk(1, sample(1, force=FORCE_LIMIT + 0.2)))
    with pytest.raises(TeacherStop) as stop:
        monitor()
    failure = Failure(FailureCategory.COLLISION, stop.value.code, str(stop.value))
    # the runner's own routing for this stop
    assert resolve_transition(State.MOVE_ABOVE_PLACE, ActionStatus.FAILED, failure) is State.ERROR
    trace = tuple(State(item) for item in DONE_TRACE[:DONE_TRACE.index("MOVE_ABOVE_PLACE") + 1]) + (State.ERROR,)
    result = type("Result", (), {"state_trace": trace, "failure": failure})()
    # the real evidence capture of the adapter, on its own sources
    sample_after = evidence(step=2000)
    adapter._snapshot = lambda: sample_after
    adapter._evidence = lambda value: {"reset_epoch": 17, "simulation_step": 2000, "publisher_sequence": 2000,
        "cup_position_world_m": [0.0, 0.0, 0.1], "cup_orientation_world_xyzw": [0, 0, 0, 1],
        "cup_linear_velocity_world_m_s": [0.0] * 3, "cup_angular_velocity_world_rad_s": [0.0] * 3,
        "left_contact_count": 1, "right_contact_count": 1, "maximum_normal_force_n": 0.5, "table_contact": False}
    adapter._scene_membership = lambda: (["plastic_cup"], {"table": 1})
    adapter._release_marker_sequence = None
    captured = adapter._capture_failure_evidence(result)
    assert captured["failure_boundary_state"] == "MOVE_ABOVE_PLACE"
    document = manifest([item.value for item in trace], status="ERROR")
    document["failure"] = stop.value.code
    document["failure_evidence"] = captured
    document["state_events"].append(dict(event("MOVE_ABOVE_PLACE", 500), validation_failure=stop.value.code))
    validate(document, "ERROR")
