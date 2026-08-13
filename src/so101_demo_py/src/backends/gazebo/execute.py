"""Bounded Gazebo execute probe using unified policy and shared MoveIt clients."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from ament_index_python.packages import get_package_share_directory

from ...application.backend_execute import ExecuteBoundary, classify_execute_boundary
from ...control.planning_scene.task_scene import RosTaskScenePort
from ...control.trajectory.reset_control import GazeboAttachmentMonitor
from ...core.domain import ActionResult, ActionStatus, Failure, FailureCategory
from ...core.policy import load_task_policy
from ...core.task_geometry import Pose7, load_task_geometry
from ...runtime.result_manifest import write_run_result
from .commands import GazeboCommandAdapter
from .reset import GazeboResetState
from .workflow import execute_gazebo_workflow


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _complete_runtime_options(options: argparse.Namespace) -> None:
    """Fill Teleop's bounded request from the installed immutable bundle."""

    if options.result is None:
        checkpoint = options.checkpoint or (
            Path(os.environ.get("SO101_TELEOP_EVIDENCE_BASE", "/tmp/so101-teleop"))
            / options.session_id
            / "checkpoint.json"
        )
        options.result = checkpoint.with_name("gazebo-run-result.json")
    if options.policy is None:
        from ament_index_python.packages import get_package_share_directory

        share = Path(get_package_share_directory("so101_demo_py"))
        options.policy = (
            share / "config/policies/light_cup_wall_pick/v1/gazebo.yaml"
        )
    options.policy_sha256 = options.policy_sha256 or _sha256(options.policy)
    if (
        options.source_commit is None
        or options.installed_prefix is None
        or options.bundle_sha256 is None
    ):
        from ...runtime.provenance import installed_bundle

        bundle = installed_bundle()
        inputs = bundle.manifest["inputs"]
        options.source_commit = options.source_commit or inputs["source_commit"]
        options.installed_prefix = options.installed_prefix or inputs["package_prefix"]
        options.bundle_sha256 = options.bundle_sha256 or bundle.bundle_sha256


def _failure(category: FailureCategory, code: str, message: str) -> ActionResult:
    return ActionResult(ActionStatus.FAILED, Failure(category, code, message))


def _trajectory_result(error_code: int, error_string: str) -> ActionResult:
    names = {
        0: "SUCCESSFUL",
        -1: "INVALID_GOAL",
        -2: "INVALID_JOINTS",
        -3: "OLD_HEADER_TIMESTAMP",
        -4: "PATH_TOLERANCE_VIOLATED",
        -5: "GOAL_TOLERANCE_VIOLATED",
    }
    if error_code == 0:
        return ActionResult(ActionStatus.SUCCEEDED)
    return _failure(
        FailureCategory.EXECUTION,
        names.get(error_code, f"FOLLOW_JOINT_TRAJECTORY_{error_code}"),
        error_string or f"FollowJointTrajectory returned {error_code}",
    )


def _atomic_json(path: Path, document: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)
    return path


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--mode", choices=("execute",), default="execute")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--installed-prefix")
    parser.add_argument("--policy-sha256")
    parser.add_argument("--bundle-sha256")
    parser.add_argument("--readiness-timeout-s", type=float, default=60.0)
    options, _ = parser.parse_known_args(arguments)
    _complete_runtime_options(options)

    import rclpy
    from control_msgs.action import FollowJointTrajectory
    from rclpy.action import ActionClient
    from ros_gz_interfaces.msg import WorldStatistics
    from sensor_msgs.msg import JointState
    from tf2_msgs.msg import TFMessage
    from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

    policy = load_task_policy(options.policy)
    evidence_root = options.result.parent / f"{options.result.stem}.d"
    evidence_path = evidence_root / "gazebo-execute-evidence.json"
    rclpy.init()
    node = rclpy.create_node("so101_unified_gazebo_execute")
    latest_joint: dict[str, float] = {}
    latest_pose: dict[str, object] = {}
    latest_stats: dict[str, object] = {}

    def joints(message: JointState) -> None:
        if len(message.name) == len(message.position):
            latest_joint.update(zip(message.name, message.position, strict=True))

    def poses(message: TFMessage) -> None:
        latest_pose["transform_count"] = len(message.transforms)
        latest_pose["child_frames"] = [item.child_frame_id for item in message.transforms]
        for item in message.transforms:
            if "plastic_cup" not in item.child_frame_id:
                continue
            value = item.transform
            latest_pose["plastic_cup_pose_xyz_xyzw"] = [
                value.translation.x,
                value.translation.y,
                value.translation.z,
                value.rotation.x,
                value.rotation.y,
                value.rotation.z,
                value.rotation.w,
            ]

    def stats(message: WorldStatistics) -> None:
        latest_stats.update(
            {
                "iterations": int(message.iterations),
                "paused": bool(message.paused),
                "sim_time_s": float(message.sim_time.sec)
                + float(message.sim_time.nanosec) * 1e-9,
            }
        )

    subscriptions = [
        node.create_subscription(JointState, "/joint_states", joints, 100),
        node.create_subscription(TFMessage, "/so101/gazebo_pose_info", poses, 100),
        node.create_subscription(
            WorldStatistics, "/so101/gazebo_world_stats", stats, 100
        ),
    ]
    arm = ActionClient(node, FollowJointTrajectory, "/arm_controller/follow_joint_trajectory")
    gripper = ActionClient(
        node, FollowJointTrajectory, "/gripper_controller/follow_joint_trajectory"
    )

    def progress() -> None:
        rclpy.spin_once(node, timeout_sec=0.01)

    def wait_for(predicate, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while rclpy.ok() and time.monotonic() < deadline:
            if predicate():
                return True
            progress()
        return False

    def send_trajectory(
        client: Any,
        joint_names: tuple[str, ...],
        points: tuple[tuple[float, ...], ...],
        step_seconds: int,
    ) -> ActionResult:
        if not client.wait_for_server(timeout_sec=10.0):
            return _failure(
                FailureCategory.EXECUTION,
                "CONTROLLER_UNAVAILABLE",
                "FollowJointTrajectory action is unavailable",
            )
        trajectory = JointTrajectory(joint_names=list(joint_names))
        trajectory.points = []
        for index, positions in enumerate(points, start=1):
            point = JointTrajectoryPoint(positions=list(positions))
            point.time_from_start.sec = index * step_seconds
            trajectory.points.append(point)
        goal = FollowJointTrajectory.Goal(trajectory=trajectory)
        sent = client.send_goal_async(goal)
        if not wait_for(sent.done, 10.0):
            return _failure(FailureCategory.EXECUTION, "ACTION_GOAL_TIMEOUT", "goal timeout")
        handle = sent.result()
        if handle is None or not handle.accepted:
            return _failure(FailureCategory.EXECUTION, "ACTION_REJECTED", "goal rejected")
        completed = handle.get_result_async()
        timeout_s = step_seconds * len(points) + 20.0
        if not wait_for(completed.done, timeout_s):
            handle.cancel_goal_async()
            return _failure(
                FailureCategory.EXECUTION,
                "ACTION_RESULT_TIMEOUT",
                "trajectory result timeout",
            )
        wrapped = completed.result()
        result = wrapped.result
        return _trajectory_result(int(result.error_code), str(result.error_string))

    action = _failure(FailureCategory.INTERNAL, "EXECUTE_NOT_STARTED", "not started")
    phase = "readiness"
    evidence_valid = False
    try:
        ready = wait_for(
            lambda: (
                len(latest_joint) == 6
                and bool(latest_pose)
                and bool(latest_stats)
                and arm.server_is_ready()
                and gripper.server_is_ready()
            ),
            options.readiness_timeout_s,
        )
        if not ready:
            action = _failure(
                FailureCategory.OBSERVATION,
                "GAZEBO_READINESS_TIMEOUT",
                "joint, world, controller, bridge, or MoveIt readiness timed out",
            )
        else:
            initial_joint = [float(latest_joint[name]) for name in policy.all_joints]
            share = Path(get_package_share_directory("so101_demo_py"))
            geometry = load_task_geometry(
                share / "assets/common/geometry-manifest.yaml"
            )
            scene = RosTaskScenePort(node, "gazebo", options.readiness_timeout_s)
            commands = GazeboCommandAdapter()
            attachment_state = GazeboResetState()
            attachment = GazeboAttachmentMonitor(
                attachment_state, "/so101/object_attached_event"
            )

            class Operations:
                def __init__(self) -> None:
                    self.receipts: list[dict[str, object]] = []

                def _record(self, phase_name: str, result: ActionResult) -> ActionResult:
                    self.receipts.append(
                        {
                            "phase": phase_name,
                            "status": result.status.value,
                            "failure_code": None
                            if result.failure is None
                            else result.failure.code,
                        }
                    )
                    return result

                def arm(self, phase_name: str, state) -> ActionResult:
                    return self._record(
                        phase_name,
                        send_trajectory(
                            arm,
                            policy.arm_joints,
                            state.waypoints,
                            2,
                        ),
                    )

                def gripper(self, phase_name: str, target: float) -> ActionResult:
                    return self._record(
                        phase_name,
                        send_trajectory(
                            gripper,
                            (policy.gripper_joint,),
                            ((target,),),
                            2,
                        ),
                    )

                def physical(self, phase_name: str, attach_value: bool) -> ActionResult:
                    receipt = (
                        commands.request_attach()
                        if attach_value
                        else commands.request_detach()
                    )
                    if not receipt.success:
                        result = _failure(
                            FailureCategory.EXECUTION,
                            receipt.failure_code or "GAZEBO_ATTACHMENT_COMMAND_FAILED",
                            "Gazebo attachment command failed",
                        )
                    else:
                        converged = wait_for(
                            lambda: attachment_state.snapshot()["attached"]
                            is attach_value,
                            5.0,
                        )
                        result = (
                            ActionResult(ActionStatus.SUCCEEDED)
                            if converged
                            else _failure(
                                FailureCategory.OBSERVATION,
                                "GAZEBO_ATTACHMENT_VERIFY_FAILED",
                                f"attachment did not converge to {attach_value}",
                            )
                        )
                    return self._record(phase_name, result)

                def scene(self, phase_name: str, attach_value: bool) -> ActionResult:
                    current_geometry = geometry
                    if not attach_value:
                        pose_values = latest_pose.get("plastic_cup_pose_xyz_xyzw")
                        if isinstance(pose_values, list) and len(pose_values) == 7:
                            cup = replace(
                                geometry.object("plastic_cup"),
                                pose=Pose7(tuple(float(value) for value in pose_values)),
                            )
                            current_geometry = replace(
                                geometry,
                                objects=tuple(
                                    cup if item.object_id == "plastic_cup" else item
                                    for item in geometry.objects
                                ),
                            )
                    receipt = (
                        scene.attach_task_object(
                            current_geometry, "plastic_cup", "gripper"
                        )
                        if attach_value
                        else scene.detach_task_object(current_geometry, "plastic_cup")
                    )
                    if receipt.success:
                        receipt = scene.observe_task_scene(
                            current_geometry,
                            expected_cup_attachment="gripper"
                            if attach_value
                            else None,
                        )
                    result = (
                        ActionResult(ActionStatus.SUCCEEDED)
                        if receipt.success
                        else _failure(
                            FailureCategory.MOVEIT_SCENE,
                            receipt.failure_code or "MOVEIT_SCENE_FAILED",
                            f"Planning Scene phase {phase_name} failed",
                        )
                    )
                    return self._record(phase_name, result)

            operations = Operations()
            boundary = execute_gazebo_workflow(policy, operations)
            phase = boundary.phase
            action = boundary.action
            evidence_valid = boundary.evidence_valid
            attachment.close()
            _atomic_json(
                evidence_path,
                {
                    "action_error_code": None
                    if action.failure is None
                    else action.failure.code,
                    "action_status": action.status.value,
                    "backend": "gazebo",
                    "completed_boundary": phase
                    if action.status is ActionStatus.SUCCEEDED
                    else None,
                    "gz_partition": os.environ.get("GZ_PARTITION", ""),
                    "initial_joints_rad": initial_joint,
                    "phase_receipts": operations.receipts,
                    "policy_sha256": options.policy_sha256,
                    "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", ""),
                    "session_id": options.session_id,
                    "terminal_joints_rad": [
                        float(latest_joint[name]) for name in policy.all_joints
                    ],
                    "world_pose": latest_pose,
                    "world_stats": latest_stats,
                },
            )
    except Exception as error:
        action = _failure(FailureCategory.INTERNAL, "GAZEBO_EXECUTE_EXCEPTION", str(error))
        evidence_valid = bool(latest_joint and latest_pose and latest_stats)
        _atomic_json(
            evidence_path,
            {
                "backend": "gazebo",
                "error": f"{type(error).__name__}: {error}",
                "gz_partition": os.environ.get("GZ_PARTITION", ""),
                "session_id": options.session_id,
                "world_pose": latest_pose,
                "world_stats": latest_stats,
            },
        )
    finally:
        del subscriptions
        node.destroy_node()
        rclpy.shutdown()

    result = classify_execute_boundary(
        ExecuteBoundary(phase, action, evidence_valid, (str(evidence_path),)),
        backend="gazebo",
        session_id=options.session_id,
        reset_epoch=0,
        source_commit=options.source_commit,
        installed_prefix=options.installed_prefix,
        policy_sha256=options.policy_sha256,
        bundle_sha256=options.bundle_sha256,
    )
    write_run_result(options.result, result)
    print(f"run_status={result.run_status.value}", flush=True)
    print(f"first_failed_phase={result.first_failed_phase}", flush=True)
    print(f"error_code={result.error_code}", flush=True)
    if result.error_code is not None:
        print(f"failure_code={result.error_code}", flush=True)
    print(f"evidence_file={options.result}", flush=True)
    return 0 if result.run_status.value == "SUCCEEDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
