"""Live RESET_WORLD command with observable postcondition proof."""

import argparse
import json
import math
import os
from pathlib import Path
import time


def reset_live_world(
    backend, transport, apply_scene, *, object_id: str,
    parking_pose: tuple[float, ...], spawn_pose: tuple[float, ...],
    home_arm: tuple[float, ...], home_gripper: float, timeout_s: float,
    monotonic=time.monotonic, wait=time.sleep,
) -> dict[str, object]:
    """Park the cup, home the robot, respawn it, and prove a reusable initial state."""
    if not transport.publish_empty("/so101/detach_object"):
        raise RuntimeError("Gazebo detach command was not published")
    detach_deadline=monotonic()+timeout_s
    while backend.attachment_state() != "detached":
        if monotonic() >= detach_deadline:
            raise RuntimeError("Gazebo detach did not converge")
        wait(0.05)

    backend.set_object_pose(parking_pose)
    apply_scene("detach",parking_pose)
    backend.move_arm((home_arm,))
    backend.move_gripper(home_gripper)
    backend.set_object_pose(spawn_pose)
    scene=apply_scene("detach",spawn_pose)

    proof_deadline=monotonic()+timeout_s
    last: dict[str, object] = {}
    while monotonic() <= proof_deadline:
        observed=backend.sample()
        contacts=backend.contacts()
        position_error=math.dist(observed.object_xyz,spawn_pose[:3])
        finger_contact=any(
            "finger" in pair.finger_collision or "jaw" in pair.finger_collision
            for pair in contacts
        )
        last={
            "status":"RESET_WORLD_PENDING",
            "object_id":object_id,
            "object_pose_error_m":position_error,
            "gazebo_attachment_state":backend.attachment_state(),
            "moveit_world_objects":scene["world_objects"],
            "moveit_attached_objects":scene["attached_objects"],
            "finger_contact":finger_contact,
            "arm_tcp_finite":all(
                math.isfinite(value) for value in (*observed.tcp_xyz,*observed.tcp_xyzw)
            ),
        }
        if (
            position_error <= 0.001
            and last["gazebo_attachment_state"] == "detached"
            and object_id in scene["world_objects"]
            and object_id not in scene["attached_objects"]
            and not finger_contact
            and last["arm_tcp_finite"]
        ):
            last["status"]="RESET_WORLD_PROVED"
            return last
        wait(0.05)
    raise RuntimeError(f"RESET_WORLD postconditions did not converge: {last}")


def main(argv=None):
    parser=argparse.ArgumentParser(description="Reset SO-101 Gazebo and Planning Scene state")
    parser.add_argument("--timeout", type=float, default=10.0)
    options=parser.parse_args(argv)
    try:
        import yaml
        from ament_index_python.packages import get_package_share_directory
        from ..gazebo.transport import GazeboTransport
        from ..live_execute import _apply_scene
        from ..policy_config import load_policy_bundle
        from ..test_support.ros_gazebo_backend import RosGazeboLiveBackend

        share=Path(get_package_share_directory("so101_gazebo_demo_py"))
        bundle=load_policy_bundle(
            share/"config/task_objects/light_plastic_cup.yaml",
            share/"config/motion_policies/light_cup_wall_pick.yaml",
            share/"config/validation_policies/light_cup_wall_pick.yaml",
        )
        initial=yaml.safe_load((share/"config/initial_positions.yaml").read_text())["initial_positions"]
        evidence=reset_live_world(
            RosGazeboLiveBackend(bundle.validation.physical_outcome.planning_shadow.max_pair_age_s),
            GazeboTransport(), _apply_scene,
            object_id=bundle.task_object.object_id,
            parking_pose=bundle.task_object.reset_parking_pose.values,
            spawn_pose=bundle.task_object.spawn_pose.values,
            home_arm=tuple(float(initial[str(index)]) for index in range(1,6)),
            home_gripper=float(initial["6"]), timeout_s=options.timeout,
        )
        evidence_dir=Path(os.environ.get("SO101_PY_EVIDENCE_DIR","/tmp/so101-py-runtime"))
        evidence_dir.mkdir(parents=True,exist_ok=True)
        (evidence_dir/"reset-world.json").write_text(json.dumps(evidence,indent=2))
        print(json.dumps(evidence,sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"status":"RESET_WORLD_FAILED","error":str(error)},sort_keys=True))
        return 1
