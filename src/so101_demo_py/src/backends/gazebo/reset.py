"""Gazebo implementations of the complete transactional reset ports."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from ...application.transactional_reset import TransactionalResetCoordinator
from ...control.moveit.planning import JointPlanRequest
from ...core.domain import ActionStatus
from ...core.task_geometry import Pose7, TaskGeometry
from ...ports.reset import (
    HomePlanReceipt,
    ResetStepReceipt,
    TransactionalResetPorts,
    TransactionalResetReceipt,
    TransactionalResetRequest,
)
from ...ports.world import ResetReceipt


def _pose_matches(expected: Pose7, actual: Pose7, tolerance: float = 1e-5) -> bool:
    position_match = all(
        math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)
        for left, right in zip(expected.values[:3], actual.values[:3], strict=True)
    )
    direct = all(
        math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)
        for left, right in zip(expected.values[3:], actual.values[3:], strict=True)
    )
    negated = all(
        math.isclose(left, -right, rel_tol=0.0, abs_tol=tolerance)
        for left, right in zip(expected.values[3:], actual.values[3:], strict=True)
    )
    return position_match and (direct or negated)


class GazeboPhysicalResetPort:
    def __init__(
        self,
        commands: Any,
        *,
        observe_attachment,
        observe_pose,
        timeout_s: float,
        clock=time.monotonic,
        wait=time.sleep,
    ) -> None:
        self._commands = commands
        self._observe_attachment = observe_attachment
        self._observe_pose = observe_pose
        self._timeout_s = timeout_s
        self._clock = clock
        self._wait = wait

    def _converge(self, predicate, failure_code: str) -> ResetStepReceipt:
        deadline = self._clock() + self._timeout_s
        latest = None
        while self._clock() < deadline:
            latest = predicate()
            if latest is True:
                return ResetStepReceipt(True, None, {"converged": True})
            self._wait(min(0.01, self._timeout_s))
        return ResetStepReceipt(False, failure_code, {"last_observation": latest})

    def detach_task_object(self) -> ResetStepReceipt:
        command = self._commands.request_detach()
        if not command.success:
            return command
        verified = self._converge(
            lambda: not bool(self._observe_attachment()),
            "RESET_GAZEBO_DETACH_VERIFY_FAILED",
        )
        return ResetStepReceipt(
            verified.success,
            verified.failure_code,
            {"command": command.evidence, "verification": verified.evidence},
        )

    def _move(self, pose: Pose7) -> ResetStepReceipt:
        command = self._commands.set_task_object_pose(pose)
        if not command.success:
            return command

        def matches() -> bool:
            observed = self._observe_pose()
            return observed is not None and _pose_matches(pose, observed)

        verified = self._converge(matches, "RESET_GAZEBO_POSE_VERIFY_FAILED")
        return ResetStepReceipt(
            verified.success,
            verified.failure_code,
            {
                "requested_pose": pose.values,
                "command": command.evidence,
                "verification": verified.evidence,
            },
        )

    def park_task_object(self, pose: Pose7) -> ResetStepReceipt:
        return self._move(pose)

    def restore_task_object(self, pose: Pose7) -> ResetStepReceipt:
        return self._move(pose)


class GazeboRobotResetPort:
    ARM_JOINTS = ("1", "2", "3", "4", "5")

    def __init__(
        self,
        *,
        planner: Any,
        executor: Any,
        command_gripper,
        observe_joints,
        home_positions: tuple[float, float, float, float, float],
        gripper_open_position: float,
        position_tolerance: float,
        velocity_tolerance: float,
        timeout_s: float,
        clock=time.monotonic,
        wait=time.sleep,
    ) -> None:
        self._planner = planner
        self._executor = executor
        self._command_gripper = command_gripper
        self._observe_joints = observe_joints
        self._home_positions = home_positions
        self._gripper_open_position = gripper_open_position
        self._position_tolerance = position_tolerance
        self._velocity_tolerance = velocity_tolerance
        self._timeout_s = timeout_s
        self._clock = clock
        self._wait = wait

    def _verify(self, targets: dict[str, float]) -> ResetStepReceipt:
        deadline = self._clock() + self._timeout_s
        latest: ResetStepReceipt | None = None
        while self._clock() < deadline:
            positions, velocities = self._observe_joints()
            errors = {
                name: abs(float(positions.get(name, math.inf)) - target)
                for name, target in targets.items()
            }
            speeds = {
                name: abs(float(velocities.get(name, math.inf))) for name in targets
            }
            success = all(
                value <= self._position_tolerance for value in errors.values()
            ) and all(value <= self._velocity_tolerance for value in speeds.values())
            latest = ResetStepReceipt(
                success,
                None if success else "RESET_JOINT_VERIFY_FAILED",
                {
                    "targets": targets,
                    "positions": positions,
                    "velocities": velocities,
                    "position_errors": errors,
                    "absolute_velocities": speeds,
                },
            )
            if success:
                return latest
            self._wait(min(0.01, self._timeout_s))
        return latest or ResetStepReceipt(
            False,
            "RESET_JOINT_VERIFY_FAILED",
            {"targets": targets, "observation": "unavailable"},
        )

    def open_gripper(self) -> ResetStepReceipt:
        commanded = self._command_gripper(self._gripper_open_position)
        if not commanded.success:
            return commanded
        verified = self._verify({"6": self._gripper_open_position})
        return ResetStepReceipt(
            verified.success,
            verified.failure_code,
            {"command": commanded.evidence, "verification": verified.evidence},
        )

    def plan_home(self, named_state: str) -> HomePlanReceipt:
        if named_state != "home":
            return HomePlanReceipt(
                False,
                None,
                "RESET_HOME_STATE_INVALID",
                {"requested": named_state, "required": "home"},
            )
        positions, _velocities = self._observe_joints()
        try:
            current = tuple(float(positions[name]) for name in self.ARM_JOINTS)
        except (KeyError, TypeError, ValueError) as error:
            return HomePlanReceipt(
                False,
                None,
                "RESET_JOINT_OBSERVATION_FAILED",
                {"message": str(error)},
            )
        request = JointPlanRequest(
            self.ARM_JOINTS,
            current,
            self._home_positions,
            velocity_scaling=0.1,
            acceleration_scaling=0.1,
            planning_time_s=min(self._timeout_s, 10.0),
        )
        outcome = self._planner.plan_joint_path(request, timeout_s=self._timeout_s)
        if outcome.failure is not None or outcome.trajectory is None:
            return HomePlanReceipt(
                False,
                None,
                "RESET_PLAN_HOME_FAILED",
                {"failure": repr(outcome.failure)},
            )
        return HomePlanReceipt(
            True,
            outcome.trajectory,
            None,
            {"named_state": named_state, "target_positions": self._home_positions},
        )

    def execute_home_and_verify(self, plan: Any) -> ResetStepReceipt:
        executed = self._executor.execute(plan, timeout_s=self._timeout_s)
        if executed.status is not ActionStatus.SUCCEEDED:
            code = executed.failure.code if executed.failure is not None else "UNKNOWN"
            return ResetStepReceipt(
                False, "RESET_EXECUTE_HOME_FAILED", {"execution_code": code}
            )
        verified = self._verify(dict(zip(self.ARM_JOINTS, self._home_positions, strict=True)))
        return ResetStepReceipt(
            verified.success,
            verified.failure_code,
            {"executed": True, "verification": verified.evidence},
        )


class GazeboSceneResetPort:
    def __init__(self, scene: Any, geometry: TaskGeometry) -> None:
        self._scene = scene
        self._geometry = geometry

    @staticmethod
    def _convert(receipt, code: str) -> ResetStepReceipt:
        return ResetStepReceipt(
            receipt.success,
            None if receipt.success else code,
            receipt.evidence,
        )

    def detach_task_object(self) -> ResetStepReceipt:
        receipt = self._scene.detach_task_object(
            self._geometry, "plastic_cup"
        )
        if not receipt.success:
            return self._convert(receipt, "RESET_MOVEIT_DETACH_FAILED")
        observed = self._scene.observe_task_scene(
            self._geometry, expected_cup_attachment=None
        )
        return self._convert(observed, "RESET_MOVEIT_DETACH_VERIFY_FAILED")

    def synchronize_task_scene(self, cup_pose: Pose7) -> ResetStepReceipt:
        cup = replace(self._geometry.object("plastic_cup"), pose=cup_pose)
        geometry = replace(
            self._geometry,
            objects=tuple(
                cup if item.object_id == "plastic_cup" else item
                for item in self._geometry.objects
            ),
        )
        applied = self._scene.apply_task_scene(geometry)
        if not applied.success:
            return self._convert(applied, "RESET_SCENE_APPLY_FAILED")
        observed = self._scene.observe_task_scene(
            geometry, expected_cup_attachment=None
        )
        return self._convert(observed, "RESET_SCENE_VERIFY_FAILED")


class GazeboResetState:
    """Thread-safe latest physical, joint, TF, controller, and attachment state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.cup_pose: Pose7 | None = None
        self.attached: bool | None = None
        self.positions: dict[str, float] = {}
        self.velocities: dict[str, float] = {}
        self.tf_frames: set[str] = set()
        self.controllers: dict[str, str] = {}
        self.entity_ids: dict[str, int] = {}
        self.attachment_probe: dict[str, object] = {}

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "cup_pose": self.cup_pose,
                "attached": self.attached,
                "positions": dict(self.positions),
                "velocities": dict(self.velocities),
                "tf_frames": sorted(self.tf_frames),
                "controllers": dict(self.controllers),
                "entity_ids": dict(self.entity_ids),
                "attachment_probe": dict(self.attachment_probe),
            }


class GazeboResetObservationPort:
    def __init__(
        self,
        state: GazeboResetState,
        scene: Any,
        geometry: TaskGeometry,
        home_positions: tuple[float, ...],
        gripper_open: float,
        position_tolerance: float,
        velocity_tolerance: float,
    ) -> None:
        self._state = state
        self._scene = scene
        self._geometry = geometry
        self._home_positions = home_positions
        self._gripper_open = gripper_open
        self._position_tolerance = position_tolerance
        self._velocity_tolerance = velocity_tolerance

    def _evidence(self) -> dict[str, object]:
        value = self._state.snapshot()
        pose = value["cup_pose"]
        value["cup_pose"] = None if pose is None else pose.values
        return value

    def observe_initial(self) -> ResetStepReceipt:
        evidence = self._evidence()
        required_controllers = {
            "joint_state_broadcaster",
            "arm_controller",
            "gripper_controller",
        }
        success = (
            evidence["cup_pose"] is not None
            and evidence["attached"] is not None
            and set(evidence["positions"]) >= {"1", "2", "3", "4", "5", "6"}
            and required_controllers <= set(evidence["controllers"])
            and all(
                evidence["controllers"][name] == "active" for name in required_controllers
            )
            and "so101_tcp" in evidence["tf_frames"]
        )
        return ResetStepReceipt(
            success,
            None if success else "RESET_OBSERVE_INITIAL_FAILED",
            evidence,
        )

    def verify_final(self) -> ResetStepReceipt:
        evidence = self._evidence()
        scene = self._scene.observe_task_scene(
            self._geometry, expected_cup_attachment=None
        )
        expected = {
            **dict(zip(("1", "2", "3", "4", "5"), self._home_positions, strict=True)),
            "6": self._gripper_open,
        }
        positions = evidence["positions"]
        velocities = evidence["velocities"]
        joints_ok = all(
            name in positions
            and abs(float(positions[name]) - target) <= self._position_tolerance
            and name in velocities
            and abs(float(velocities[name])) <= self._velocity_tolerance
            for name, target in expected.items()
        )
        pose = self._state.snapshot()["cup_pose"]
        success = (
            scene.success
            and evidence["attached"] is False
            and pose is not None
            and _pose_matches(self._geometry.object("plastic_cup").pose, pose)
            and joints_ok
            and "so101_tcp" in evidence["tf_frames"]
        )
        evidence["scene"] = scene.evidence
        evidence["joints_match"] = joints_ok
        return ResetStepReceipt(
            success,
            None if success else "RESET_FINAL_VERIFY_FAILED",
            evidence,
        )


def execute_gazebo_reset_transaction(
    request: TransactionalResetRequest,
    *,
    observation: Any,
    goals: Any,
    physical: Any,
    scene: Any,
    robot: Any,
) -> TransactionalResetReceipt:
    return TransactionalResetCoordinator(
        TransactionalResetPorts(observation, goals, physical, scene, robot)
    ).run(request)


class GazeboResetAdapter:
    """Compatibility adapter for the neutral epoch/step lifecycle reset port."""

    def __init__(
        self,
        observer: Any,
        request_reset: Callable[[str], bool],
        *,
        timeout_s: float,
        clock: Callable[[], float] = time.monotonic,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            raise ValueError("timeout_s must be finite and positive")
        self._observer = observer
        self._request_reset = request_reset
        self._timeout_s = timeout_s
        self._clock = clock
        self._wait = wait

    def reset(self, keyframe: str) -> ResetReceipt:
        if not keyframe:
            raise ValueError("keyframe must be non-empty")
        before = self._observer.snapshot()
        old_epoch = int(before.reset_epoch)
        if not self._request_reset(keyframe):
            return ResetReceipt(
                old_epoch,
                old_epoch,
                keyframe,
                int(before.simulation_step),
                str(before.simulation_session_id),
                False,
            )
        deadline = self._clock() + self._timeout_s
        latest = before
        while self._clock() < deadline:
            latest = self._observer.snapshot()
            if (
                str(latest.simulation_session_id) == str(before.simulation_session_id)
                and int(latest.reset_epoch) == old_epoch + 1
                and int(latest.simulation_step) == 0
            ):
                return ResetReceipt(
                    old_epoch,
                    int(latest.reset_epoch),
                    keyframe,
                    0,
                    str(latest.simulation_session_id),
                    True,
                )
            self._wait(min(0.01, self._timeout_s))
        return ResetReceipt(
            old_epoch,
            int(latest.reset_epoch),
            keyframe,
            int(latest.simulation_step),
            str(latest.simulation_session_id),
            False,
        )
