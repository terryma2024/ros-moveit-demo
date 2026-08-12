"""Gazebo-parity preopen and staged MoveIt approach for the MuJoCo task."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from so101_demo.application.scene_setup import scene_matches_task_geometry
from so101_demo.control.gripper.client import GripperClient
from so101_demo.control.moveit.planning import (
    JointPlanRequest,
    MoveItPlanningClient,
    make_get_motion_plan_request,
)
from so101_demo.control.trajectory.executor import MoveItExecutionClient, make_execute_goal

ARM_JOINTS = ("1", "2", "3", "4", "5")
ALL_JOINTS = (*ARM_JOINTS, "6")
APPROACH_PHASES = ("MOVE_ABOVE_OBJECT", "DESCEND")


@dataclass(frozen=True, slots=True)
class PhasePolicy:
    name: str
    waypoints: tuple[tuple[float, ...], ...]
    velocity_scaling: float
    acceleration_scaling: float


@dataclass(frozen=True, slots=True)
class StagedApproachPolicy:
    preopen_q6: float
    phases: tuple[PhasePolicy, ...]
    planning_time_s: float
    plan_timeout_s: float
    execute_timeout_s: float
    gripper_duration_s: float
    gripper_timeout_s: float
    stable_window_s: float
    stable_timeout_s: float
    joint_state_max_age_s: float
    max_joint_speed_rad_s: float
    max_position_span_rad: float
    plan_start_tolerance_rad: float
    convergence_tolerance_rad: float
    maximum_replans_per_segment: int
    maximum_receipt_age_s: float
    maximum_preclose_cup_displacement_m: float
    maximum_preclose_force_n: float


@dataclass(frozen=True, slots=True)
class JointObservation:
    received_monotonic_s: float
    positions: tuple[float, ...]
    velocities: tuple[float, ...]


class JointStabilityWindow:
    """Track a real-time joint window without using simulation pause."""

    def __init__(self, capacity: int = 512) -> None:
        self._samples: deque[JointObservation] = deque(maxlen=capacity)

    def append(self, sample: JointObservation) -> None:
        self._samples.append(sample)

    @property
    def latest(self) -> JointObservation | None:
        return self._samples[-1] if self._samples else None

    def stable(
        self,
        *,
        now_s: float,
        window_s: float,
        max_age_s: float,
        max_speed_rad_s: float,
        max_span_rad: float,
    ) -> bool:
        latest = self.latest
        if latest is None or not 0.0 <= now_s - latest.received_monotonic_s <= max_age_s:
            return False
        selected = tuple(
            sample
            for sample in self._samples
            if latest.received_monotonic_s - sample.received_monotonic_s <= window_s
        )
        if (
            len(selected) < 2
            or selected[-1].received_monotonic_s - selected[0].received_monotonic_s
            < 0.95 * window_s
        ):
            return False
        if any(
            abs(velocity) > max_speed_rad_s
            for sample in selected
            for velocity in sample.velocities[: len(ARM_JOINTS)]
        ):
            return False
        return all(
            max(sample.positions[index] for sample in selected)
            - min(sample.positions[index] for sample in selected)
            <= max_span_rad
            for index in range(len(ARM_JOINTS))
        )


def _positive(value: Any, name: str) -> float:
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return converted


def load_staged_policy(path: Path) -> tuple[StagedApproachPolicy, str]:
    raw = path.read_bytes()
    document = yaml.safe_load(raw)
    settings = document["staged_approach_execution"]
    if settings.get("pause_physics") is not False:
        raise ValueError("staged approach must keep MuJoCo physics running")
    if tuple(settings["phases"]) != APPROACH_PHASES:
        raise ValueError("staged approach phases must match the Gazebo lifecycle")
    phases: list[PhasePolicy] = []
    for name in APPROACH_PHASES:
        source = document["states"][name]
        waypoints = tuple(tuple(float(value) for value in item) for item in source["waypoints"])
        if not waypoints or any(len(item) != len(ARM_JOINTS) for item in waypoints):
            raise ValueError(f"{name} waypoint ladder is incomplete")
        phases.append(
            PhasePolicy(
                name,
                waypoints,
                _positive(source["velocity_scaling"], f"{name}.velocity_scaling"),
                _positive(source["acceleration_scaling"], f"{name}.acceleration_scaling"),
            )
        )
    replans = int(settings["maximum_replans_per_segment"])
    if replans < 0:
        raise ValueError("maximum_replans_per_segment must be non-negative")
    policy = StagedApproachPolicy(
        preopen_q6=float(document["gripper_actions"]["preopen_q6"]),
        phases=tuple(phases),
        planning_time_s=_positive(settings["planning_time_s"], "planning_time_s"),
        plan_timeout_s=_positive(settings["plan_timeout_s"], "plan_timeout_s"),
        execute_timeout_s=_positive(settings["execute_timeout_s"], "execute_timeout_s"),
        gripper_duration_s=_positive(settings["gripper_duration_s"], "gripper_duration_s"),
        gripper_timeout_s=_positive(settings["gripper_timeout_s"], "gripper_timeout_s"),
        stable_window_s=_positive(settings["stable_window_s"], "stable_window_s"),
        stable_timeout_s=_positive(settings["stable_timeout_s"], "stable_timeout_s"),
        joint_state_max_age_s=_positive(settings["joint_state_max_age_s"], "joint_state_max_age_s"),
        max_joint_speed_rad_s=_positive(settings["max_joint_speed_rad_s"], "max_joint_speed_rad_s"),
        max_position_span_rad=_positive(settings["max_position_span_rad"], "max_position_span_rad"),
        plan_start_tolerance_rad=_positive(
            settings["plan_start_tolerance_rad"], "plan_start_tolerance_rad"
        ),
        convergence_tolerance_rad=_positive(
            settings["convergence_tolerance_rad"], "convergence_tolerance_rad"
        ),
        maximum_replans_per_segment=replans,
        maximum_receipt_age_s=_positive(settings["maximum_receipt_age_s"], "maximum_receipt_age_s"),
        maximum_preclose_cup_displacement_m=_positive(
            settings["maximum_preclose_cup_displacement_m"],
            "maximum_preclose_cup_displacement_m",
        ),
        maximum_preclose_force_n=_positive(
            settings["maximum_preclose_force_n"], "maximum_preclose_force_n"
        ),
    )
    values = (
        policy.preopen_q6,
        *(value for phase in policy.phases for waypoint in phase.waypoints for value in waypoint),
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("staged approach policy contains nonfinite values")
    return policy, hashlib.sha256(raw).hexdigest()


def maximum_joint_error(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    if len(first) != len(second):
        return math.inf
    return max((abs(left - right) for left, right in zip(first, second, strict=True)), default=0.0)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _trajectory_positions(trajectory: Any, point_index: int) -> tuple[float, ...]:
    joint_trajectory = trajectory.joint_trajectory
    point = joint_trajectory.points[point_index]
    by_name = dict(zip(joint_trajectory.joint_names, point.positions, strict=True))
    return tuple(float(by_name[name]) for name in ARM_JOINTS)


def _with_open_gripper(trajectory: Any, q6: float) -> Any:
    value = copy.deepcopy(trajectory)
    if "6" in value.joint_trajectory.joint_names:
        return value
    value.joint_trajectory.joint_names.append("6")
    for point in value.joint_trajectory.points:
        point.positions.append(q6)
        if point.velocities:
            point.velocities.append(0.0)
        if point.accelerations:
            point.accelerations.append(0.0)
        if point.effort:
            point.effort.append(0.0)
    return value


def _gripper_display(start: tuple[float, ...], q6: float) -> Any:
    from builtin_interfaces.msg import Duration
    from moveit_msgs.msg import RobotTrajectory
    from trajectory_msgs.msg import JointTrajectoryPoint

    result = RobotTrajectory()
    result.joint_trajectory.joint_names = list(ALL_JOINTS)
    result.joint_trajectory.points = [
        JointTrajectoryPoint(positions=list(start)),
        JointTrajectoryPoint(
            positions=[*start[: len(ARM_JOINTS)], q6],
            time_from_start=Duration(sec=2),
        ),
    ]
    return result


def _evidence_summary(evidence: Any) -> dict[str, Any]:
    return {
        "publisher_sequence": evidence.publisher_sequence,
        "simulation_step": evidence.simulation_step,
        "reset_epoch": evidence.reset_epoch,
        "paused": evidence.paused,
        "cup_position_world_m": list(evidence.object_state.position_world),
        "left_contact_count": len(evidence.left_fingertip_contacts),
        "right_contact_count": len(evidence.right_fingertip_contacts),
        "other_contact_geoms": sorted(
            {contact.geom2 for contact in evidence.other_object_contacts}
        ),
        "maximum_normal_force_n": evidence.maximum_normal_force_n,
    }


def _assert_preclose_safe(evidence: Any, reference: Any, policy: StagedApproachPolicy) -> None:
    if evidence.paused:
        raise RuntimeError("MuJoCo physics paused during staged approach")
    if evidence.simulation_session_id != reference.simulation_session_id:
        raise RuntimeError("simulation session changed during staged approach")
    if evidence.reset_epoch != reference.reset_epoch:
        raise RuntimeError("reset epoch changed during staged approach")
    if evidence.left_fingertip_contacts or evidence.right_fingertip_contacts:
        raise RuntimeError("early fingertip contact before Close")
    forbidden = tuple(
        contact
        for contact in evidence.other_object_contacts
        if "table" not in contact.body2.lower() and "table" not in contact.geom2.lower()
    )
    if forbidden:
        raise RuntimeError("forbidden cup contact before Close")
    if (
        math.dist(evidence.object_state.position_world, reference.object_state.position_world)
        > policy.maximum_preclose_cup_displacement_m
    ):
        raise RuntimeError("cup moved before Close")
    if evidence.maximum_normal_force_n > policy.maximum_preclose_force_n:
        raise RuntimeError("pre-Close force boundary exceeded")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="staged_approach")
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--mode", choices=("plan_only", "execute"), default="plan_only")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--stop-after", choices=APPROACH_PHASES, default="DESCEND")
    parser.add_argument("--simulation-session-id", required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    parser.add_argument("--hold-seconds", type=float, default=0.0)
    return parser


def _default_policy_path() -> Path:
    from ament_index_python.packages import get_package_share_directory

    return (
        Path(get_package_share_directory("so101_demo_py"))
        / "config/motion_policies/light_cup_wall_pick.yaml"
    )


def run_ros(options: argparse.Namespace) -> dict[str, Any]:
    import rclpy
    from control_msgs.action import FollowJointTrajectory
    from moveit_msgs.action import ExecuteTrajectory
    from moveit_msgs.msg import DisplayTrajectory, PlanningSceneComponents, RobotState
    from moveit_msgs.srv import GetMotionPlan, GetPlanningScene
    from rclpy.action import ActionClient
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
    from sensor_msgs.msg import JointState
    from so101_demo.backends.mujoco.observer import EvidenceStale, MujocoWorldObserver

    if options.execute != (options.mode == "execute"):
        raise RuntimeError("execute mode requires the explicit --execute gate")
    policy_path = options.policy or _default_policy_path()
    policy, policy_sha256 = load_staged_policy(policy_path)
    result: dict[str, Any] = {
        "schema_version": 1,
        "mode": options.mode,
        "stop_after": options.stop_after,
        "policy_path": str(policy_path),
        "policy_sha256": policy_sha256,
        "simulation_session_id": options.simulation_session_id,
        "physics_paused_calls": 0,
        "close_gripper_calls": 0,
        "segments": [],
        "status": "RUNNING",
    }
    rclpy.init()
    node = rclpy.create_node("so101_staged_approach")
    window = JointStabilityWindow()

    def accept_joint_state(message: JointState) -> None:
        if len(message.name) != len(message.position) or len(set(message.name)) != len(
            message.name
        ):
            return
        by_name = dict(zip(message.name, message.position, strict=True))
        if any(name not in by_name for name in ALL_JOINTS):
            return
        positions = tuple(float(by_name[name]) for name in ALL_JOINTS)
        if len(message.velocity) == len(message.name):
            velocity_by_name = dict(zip(message.name, message.velocity, strict=True))
            velocities = tuple(float(velocity_by_name[name]) for name in ALL_JOINTS)
        else:
            previous = window.latest
            now = time.monotonic()
            if previous is None or now <= previous.received_monotonic_s:
                velocities = (math.inf,) * len(ALL_JOINTS)
            else:
                elapsed = now - previous.received_monotonic_s
                velocities = tuple(
                    (value - prior) / elapsed
                    for value, prior in zip(positions, previous.positions, strict=True)
                )
            window.append(JointObservation(now, positions, velocities))
            return
        window.append(JointObservation(time.monotonic(), positions, velocities))

    joint_subscription = node.create_subscription(
        JointState, "/joint_states", accept_joint_state, qos_profile_sensor_data
    )
    del joint_subscription
    observer = MujocoWorldObserver(
        node,
        options.simulation_session_id,
        max_age_s=policy.maximum_receipt_age_s,
    )
    planning_service = node.create_client(GetMotionPlan, "/plan_kinematic_path")
    scene_service = node.create_client(GetPlanningScene, "/get_planning_scene")
    execute_action = ActionClient(node, ExecuteTrajectory, "/execute_trajectory")
    gripper_action = ActionClient(
        node, FollowJointTrajectory, "/gripper_controller/follow_joint_trajectory"
    )
    publisher = node.create_publisher(
        DisplayTrajectory,
        "/display_planned_path",
        QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        ),
    )

    def progress() -> None:
        rclpy.spin_once(node, timeout_sec=0.01)

    planning_client = MoveItPlanningClient(
        planning_service,
        request_factory=make_get_motion_plan_request,
        progress=progress,
    )
    execution_client = MoveItExecutionClient(
        execute_action,
        goal_factory=make_execute_goal,
        progress=progress,
    )
    gripper_client = GripperClient(gripper_action, progress=progress)

    def spin_until(predicate, timeout_s: float, message: str):
        deadline = time.monotonic() + timeout_s
        while rclpy.ok() and time.monotonic() < deadline:
            value = predicate()
            if value is not None and value is not False:
                return value
            progress()
        raise RuntimeError(message)

    def fresh_evidence():
        try:
            return observer.snapshot()
        except EvidenceStale:
            return None

    def stable_observation() -> JointObservation | None:
        if window.stable(
            now_s=time.monotonic(),
            window_s=policy.stable_window_s,
            max_age_s=policy.joint_state_max_age_s,
            max_speed_rad_s=policy.max_joint_speed_rad_s,
            max_span_rad=policy.max_position_span_rad,
        ):
            return window.latest
        return None

    def wait_stable() -> JointObservation:
        return spin_until(
            stable_observation,
            policy.stable_timeout_s,
            "joint stability window timeout",
        )

    display = DisplayTrajectory()
    display.model_id = "so101"
    try:
        if not planning_service.wait_for_service(timeout_sec=30.0):
            raise RuntimeError("/plan_kinematic_path unavailable")
        if not scene_service.wait_for_service(timeout_sec=30.0):
            raise RuntimeError("/get_planning_scene unavailable")
        scene_request = GetPlanningScene.Request()
        scene_request.components.components = (
            PlanningSceneComponents.WORLD_OBJECT_NAMES
            | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
            | PlanningSceneComponents.OBJECT_COLORS
        )
        scene_future = scene_service.call_async(scene_request)
        spin_until(lambda: scene_future.done(), 15.0, "Planning Scene query timeout")
        scene_response = scene_future.result()
        if scene_response is None or not scene_matches_task_geometry(scene_response.scene):
            raise RuntimeError("Planning Scene geometry is incomplete")
        result["planning_scene_verified"] = True

        initial_joints = wait_stable()
        reference_evidence = spin_until(fresh_evidence, 10.0, "fresh MuJoCo evidence timeout")
        _assert_preclose_safe(reference_evidence, reference_evidence, policy)
        result["initial_joint_positions_rad"] = list(initial_joints.positions)
        result["initial_evidence"] = _evidence_summary(reference_evidence)
        display.trajectory_start = RobotState(
            joint_state=JointState(
                name=list(ALL_JOINTS),
                position=list(initial_joints.positions),
            )
        )
        display.trajectory.append(_gripper_display(initial_joints.positions, policy.preopen_q6))
        publisher.publish(display)

        if options.mode == "execute":
            gripper_result = gripper_client.command(
                policy.preopen_q6,
                policy.gripper_duration_s,
                policy.gripper_timeout_s,
            )
            if gripper_result.failure is not None:
                raise RuntimeError(f"preopen failed: {gripper_result.failure.code}")
            opened = spin_until(
                lambda: (
                    window.latest
                    if window.latest is not None
                    and abs(window.latest.positions[-1] - policy.preopen_q6)
                    <= policy.convergence_tolerance_rad
                    else None
                ),
                policy.stable_timeout_s,
                "preopen convergence timeout",
            )
            wait_stable()
            result["preopen_actual_q6_rad"] = opened.positions[-1]
        else:
            result["preopen_actual_q6_rad"] = None

        synthetic_current = (*initial_joints.positions[: len(ARM_JOINTS)], policy.preopen_q6)
        stop_index = APPROACH_PHASES.index(options.stop_after)
        for phase_index, phase in enumerate(policy.phases):
            if phase_index > stop_index:
                break
            for waypoint_index, target in enumerate(phase.waypoints):
                segment: dict[str, Any] = {
                    "phase": phase.name,
                    "waypoint_index": waypoint_index,
                    "target_arm_rad": list(target),
                    "attempts": [],
                }
                selected = None
                for attempt_index in range(policy.maximum_replans_per_segment + 1):
                    if options.mode == "execute":
                        start = wait_stable()
                        current = start.positions
                        evidence = spin_until(
                            fresh_evidence, 2.0, "fresh pre-plan MuJoCo evidence timeout"
                        )
                        _assert_preclose_safe(evidence, reference_evidence, policy)
                    else:
                        current = synthetic_current
                    arm_start = current[: len(ARM_JOINTS)]
                    outcome = planning_client.plan_joint_path(
                        JointPlanRequest(
                            joint_names=ARM_JOINTS,
                            current_positions=arm_start,
                            target_positions=target,
                            velocity_scaling=phase.velocity_scaling,
                            acceleration_scaling=phase.acceleration_scaling,
                            planning_time_s=policy.planning_time_s,
                            start_state_joint_names=ALL_JOINTS,
                            start_state_positions=current,
                        ),
                        timeout_s=policy.plan_timeout_s,
                    )
                    attempt: dict[str, Any] = {
                        "attempt": attempt_index + 1,
                        "plan_start_arm_rad": list(arm_start),
                    }
                    if outcome.failure is not None or outcome.trajectory is None:
                        attempt["planning_failure"] = (
                            "EMPTY" if outcome.failure is None else outcome.failure.code
                        )
                        segment["attempts"].append(attempt)
                        continue
                    trajectory = outcome.trajectory
                    first = _trajectory_positions(trajectory, 0)
                    endpoint = _trajectory_positions(trajectory, -1)
                    attempt.update(
                        {
                            "trajectory_points": len(trajectory.joint_trajectory.points),
                            "trajectory_start_arm_rad": list(first),
                            "trajectory_endpoint_arm_rad": list(endpoint),
                            "endpoint_error_rad": maximum_joint_error(endpoint, target),
                        }
                    )
                    if attempt["endpoint_error_rad"] > policy.convergence_tolerance_rad:
                        attempt["planning_failure"] = "TRAJECTORY_ENDPOINT_MISMATCH"
                        segment["attempts"].append(attempt)
                        continue
                    if options.mode == "execute":
                        handoff = window.latest
                        if handoff is None:
                            attempt["planning_failure"] = "JOINT_STATE_MISSING_AT_HANDOFF"
                            segment["attempts"].append(attempt)
                            continue
                        drift = maximum_joint_error(handoff.positions[: len(ARM_JOINTS)], first)
                        attempt["plan_to_execute_drift_rad"] = drift
                        if drift > policy.plan_start_tolerance_rad:
                            attempt["planning_failure"] = "PLAN_TO_EXECUTE_DRIFT"
                            segment["attempts"].append(attempt)
                            continue
                    segment["attempts"].append(attempt)
                    selected = trajectory
                    break
                if selected is None:
                    result["segments"].append(segment)
                    raise RuntimeError(f"bounded planning failed at {phase.name}[{waypoint_index}]")
                display.trajectory.append(_with_open_gripper(selected, policy.preopen_q6))
                publisher.publish(display)
                if options.mode == "execute":

                    def monitor() -> None:
                        evidence = fresh_evidence()
                        if evidence is None:
                            raise RuntimeError("stale MuJoCo evidence during execution")
                        _assert_preclose_safe(evidence, reference_evidence, policy)

                    executed = execution_client.execute(
                        selected,
                        policy.execute_timeout_s,
                        monitor=monitor,
                    )
                    if executed.failure is not None:
                        segment["execution_failure"] = executed.failure.code
                        result["segments"].append(segment)
                        raise RuntimeError(f"execution failed: {executed.failure.code}")
                    converged = spin_until(
                        lambda: (
                            window.latest
                            if window.latest is not None
                            and maximum_joint_error(
                                window.latest.positions[: len(ARM_JOINTS)], target
                            )
                            <= policy.convergence_tolerance_rad
                            else None
                        ),
                        policy.stable_timeout_s,
                        f"convergence timeout at {phase.name}[{waypoint_index}]",
                    )
                    wait_stable()
                    final_evidence = spin_until(
                        fresh_evidence, 2.0, "fresh post-execute MuJoCo evidence timeout"
                    )
                    _assert_preclose_safe(final_evidence, reference_evidence, policy)
                    segment["execution_succeeded"] = True
                    segment["actual_endpoint_arm_rad"] = list(
                        converged.positions[: len(ARM_JOINTS)]
                    )
                    segment["actual_endpoint_error_rad"] = maximum_joint_error(
                        converged.positions[: len(ARM_JOINTS)], target
                    )
                    segment["post_execute_evidence"] = _evidence_summary(final_evidence)
                    synthetic_current = converged.positions
                else:
                    segment["execution_succeeded"] = False
                    synthetic_current = (*target, policy.preopen_q6)
                result["segments"].append(segment)
                _atomic_json(options.evidence_file, result)
                print(
                    f"STAGED_APPROACH phase={phase.name} waypoint={waypoint_index} "
                    f"mode={options.mode} selected=true",
                    flush=True,
                )

        result["status"] = "CLOSE_READY"
        result["completed_phase"] = options.stop_after
        result["selected_segments"] = len(result["segments"])
        result["final_joint_positions_rad"] = list(synthetic_current)
        result["close_gripper_calls"] = 0
        _atomic_json(options.evidence_file, result)
        print(
            f"STAGED_APPROACH_OK status=CLOSE_READY segments={len(result['segments'])}",
            flush=True,
        )
        hold_deadline = time.monotonic() + max(0.0, options.hold_seconds)
        while rclpy.ok() and time.monotonic() < hold_deadline:
            publisher.publish(display)
            rclpy.spin_once(node, timeout_sec=0.2)
        return result
    except Exception as error:
        result["status"] = "FAILED"
        result["error"] = f"{type(error).__name__}: {error}"
        _atomic_json(options.evidence_file, result)
        raise
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main(arguments: list[str] | None = None) -> int:
    options = _build_parser().parse_args(arguments)
    try:
        run_ros(options)
    except Exception as error:
        print(f"STAGED_APPROACH_FAILED {type(error).__name__}: {error}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
