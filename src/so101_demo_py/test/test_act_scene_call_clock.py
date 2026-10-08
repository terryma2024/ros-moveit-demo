"""Actual ROS clock reads remain distinct from service wall-clock bounds."""

from types import SimpleNamespace

import pytest


def test_scene_call_retains_actual_ros_clock_read_intervals():
    from moveit_msgs.srv import ApplyPlanningScene
    from so101_demo.control.planning_scene.task_scene import record_scene_service_call

    instants = iter((1200000000, 1300000000))
    clock = SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=next(instants)))
    records = []
    response = ApplyPlanningScene.Response(success=True)
    assert record_scene_service_call(request=ApplyPlanningScene.Request(), phase="APPLY",
        service="/apply_planning_scene", invoke=lambda: response, records=records,
        ros_clock=clock) is response
    call = records[0]
    assert call["schema_version"] == 2
    first, last = call["request_ros_clock"], call["response_ros_clock"]
    assert first["sim_time_ns"] == 1200000000 and last["sim_time_ns"] == 1300000000
    assert (0 < first["begin_monotonic_ns"] <= first["end_monotonic_ns"]
        <= call["request_monotonic_ns"] <= call["response_monotonic_ns"]
        <= last["begin_monotonic_ns"] <= last["end_monotonic_ns"])
    assert call["response"] == {"success": True}


def test_scene_call_retains_refused_call_without_fabricating_a_response_clock():
    from moveit_msgs.srv import ApplyPlanningScene
    from so101_demo.control.planning_scene.task_scene import record_scene_service_call

    clock = SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=1200000000))
    records = []
    def refused():
        raise RuntimeError("actual refusal")
    with pytest.raises(RuntimeError, match="actual refusal"):
        record_scene_service_call(request=ApplyPlanningScene.Request(), phase="APPLY",
            service="/apply_planning_scene", invoke=refused, records=records, ros_clock=clock)
    assert records[0]["error"] == "actual refusal"
    assert records[0]["response"] is None
    assert records[0]["response_ros_clock"]["sim_time_ns"] == 1200000000
