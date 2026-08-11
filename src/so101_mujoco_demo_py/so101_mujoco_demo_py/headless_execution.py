"""Bounded headless MoveIt planning and optional safe execution diagnostic."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

REQUIRED_NODES = {
    "/controller_manager",
    "/move_group",
    "/robot_state_publisher",
    "/so101_headless_execution",
}
REQUIRED_TOPICS = {
    "/joint_states",
    "/monitored_planning_scene",
    "/so101/simulation/evidence",
    "/tf",
    "/tf_static",
}
REQUIRED_SERVICES = {
    "/get_planning_scene",
    "/mujoco_ros2_control_node/reset_world",
    "/mujoco_ros2_control_node/set_pause",
    "/plan_kinematic_path",
}
REQUIRED_ACTIONS = {
    "/arm_controller/follow_joint_trajectory",
    "/execute_trajectory",
}
CONTROLLER_MAPPING = {
    "arm_controller": ["1", "2", "3", "4", "5"],
    "gripper_controller": ["6"],
    "joint_state_broadcaster": [],
}


def _require_subset(label: str, required: set[str], observed: list[str]) -> None:
    missing = required - set(observed)
    assert not missing, f"missing {label}: {sorted(missing)}"


def assert_headless_summary(summary: dict[str, Any], *, expected_mode: str) -> None:
    """Validate evidence from a completed launch without trusting its success log."""

    assert summary["schema_version"] == 1
    assert summary["run_mode"] == expected_mode
    assert expected_mode in {"dry_run", "execute"}
    assert summary["planning_group"] == "arm"
    assert summary["tcp_link"] == "so101_tcp"
    readiness = summary["ready"]
    _require_subset("nodes", REQUIRED_NODES, readiness["nodes"])
    _require_subset("topics", REQUIRED_TOPICS, readiness["topics"])
    _require_subset("services", REQUIRED_SERVICES, readiness["services"])
    _require_subset("actions", REQUIRED_ACTIONS, readiness["actions"])
    assert readiness["controllers"] == CONTROLLER_MAPPING
    assert readiness["tf_world_to_tcp"] is True
    assert readiness["moveit_planning_group"] == "arm"
    assert summary["plan"]["accepted"] is True
    assert summary["plan"]["trajectory_points"] > 0
    assert summary["mujoco"]["publisher_sequence_delta"] > 0
    assert summary["mujoco"]["simulation_step_delta"] > 0
    assert summary["mujoco"]["reset_epoch_before"] == summary["mujoco"]["reset_epoch_after"]
    execution = summary["execution"]
    joints = summary["joint_state"]
    if expected_mode == "dry_run":
        assert summary["execution_requested"] is False
        assert execution["goal_sent"] is False, "dry_run sent an execution goal"
        assert execution["succeeded"] is False
        assert execution["controller_result"] == "NOT_REQUESTED"
    else:
        assert summary["execution_requested"] is True
        assert execution["goal_sent"] is True
        assert execution["succeeded"] is True
        assert execution["controller_result"] == "SUCCEEDED"
        assert joints["converged"] is True
        assert joints["maximum_target_error_rad"] is not None
        assert joints["maximum_motion_rad"] > 0.0, "execute produced no joint movement"
    shutdown = summary["shutdown"]
    assert shutdown["launch_exit_code"] == 0
    assert shutdown["domain_nodes_after"] == []


def _write_json(destination: Path, value: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, destination)


def _names(node: Any) -> tuple[list[str], list[str], list[str], list[str]]:
    import rclpy.action

    nodes = sorted(
        f"/{name}" if namespace == "/" else f"{namespace}/{name}"
        for name, namespace in node.get_node_names_and_namespaces()
    )
    topics = sorted(name for name, _ in node.get_topic_names_and_types())
    services = sorted(name for name, _ in node.get_service_names_and_types())
    actions = sorted(name for name, _ in rclpy.action.get_action_names_and_types(node))
    return nodes, topics, services, actions


def _spin_until(node: Any, predicate, deadline: float, message: str) -> Any:
    import rclpy

    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        rclpy.spin_once(node, timeout_sec=0.05)
    raise RuntimeError(message)


def _service_result(node: Any, client: Any, request: Any, deadline: float) -> Any:
    import rclpy

    remaining = max(0.0, deadline - time.monotonic())
    if not client.wait_for_service(timeout_sec=remaining):
        raise RuntimeError(f"service unavailable: {client.srv_name}")
    future = client.call_async(request)
    while not future.done() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
    if not future.done() or future.exception() is not None:
        raise RuntimeError(f"service failed: {client.srv_name}")
    return future.result()


def _wait_for_active_controllers(
    node: Any, client: Any, request: Any, deadline: float
) -> dict[str, str]:
    latest_states: dict[str, str] = {}
    while time.monotonic() < deadline:
        response = _service_result(node, client, request, deadline)
        observed_states = {controller.name: controller.state for controller in response.controller}
        latest_states = {name: observed_states.get(name, "missing") for name in CONTROLLER_MAPPING}
        if all(state == "active" for state in latest_states.values()):
            return latest_states
    raise RuntimeError(f"controller readiness timeout: {latest_states}")


def _run_motion_boundary(
    *,
    execute: bool,
    pause_world,
    observe_evidence,
    capture_start,
    plan,
    execute_trajectory,
    progress,
    monotonic,
    deadline: float,
) -> tuple[Any, Any, Any | None]:
    """Plan from a frozen execute start and restore running state before returning."""

    if not execute:
        start = capture_start()
        return start, plan(start), None

    restore_running = True
    try:
        if not pause_world(True):
            raise RuntimeError("MuJoCo pause request failed")
        while monotonic() < deadline:
            evidence = observe_evidence()
            if evidence is not None and evidence.paused:
                break
            progress()
        else:
            raise RuntimeError("authoritative paused MuJoCo evidence timeout")

        start = capture_start()
        trajectory = plan(start)
        if not pause_world(False):
            raise RuntimeError("MuJoCo resume request failed")
        restore_running = False
        execution = execute_trajectory(trajectory)
        return start, trajectory, execution
    finally:
        if restore_running and not pause_world(False):
            raise RuntimeError("MuJoCo cleanup resume request failed")


def run_diagnostic(options: argparse.Namespace) -> dict[str, Any]:
    import rclpy
    import tf2_ros
    import yaml
    from control_msgs.action import FollowJointTrajectory
    from control_msgs.msg import JointTrajectoryControllerState
    from controller_manager_msgs.srv import ListControllers
    from moveit_msgs.action import ExecuteTrajectory
    from moveit_msgs.srv import GetMotionPlan
    from rclpy.action import ActionClient
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.time import Time
    from sensor_msgs.msg import JointState

    from .motion.executor import MoveItExecutionClient, make_execute_goal
    from .moveit.planning import (
        JointPlanRequest,
        MoveItPlanningClient,
        make_get_motion_plan_request,
    )
    from .mujoco.client import MujocoRosClient, MujocoServiceError
    from .mujoco.observer import EvidenceStale, MujocoWorldObserver

    configuration = yaml.safe_load(Path(options.config).read_text(encoding="utf-8"))
    if configuration["schema_version"] != 1:
        raise RuntimeError("unsupported headless execution schema")
    arm_joints = tuple(configuration["arm_joints"])
    target = tuple(float(value) for value in configuration["safe_poses"][options.safe_pose])
    if len(target) != len(arm_joints) or not all(math.isfinite(value) for value in target):
        raise RuntimeError("safe pose is incomplete or nonfinite")
    if options.run_mode == "execute" and not options.execute:
        raise RuntimeError("execute mode requires explicit --execute")
    if options.run_mode == "dry_run" and options.execute:
        raise RuntimeError("dry_run cannot request execution")

    rclpy.init()
    node = rclpy.create_node("so101_headless_execution")
    latest_joint_state: JointState | None = None
    latest_joint_state_received_monotonic_s: float | None = None
    boundary_measurements: list[dict[str, Any]] = []
    controller_state_stream: list[dict[str, Any]] = []
    pause_boundaries: list[dict[str, Any]] = []

    def accept_joint_state(message: JointState) -> None:
        nonlocal latest_joint_state, latest_joint_state_received_monotonic_s
        if len(message.name) == len(message.position):
            latest_joint_state = message
            latest_joint_state_received_monotonic_s = time.monotonic()

    def serialize_joint_sample() -> dict[str, Any] | None:
        message = latest_joint_state
        if (
            message is None
            or latest_joint_state_received_monotonic_s is None
            or len(message.name) != len(message.position)
            or len(set(message.name)) != len(message.name)
            or not all(math.isfinite(float(value)) for value in message.position)
        ):
            return None
        stamp = message.header.stamp
        return {
            "names": list(message.name),
            "positions": [float(value) for value in message.position],
            "received_monotonic_s": latest_joint_state_received_monotonic_s,
            "simulation_stamp": {"sec": int(stamp.sec), "nanosec": int(stamp.nanosec)},
        }

    def serialize_atomic_evidence(evidence: Any) -> dict[str, Any] | None:
        if evidence is None:
            return None
        return {
            "simulation_time_s": evidence.simulation_time_s,
            "publisher_sequence": evidence.publisher_sequence,
            "simulation_step": evidence.simulation_step,
            "reset_epoch": evidence.reset_epoch,
            "simulation_session_id": evidence.simulation_session_id,
            "paused": evidence.paused,
        }

    def serialize_trajectory_point(point: Any) -> dict[str, Any]:
        return {
            "positions": [float(value) for value in point.positions],
            "velocities": [float(value) for value in point.velocities],
            "accelerations": [float(value) for value in point.accelerations],
            "effort": [float(value) for value in point.effort],
            "time_from_start": {
                "sec": int(point.time_from_start.sec),
                "nanosec": int(point.time_from_start.nanosec),
            },
        }

    def accept_controller_state(message: JointTrajectoryControllerState) -> None:
        stamp = message.header.stamp
        controller_state_stream.append(
            {
                "received_monotonic_s": time.monotonic(),
                "header_stamp": {"sec": int(stamp.sec), "nanosec": int(stamp.nanosec)},
                "joint_names": list(message.joint_names),
                "reference": serialize_trajectory_point(message.reference),
                "feedback": serialize_trajectory_point(message.feedback),
                "error": serialize_trajectory_point(message.error),
                "output": serialize_trajectory_point(message.output),
                "speed_scaling_factor": float(message.speed_scaling_factor),
            }
        )

    def emit_measurement(boundary: str, evidence: Any, trajectory: Any | None = None) -> None:
        measurement: dict[str, Any] = {
            "boundary": boundary,
            "boundary_monotonic_s": time.monotonic(),
            "joint_sample": serialize_joint_sample(),
            "controller_states": controller_states,
            "atomic_evidence": serialize_atomic_evidence(evidence),
        }
        if trajectory is not None:
            joint_trajectory = trajectory.joint_trajectory
            first_point = joint_trajectory.points[0]
            measurement["trajectory_first_point"] = {
                "joint_names": list(joint_trajectory.joint_names),
                "positions": [float(value) for value in first_point.positions],
                "time_from_start": {
                    "sec": int(first_point.time_from_start.sec),
                    "nanosec": int(first_point.time_from_start.nanosec),
                },
            }
        boundary_measurements.append(measurement)

    subscription = node.create_subscription(
        JointState, "/joint_states", accept_joint_state, qos_profile_sensor_data
    )
    del subscription
    controller_subscription = node.create_subscription(
        JointTrajectoryControllerState,
        "/arm_controller/controller_state",
        accept_controller_state,
        10,
    )
    del controller_subscription
    observer = MujocoWorldObserver(node, options.simulation_session_id, max_age_s=0.5)
    tf_buffer = tf2_ros.Buffer()
    tf_listener = tf2_ros.TransformListener(tf_buffer, node)
    del tf_listener
    planner_action = ActionClient(node, ExecuteTrajectory, "/execute_trajectory")
    controller_action = ActionClient(
        node, FollowJointTrajectory, "/arm_controller/follow_joint_trajectory"
    )
    planner_service = node.create_client(GetMotionPlan, "/plan_kinematic_path")
    list_controllers = node.create_client(ListControllers, "/controller_manager/list_controllers")
    mujoco_client = MujocoRosClient(
        node,
        node,
        service_timeout_s=min(5.0, options.readiness_timeout_s),
    )
    deadline = time.monotonic() + options.readiness_timeout_s
    try:

        def graph_ready():
            nodes, topics, services, actions = _names(node)
            if not (
                REQUIRED_NODES <= set(nodes)
                and REQUIRED_TOPICS <= set(topics)
                and REQUIRED_SERVICES <= set(services)
                and REQUIRED_ACTIONS <= set(actions)
            ):
                return None
            return nodes, topics, services, actions

        nodes, topics, services, actions = _spin_until(
            node, graph_ready, deadline, "ROS graph readiness timeout"
        )
        controller_states = _wait_for_active_controllers(
            node, list_controllers, ListControllers.Request(), deadline
        )
        if not planner_action.wait_for_server(
            timeout_sec=max(0.0, deadline - time.monotonic())
        ) or not controller_action.wait_for_server(
            timeout_sec=max(0.0, deadline - time.monotonic())
        ):
            raise RuntimeError("trajectory action readiness timeout")
        _spin_until(
            node,
            lambda: tf_buffer.can_transform("world", "so101_tcp", Time()),
            deadline,
            "world to so101_tcp TF timeout",
        )
        planning_client = MoveItPlanningClient(
            planner_service,
            request_factory=make_get_motion_plan_request,
            progress=lambda: rclpy.spin_once(node, timeout_sec=0.01),
        )
        execution_client = (
            MoveItExecutionClient(
                planner_action,
                goal_factory=make_execute_goal,
                progress=lambda: rclpy.spin_once(node, timeout_sec=0.01),
            )
            if options.execute
            else None
        )
        before_evidence = None
        if not options.execute:
            before_evidence = _spin_until(
                node,
                lambda: _fresh_evidence(observer, EvidenceStale),
                deadline,
                "MuJoCo evidence timeout",
            )

        def pause_world(paused: bool) -> bool:
            requested_at = time.monotonic()
            if requested_at >= deadline:
                raise MujocoServiceError("pause request exceeded headless execution deadline")
            try:
                success = mujoco_client.pause(paused)
            except MujocoServiceError as error:
                pause_boundaries.append(
                    {
                        "requested_paused": paused,
                        "requested_monotonic_s": requested_at,
                        "completed_monotonic_s": time.monotonic(),
                        "success": False,
                        "error": str(error),
                    }
                )
                raise
            pause_boundaries.append(
                {
                    "requested_paused": paused,
                    "requested_monotonic_s": requested_at,
                    "completed_monotonic_s": time.monotonic(),
                    "success": success,
                }
            )
            if not success:
                raise MujocoServiceError(f"pause({paused}) returned failure")
            return True

        def capture_start() -> tuple[float, ...]:
            return _spin_until(
                node,
                lambda: _joint_positions(latest_joint_state, arm_joints),
                deadline,
                "complete arm joint state timeout",
            )

        def plan_from(start_positions: tuple[float, ...]):
            nonlocal before_evidence
            if options.execute:
                before_evidence = _fresh_evidence(observer, EvidenceStale)
                if before_evidence is None or not before_evidence.paused:
                    raise RuntimeError("planning start lacks authoritative paused evidence")
            assert before_evidence is not None
            emit_measurement("plan_request", before_evidence)
            outcome = planning_client.plan_joint_path(
                JointPlanRequest(
                    joint_names=arm_joints,
                    current_positions=start_positions,
                    target_positions=target,
                    velocity_scaling=float(configuration["velocity_scaling"]),
                    acceleration_scaling=float(configuration["acceleration_scaling"]),
                    planning_time_s=float(configuration["planning_time_s"]),
                    planning_group=configuration["planning_group"],
                    tcp_link=configuration["tcp_link"],
                ),
                timeout_s=max(0.1, deadline - time.monotonic()),
            )
            if outcome.failure is not None or outcome.trajectory is None:
                code = None if outcome.failure is None else outcome.failure.code
                raise RuntimeError(f"planning failed: {code}")
            response_evidence = _fresh_evidence(observer, EvidenceStale)
            emit_measurement("plan_response", response_evidence, outcome.trajectory)
            if options.execute:
                if response_evidence is None or not response_evidence.paused:
                    raise RuntimeError("MuJoCo resumed before planning completed")
                emit_measurement("pre_execute", response_evidence, outcome.trajectory)
            return outcome.trajectory

        def execute_trajectory(trajectory):
            assert execution_client is not None
            outcome = execution_client.execute(trajectory, max(0.1, deadline - time.monotonic()))
            if outcome.failure is not None:
                raise RuntimeError(f"execution failed: {outcome.failure.code}")
            return outcome

        before_positions, trajectory, execution = _run_motion_boundary(
            execute=options.execute,
            pause_world=pause_world,
            observe_evidence=lambda: _fresh_evidence(observer, EvidenceStale),
            capture_start=capture_start,
            plan=plan_from,
            execute_trajectory=execute_trajectory,
            progress=lambda: rclpy.spin_once(node, timeout_sec=0.01),
            monotonic=time.monotonic,
            deadline=deadline,
        )
        points = trajectory.joint_trajectory.points
        execution_succeeded = execution is not None
        controller_result = "SUCCEEDED" if execution_succeeded else "NOT_REQUESTED"

        tolerance = float(configuration["joint_convergence_tolerance_rad"])
        if options.execute:
            after_positions = _spin_until(
                node,
                lambda: _converged_positions(latest_joint_state, arm_joints, target, tolerance),
                deadline,
                "joint convergence timeout",
            )
        else:
            after_positions = _joint_positions(latest_joint_state, arm_joints) or before_positions
        after_evidence = _spin_until(
            node,
            lambda: _advanced_evidence(observer, before_evidence, EvidenceStale),
            deadline,
            "MuJoCo evidence did not advance",
        )
        maximum_target_error = max(
            abs(value - wanted) for value, wanted in zip(after_positions, target, strict=True)
        )
        maximum_motion = max(
            abs(value - before)
            for value, before in zip(after_positions, before_positions, strict=True)
        )
        if options.execute and maximum_motion < float(configuration["minimum_joint_motion_rad"]):
            raise RuntimeError("executed trajectory did not produce minimum joint movement")
        return {
            "schema_version": 1,
            "run_mode": options.run_mode,
            "execution_requested": bool(options.execute),
            "planning_group": configuration["planning_group"],
            "tcp_link": configuration["tcp_link"],
            "safe_pose": options.safe_pose,
            "ready": {
                "nodes": nodes,
                "topics": topics,
                "services": services,
                "actions": actions,
                "controllers": configuration["controller_mapping"],
                "controller_states": controller_states,
                "tf_world_to_tcp": True,
                "moveit_planning_group": configuration["planning_group"],
            },
            "plan": {"accepted": True, "trajectory_points": len(points)},
            "execution": {
                "goal_sent": bool(options.execute),
                "succeeded": execution_succeeded,
                "controller_result": controller_result,
            },
            "joint_state": {
                "before": dict(zip(arm_joints, before_positions, strict=True)),
                "after": dict(zip(arm_joints, after_positions, strict=True)),
                "target": dict(zip(arm_joints, target, strict=True)),
                "converged": bool(options.execute and maximum_target_error <= tolerance),
                "maximum_target_error_rad": maximum_target_error if options.execute else None,
                "maximum_motion_rad": maximum_motion,
            },
            "mujoco": {
                "session_id": options.simulation_session_id,
                "publisher_sequence_delta": (
                    after_evidence.publisher_sequence - before_evidence.publisher_sequence
                ),
                "simulation_step_delta": (
                    after_evidence.simulation_step - before_evidence.simulation_step
                ),
                "reset_epoch_before": before_evidence.reset_epoch,
                "reset_epoch_after": after_evidence.reset_epoch,
                "pause_boundaries": pause_boundaries,
            },
            "shutdown": {"launch_exit_code": None, "domain_nodes_after": None},
        }
    finally:
        print(
            "HEADLESS_BOUNDARY_RECORDS " + json.dumps(boundary_measurements, sort_keys=True),
            flush=True,
        )
        print(
            "HEADLESS_CONTROLLER_STATE_STREAM "
            + json.dumps(controller_state_stream, sort_keys=True),
            flush=True,
        )
        print(
            "HEADLESS_PAUSE_BOUNDARIES " + json.dumps(pause_boundaries, sort_keys=True),
            flush=True,
        )
        node.destroy_node()
        rclpy.shutdown()


def _fresh_evidence(observer: Any, stale_type: type[Exception]) -> Any | None:
    try:
        return observer.snapshot()
    except stale_type:
        return None


def _advanced_evidence(observer: Any, before: Any, stale_type: type[Exception]) -> Any | None:
    current = _fresh_evidence(observer, stale_type)
    if current is None:
        return None
    if (
        current.publisher_sequence <= before.publisher_sequence
        or current.simulation_step <= before.simulation_step
    ):
        return None
    return current


def _joint_positions(message: Any, joints: tuple[str, ...]) -> tuple[float, ...] | None:
    if message is None or len(message.name) != len(message.position):
        return None
    positions = dict(zip(message.name, message.position, strict=True))
    if any(name not in positions for name in joints):
        return None
    values = tuple(float(positions[name]) for name in joints)
    return values if all(math.isfinite(value) for value in values) else None


def _converged_positions(
    message: Any,
    joints: tuple[str, ...],
    target: tuple[float, ...],
    tolerance: float,
) -> tuple[float, ...] | None:
    values = _joint_positions(message, joints)
    if values is None:
        return None
    return (
        values
        if all(abs(value - wanted) <= tolerance for value, wanted in zip(values, target))
        else None
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-mode", choices=("dry_run", "execute"), default="dry_run")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--simulation-session-id", required=True)
    parser.add_argument("--safe-pose", default="task12_safe")
    parser.add_argument("--config", required=True)
    parser.add_argument("--evidence-file", required=True)
    parser.add_argument("--readiness-timeout-s", type=float, default=30.0)
    return parser


def strip_ros_arguments(arguments: list[str]) -> list[str]:
    if "--ros-args" not in arguments:
        return arguments
    return arguments[: arguments.index("--ros-args")]


def main(arguments: list[str] | None = None) -> int:
    application_arguments = sys.argv[1:] if arguments is None else arguments
    options = build_parser().parse_args(strip_ros_arguments(application_arguments))
    evidence_file = Path(options.evidence_file)
    try:
        summary = run_diagnostic(options)
    except Exception as error:
        _write_json(
            evidence_file,
            {
                "schema_version": 1,
                "run_mode": options.run_mode,
                "execution_requested": bool(options.execute),
                "error": f"{type(error).__name__}: {error}",
            },
        )
        print(f"HEADLESS_EXECUTION_FAILED {type(error).__name__}: {error}")
        return 1
    _write_json(evidence_file, summary)
    print(
        "HEADLESS_EXECUTION_OK "
        f"mode={options.run_mode} points={summary['plan']['trajectory_points']} "
        f"step_delta={summary['mujoco']['simulation_step_delta']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
