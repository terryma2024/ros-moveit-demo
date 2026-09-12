from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.parallel_batch.contracts import AttemptStatus, RunMode, ValidationStatus
from so101_demo.parallel_batch.resources import WorkerResources


def _resources(root: Path, worker: str, slot: int, domain: int) -> WorkerResources:
    worker_root = root / worker
    paths = {
        "render": worker_root / "render",
        "ros_home": worker_root / "ros-home",
        "ros_log": worker_root / "ros-log",
        "tmp": worker_root / "tmp",
        "socket": worker_root / "socket",
    }
    for path in paths.values():
        path.mkdir(parents=True)
    return WorkerResources(
        worker_id=worker,
        slot_index=slot,
        generation=1,
        ros_domain_id=domain,
        simulation_port="not_applicable",
        bridge_port="not_applicable",
        gz_partition="not_applicable",
        session_id=f"session-{worker}",
        controller_namespace=f"/{worker}",
        render_backend="egl",
        render_context_id=f"egl-{worker}",
        render_context_namespace=paths["render"],
        virtual_display="not_applicable",
        ros_home=paths["ros_home"],
        ros_log_dir=paths["ros_log"],
        temp_dir=paths["tmp"],
        socket_namespace=paths["socket"],
        socket_path=paths["socket"] / "worker.sock",
        worker_root=worker_root,
        environment={
            "ROS_DOMAIN_ID": str(domain),
            "ROS_HOME": str(paths["ros_home"]),
            "ROS_LOG_DIR": str(paths["ros_log"]),
            "TMPDIR": str(paths["tmp"]),
        },
    )


class _Child:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        del timeout
        self.returncode = 0
        return 0


class _ProcessGroup:
    def __init__(self) -> None:
        self.specs = []
        self.environments = []
        self.shutdown_calls = 0

    @property
    def manifest(self):
        from so101_demo.runtime.task_stack import OwnedProcessManifest

        return OwnedProcessManifest(tuple())

    def start(self, spec, *, environment=None):
        self.specs.append(spec)
        self.environments.append(dict(environment or {}))
        return SimpleNamespace(
            role=spec.role,
            pid=100 + len(self.specs),
            pgid=100 + len(self.specs),
        )

    def shutdown(self):
        self.shutdown_calls += 1


def test_worker_launch_configs_keep_resources_distinct(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import headless_task_station_config

    first = _resources(tmp_path, "worker-1", 0, 181)
    second = _resources(tmp_path, "worker-2", 1, 182)

    first_config = headless_task_station_config(first)
    second_config = headless_task_station_config(second)

    assert first_config.session_id == "session-worker-1"
    assert second_config.session_id == "session-worker-2"
    assert first.ros_domain_id != second.ros_domain_id
    assert first.worker_root != second.worker_root
    assert first_config.headless is True
    assert first_config.processes[0].argv[-5:] == (
        "headless:=true",
        "sensor_rendering:=true",
        "include_teleop:=false",
        "session_id:=session-worker-1",
        f"task_evidence_root:={first.worker_root}",
    )


def test_visible_task_station_wrapper_keeps_legacy_macos_defaults(tmp_path: Path) -> None:
    from so101_demo.runtime.task_stack import default_task_station_config

    config = default_task_station_config(
        "visible-session", tmp_path, include_teleop=True
    )

    assert config.headless is False
    assert "headless:=false" in config.processes[0].argv
    assert "include_teleop:=true" in config.processes[0].argv


def test_owned_group_signals_only_an_exact_manifest_identity() -> None:
    from so101_demo.runtime.task_stack import OwnedProcessGroup, StackProcessSpec

    identities = {
        401: (401, ("ros2", "launch", "worker-a"), 9001),
        402: (402, ("ros2", "launch", "worker-b"), 9002),
    }
    children = iter((_Child(401), _Child(402)))
    signals = []
    first = OwnedProcessGroup(
        popen=lambda *_args, **_kwargs: next(children),
        identity_probe=lambda pid: identities[pid],
        killpg=lambda pgid, value: signals.append((pgid, value)),
    )
    second = OwnedProcessGroup(
        popen=lambda *_args, **_kwargs: next(children),
        identity_probe=lambda pid: identities[pid],
        killpg=lambda pgid, value: signals.append((pgid, value)),
    )
    first.start(StackProcessSpec("station", identities[401][1]))
    second.start(StackProcessSpec("station", identities[402][1]))

    assert first.manifest.processes[0].start_time_ticks == 9001
    assert first.manifest.processes[0].cmdline == identities[401][1]
    first.shutdown()

    assert [pgid for pgid, _value in signals] == [401]
    assert second.manifest.processes[0].pgid == 402


def test_owned_group_refuses_reused_pid_identity() -> None:
    from so101_demo.runtime.task_stack import OwnedProcessGroup, StackProcessSpec

    identity = [(510, ("ros2", "launch", "worker"), 10)]
    signals = []
    group = OwnedProcessGroup(
        popen=lambda *_args, **_kwargs: _Child(510),
        identity_probe=lambda _pid: identity[0],
        killpg=lambda pgid, value: signals.append((pgid, value)),
    )
    group.start(StackProcessSpec("station", ("ros2", "launch", "worker")))
    identity[0] = (510, ("unrelated",), 11)

    with pytest.raises(RuntimeError, match="identity changed"):
        group.shutdown()

    assert signals == []


def test_dry_run_has_no_physical_or_consumer_command(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    processes = _ProcessGroup()
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.DRY_RUN,
        process_group=processes,
    )

    runtime.start_physical_runtime()
    decision = runtime.scheduler_trace(SimpleNamespace())

    assert processes.specs == []
    assert runtime.consumer_argv("7") is None
    assert decision.status is ValidationStatus.VALIDATION_PASSED


def test_plan_only_plans_complete_expert_prefix_without_consumer_or_action_goal(
    tmp_path: Path,
) -> None:
    from so101_demo.core.domain import State
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    processes = _ProcessGroup()
    calls = []

    def plan_prefix(lease, admitted, states):
        calls.append((lease, admitted, states))
        return "planned"

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=processes,
        ready_probe=lambda required: required
        == ("controllers", "move_group", "joint_states", "planning_scene"),
        plan_prefix=plan_prefix,
    )
    runtime.start_physical_runtime()
    lease = SimpleNamespace(point_id="P01")
    admitted = SimpleNamespace(pose="accepted")

    assert runtime.worker_ready_gate() is True
    assert runtime.plan_expert(lease, admitted).status is ValidationStatus.VALIDATION_PASSED
    assert calls[0][2] == (
        State.MOVE_ABOVE_OBJECT,
        State.DESCEND,
        State.LIFT,
        State.MOVE_ABOVE_PLACE,
        State.DESCEND_TO_PLACE,
        State.RETREAT,
    )
    assert [spec.role for spec in processes.specs] == ["task-station"]
    assert runtime.consumer_argv("7") is None


def test_ros_plan_prefix_adapter_uses_dynamic_targets_for_every_motion_state() -> None:
    from so101_demo.core.domain import State
    from so101_demo.runtime.parallel_worker_runtime import RosDynamicPlanPrefixAdapter

    calls = []
    planner = SimpleNamespace(control=object())
    sample = object()
    template = SimpleNamespace(
        arm_joint_names=("shoulder",),
        planning_frame="world",
        planning_group="arm",
        tcp_link="gripper_frame_link",
        position_tolerance_m=0.01,
        orientation_tolerance_rad=(0.1, 0.1, 0.1),
        planning_timeout_s=2.0,
        velocity_scaling=0.2,
        acceleration_scaling=0.2,
    )
    targets = object()

    def plan_state(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(accepted=True), "before", "after"

    adapter = RosDynamicPlanPrefixAdapter(
        object(),
        template,
        object(),
        planner_factory=lambda node, joints: planner,
        target_resolver=lambda value, policy: targets
        if (value, policy) == (sample, template)
        else None,
        plan_state=plan_state,
    )
    states = (State.MOVE_ABOVE_OBJECT, State.DESCEND, State.RETREAT)

    plans = adapter(SimpleNamespace(point_id="P01"), sample, states)

    assert len(plans) == 3
    assert [call["state"] for call in calls] == list(states)
    assert all(call["provider"] is targets for call in calls)
    assert all(call["control"] is planner.control for call in calls)


def test_execute_consumer_has_exact_mode_and_reset_epoch_semantics(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    processes = _ProcessGroup()
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.EXECUTE,
        process_group=processes,
        execute_result=lambda _lease, _admitted, _child: SimpleNamespace(
            status=AttemptStatus.PASSED,
            physical_action_proven_absent=False,
        ),
    )
    runtime.start_physical_runtime()
    lease = SimpleNamespace(point_id="P01")
    admitted = SimpleNamespace(reset_epoch="reset-7")

    assert runtime.execute_expert(lease, admitted).status is AttemptStatus.PASSED
    consumer = processes.specs[-1]
    assert consumer.role == "dynamic-consumer"
    argv = consumer.argv
    backend = argv.index("--backend")
    assert argv[backend : backend + 7] == (
        "--backend",
        "mujoco",
        "--mode",
        "execute",
        "--execute",
        "--expected-reset-epoch",
        "reset-7",
    )
    assert "--execute" in argv
    assert processes.environments[-1]["ROS_DOMAIN_ID"] == "181"


def test_runtime_owns_localization_publication_and_fresh_camera_artifacts(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    events = []
    resources = _resources(tmp_path, "worker-1", 0, 181)
    reset = SimpleNamespace(reset_completed_monotonic_s=10.0)
    localized = SimpleNamespace(reset_epoch="reset-8", pose="world-pose")
    admitted = SimpleNamespace(reset_epoch="reset-8", pose="accepted")

    def capture(path, newer_than):
        path.write_bytes(b"rgb")
        events.append((path.name, newer_than))
        return path

    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda lease: reset,
        initial_gate=lambda lease, receipt: (lease, receipt),
        localize=lambda lease, result: localized,
        admit_pose=lambda lease, value: admitted,
        publish_pose=lambda value: events.append(("POSE_ACCEPTED", value)),
        capture_rgb=capture,
    )
    lease = SimpleNamespace(point_id="P01")
    runtime.start_physical_runtime()

    receipt, gate = runtime.reset_and_validate_point(lease)
    assert receipt is reset
    assert gate == (lease, reset)
    assert runtime.localize_and_admit_pose(lease, "broker-result") is admitted
    runtime.capture_terminal(lease, action_boundary_monotonic_s=20.0)

    assert events == [
        ("initial-rgb.png", 10.0),
        ("POSE_ACCEPTED", admitted),
        ("terminal-rgb.png", 20.0),
    ]
    assert resources.worker_root / "initial-rgb.png" in runtime.captured_artifacts
    assert resources.worker_root / "terminal-rgb.png" in runtime.captured_artifacts


def test_rgb_capture_fails_closed_when_no_regular_artifact_is_saved(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        capture_rgb=lambda path, _newer_than: path,
    )
    runtime.start_physical_runtime()

    with pytest.raises(RuntimeError, match="regular artifact"):
        runtime.reset_point(SimpleNamespace(point_id="P01"))


def test_recover_and_shutdown_use_only_the_runtime_owned_group(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    processes = _ProcessGroup()
    recoveries = []
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda worker, generation, deadline: recoveries.append(
            (worker, generation, deadline)
        )
        or True,
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 3, 120.0) is True
    runtime.shutdown_owned()

    assert recoveries == [("worker-1", 3, 120.0)]
    assert processes.shutdown_calls == 2
    assert [spec.role for spec in processes.specs] == [
        "task-station",
        "task-station",
    ]
