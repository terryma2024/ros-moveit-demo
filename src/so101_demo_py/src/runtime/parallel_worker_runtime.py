"""Isolated, injectable runtime boundary for one parallel MuJoCo Worker."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..application.qualification_stack import ros2_command
from ..core.domain import State
from ..parallel_batch.contracts import AttemptStatus, RunMode, ValidationStatus
from ..parallel_batch.resources import WorkerResources
from .task_stack import (
    OwnedProcessGroup,
    OwnedProcessManifest,
    PersistentStackConfig,
    StackProcessSpec,
)


_READY_REQUIREMENTS = (
    "controllers",
    "move_group",
    "joint_states",
    "planning_scene",
)

_EXPERT_MOTION_PREFIX = (
    State.MOVE_ABOVE_OBJECT,
    State.DESCEND,
    State.LIFT,
    State.MOVE_ABOVE_PLACE,
    State.DESCEND_TO_PLACE,
    State.RETREAT,
)


@dataclass(frozen=True, slots=True)
class RuntimeDecision:
    status: AttemptStatus | ValidationStatus
    reason: str = "OK"
    physical_action_proven_absent: bool = True


class RosDynamicPlanPrefixAdapter:
    """Use ``RosDynamicPlanner`` for every dynamic plan-only motion state."""

    def __init__(
        self,
        node: Any,
        template: Any,
        scene: Any,
        *,
        planner_factory: Callable[[Any, tuple[str, ...]], Any] | None = None,
        target_resolver: Callable[[Any, Any], Any] | None = None,
        plan_state: Callable[..., Any] | None = None,
    ) -> None:
        if planner_factory is None:
            from ..ros.dynamic_planner import RosDynamicPlanner

            planner_factory = RosDynamicPlanner
        if target_resolver is None:
            from ..core.dynamic_pick import resolve_motion_targets

            target_resolver = resolve_motion_targets
        if plan_state is None:
            from ..application.dynamic_plan_only import plan_dynamic_state_with_scene_gates

            plan_state = plan_dynamic_state_with_scene_gates
        from ..application.dynamic_plan_only import DynamicPlanningOptions

        self._template = template
        self._scene = scene
        self._planner = planner_factory(node, template.arm_joint_names)
        self._target_resolver = target_resolver
        self._plan_state = plan_state
        self._options = DynamicPlanningOptions(
            template.planning_frame,
            template.planning_group,
            template.tcp_link,
            template.position_tolerance_m,
            template.orientation_tolerance_rad,
            template.planning_timeout_s,
            template.velocity_scaling,
            template.acceleration_scaling,
        )

    def __call__(self, lease: Any, admitted: Any, states: tuple[State, ...]):
        del lease
        targets = self._target_resolver(admitted, self._template)
        plans = []
        for state in states:
            plan, _before, _after = self._plan_state(
                state=state,
                provider=targets,
                control=self._planner.control,
                options=self._options,
                scene=self._scene,
                sample=admitted,
                template=self._template,
            )
            if getattr(plan, "accepted", None) is not True:
                raise RuntimeError("CUP_POSE_PLAN_FAILED")
            plans.append(plan)
        return tuple(plans)

    def close(self) -> None:
        self._planner.close()


def headless_task_station_config(resources: WorkerResources) -> PersistentStackConfig:
    """Construct the single supported Linux headless Worker launch command."""

    if not isinstance(resources, WorkerResources):
        raise TypeError("WorkerResources are required")
    command = ros2_command(
        "launch",
        "so101_demo_py",
        "so101_mujoco_task_station.launch.py",
        "headless:=true",
        "sensor_rendering:=true",
        "include_teleop:=false",
        f"session_id:={resources.session_id}",
        f"task_evidence_root:={resources.worker_root}",
    )
    return PersistentStackConfig(
        resources.session_id,
        True,
        resources.worker_root,
        (StackProcessSpec("task-station", tuple(command)),),
    )


def _required(name: str):
    def missing(*_args, **_kwargs):
        raise RuntimeError(f"parallel Worker runtime port is required: {name}")

    return missing


class DryRunWorkerRuntime:
    """Scheduler-only Worker runtime that cannot construct a ROS command."""

    def __init__(self, resources: WorkerResources) -> None:
        self.resources = resources

    @property
    def owned_process_manifest(self) -> OwnedProcessManifest:
        return OwnedProcessManifest(tuple())

    @property
    def captured_artifacts(self) -> tuple[Path, ...]:
        return tuple()

    def start_physical_runtime(self) -> None:
        return None

    def worker_ready_gate(self) -> bool:
        return True

    def consumer_argv(self, reset_epoch: object) -> None:
        del reset_epoch
        return None

    def scheduler_trace(self, lease: Any) -> RuntimeDecision:
        del lease
        return RuntimeDecision(ValidationStatus.VALIDATION_PASSED)

    def reset_and_validate_point(self, lease: Any):
        del lease
        raise RuntimeError("dry-run has no physical point gate")

    def localize_and_admit_pose(self, lease: Any, broker_result: Any):
        del lease, broker_result
        raise RuntimeError("dry-run has no perception admission")

    reset_point = reset_and_validate_point
    admit_pose = localize_and_admit_pose

    def plan_expert(self, lease: Any, admitted: Any):
        del lease, admitted
        raise RuntimeError("dry-run cannot plan")

    def execute_expert(self, lease: Any, admitted: Any):
        del lease, admitted
        raise RuntimeError("dry-run cannot execute")

    def capture_terminal(self, lease: Any, **kwargs):
        del lease, kwargs
        return tuple()

    def cancel_motion(self, lease: Any) -> bool:
        del lease
        return True

    def confirm_no_controller_goal(self, lease: Any) -> bool:
        del lease
        return True

    def recover(self, worker_id: str, generation: int, deadline_monotonic_s: float) -> bool:
        del worker_id, generation, deadline_monotonic_s
        return True

    def shutdown_owned(self) -> None:
        return None


class ParallelWorkerRuntime:
    """Own one headless station and all lease-scoped Worker operations."""

    def __init__(
        self,
        resources: WorkerResources,
        run_mode: RunMode,
        *,
        process_group: Any | None = None,
        ready_probe: Callable[[tuple[str, ...]], bool] | None = None,
        reset_point: Callable[[Any], Any] | None = None,
        initial_gate: Callable[[Any, Any], Any] | None = None,
        localize: Callable[[Any, Any], Any] | None = None,
        admit_pose: Callable[[Any, Any], Any] | None = None,
        publish_pose: Callable[[Any], Any] | None = None,
        plan_prefix: Callable[[Any, Any, tuple[State, ...]], Any] | None = None,
        execute_result: Callable[[Any, Any, Any], Any] | None = None,
        capture_rgb: Callable[[Path, float], Path] | None = None,
        cancel_motion: Callable[[Any], bool] | None = None,
        confirm_no_controller_goal: Callable[[Any], bool] | None = None,
        recovery: Callable[[str, int, float], bool] | None = None,
    ) -> None:
        if not isinstance(resources, WorkerResources):
            raise TypeError("WorkerResources are required")
        if run_mode not in (RunMode.PLAN_ONLY, RunMode.EXECUTE):
            raise ValueError("physical Worker runtime requires plan_only or execute")
        self.resources = resources
        self.run_mode = run_mode
        self._processes = process_group or OwnedProcessGroup()
        self._ready_probe = ready_probe or _required("ready_probe")
        self._reset_point = reset_point or _required("reset_point")
        self._initial_gate = initial_gate or _required("initial_gate")
        self._localize = localize or _required("localize")
        self._admit_pose = admit_pose or _required("admit_pose")
        self._publish_pose = publish_pose or _required("publish_pose")
        self._plan_prefix = plan_prefix or _required("plan_prefix")
        self._execute_result = execute_result or _required("execute_result")
        self._capture_rgb = capture_rgb or _required("capture_rgb")
        self._cancel_motion = cancel_motion or (lambda _lease: True)
        self._confirm_no_controller_goal = confirm_no_controller_goal or (
            lambda _lease: True
        )
        self._recovery = recovery or (lambda _worker, _generation, _deadline: True)
        self._physical_started = False
        self._captured: list[Path] = []

    @property
    def owned_process_manifest(self) -> OwnedProcessManifest:
        return self._processes.manifest

    @property
    def captured_artifacts(self) -> tuple[Path, ...]:
        return tuple(self._captured)

    def start_physical_runtime(self) -> None:
        if self._physical_started:
            raise RuntimeError("parallel Worker physical runtime already started")
        config = headless_task_station_config(self.resources)
        for spec in config.processes:
            self._processes.start(spec, environment=self.resources.environment)
        self._physical_started = True

    def worker_ready_gate(self) -> bool:
        return self._physical_started and self._ready_probe(_READY_REQUIREMENTS) is True

    def _capture_fresh_rgb(self, name: str, boundary: float) -> Path:
        path = self.resources.worker_root / name
        captured = self._capture_rgb(path, boundary)
        if Path(captured) != path:
            raise RuntimeError(f"{name} capture escaped the Worker root")
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"{name} capture did not save a regular artifact")
        self._captured.append(path)
        return path

    def reset_point(self, lease: Any):
        if not self._physical_started:
            raise RuntimeError("parallel Worker physical runtime is not started")
        receipt = self._reset_point(lease)
        boundary = getattr(receipt, "reset_completed_monotonic_s", None)
        if isinstance(boundary, bool) or not isinstance(boundary, (int, float)):
            raise RuntimeError("reset receipt lacks a source-frame boundary")
        self._capture_fresh_rgb("initial-rgb.png", float(boundary))
        return receipt

    def point_initial_gate(self, lease: Any, reset_receipt: Any):
        return self._initial_gate(lease, reset_receipt)

    def reset_and_validate_point(self, lease: Any):
        receipt = self.reset_point(lease)
        return receipt, self.point_initial_gate(lease, receipt)

    def localize_and_admit_pose(self, lease: Any, broker_result: Any):
        localized = self._localize(lease, broker_result)
        admitted = self._admit_pose(lease, localized)
        if admitted is None or admitted is False:
            raise RuntimeError("POSE_ADMISSION_REJECTED")
        published = self._publish_pose(admitted)
        if published is False:
            raise RuntimeError("POSE_ACCEPTED_PUBLICATION_FAILED")
        return admitted

    def admit_pose(self, lease: Any, broker_result: Any):
        return self.localize_and_admit_pose(lease, broker_result)

    def plan_expert(self, lease: Any, admitted: Any):
        if self.run_mode is not RunMode.PLAN_ONLY:
            raise RuntimeError("expert planning requires plan_only")
        self._plan_prefix(lease, admitted, _EXPERT_MOTION_PREFIX)
        return RuntimeDecision(ValidationStatus.VALIDATION_PASSED)

    def consumer_argv(self, reset_epoch: object) -> tuple[str, ...] | None:
        if self.run_mode is not RunMode.EXECUTE:
            return None
        return tuple(
            ros2_command(
                "run",
                "so101_demo_py",
                "dynamic_cup_pick_place",
                "--backend",
                "mujoco",
                "--mode",
                "execute",
                "--execute",
                "--expected-reset-epoch",
                str(reset_epoch),
                "--session-id",
                self.resources.session_id,
                "--evidence-root",
                str(self.resources.worker_root / "dynamic"),
                "--scene-source",
                "observe_only",
            )
        )

    def execute_expert(self, lease: Any, admitted: Any):
        if self.run_mode is not RunMode.EXECUTE:
            raise RuntimeError("expert execution requires execute")
        reset_epoch = getattr(admitted, "reset_epoch", None)
        if reset_epoch is None:
            raise RuntimeError("accepted pose lacks reset epoch")
        argv = self.consumer_argv(reset_epoch)
        if argv is None:
            raise RuntimeError("execute consumer command is unavailable")
        child = self._processes.start(
            StackProcessSpec("dynamic-consumer", argv),
            environment=self.resources.environment,
        )
        result = self._execute_result(lease, admitted, child)
        if not isinstance(getattr(result, "status", None), AttemptStatus):
            raise RuntimeError("execute result lacks an AttemptStatus")
        return result

    def capture_terminal(
        self,
        lease: Any,
        *,
        action_boundary_monotonic_s: float,
    ) -> tuple[Path, ...]:
        del lease
        if (
            isinstance(action_boundary_monotonic_s, bool)
            or not isinstance(action_boundary_monotonic_s, (int, float))
        ):
            raise RuntimeError("terminal capture boundary is required")
        self._capture_fresh_rgb(
            "terminal-rgb.png", float(action_boundary_monotonic_s)
        )
        return tuple(self._captured)

    def cancel_motion(self, lease: Any) -> bool:
        return self._cancel_motion(lease) is True

    def confirm_no_controller_goal(self, lease: Any) -> bool:
        return self._confirm_no_controller_goal(lease) is True

    def recover(self, worker_id: str, generation: int, deadline_monotonic_s: float) -> bool:
        self.shutdown_owned()
        recovered = self._recovery(worker_id, generation, deadline_monotonic_s) is True
        if recovered:
            self.start_physical_runtime()
        return recovered

    def shutdown_owned(self) -> None:
        try:
            self._processes.shutdown()
        finally:
            self._physical_started = False


def build_worker_runtime(
    resources: WorkerResources,
    run_mode: RunMode,
    **ports,
) -> DryRunWorkerRuntime | ParallelWorkerRuntime:
    """Select scheduler-only or physical runtime without constructing side effects."""

    if not isinstance(run_mode, RunMode):
        raise TypeError("run_mode must be a RunMode")
    if run_mode is RunMode.DRY_RUN:
        return DryRunWorkerRuntime(resources)
    return ParallelWorkerRuntime(resources, run_mode, **ports)
