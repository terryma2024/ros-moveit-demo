#!/usr/bin/env python3
import json
from pathlib import Path
import sys


def assert_summary(path: Path) -> None:
    value=json.loads(Path(path).read_text())
    assert value["exit_code"] == 0 and value["status"] == "DONE"
    assert value["state_trace"][-1] == "DONE"
    assert value["controller"] == {"arm":"SUCCEEDED","gripper":"SUCCEEDED"}
    assert value["moveit"]["planned_points"] > 0 and value["moveit"]["execute_succeeded"]
    assert "plastic_cup" in value["moveit"]["attached_scene"]["attached_objects"]
    assert "plastic_cup" in value["moveit"]["detached_scene"]["world_objects"]
    assert "plastic_cup" in value["moveit"]["synchronized_scene"]["world_objects"]
    assert len(value["moveit"]["shadow_checks"]) == 3
    assert all(check["healthy"] for check in value["moveit"]["shadow_checks"])
    assert value["gazebo"]["events"] == []
    assert value["gazebo"]["attachment_state"] == "detached"
    assert value["gazebo"]["bilateral_before_attach"]
    assert value["gazebo"]["max_penetration_m"] <= .000800002
    assert value["physical"]["micro_lift_world_z"] >= .002
    assert value["physical"]["lateral_drift_m"] <= .001
    assert value["final_outcome"]["success"]
    assert value["final_outcome"]["failure_code"] is None
    assert value["final_outcome"]["sample_count"] > 1
    assert len(value["tf"]["initial_tcp_xyz"]) == len(value["tf"]["final_tcp_xyz"]) == 3
    assert value["provenance"]["package_share"].endswith("/share/so101_gazebo_demo_py")
    assert value["provenance"]["ros_domain_id"] and value["provenance"]["gz_partition"]


if __name__ == "__main__": assert_summary(Path(sys.argv[1]))
