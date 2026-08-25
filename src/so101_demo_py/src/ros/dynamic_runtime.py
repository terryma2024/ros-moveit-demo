"""ROS-aware composition for the V2.1 single-state dynamic plan-only path."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

from ..application.dynamic_plan_only import (
    DynamicPlanningOptions,
    plan_dynamic_state_with_scene_gates,
)
from ..cli.cup_pose_subscriber import status_line
from ..core.domain import State
from ..core.domain import RunMode, RunRequest
from ..core.dynamic_pick import resolve_motion_targets
from ..core.runner import StateMachineRunner
from ..core.dynamic_pick_policy import (
    LoadedDynamicPolicy,
    load_dynamic_pick_template,
    load_dynamic_policy_variant,
)
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
    from ..control.planning_scene.task_scene import RosTaskScenePort
    from ..core.task_geometry import load_task_geometry
    from .cup_scene_observer import RosMujocoCupSceneObserver
    from .dynamic_mujoco_execution import RosDynamicMujocoExecution

    return SimpleNamespace(
        rclpy=rclpy,
        parameter=Parameter,
        get_package_share_directory=get_package_share_directory,
        load_policy=load_dynamic_policy_variant,
        load_geometry=load_task_geometry,
        cup_pose_source=RosCupPoseSource,
        cup_scene_observer=RosMujocoCupSceneObserver,
        task_scene_port=RosTaskScenePort,
        resolve_motion_targets=resolve_motion_targets,
        execution=RosDynamicMujocoExecution,
        build_actions=build_dynamic_actions,
        runner=StateMachineRunner,
    )


def run_dynamic_execute(options, *, _runtime=None) -> int:
    """Run the MuJoCo dynamic strategy through the shared state machine."""

    if (
        not options.session_id
        or options.expected_reset_epoch is None
        or options.evidence_root is None
    ):
        print("status=ERROR failure=DYNAMIC_LIVE_RUNTIME_CONFIG_REQUIRED")
        return 1

    from ..application.cup_pose_preflight import validate_cup_scene
    from ..application.dynamic_scene_sync import prepare_dynamic_cup_scene

    runtime = _dynamic_execute_runtime() if _runtime is None else _runtime
    share_dir = Path(runtime.get_package_share_directory("so101_demo_py"))
    try:
        loaded = runtime.load_policy(share_dir, backend="mujoco")
    except Exception as error:
        print(status_line("ERROR", failure=_failure_code(error), message=error))
        return 1
    if not loaded.execution_allowed:
        print("status=ERROR failure=DYNAMIC_EXECUTION_NOT_QUALIFIED")
        return 1
    try:
        geometry = runtime.load_geometry(
            share_dir / "assets" / "common" / "geometry-manifest.yaml"
        )
    except Exception as error:
        print(status_line("ERROR", failure=_failure_code(error), message=error))
        return 1

    runtime.rclpy.init()
    node = runtime.rclpy.create_node(
        "so101_dynamic_cup_pick_place",
        parameter_overrides=[runtime.parameter("use_sim_time", value=True)],
    )
    truth_observer = None
    task_scene = None
    execution = None
    try:
        source = runtime.cup_pose_source(node, loaded.template)
        sample = source.get_one(options.cup_pose_timeout_s)
        truth_observer = runtime.cup_scene_observer(node, options.session_id)
        initial = truth_observer.observe(5.0)
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
        evidence_file = Path(options.evidence_root) / "dynamic-execute-manifest.json"
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
        runner = runtime.runner(
            runtime.build_actions(execution, targets),
            session_id=options.session_id,
            policy_bundle_sha256=loaded.sha256,
            world_observer=execution.observer,
        )
        result = runner.run(RunRequest(mode=RunMode.EXECUTE))
        execution.finish(result)
        if result.status.value == "DONE":
            print(
                status_line(
                    "DONE",
                    strategy="dynamic",
                    evidence=evidence_file,
                    transition_count=result.transition_count,
                )
            )
            return 0
        code = "DYNAMIC_EXECUTION_FAILED"
        if result.failure is not None and result.failure.code:
            code = result.failure.code
        print(status_line("ERROR", failure=code, evidence=evidence_file))
        return 1
    except Exception as error:
        if execution is not None:
            class FailedResult:
                status = type("Status", (), {"value": "ERROR"})()
                current_state = State.ERROR
                transition_count = 0
                state_trace = (State.ERROR,)
                failure = type("Failure", (), {"code": _failure_code(error)})()

            execution.finish(FailedResult())
        print(status_line("ERROR", failure=_failure_code(error), message=error))
        return 1
    finally:
        if execution is not None:
            execution.close()
        if task_scene is not None:
            close_task_scene = getattr(task_scene, "close", None)
            if close_task_scene is not None:
                close_task_scene()
        if truth_observer is not None:
            truth_observer.close()
        node.destroy_node()
        if runtime.rclpy.ok():
            runtime.rclpy.shutdown()
