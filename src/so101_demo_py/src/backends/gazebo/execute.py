"""Bounded Gazebo execute probe using unified policy and shared MoveIt clients."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from ...application.backend_execute import ExecuteBoundary, classify_execute_boundary
from ...control.moveit.planning import (
    JointPlanRequest,
    MoveItPlanningClient,
    make_get_motion_plan_request,
)
from ...control.trajectory.executor import MoveItExecutionClient, make_execute_goal
from ...core.domain import ActionResult, ActionStatus, Failure, FailureCategory
from ...core.policy import load_task_policy
from ...runtime.result_manifest import write_run_result


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
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--readiness-timeout-s", type=float, default=60.0)
    options, _ = parser.parse_known_args(arguments)

    import rclpy
    from control_msgs.action import FollowJointTrajectory
    from moveit_msgs.action import ExecuteTrajectory
    from moveit_msgs.srv import GetMotionPlan
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
    plan_client = node.create_client(GetMotionPlan, "/plan_kinematic_path")
    execute_client = ActionClient(node, ExecuteTrajectory, "/execute_trajectory")

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
                and plan_client.service_is_ready()
                and execute_client.server_is_ready()
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
            evidence_valid = True
            initial_joint = [float(latest_joint[name]) for name in policy.all_joints]
            phase = "PREPARE_OPEN_GRIPPER"
            action = send_trajectory(
                gripper,
                (policy.gripper_joint,),
                ((policy.gripper.preopen_q6,),),
                5,
            )
            if action.status is ActionStatus.SUCCEEDED:
                phase = "MOVE_ABOVE_OBJECT"
                waypoints = policy.states["MOVE_ABOVE_OBJECT"].waypoints
                action = send_trajectory(arm, policy.arm_joints, waypoints[:-1], 2)
                if action.status is ActionStatus.SUCCEEDED:
                    current = tuple(float(latest_joint[name]) for name in policy.all_joints)
                    planning = MoveItPlanningClient(
                        plan_client,
                        request_factory=make_get_motion_plan_request,
                        progress=progress,
                    ).plan_joint_path(
                        JointPlanRequest(
                            policy.arm_joints,
                            current[:5],
                            waypoints[-1],
                            0.03,
                            0.03,
                            8.0,
                            start_state_joint_names=policy.all_joints,
                            start_state_positions=current,
                        ),
                        15.0,
                    )
                    if planning.failure is not None or planning.trajectory is None:
                        failure = planning.failure
                        action = _failure(
                            FailureCategory.PLANNING,
                            "PLANNING_FAILED" if failure is None else failure.code,
                            "MoveIt returned no trajectory"
                            if failure is None
                            else failure.message,
                        )
                    else:
                        action = MoveItExecutionClient(
                            execute_client,
                            goal_factory=make_execute_goal,
                            progress=progress,
                        ).execute(planning.trajectory, 45.0)
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

    # A successful first boundary is not a completed nine-phase run; its evidence is
    # valid, but Task 13 must continue before it can claim SUCCEEDED.
    if action.status is ActionStatus.SUCCEEDED:
        action = _failure(
            FailureCategory.INTERNAL,
            "GAZEBO_EXECUTE_INCOMPLETE",
            "MOVE_ABOVE_OBJECT succeeded but the remaining common phases are not complete",
        )
        evidence_valid = False
    result = classify_execute_boundary(
        ExecuteBoundary(phase, action, evidence_valid, (str(evidence_path),)),
        backend="gazebo",
        session_id=options.session_id,
        reset_epoch=0,
        policy_sha256=options.policy_sha256,
        bundle_sha256=options.bundle_sha256,
    )
    write_run_result(options.result, result)
    print(f"run_status={result.run_status.value}", flush=True)
    print(f"first_failed_phase={result.first_failed_phase}", flush=True)
    print(f"error_code={result.error_code}", flush=True)
    print(f"evidence_file={options.result}", flush=True)
    return 0 if result.run_status.value == "SUCCEEDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
