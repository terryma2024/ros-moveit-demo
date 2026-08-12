#!/usr/bin/env python3
"""production live phase: execute the five formal MOVE_ABOVE_PLACE waypoints."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import asdict
from pathlib import Path

import rclpy
from moveit_msgs.action import ExecuteTrajectory
from moveit_msgs.msg import PlanningSceneComponents
from moveit_msgs.srv import GetMotionPlan, GetPlanningScene
from rclpy.action import ActionClient
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState

from so101_mujoco_demo_py.dynamic_transport_evidence import (
    AtomicTransportEvidenceStore,
    ContactForceMode,
    analyze_dynamic_transport,
)
from so101_mujoco_demo_py.live_runtime import load_live_task_policy
from so101_mujoco_demo_py.motion.executor import (
    MoveItExecutionClient,
    SustainedConditionGuard,
    make_execute_goal,
)
from so101_mujoco_demo_py.moveit.planning import (
    JointPlanRequest,
    MoveItPlanningClient,
    make_get_motion_plan_request,
)
from so101_mujoco_demo_py.mujoco.observer import EvidenceStale, MujocoWorldObserver
from so101_mujoco_demo_py.mujoco.transport_observer import (
    BoundaryActionClient,
    DynamicTransportEvidenceObserver,
    EvidenceInvalid,
    check_force,
    publisher_provenance,
)
from so101_mujoco_demo_py.staged_approach import maximum_joint_error

SESSION_ID = os.environ["SO101_SIMULATION_SESSION_ID"]
EXPECTED_EPOCH = int(os.environ["SO101_EXPECTED_RESET_EPOCH"])
EVIDENCE_PATH = Path(os.environ["SO101_EVIDENCE_ROOT"]) / "transport.json"
DYNAMIC_RAW_ROOT = EVIDENCE_PATH.parent / "transport-dynamic-raw"
DYNAMIC_SUMMARY_PATH = EVIDENCE_PATH.parent / "transport-dynamic-summary.json"
ARM_JOINTS = ("1", "2", "3", "4", "5")
ALL_JOINTS = (*ARM_JOINTS, "6")
EXPECTED_START_ARM = (
    -0.00031950472111697334,
    0.2015600757345103,
    0.1299877504869264,
    1.2401457978939827,
    -0.00027049232842978966,
)
EXPECTED_Q6 = -0.048510207270894154
TARGETS = (
    (0.078649232242, 0.202916192985, 0.125650124859, 1.227082691882, 0.000085728349),
    (0.157580578693, 0.204866593526, 0.121644794912, 1.213983979051, 0.000461011907),
    (0.236511925143, 0.206816994066, 0.117639464964, 1.200885266221, 0.000836295464),
    (0.315443271594, 0.208767394607, 0.113634135017, 1.187786553390, 0.001211579022),
    (0.394374618045, 0.210717795147, 0.109628805069, 1.174687840559, 0.001586862580),
)
CONTACT_LOSS_GRACE_S = 0.05
MAX_SEGMENT_CUP_DISPLACEMENT_M = 0.04
MIN_TOTAL_LATERAL_M = 0.06
MAX_TOTAL_LATERAL_M = 0.12
MAX_TOTAL_VERTICAL_CHANGE_M = 0.03
DIAGNOSTIC_HARD_STOP_FORCE_N = 11.60
MAXIMUM_REACTION_STEPS = 25
PHYSICS_TIMESTEP_S = 0.002


def atomic_write(document: dict, path: Path = EVIDENCE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_dict(value) -> dict:
    return {
        "publisher_sequence": value.publisher_sequence,
        "simulation_step": value.simulation_step,
        "reset_epoch": value.reset_epoch,
        "paused": value.paused,
        "cup_position_world_m": list(value.object_state.position_world),
        "left_contact_count": len(value.left_fingertip_contacts),
        "right_contact_count": len(value.right_fingertip_contacts),
        "other_contact_geoms": sorted({item.geom2 for item in value.other_object_contacts}),
        "maximum_normal_force_n": value.maximum_normal_force_n,
    }


def main() -> int:
    task_policy = load_live_task_policy()
    assert task_policy.contact is not None
    maximum_safe_force_n = task_policy.contact.thresholds.maximum_safe_force_n
    result = {
        "schema": "so101-live-noslip-transport-v1",
        "simulation_session_id": SESSION_ID,
        "targets_arm_rad": [list(target) for target in TARGETS],
        "physics_pause_calls": 0,
        "simulator_constraint_calls": 0,
        "direct_object_state_writes": 0,
        "status": "RUNNING",
        "segments": [],
    }
    rclpy.init()
    node = rclpy.create_node("so101_live_transport")
    latest_joint: dict[str, float] = {}

    def on_joints(message: JointState) -> None:
        if len(message.name) == len(message.position):
            latest_joint.update(zip(message.name, message.position, strict=True))

    subscription = node.create_subscription(
        JointState, "/joint_states", on_joints, qos_profile_sensor_data
    )
    observer = MujocoWorldObserver(node, SESSION_ID, max_age_s=0.5)
    planning_service = node.create_client(GetMotionPlan, "/plan_kinematic_path")
    get_scene = node.create_client(GetPlanningScene, "/get_planning_scene")
    execute_action = ActionClient(node, ExecuteTrajectory, "/execute_trajectory")
    dynamic_observer = DynamicTransportEvidenceObserver(
        node=node,
        simulation_session_id=SESSION_ID,
        reset_epoch=EXPECTED_EPOCH,
        store=AtomicTransportEvidenceStore(DYNAMIC_RAW_ROOT, run_id=SESSION_ID),
        maximum_reaction_steps=MAXIMUM_REACTION_STEPS,
    )

    def progress() -> None:
        rclpy.spin_once(node, timeout_sec=0.01)

    def wait_for(predicate, timeout_s: float, message: str):
        deadline = time.monotonic() + timeout_s
        while rclpy.ok() and time.monotonic() < deadline:
            value = predicate()
            if value is not None and value is not False:
                return value
            progress()
        raise RuntimeError(message)

    def snapshot():
        try:
            return observer.snapshot()
        except EvidenceStale:
            return None

    def stable_bilateral(
        epoch: int,
        mode: ContactForceMode,
        duration_s: float = 0.20,
    ):
        start: float | None = None
        last_sequence = -1
        latest = None
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            progress()
            evidence = snapshot()
            if evidence is None or evidence.publisher_sequence == last_sequence:
                continue
            last_sequence = evidence.publisher_sequence
            if evidence.paused or evidence.reset_epoch != epoch:
                raise RuntimeError("MuJoCo pause/reset during bilateral gate")
            force = check_force(
                evidence.maximum_normal_force_n,
                mode,
                static_threshold_n=maximum_safe_force_n,
                diagnostic_stop_n=DIAGNOSTIC_HARD_STOP_FORCE_N,
            )
            if force.cancel:
                raise RuntimeError(force.reason)
            if dynamic_observer.invalid_reason is not None:
                raise RuntimeError(dynamic_observer.invalid_reason)
            if dynamic_observer.hazard is not None:
                raise RuntimeError("diagnostic hazard latch received")
            if any(item.geom2 == "table_collision" for item in evidence.other_object_contacts):
                raise RuntimeError("cup regained table support")
            bilateral = bool(evidence.left_fingertip_contacts and evidence.right_fingertip_contacts)
            now = time.monotonic()
            start = start if bilateral and start is not None else (now if bilateral else None)
            latest = evidence
            if start is not None and now - start >= duration_s:
                return latest
        raise RuntimeError("stable bilateral fingertip contact timeout")

    try:
        for client, name in (
            (planning_service, "/plan_kinematic_path"),
            (get_scene, "/get_planning_scene"),
        ):
            if not client.wait_for_service(timeout_sec=20.0):
                raise RuntimeError(f"{name} unavailable")
        if not execute_action.wait_for_server(timeout_sec=20.0):
            raise RuntimeError("execute action unavailable")

        def evidence_publishers():
            provenance = {
                "snapshot": publisher_provenance(
                    node,
                    topic="/so101/simulation/evidence",
                    message_kind="SimulationEvidence",
                ),
                "physics_step_chunk": publisher_provenance(
                    node,
                    topic="/so101/simulation/physics_step_chunks",
                    message_kind="PhysicsStepEvidenceChunk",
                ),
            }
            if all(item["publisher_count"] > 0 for item in provenance.values()):
                return provenance
            return None

        provenance = wait_for(
            evidence_publishers,
            5.0,
            "simulation evidence publishers unavailable",
        )
        result["publisher_provenance"] = provenance
        result["observer_expected_session_id"] = SESSION_ID
        dynamic_observer.checkpoint_producer_provenance(provenance)
        atomic_write(result)
        if any(item["publisher_count"] != 1 for item in provenance.values()):
            raise RuntimeError("simulation evidence publisher count is not exactly one per topic")
        wait_for(lambda: len(latest_joint) == 6, 5.0, "joint state unavailable")
        before = wait_for(snapshot, 5.0, "MuJoCo evidence unavailable")
        result["first_snapshot_session_id"] = before.simulation_session_id
        dynamic_observer.checkpoint_snapshot_session(before.simulation_session_id)
        atomic_write(result)
        if before.paused or before.reset_epoch != EXPECTED_EPOCH:
            raise RuntimeError("unexpected initial MuJoCo provenance")
        start_positions = tuple(float(latest_joint[name]) for name in ALL_JOINTS)
        if maximum_joint_error(start_positions[:5], EXPECTED_START_ARM) > 0.01:
            raise RuntimeError("robot is not at the verified EXP-105 endpoint")
        if abs(start_positions[-1] - EXPECTED_Q6) > 0.002:
            raise RuntimeError("q6 is not at the verified EXP-104 endpoint")
        stable = stable_bilateral(
            before.reset_epoch,
            ContactForceMode.PRE_TRANSPORT_STATIC_HOLD,
        )
        initial_cup = tuple(stable.object_state.position_world)
        result["before_joints_rad"] = list(start_positions)
        result["before_evidence"] = evidence_dict(stable)

        query = GetPlanningScene.Request()
        query.components.components = PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
        queried = get_scene.call_async(query)
        wait_for(lambda: queried.done(), 3.0, "MoveIt attach readback timeout")
        response = queried.result()
        attached_ids = (
            []
            if response is None
            else [item.object.id for item in response.scene.robot_state.attached_collision_objects]
        )
        if "plastic_cup" not in attached_ids:
            raise RuntimeError("MoveIt collision shadow is not attached")
        result["moveit_attached_ids"] = attached_ids
        atomic_write(result)

        planning = MoveItPlanningClient(
            planning_service,
            request_factory=make_get_motion_plan_request,
            progress=progress,
        )
        previous_cup = initial_cup
        for index, target in enumerate(TARGETS, start=1):
            current = tuple(float(latest_joint[name]) for name in ALL_JOINTS)
            planned = planning.plan_joint_path(
                JointPlanRequest(
                    joint_names=ARM_JOINTS,
                    current_positions=current[:5],
                    target_positions=target,
                    velocity_scaling=0.05,
                    acceleration_scaling=0.05,
                    planning_time_s=5.0,
                    start_state_joint_names=ALL_JOINTS,
                    start_state_positions=current,
                ),
                timeout_s=12.0,
            )
            if planned.failure is not None or planned.trajectory is None:
                code = "EMPTY" if planned.failure is None else planned.failure.code
                raise RuntimeError(f"transport waypoint {index} planning failed: {code}")
            trajectory_start = tuple(
                float(value) for value in planned.trajectory.joint_trajectory.points[0].positions
            )
            handoff = tuple(float(latest_joint[name]) for name in ARM_JOINTS)
            drift = maximum_joint_error(handoff, trajectory_start)
            if drift > 0.01:
                raise RuntimeError(f"transport waypoint {index} plan drift exceeded")

            contact_guard = SustainedConditionGuard(CONTACT_LOSS_GRACE_S)

            def monitor() -> None:
                evidence = snapshot()
                if evidence is None:
                    raise RuntimeError("stale MuJoCo evidence during transport")
                if evidence.paused or evidence.reset_epoch != before.reset_epoch:
                    raise RuntimeError("MuJoCo pause/reset during transport")
                force = check_force(
                    evidence.maximum_normal_force_n,
                    ContactForceMode.DYNAMIC_TRANSPORT_SHADOW,
                    static_threshold_n=maximum_safe_force_n,
                    diagnostic_stop_n=DIAGNOSTIC_HARD_STOP_FORCE_N,
                )
                if force.diagnostic_hazard_breached:
                    raise RuntimeError(force.reason)
                if dynamic_observer.invalid_reason is not None:
                    raise RuntimeError(dynamic_observer.invalid_reason)
                if dynamic_observer.hazard is not None:
                    raise RuntimeError("diagnostic hazard latch received")
                contact_guard.require(
                    bool(evidence.left_fingertip_contacts and evidence.right_fingertip_contacts),
                    "bilateral contact lost during transport",
                )
                if any(item.geom2 == "table_collision" for item in evidence.other_object_contacts):
                    raise RuntimeError("cup regained table support during transport")

            def goal_dispatched() -> None:
                try:
                    if index > 1:
                        dynamic_observer.mark_waypoint_complete(waypoint=index - 1)
                    dynamic_observer.mark_goal_dispatched(waypoint=index)
                except EvidenceInvalid as error:
                    dynamic_observer.record_invalid(error)

            def cancellation_requested() -> None:
                try:
                    dynamic_observer.publish_cancellation_request()
                except EvidenceInvalid as error:
                    dynamic_observer.record_invalid(error)

            execution = MoveItExecutionClient(
                BoundaryActionClient(
                    execute_action,
                    on_goal_dispatched=goal_dispatched,
                    on_cancellation_requested=cancellation_requested,
                ),
                goal_factory=make_execute_goal,
                progress=progress,
            ).execute(
                planned.trajectory,
                45.0,
                monitor=monitor,
            )
            if execution.failure is not None:
                if dynamic_observer.hazard is not None:
                    ack_deadline = time.monotonic() + 1.0
                    while (
                        dynamic_observer.cancellation_request_upper_bound_step is None
                        and dynamic_observer.invalid_reason is None
                        and time.monotonic() < ack_deadline
                    ):
                        progress()
                    if (
                        dynamic_observer.cancellation_request_upper_bound_step is None
                        and dynamic_observer.invalid_reason is None
                    ):
                        dynamic_observer.record_invalid(
                            EvidenceInvalid("cancellation request physics-step ack timeout")
                        )
                    if dynamic_observer.invalid_reason is None:
                        status = "VALID_SAFETY_ABORT"
                        partial_index = dynamic_observer.close_safety_abort()
                    else:
                        status = "INVALID"
                        partial_index = dynamic_observer.close_invalid_abort()
                    result.update(
                        {
                            "status": status,
                            "outcome_class": status,
                            "dynamic_raw_index": str(partial_index),
                            "dynamic_raw_index_sha256": sha256_file(partial_index),
                        }
                    )
                    atomic_write(result)
                    return 2
                raise RuntimeError(
                    f"transport waypoint {index} execution failed: "
                    f"{execution.failure.code}: {execution.failure.message}"
                )
            wait_for(
                lambda: (
                    tuple(float(latest_joint[name]) for name in ARM_JOINTS)
                    if maximum_joint_error(
                        tuple(float(latest_joint[name]) for name in ARM_JOINTS),
                        target,
                    )
                    <= 0.01
                    else None
                ),
                10.0,
                f"transport waypoint {index} endpoint timeout",
            )
            after = stable_bilateral(
                before.reset_epoch,
                ContactForceMode.DYNAMIC_TRANSPORT_SHADOW,
            )
            cup = tuple(after.object_state.position_world)
            segment_displacement = math.dist(cup, previous_cup)
            if segment_displacement > MAX_SEGMENT_CUP_DISPLACEMENT_M:
                raise RuntimeError(f"transport waypoint {index} cup displacement exceeded")
            result["segments"].append(
                {
                    "waypoint": index,
                    "trajectory_points": len(planned.trajectory.joint_trajectory.points),
                    "plan_to_execute_drift_rad": drift,
                    "terminal_joints_rad": [float(latest_joint[name]) for name in ALL_JOINTS],
                    "terminal_evidence": evidence_dict(after),
                    "segment_cup_displacement_m": segment_displacement,
                }
            )
            atomic_write(result)
            previous_cup = cup

        terminal = tuple(result["segments"][-1]["terminal_evidence"]["cup_position_world_m"])
        total_vertical_change = terminal[2] - initial_cup[2]
        total_lateral = math.hypot(terminal[0] - initial_cup[0], terminal[1] - initial_cup[1])
        if abs(total_vertical_change) > MAX_TOTAL_VERTICAL_CHANGE_M:
            raise RuntimeError("transport total vertical change exceeded")
        if not MIN_TOTAL_LATERAL_M <= total_lateral <= MAX_TOTAL_LATERAL_M:
            raise RuntimeError("transport total lateral displacement outside gate")
        dynamic_observer.mark_waypoint_complete(waypoint=len(TARGETS))
        dynamic_observer.mark_phase_complete(waypoint=len(TARGETS))
        transport_outcome = "FORMAL_MOVE_ABOVE_PLACE_PROVED"
        summary = analyze_dynamic_transport(
            dynamic_observer.build_run(
                physics_timestep_s=PHYSICS_TIMESTEP_S,
                physical_transport_outcome=transport_outcome,
            ),
            shadow_force_n=maximum_safe_force_n,
        )
        atomic_write(asdict(summary), DYNAMIC_SUMMARY_PATH)
        dynamic_index = dynamic_observer.close_success(physical_transport_outcome=transport_outcome)
        result.update(
            {
                "status": transport_outcome,
                "total_vertical_change_m": total_vertical_change,
                "total_lateral_displacement_m": total_lateral,
                "dynamic_raw_index": str(dynamic_index),
                "dynamic_raw_index_sha256": sha256_file(dynamic_index),
                "dynamic_summary": str(DYNAMIC_SUMMARY_PATH),
                "dynamic_summary_sha256": sha256_file(DYNAMIC_SUMMARY_PATH),
            }
        )
        atomic_write(result)
        print(
            f"EXP106_OK dz_m={total_vertical_change:.9f} lateral_m={total_lateral:.9f} "
            f"segments={len(TARGETS)}",
            flush=True,
        )
        return 0
    except Exception as error:
        result["status"] = "FAILED"
        result["error"] = f"{type(error).__name__}: {error}"
        result["observer_expected_session_id"] = SESSION_ID
        result["observer_last_received_session_id"] = (
            dynamic_observer.first_snapshot_session_id
        )
        try:
            partial_index = dynamic_observer.close_invalid(error)
            result["dynamic_raw_index"] = str(partial_index)
            result["dynamic_raw_index_sha256"] = sha256_file(partial_index)
        except Exception as close_error:
            result["dynamic_raw_close_error"] = f"{type(close_error).__name__}: {close_error}"
        atomic_write(result)
        print(f"EXP106_FAILED {type(error).__name__}: {error}", flush=True)
        return 1
    finally:
        del subscription
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
