"""ROS-aware composition for the V2.1 single-state dynamic plan-only path."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from ..application.dynamic_plan_only import (
    DynamicPlanningOptions,
    plan_dynamic_state_with_scene_gates,
)
from ..cli.cup_pose_subscriber import status_line
from ..core.domain import RunMode, RunRequest, State
from ..core.dynamic_pick import resolve_motion_targets
from ..core.dynamic_pick_policy import (
    LoadedDynamicPolicy,
    load_dynamic_pick_template,
    load_dynamic_policy_variant,
)
from ..core.runner import StateMachineRunner
from ..profiling.session import SemanticProfiler
from ..profiling.wrappers import profile_actions
from ..runtime.dynamic_plan_manifest import write_dynamic_plan_manifest
from .cup_pose_source import RosCupPoseSource
from .cup_scene_observer import RosCupSceneObserver
from .dynamic_planner import RosDynamicPlanner


def _failure_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return code
    prefix = str(error).split(":", 1)[0]
    if prefix and prefix.upper() == prefix and " " not in prefix:
        return prefix
    return "DYNAMIC_PLAN_FAILED"


def _load_policy(options, share_dir: Path) -> LoadedDynamicPolicy:
    if not options.dynamic_policy:
        return load_dynamic_policy_variant(share_dir, backend=options.backend)
    path = Path(options.dynamic_policy)
    raw = path.read_bytes()
    return LoadedDynamicPolicy(
        load_dynamic_pick_template(
            path,
            expected_backend=options.backend,
            expected_execution_allowed=False,
        ),
        path,
        hashlib.sha256(raw).hexdigest(),
        "CALIBRATION_REQUIRED",
        options.backend,
        False,
    )


def run_dynamic_plan_only(options) -> int:
    if not options.plan_only_state or not options.evidence_file:
        print("status=ERROR failure=DYNAMIC_PLAN_CONFIG_REQUIRED")
        return 1
    try:
        state = State(options.plan_only_state)
    except ValueError:
        print("status=ERROR failure=PLAN_ONLY_STATE_UNSUPPORTED")
        return 1

    import rclpy
    from ament_index_python.packages import get_package_share_directory
    from rclpy.parameter import Parameter

    share_dir = Path(get_package_share_directory("so101_demo_py"))
    try:
        loaded = _load_policy(options, share_dir)
    except Exception as error:
        print(status_line("ERROR", failure=_failure_code(error), message=error))
        return 1
    installed_prefix = options.installed_prefix or str(share_dir.parents[1])
    rclpy.init()
    node = rclpy.create_node(
        "so101_dynamic_cup_pick_place",
        parameter_overrides=[Parameter("use_sim_time", value=True)],
    )
    scene = None
    planner = None
    try:
        source = RosCupPoseSource(node, loaded.template)
        sample = source.get_one(options.cup_pose_timeout_s)
        targets = resolve_motion_targets(sample, loaded.template)
        scene = RosCupSceneObserver(node)
        planner = RosDynamicPlanner(node, loaded.template.arm_joint_names)
        planning = DynamicPlanningOptions(
            loaded.template.planning_frame,
            loaded.template.planning_group,
            loaded.template.tcp_link,
            loaded.template.position_tolerance_m,
            loaded.template.orientation_tolerance_rad,
            loaded.template.planning_timeout_s,
            loaded.template.velocity_scaling,
            loaded.template.acceleration_scaling,
        )
        plan, before, after = plan_dynamic_state_with_scene_gates(
            state=state,
            provider=targets,
            control=planner.control,
            options=planning,
            scene=scene,
            sample=sample,
            template=loaded.template,
        )
        if not plan.accepted or after is None:
            print(
                status_line(
                    "ERROR",
                    failure="CUP_POSE_PLAN_FAILED",
                    message=plan.error_code or "MoveIt planning failed",
                )
            )
            return 1
        evidence_path = write_dynamic_plan_manifest(
            Path(options.evidence_file),
            backend=options.backend,
            source_commit=options.source_commit,
            installed_prefix=installed_prefix,
            policy_path=loaded.path,
            policy_sha256=loaded.sha256,
            qualification_status=loaded.qualification_status,
            selected_state=state.value,
            sample=sample,
            targets=targets,
            before_scene=before,
            after_scene=after,
            plan=plan,
        )
        print(
            status_line(
                "PLAN_ONLY_COMPLETE",
                strategy="dynamic",
                state=state.value,
                evidence=evidence_path,
            )
        )
        return 0
    except Exception as error:
        print(status_line("ERROR", failure=_failure_code(error), message=error))
        return 1
    finally:
        if planner is not None:
            planner.close()
        if scene is not None:
            scene.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def _dynamic_execute_runtime():
    """Load ROS adapters lazily and expose a narrow orchestration test seam."""

    import rclpy
    from ament_index_python.packages import get_package_share_directory
    from rclpy.parameter import Parameter

    from ..application.dynamic_execute import build_dynamic_actions
    from ..application.task_reachability import check_task_reachability
    from ..control.planning_scene.task_scene import RosTaskScenePort
    from ..core.task_geometry import load_task_geometry
    from ..core.task_points import TaskPoint
    from .cup_scene_observer import RosMujocoCupSceneObserver
    from .dynamic_mujoco_execution import RosDynamicMujocoExecution
    from .task_reachability import RosJointStateReader, RosMoveGroupReachabilityPlanner

    def reachability_preflight(node, sample, template, scene_revision):
        point = TaskPoint(
            id="perceived_cup",
            label="Perceived cup",
            cup_position_world_m=tuple(sample.pose_world.values[:3]),
        )
        planner = RosMoveGroupReachabilityPlanner(node, template)
        reader = RosJointStateReader(node, template.arm_joint_names)
        try:
            start = reader.read(template.planning_timeout_s)
            return check_task_reachability(
                point,
                template,
                start,
                planner,
                scene_revision=scene_revision,
            )
        finally:
            reader.close()
            planner.close()

    return SimpleNamespace(
        rclpy=rclpy,
        parameter=Parameter,
        get_package_share_directory=get_package_share_directory,
        load_policy=load_dynamic_policy_variant,
        load_geometry=load_task_geometry,
        cup_pose_source=RosCupPoseSource,
        cup_scene_observer=RosMujocoCupSceneObserver,
        task_scene_port=RosTaskScenePort,
        cleanup_task_scene=lambda _scene: None,
        resolve_motion_targets=resolve_motion_targets,
        reachability_preflight=reachability_preflight,
        execution=RosDynamicMujocoExecution,
        build_actions=build_dynamic_actions,
        runner=StateMachineRunner,
    )


def _write_reachability_evidence(path: Path, session_id: str, report: Any) -> None:
    from ..cli.task_reachability import result_document

    document = result_document((report,))
    document["session_id"] = session_id
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


@dataclass(frozen=True, slots=True)
class _CleanupFailure:
    resource: str
    error: BaseException


@dataclass(frozen=True, slots=True)
class _CleanupOutcome:
    failures: tuple[_CleanupFailure, ...]

    @property
    def message(self) -> str:
        return "; ".join(f"{failure.resource}: {failure.error}" for failure in self.failures)


def _cleanup_dynamic_execute(
    *,
    runtime: Any,
    initialized_here: bool,
    node: Any | None,
    execution: Any | None,
    task_scene: Any | None,
    truth_observer: Any | None,
) -> _CleanupOutcome:
    """Attempt every owned cleanup operation and retain all failures."""

    failures: list[_CleanupFailure] = []

    def attempt(resource: str, operation: Callable[[], None]) -> None:
        try:
            operation()
        except BaseException as error:
            failures.append(_CleanupFailure(resource, error))

    if execution is not None:
        attempt("execution", execution.close)
    if task_scene is not None:
        attempt("task_scene", lambda: runtime.cleanup_task_scene(task_scene))
    if truth_observer is not None:
        attempt("truth_observer", truth_observer.close)
    if node is not None:
        attempt("node", node.destroy_node)
    if initialized_here:
        attempt("rclpy_context", runtime.rclpy.shutdown)
    return _CleanupOutcome(tuple(failures))


def _finish_failed_execution(execution: Any, error: Exception) -> None:
    class FailedResult:
        status = type("Status", (), {"value": "ERROR"})()
        current_state = State.ERROR
        transition_count = 0
        state_trace = (State.ERROR,)
        failure = type("Failure", (), {"code": _failure_code(error)})()

    execution.finish(FailedResult())


def run_dynamic_execute(
    options,
    *,
    profiler: SemanticProfiler | None = None,
    _runtime=None,
) -> int:
    """Run the MuJoCo dynamic strategy through the shared state machine."""

    if (
        not options.session_id
        or options.expected_reset_epoch is None
        or options.evidence_root is None
    ):
        print("status=ERROR failure=DYNAMIC_LIVE_RUNTIME_CONFIG_REQUIRED")
        return 1

    from ..application.cup_pose_preflight import (
        validate_cup_scene,
        validate_mujoco_scene_identity,
    )
    from ..application.dynamic_scene_sync import prepare_dynamic_cup_scene

    runtime = _dynamic_execute_runtime() if _runtime is None else _runtime
    setup_token = (
        profiler.start_span("runtime.setup", {"backend": "mujoco"})
        if profiler is not None
        else None
    )
    setup_finished = False

    def finish_setup(outcome: str, reason_code: str | None = None) -> None:
        nonlocal setup_finished
        if setup_token is None or setup_finished:
            return
        attributes: dict[str, object] = {"backend": "mujoco"}
        if reason_code is not None:
            attributes["reason_code"] = reason_code
        profiler.finish_span(setup_token, outcome=outcome, attributes=attributes)
        setup_finished = True

    share_dir = Path(runtime.get_package_share_directory("so101_demo_py"))
    try:
        loaded = runtime.load_policy(share_dir, backend="mujoco")
    except Exception as error:
        finish_setup("rejected", _failure_code(error))
        print(status_line("ERROR", failure=_failure_code(error), message=error))
        return 1
    if not loaded.execution_allowed:
        finish_setup("rejected", "DYNAMIC_EXECUTION_NOT_QUALIFIED")
        print("status=ERROR failure=DYNAMIC_EXECUTION_NOT_QUALIFIED")
        return 1
    try:
        geometry = runtime.load_geometry(share_dir / "assets" / "common" / "geometry-manifest.yaml")
    except Exception as error:
        finish_setup("rejected", _failure_code(error))
        print(status_line("ERROR", failure=_failure_code(error), message=error))
        return 1

    initialized_here = False
    node = None
    truth_observer = None
    task_scene = None
    execution = None
    result = None
    evidence_file = Path(options.evidence_root) / "dynamic-execute-manifest.json"
    reachability_file = Path(options.evidence_root) / "reachability-observed.json"
    primary_failure = None
    primary_message = None
    secondary_failures: list[tuple[str, BaseException]] = []
    try:
        runtime.rclpy.init()
        initialized_here = True
        node = runtime.rclpy.create_node(
            "so101_dynamic_cup_pick_place",
            parameter_overrides=[runtime.parameter("use_sim_time", value=True)],
        )
        source = runtime.cup_pose_source(node, loaded.template)
        print("status=READY subscription=/cup_pose", flush=True)
        sample = source.get_one(options.cup_pose_timeout_s)
        truth_observer = runtime.cup_scene_observer(
            node,
            options.session_id,
            options.expected_reset_epoch,
        )
        initial = truth_observer.observe(5.0)
        validate_mujoco_scene_identity(
            initial,
            expected_session_id=options.session_id,
            expected_reset_epoch=options.expected_reset_epoch,
        )
        task_scene = runtime.task_scene_port(
            node,
            "mujoco",
            loaded.template.planning_timeout_s,
        )
        prepare_dynamic_cup_scene(
            sample,
            initial,
            loaded.template,
            geometry,
            task_scene,
        )
        validate_cup_scene(sample, truth_observer.observe(5.0), loaded.template)
        validate_cup_scene(sample, truth_observer.observe(5.0), loaded.template)
        targets = runtime.resolve_motion_targets(sample, loaded.template)
        reachability = runtime.reachability_preflight(
            node,
            sample,
            loaded.template,
            getattr(initial, "reset_epoch", None),
        )
        _write_reachability_evidence(
            reachability_file,
            options.session_id,
            reachability,
        )
        if reachability.status.value == "UNREACHABLE":
            raise RuntimeError("DYNAMIC_TARGET_UNREACHABLE")
        if reachability.status.value != "REACHABLE":
            raise RuntimeError("DYNAMIC_TARGET_REACHABILITY_UNKNOWN")
        execution = runtime.execution(
            node,
            loaded.template,
            targets,
            session_id=options.session_id,
            expected_reset_epoch=options.expected_reset_epoch,
            evidence_file=evidence_file,
            urdf_path=share_dir / "assets" / "mujoco" / "so101.urdf",
            policy_path=loaded.path,
            policy_sha256=loaded.sha256,
        )
        actions = profile_actions(
            runtime.build_actions(execution, targets),
            profiler,
        )
        runner = runtime.runner(
            actions,
            session_id=options.session_id,
            policy_bundle_sha256=loaded.sha256,
            world_observer=execution.observer,
        )
        finish_setup("accepted")
        result = runner.run(RunRequest(mode=RunMode.EXECUTE))
    except Exception as error:
        finish_setup("rejected", _failure_code(error))
        primary_failure = _failure_code(error)
        primary_message = error
        if execution is not None:
            try:
                _finish_failed_execution(execution, error)
            except BaseException as finish_error:
                secondary_failures.append(("DYNAMIC_EXECUTION_FINISH_FAILED", finish_error))
    else:
        try:
            execution.finish(result)
        except BaseException as finish_error:
            if result.status.value == "DONE":
                primary_failure = "DYNAMIC_EXECUTION_FINISH_FAILED"
                primary_message = finish_error
            else:
                secondary_failures.append(("DYNAMIC_EXECUTION_FINISH_FAILED", finish_error))
        if result.status.value != "DONE":
            primary_failure = "DYNAMIC_EXECUTION_FAILED"
            if result.failure is not None and result.failure.code:
                primary_failure = result.failure.code
    finally:
        cleanup_token = (
            profiler.start_span("runtime.cleanup")
            if profiler is not None
            else None
        )
        cleanup = _cleanup_dynamic_execute(
            runtime=runtime,
            initialized_here=initialized_here,
            node=node,
            execution=execution,
            task_scene=task_scene,
            truth_observer=truth_observer,
        )
        if cleanup_token is not None:
            profiler.finish_span(
                cleanup_token,
                outcome="ok" if not cleanup.failures else "error",
                attributes={"failure_count": len(cleanup.failures)},
            )

    if primary_failure is not None:
        fields = {"failure": primary_failure}
        if result is not None:
            fields["evidence"] = evidence_file
        if primary_message is not None:
            fields["message"] = primary_message
        print(status_line("ERROR", **fields))
        for failure, error in secondary_failures:
            print(status_line("ERROR", failure=failure, message=error, secondary=True))
        if cleanup.failures:
            print(
                status_line(
                    "ERROR",
                    failure="DYNAMIC_EXECUTION_CLEANUP_FAILED",
                    message=cleanup.message,
                    secondary=True,
                )
            )
        return 1

    if cleanup.failures:
        print(
            status_line(
                "ERROR",
                failure="DYNAMIC_EXECUTION_CLEANUP_FAILED",
                message=cleanup.message,
                workflow_status="DONE",
            )
        )
        return 1

    print(
        status_line(
            "DONE",
            strategy="dynamic",
            evidence=evidence_file,
            transition_count=result.transition_count,
        )
    )
    return 0
