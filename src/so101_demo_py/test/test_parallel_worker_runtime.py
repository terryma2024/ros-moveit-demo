from dataclasses import replace
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from so101_demo.core.dynamic_pick import DYNAMIC_REACHABILITY_STATES
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
    def __init__(self, events=None, on_shutdown=None) -> None:
        self.specs = []
        self.environments = []
        self.shutdown_calls = 0
        self.events = events
        self.on_shutdown = on_shutdown

    @property
    def manifest(self):
        from so101_demo.runtime.task_stack import OwnedProcessManifest

        return OwnedProcessManifest(tuple())

    def start(self, spec, *, environment=None):
        self.specs.append(spec)
        self.environments.append(dict(environment or {}))
        if self.events is not None:
            self.events.append(("start", spec.role))
        return SimpleNamespace(
            role=spec.role,
            pid=100 + len(self.specs),
            pgid=100 + len(self.specs),
        )

    def shutdown(self):
        self.shutdown_calls += 1
        if self.on_shutdown is not None:
            self.on_shutdown()


def _lease(
    worker="worker-1", *, generation=1, point="P01", attempt="attempt-1"
):
    return SimpleNamespace(
        batch_id="batch-1",
        coordinator_epoch=1,
        worker_id=worker,
        worker_generation=generation,
        point_id=point,
        attempt_id=attempt,
        lease_generation=1,
    )


def _write_capture(path, source_stamp, source_stamp_ns=12_000_000_000):
    from so101_demo.runtime.parallel_worker_runtime import (
        InferenceSnapshotReceipt,
        SourceStampedCapture,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix != ".npy":
        path.write_bytes(b"rgb")
        return SourceStampedCapture(path, source_stamp)
    buffer = io.BytesIO()
    np.save(buffer, np.zeros((4, 5, 3), dtype=np.uint8), allow_pickle=False)
    payload = buffer.getvalue()
    path.write_bytes(payload)
    path.chmod(0o400)
    return InferenceSnapshotReceipt(
        path,
        source_stamp,
        source_stamp_ns=source_stamp_ns,
        source_frame_id="task_camera_frame",
        shape=(4, 5, 3),
        input_sha256=hashlib.sha256(payload).hexdigest(),
        simulation_session_id="session-worker-1",
        source_clock="ros_sim",
    )


def test_stop_control_fences_new_runtime_side_effects(tmp_path):
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: pytest.fail("reset started after stop"),
    )
    runtime.start_physical_runtime()

    assert runtime.shutdown_control("stop", deadline_monotonic_s=99.0) is True
    assert runtime.stop_requested is True
    with pytest.raises(RuntimeError, match="STOP_REQUESTED"):
        runtime.reset_point(_lease())


def test_inference_rgb_must_be_newer_than_reset_sim_clock_and_same_session(tmp_path):
    from so101_demo.runtime.parallel_worker_runtime import (
        InferenceSnapshotReceipt,
        SourceStampedCapture,
        build_worker_runtime,
    )

    def capture(path, boundary):
        if path.suffix != ".npy":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"rgb")
            return SourceStampedCapture(path, boundary + 1.0, source_stamp_ns=12_000_000_001)
        receipt = _write_capture(path, boundary + 1.0)
        return InferenceSnapshotReceipt(
            receipt.path, receipt.source_stamp_monotonic_s,
            source_stamp_ns=12_000_000_000,
            source_frame_id=receipt.source_frame_id,
            shape=receipt.shape,
            input_sha256=receipt.input_sha256,
            simulation_session_id="stale-session",
            source_clock="ros_sim",
        )

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0,
            simulation_time_s=12.0,
            simulation_session_id="session-worker-1",
        ),
        initial_gate=lambda *_args: object(),
        resume_physics=lambda *_args: True,
        capture_rgb=capture,
    )
    runtime.start_physical_runtime()
    reset = runtime.reset_point(_lease())

    with pytest.raises(RuntimeError, match="simulation watermark|simulation session"):
        runtime.point_initial_gate(_lease(), reset)


@pytest.mark.parametrize(
    "mode,disposition,expected",
    [
        (RunMode.PLAN_ONLY, "FAILED", ValidationStatus.VALIDATION_FAILED),
        (RunMode.PLAN_ONLY, "INVALID", ValidationStatus.VALIDATION_INVALID),
        (RunMode.EXECUTE, "FAILED", AttemptStatus.FAILED),
        (RunMode.EXECUTE, "INVALID", AttemptStatus.INVALID),
    ],
)
def test_perception_terminal_maps_without_planning_or_execution(
    tmp_path, mode, disposition, expected
):
    from so101_demo.runtime.parallel_worker_runtime import (
        SourceStampedCapture,
        build_worker_runtime,
    )

    called = []
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 1, 181),
        mode,
        plan_prefix=lambda *_args: called.append("plan"),
        execute_result=lambda *_args: called.append("execute"),
    )
    terminal = SimpleNamespace(
        perception_terminal=True,
        disposition=disposition,
        reason="PERCEPTION_TEST",
    )
    if mode is RunMode.PLAN_ONLY:
        decision = runtime.plan_expert(_lease(), terminal)
    else:
        decision = runtime.execute_expert(_lease(), terminal)
    assert decision.status is expected
    assert decision.reason == "PERCEPTION_TEST"
    assert called == []


def test_workspace_reservation_precedes_first_post_reset_artifact(tmp_path):
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    resources = _resources(tmp_path, "worker-1", 1, 31)
    events = []
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_epoch="reset-1",
            simulation_session_id=resources.session_id,
            reset_completed_monotonic_s=10.0,
        ),
        reserve_workspace=lambda _lease, receipt: events.append(
            ("reserved", receipt.reset_epoch)
        ) or True,
        capture_rgb=lambda path, boundary: events.append(
            ("capture", path.name)
        ) or _write_capture(path, boundary + 1.0),
    )
    runtime.start_physical_runtime()
    lease = _lease()
    reset = runtime.reset_point(lease)
    assert events == [("reserved", "reset-1")]
    runtime._initial_gate = lambda *_args: events.append(("initial-gate",)) or object()
    runtime._resume_physics = lambda *_args: events.append(("resume",)) or True
    runtime.point_initial_gate(lease, reset)
    assert events == [
        ("reserved", "reset-1"),
        ("initial-gate",),
        ("resume",),
        ("capture", "initial-rgb.png"),
        ("capture", "rgb.npy"),
    ]


def test_post_reset_snapshot_is_canonical_immutable_and_lease_bound(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    resources = _resources(tmp_path, "worker-1", 0, 181)
    lease = _lease()
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        initial_gate=lambda _lease, receipt: receipt,
        capture_rgb=lambda path, boundary: _write_capture(path, boundary + 1.0),
    )
    runtime.start_physical_runtime()

    runtime.reset_point(lease)
    runtime.point_initial_gate(
        lease, SimpleNamespace(reset_completed_monotonic_s=10.0)
    )
    snapshot = runtime.inference_snapshot(lease)

    expected = (
        resources.worker_root
        / "validations/P01/attempt-1/working/perception/input/rgb.npy"
    )
    assert snapshot.path == expected
    assert snapshot.shape == (4, 5, 3)
    assert snapshot.source_stamp_ns == 12_000_000_000
    assert snapshot.source_frame_id == "task_camera_frame"
    assert snapshot.input_sha256 == hashlib.sha256(expected.read_bytes()).hexdigest()
    assert expected.stat().st_mode & 0o777 == 0o400
    with pytest.raises(RuntimeError, match="lease identity"):
        runtime.inference_snapshot(_lease(point="P02"))


def _write_numeric(root, source_stamp):
    from so101_demo.runtime.parallel_worker_runtime import NumericEvidenceReceipt

    root.mkdir(parents=True, exist_ok=True)
    paths = tuple(root / name for name in ("depth.json", "tf.json", "physical.json"))
    for path in paths:
        path.write_text("{}")
    return NumericEvidenceReceipt(*paths, source_stamp)


def _plan_receipt(states, completion=25.0):
    from so101_demo.runtime.parallel_worker_runtime import (
        PlanPrefixReceipt,
        PlanSegmentReceipt,
    )

    terminals = [f"terminal-{index}" for index in range(len(states))]
    return PlanPrefixReceipt(
        tuple(
            PlanSegmentReceipt(
                state,
                "initial" if index == 0 else terminals[index - 1],
                terminals[index],
                f"plan-{index}",
                f"before-{index}",
                f"after-{index}",
            )
            for index, state in enumerate(states)
        ),
        completion,
    )


def _replacement(resources: WorkerResources) -> WorkerResources:
    generation = resources.generation + 1
    session_id = f"session-{resources.worker_id}-generation-{generation}"
    environment = dict(resources.environment)
    environment["SO101_WORKER_GENERATION"] = str(generation)
    environment["SO101_SESSION_ID"] = session_id
    return replace(
        resources,
        generation=generation,
        session_id=session_id,
        environment=environment,
    )


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
    assert [process.pid for process in group.manifest.processes] == [510]


def test_owned_group_retains_manifest_when_wait_cannot_prove_exit() -> None:
    from so101_demo.runtime.task_stack import OwnedProcessGroup, StackProcessSpec

    class Unstoppable(_Child):
        def wait(self, timeout):
            raise RuntimeError(f"wait failed after {timeout}")

    group = OwnedProcessGroup(
        popen=lambda *_args, **_kwargs: Unstoppable(520),
        identity_probe=lambda _pid: (520, ("ros2", "launch", "worker"), 12),
        killpg=lambda _pgid, _value: None,
    )
    group.start(StackProcessSpec("station", ("ros2", "launch", "worker")))

    with pytest.raises(RuntimeError, match="wait failed"):
        group.shutdown()

    assert [process.pid for process in group.manifest.processes] == [520]


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
    from so101_demo.core.dynamic_pick import DYNAMIC_REACHABILITY_STATES
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    processes = _ProcessGroup()
    calls = []

    def plan_prefix(lease, admitted, states):
        calls.append((lease, admitted, states))
        return _plan_receipt(states)

    def capture(path, _boundary):
        return _write_capture(path, 26.0)

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=processes,
        ready_probe=lambda required: required
        == ("controllers", "move_group", "joint_states", "planning_scene"),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        initial_gate=lambda _lease, receipt: receipt,
        localize=lambda _lease, result: result,
        capture_numeric_evidence=lambda _lease, _localized, root, boundary: (
            _write_numeric(root, boundary + 1.0)
        ),
        admit_pose=lambda _lease, value: value,
        publish_pose=lambda _value: True,
        plan_prefix=plan_prefix,
        capture_rgb=capture,
    )
    runtime.start_physical_runtime()
    lease = _lease()
    admitted = SimpleNamespace(pose="accepted")

    assert runtime.worker_ready_gate() is True
    runtime.reset_and_validate_point(lease)
    runtime.localize_and_admit_pose(lease, admitted)
    decision = runtime.plan_expert(lease, admitted)
    assert decision.status is ValidationStatus.VALIDATION_PASSED
    assert calls[0][2] == DYNAMIC_REACHABILITY_STATES
    assert tuple(receipt.state for receipt in decision.segment_receipts) == (
        DYNAMIC_REACHABILITY_STATES
    )
    assert decision.terminal_artifacts[0].name == "terminal-rgb.png"
    assert [spec.role for spec in processes.specs] == ["task-station"]
    assert runtime.consumer_argv("7") is None


def test_ros_plan_prefix_adapter_uses_dynamic_targets_for_every_motion_state() -> None:
    from so101_demo.core.dynamic_pick import DYNAMIC_REACHABILITY_STATES
    from so101_demo.ports.evidence import PoseEvidence
    from so101_demo.ports.robot_control import (
        JointStateEvidence,
        PlanResult,
        TcpMotionRequest,
    )
    from so101_demo.runtime.parallel_worker_runtime import RosDynamicPlanPrefixAdapter

    calls = []
    starts = []
    initial = JointStateEvidence(("shoulder",), (0.0,), 1.0)

    class Control:
        def plan_tcp_motion(self, request):
            starts.append(request.start_state)
            index = len(starts)
            terminal = JointStateEvidence(
                ("shoulder",), (float(index),), float(index + 1)
            )
            return PlanResult(
                True,
                request.start_state or initial,
                f"trajectory-{index}",
                terminal_state=terminal,
            )

    planner = SimpleNamespace(control=Control())
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
        request = TcpMotionRequest(
            PoseEvidence((0.0, 0.0, 0.2), (0.0, 0.0, 0.0, 1.0))
        )
        return kwargs["control"].plan_tcp_motion(request), "before", "after"

    adapter = RosDynamicPlanPrefixAdapter(
        object(),
        template,
        object(),
        planner_factory=lambda node, joints: planner,
        target_resolver=lambda value, policy: targets
        if (value, policy) == (sample, template)
        else None,
        plan_state=plan_state,
        clock=lambda: 42.0,
    )

    receipt = adapter(_lease(), sample, DYNAMIC_REACHABILITY_STATES)

    assert len(receipt.segments) == 7
    assert [call["state"] for call in calls] == list(DYNAMIC_REACHABILITY_STATES)
    assert all(call["provider"] is targets for call in calls)
    assert starts[0] is None
    assert starts[1:] == [
        segment.terminal_state for segment in receipt.segments[:-1]
    ]
    assert receipt.completion_monotonic_s == 42.0


def test_ros_plan_prefix_adapter_fails_when_an_accepted_plan_has_no_terminal_state() -> None:
    from so101_demo.ports.evidence import PoseEvidence
    from so101_demo.ports.robot_control import PlanResult, TcpMotionRequest
    from so101_demo.runtime.parallel_worker_runtime import RosDynamicPlanPrefixAdapter

    control = SimpleNamespace(
        plan_tcp_motion=lambda _request: PlanResult(True, trajectory="trajectory")
    )
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

    def plan_state(**kwargs):
        request = TcpMotionRequest(
            PoseEvidence((0.0, 0.0, 0.2), (0.0, 0.0, 0.0, 1.0))
        )
        return kwargs["control"].plan_tcp_motion(request), "before", "after"

    adapter = RosDynamicPlanPrefixAdapter(
        object(),
        template,
        object(),
        planner_factory=lambda _node, _joints: SimpleNamespace(control=control),
        target_resolver=lambda _value, _policy: object(),
        plan_state=plan_state,
    )

    with pytest.raises(RuntimeError, match="TERMINAL_STATE_MISSING"):
        adapter(_lease(), object(), DYNAMIC_REACHABILITY_STATES)


def test_execute_consumer_has_exact_mode_and_reset_epoch_semantics(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import (
        ExecutionCompletionReceipt,
        RuntimeDecision,
        build_worker_runtime,
    )

    events = []
    processes = _ProcessGroup(events)
    resources = _resources(tmp_path, "worker-1", 0, 181)
    lease = _lease()
    reset = SimpleNamespace(reset_epoch="reset-7", reset_completed_monotonic_s=10.0)
    localized = SimpleNamespace(reset_epoch="reset-7", pose="localized")
    admitted = SimpleNamespace(reset_epoch="reset-7", pose="accepted")

    def capture(path, boundary):
        events.append(("capture", path.name, boundary))
        return _write_capture(path, boundary + 1.0)

    runtime = build_worker_runtime(
        resources,
        RunMode.EXECUTE,
        process_group=processes,
        reset_point=lambda _lease: reset,
        initial_gate=lambda _lease, receipt: receipt,
        capture_rgb=capture,
        localize=lambda _lease, _result: events.append(("localize",)) or localized,
        capture_numeric_evidence=lambda _lease, _localized, root, boundary: events.append(
            ("numeric", boundary)
        )
        or _write_numeric(root, boundary + 1.0),
        admit_pose=lambda _lease, value: events.append(("admit",)) or admitted,
        set_physics_paused=lambda _lease, paused: events.append(
            ("physics-paused", paused)
        )
        or True,
        publish_pose=lambda value: events.append(("publish", value)) or True,
        consumer_ready=lambda child: events.append(("ready", child.role)) or True,
        execute_result=lambda _lease, _admitted, _child: events.append(("await",))
        or ExecutionCompletionReceipt(
            RuntimeDecision(
                AttemptStatus.PASSED,
                physical_action_proven_absent=False,
            ),
            30.0,
        ),
    )
    runtime.start_physical_runtime()
    runtime.reset_and_validate_point(lease)
    events.clear()
    accepted = runtime.localize_and_admit_pose(lease, "broker-result")

    assert accepted is admitted
    assert events == [("localize",), ("numeric", 10.0), ("admit",)]
    decision = runtime.execute_expert(lease, admitted)

    assert decision.status is AttemptStatus.PASSED
    assert events == [
        ("localize",),
        ("numeric", 10.0),
        ("admit",),
        ("physics-paused", True),
        ("start", "dynamic-consumer"),
        ("ready", "dynamic-consumer"),
        ("publish", admitted),
        ("physics-paused", False),
        ("await",),
        ("capture", "terminal-rgb.png", 30.0),
    ]
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
        "7",
    )
    assert "--execute" in argv
    assert processes.environments[-1]["ROS_DOMAIN_ID"] == "181"
    expected_root = resources.worker_root / "attempts/P01/attempt-1/working"
    evidence_root = argv.index("--evidence-root")
    assert argv[evidence_root + 1] == str(expected_root / "dynamic")
    assert decision.terminal_artifacts == (expected_root / "terminal-rgb.png",)


def test_execute_failure_still_captures_terminal_evidence(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import (
        ExecutionCompletionReceipt,
        RuntimeDecision,
        build_worker_runtime,
    )

    lease = _lease()
    admitted = SimpleNamespace(reset_epoch="reset-7")
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.EXECUTE,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        initial_gate=lambda _lease, receipt: receipt,
        capture_rgb=lambda path, boundary: _write_capture(path, boundary + 1.0),
        localize=lambda _lease, _result: admitted,
        capture_numeric_evidence=lambda _lease, _localized, root, boundary: (
            _write_numeric(root, boundary + 1.0)
        ),
        admit_pose=lambda _lease, value: value,
        consumer_ready=lambda _child: True,
        publish_pose=lambda _value: True,
        execute_result=lambda *_args: ExecutionCompletionReceipt(
            RuntimeDecision(
                AttemptStatus.FAILED,
                reason="MOTION_FAILED",
                physical_action_proven_absent=False,
            ),
            30.0,
        ),
    )
    runtime.start_physical_runtime()
    runtime.reset_and_validate_point(lease)
    runtime.localize_and_admit_pose(lease, admitted)

    decision = runtime.execute_expert(lease, admitted)

    assert decision.status is AttemptStatus.FAILED
    assert decision.terminal_artifacts[0].name == "terminal-rgb.png"


def test_execute_never_publishes_when_consumer_subscription_is_not_ready(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    events = []
    lease = _lease()
    admitted = SimpleNamespace(reset_epoch="reset-7")
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.EXECUTE,
        process_group=_ProcessGroup(events),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        initial_gate=lambda _lease, receipt: receipt,
        capture_rgb=lambda path, boundary: _write_capture(path, boundary + 1.0),
        localize=lambda _lease, _result: admitted,
        capture_numeric_evidence=lambda _lease, _localized, root, boundary: (
            _write_numeric(root, boundary + 1.0)
        ),
        admit_pose=lambda _lease, value: value,
        set_physics_paused=lambda _lease, paused: events.append(
            ("physics-paused", paused)
        )
        or True,
        consumer_ready=lambda _child: events.append(("ready",)) or False,
        publish_pose=lambda _value: events.append(("publish",)),
        execute_result=lambda *_args: events.append(("await",)),
    )
    runtime.start_physical_runtime()
    runtime.reset_and_validate_point(lease)
    runtime.localize_and_admit_pose(lease, admitted)
    events.clear()

    with pytest.raises(RuntimeError, match="subscription is not ready"):
        runtime.execute_expert(lease, admitted)

    assert events == [
        ("physics-paused", True),
        ("start", "dynamic-consumer"),
        ("ready",),
        ("physics-paused", False),
    ]


@pytest.mark.parametrize("failed_state", [True, False])
def test_execute_fails_closed_if_pose_publication_pause_boundary_fails(
    tmp_path: Path, failed_state: bool
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    events = []
    lease = _lease()
    admitted = SimpleNamespace(reset_epoch="reset-7")
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.EXECUTE,
        process_group=_ProcessGroup(events),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        initial_gate=lambda _lease, receipt: receipt,
        capture_rgb=lambda path, boundary: _write_capture(path, boundary + 1.0),
        localize=lambda _lease, _result: admitted,
        capture_numeric_evidence=lambda _lease, _localized, root, boundary: (
            _write_numeric(root, boundary + 1.0)
        ),
        admit_pose=lambda _lease, value: value,
        set_physics_paused=lambda _lease, paused: events.append(
            ("physics-paused", paused)
        )
        or (paused is not failed_state),
        consumer_ready=lambda _child: events.append(("ready",)) or True,
        publish_pose=lambda _value: events.append(("publish",)) or True,
        execute_result=lambda *_args: events.append(("await",)),
    )
    runtime.start_physical_runtime()
    runtime.reset_and_validate_point(lease)
    runtime.localize_and_admit_pose(lease, admitted)
    events.clear()

    expected = (
        "POSE_PUBLICATION_PAUSE_FAILED"
        if failed_state is True
        else "POSE_PUBLICATION_RESUME_FAILED"
    )
    with pytest.raises(RuntimeError, match=expected):
        runtime.execute_expert(lease, admitted)

    if failed_state is True:
        assert events == [("physics-paused", True)]
    else:
        assert events == [
            ("physics-paused", True),
            ("start", "dynamic-consumer"),
            ("ready",),
            ("publish",),
            ("physics-paused", False),
        ]


def test_runtime_owns_localization_publication_and_fresh_camera_artifacts(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    events = []
    resources = _resources(tmp_path, "worker-1", 0, 181)
    reset = SimpleNamespace(
        reset_epoch="reset-8", reset_completed_monotonic_s=10.0
    )
    localized = SimpleNamespace(reset_epoch="reset-8", pose="world-pose")
    admitted = SimpleNamespace(reset_epoch="reset-8", pose="accepted")

    def capture(path, newer_than):
        events.append((path.name, newer_than))
        return _write_capture(path, newer_than + 1.0)

    def plan_prefix(_lease, _admitted, states):
        return _plan_receipt(states, completion=20.0)

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
        capture_numeric_evidence=lambda _lease, _localized, root, boundary: (
            _write_numeric(root, boundary + 1.0)
        ),
        plan_prefix=plan_prefix,
    )
    lease = _lease()
    runtime.start_physical_runtime()

    receipt, gate = runtime.reset_and_validate_point(lease)
    assert receipt is reset
    assert gate == (lease, reset)
    assert runtime.localize_and_admit_pose(lease, "broker-result") is admitted
    decision = runtime.plan_expert(lease, admitted)

    assert events == [
        ("initial-rgb.png", 10.0),
        ("rgb.npy", 10.0),
        ("POSE_ACCEPTED", admitted),
        ("terminal-rgb.png", 20.0),
    ]
    point_root = resources.worker_root / "validations/P01/attempt-1/working"
    assert point_root / "initial-rgb.png" in runtime.captured_artifacts
    assert point_root / "perception/input/rgb.npy" in runtime.captured_artifacts
    assert point_root / "terminal-rgb.png" in runtime.captured_artifacts
    assert decision.numeric_evidence.depth_path == point_root / "numeric/depth.json"


def test_rgb_capture_requires_a_strictly_newer_source_stamp(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    def stale_capture(path, _newer_than):
        return _write_capture(path, 10.0)

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        initial_gate=lambda *_args: object(),
        resume_physics=lambda *_args: True,
        capture_rgb=stale_capture,
    )
    runtime.start_physical_runtime()

    lease = _lease()
    reset = runtime.reset_point(lease)
    with pytest.raises(RuntimeError, match="newer than boundary"):
        runtime.point_initial_gate(lease, reset)


def test_point_artifacts_reject_traversal_before_capture(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    captures = []
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        capture_rgb=lambda path, boundary: captures.append((path, boundary)),
    )
    runtime.start_physical_runtime()

    with pytest.raises(RuntimeError, match="identity"):
        runtime.reset_point(_lease(point="../escape"))

    assert captures == []


def test_point_artifacts_reject_symlinked_workspace_and_never_overwrite(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    resources = _resources(tmp_path, "worker-1", 0, 181)
    outside = tmp_path / "outside"
    outside.mkdir()
    (resources.worker_root / "validations").symlink_to(outside, target_is_directory=True)
    captures = []
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        capture_rgb=lambda path, boundary: captures.append((path, boundary)),
    )
    runtime.start_physical_runtime()

    with pytest.raises(RuntimeError, match="symlink"):
        runtime.reset_point(_lease())

    assert captures == []


def test_two_points_have_distinct_non_overwriting_evidence_paths(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    observed = []

    def capture(path, boundary):
        observed.append(path)
        return _write_capture(path, boundary + 1.0)

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        initial_gate=lambda *_args: object(),
        resume_physics=lambda *_args: True,
        capture_rgb=capture,
    )
    runtime.start_physical_runtime()
    for lease in (_lease(point="P01"), _lease(point="P02")):
        reset = runtime.reset_point(lease)
        runtime.point_initial_gate(lease, reset)

    assert len(set(observed)) == 4
    assert observed[0].parts[-5:] == (
        "validations", "P01", "attempt-1", "working", "initial-rgb.png"
    )
    assert observed[2].parts[-5:] == (
        "validations", "P02", "attempt-1", "working", "initial-rgb.png"
    )


def test_localization_fails_closed_without_numeric_depth_tf_physical_receipt(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        capture_rgb=lambda path, boundary: _write_capture(path, boundary + 1.0),
        localize=lambda _lease, _result: SimpleNamespace(pose="localized"),
    )
    runtime.start_physical_runtime()
    runtime.reset_point(_lease())

    with pytest.raises(RuntimeError, match="capture_numeric_evidence"):
        runtime.localize_and_admit_pose(_lease(), "broker-result")


def test_numeric_evidence_requires_a_strictly_newer_source_stamp(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    lease = _lease()
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        capture_rgb=lambda path, boundary: _write_capture(path, boundary + 1.0),
        localize=lambda _lease, _result: SimpleNamespace(pose="localized"),
        capture_numeric_evidence=lambda _lease, _localized, root, _boundary: (
            _write_numeric(root, 10.0)
        ),
    )
    runtime.start_physical_runtime()
    runtime.reset_point(lease)

    with pytest.raises(RuntimeError, match="newer than reset boundary"):
        runtime.localize_and_admit_pose(lease, "broker-result")


def test_recover_and_shutdown_use_only_the_runtime_owned_group(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    processes = _ProcessGroup()
    recoveries = []
    resources = _resources(tmp_path, "worker-1", 0, 181)
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda worker, generation, deadline: recoveries.append(
            (worker, generation, deadline)
        )
        or True,
        replace_resources=lambda _worker, *, expected_generation: (
            _replacement(resources)
            if expected_generation == resources.generation
            else None
        ),
        monotonic=lambda: 1.0,
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 1, 120.0) is True
    runtime.shutdown_owned()

    assert recoveries == [("worker-1", 1, 120.0)]
    assert processes.shutdown_calls == 2
    assert [spec.role for spec in processes.specs] == [
        "task-station",
        "task-station",
    ]


def test_recover_rejects_stale_generation_before_shutdown_or_replacement(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    resources = _replacement(_resources(tmp_path, "worker-1", 0, 181))
    processes = _ProcessGroup()
    recoveries = []
    replacements = []
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda *args: recoveries.append(args) or True,
        replace_resources=lambda *args, **kwargs: replacements.append(
            (args, kwargs)
        )
        or _replacement(resources),
        monotonic=lambda: 1.0,
    )
    runtime.start_physical_runtime()

    assert resources.generation == 2
    assert runtime.recover("worker-1", 1, 120.0) is False
    assert processes.shutdown_calls == 0
    assert recoveries == []
    assert replacements == []
    assert [spec.role for spec in processes.specs] == ["task-station"]


def test_recover_replaces_resources_and_accepts_only_the_next_generation(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    original = _resources(tmp_path, "worker-1", 0, 181)
    replacement = _replacement(original)
    calls = []
    processes = _ProcessGroup()

    def replace_resources(worker_id, *, expected_generation):
        calls.append((worker_id, expected_generation))
        return replacement

    runtime = build_worker_runtime(
        original,
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda worker, generation, deadline: calls.append(
            (worker, generation, deadline)
        )
        or True,
        replace_resources=replace_resources,
        monotonic=lambda: 1.0,
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        capture_rgb=lambda path, boundary: _write_capture(path, boundary + 1.0),
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 1, 120.0) is True
    assert runtime.resources is replacement
    assert calls == [("worker-1", 1, 120.0), ("worker-1", 1)]
    assert replacement.generation == 2
    assert replacement.worker_id == original.worker_id
    assert replacement.slot_index == original.slot_index
    assert replacement.ros_domain_id == original.ros_domain_id
    assert replacement.worker_root == original.worker_root
    assert replacement.session_id != original.session_id
    assert processes.environments[-1] == dict(replacement.environment)
    assert f"session_id:={replacement.session_id}" in processes.specs[-1].argv
    runtime.reset_point(
        _lease(generation=2, point="P02", attempt="attempt-2")
    )


@pytest.mark.parametrize(
    "replacement_mutation",
    (
        lambda current: replace(_replacement(current), generation=current.generation),
        lambda current: replace(_replacement(current), session_id=current.session_id),
        lambda current: replace(_replacement(current), worker_id="worker-2"),
        lambda current: replace(_replacement(current), slot_index=2),
        lambda current: replace(_replacement(current), ros_domain_id=182),
        lambda current: replace(
            _replacement(current), worker_root=current.worker_root / "escaped"
        ),
        lambda current: replace(
            _replacement(current),
            environment={
                **dict(_replacement(current).environment),
                "ROS_DOMAIN_ID": "999",
            },
        ),
        lambda _current: object(),
    ),
)
def test_recover_rejects_malformed_replacement_without_starting_new_stack(
    tmp_path: Path, replacement_mutation
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    resources = _resources(tmp_path, "worker-1", 0, 181)
    processes = _ProcessGroup()
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda *_args: True,
        replace_resources=lambda *_args, **_kwargs: replacement_mutation(resources),
        monotonic=lambda: 1.0,
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 1, 120.0) is False
    assert runtime.resources is resources
    assert [spec.role for spec in processes.specs] == ["task-station"]


def test_recover_does_not_restart_when_resource_replacement_crosses_deadline(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    now = [9.0]
    resources = _resources(tmp_path, "worker-1", 0, 181)
    processes = _ProcessGroup()

    def replace_resources(*_args, **_kwargs):
        now[0] = 10.0
        return _replacement(resources)

    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda *_args: True,
        replace_resources=replace_resources,
        monotonic=lambda: now[0],
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 1, 10.0) is False
    assert runtime.resources is resources
    assert [spec.role for spec in processes.specs] == ["task-station"]


def test_recover_checks_deadline_immediately_before_replacement_restart(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    times = iter((9.0, 9.0, 9.0, 9.0, 9.0, 10.0))
    resources = _resources(tmp_path, "worker-1", 0, 181)
    processes = _ProcessGroup()
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda *_args: True,
        replace_resources=lambda *_args, **_kwargs: _replacement(resources),
        monotonic=lambda: next(times),
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 1, 10.0) is False
    assert [spec.role for spec in processes.specs] == ["task-station"]


def test_recover_does_not_continue_after_shutdown_crosses_deadline(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    now = [9.0]
    recovery_calls = []
    processes = _ProcessGroup(on_shutdown=lambda: now.__setitem__(0, 10.0))
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda *args: recovery_calls.append(args) or True,
        monotonic=lambda: now[0],
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 1, 10.0) is False
    assert recovery_calls == []
    assert [spec.role for spec in processes.specs] == ["task-station"]


def test_point_gate_resumes_only_after_fresh_camera_frame_newer_than_reset_watermark(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import (
        SourceStampedCapture,
        build_worker_runtime,
    )

    events = []
    resources = _resources(tmp_path, "worker-1", 0, 181)
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(events=events),
        ready_probe=lambda _requirements: True,
        reset_point=lambda _lease: SimpleNamespace(
            reset_epoch="reset-7", reset_epoch_value=7,
            reset_completed_monotonic_s=10.0, simulation_time_s=20.0,
        ),
        reserve_workspace=lambda *_args: True,
        initial_gate=lambda *_args: events.append(("initial-gate",)) or object(),
        resume_physics=lambda _lease, _reset: events.append(("resume",)) or True,
        capture_rgb=lambda path, boundary: (
            events.append(("capture", path.name))
            or (
                SourceStampedCapture(
                    _write_capture(path, boundary + 1.0).path,
                    boundary + 1.0,
                    21_000_000_000,
                )
                if path.name == "initial-rgb.png"
                    else _write_capture(path, boundary + 1.0, 21_000_000_001)
            )
        ),
        replace_resources=lambda *_args, **_kwargs: _replacement(resources),
    )
    runtime.start_physical_runtime()
    lease = _lease()
    reset = runtime.reset_point(lease)
    runtime.point_initial_gate(lease, reset)
    assert events[1:] == [
        ("initial-gate",),
        ("resume",),
        ("capture", "initial-rgb.png"),
        ("capture", "rgb.npy"),
    ]

    stale_root = tmp_path / "stale"
    stale_resources = _resources(stale_root, "worker-1", 0, 181)

    def stale_capture(path, boundary):
        from so101_demo.runtime.parallel_worker_runtime import (
            SourceStampedCapture,
        )

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"rgb")
        return SourceStampedCapture(
            path, boundary + 1.0, source_stamp_ns=20_000_000_000
        )

    stale = build_worker_runtime(
        stale_resources, RunMode.PLAN_ONLY, process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_epoch="reset-7", reset_epoch_value=7,
            reset_completed_monotonic_s=10.0, simulation_time_s=20.0,
        ),
        reserve_workspace=lambda *_args: True,
        initial_gate=lambda *_args: object(),
        resume_physics=lambda *_args: True,
        capture_rgb=stale_capture,
        replace_resources=lambda *_args, **_kwargs: _replacement(
            stale_resources
        ),
    )
    stale.start_physical_runtime()
    reset = stale.reset_point(lease)
    with pytest.raises(RuntimeError, match="simulation watermark"):
        stale.point_initial_gate(lease, reset)


def test_worker_owned_tree_reaps_exact_child_when_identity_or_manifest_fails(
    monkeypatch, tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import WorkerOwnedProcessTree

    class Child(_Child):
        def __init__(self, pid):
            super().__init__(pid)
            self.events = []

        def terminate(self):
            self.events.append("terminate")

        def kill(self):
            self.events.append("kill")

        def wait(self, timeout):
            self.events.append(("wait", timeout))
            self.returncode = 0
            return 0

    monkeypatch.setattr("os.getpgrp", lambda: 401)
    bad = Child(502)
    tree = WorkerOwnedProcessTree(
        popen=lambda *_args, **_kwargs: bad,
        identity_probe=lambda _pid: (999, ("other",), 5),
    )
    with pytest.raises(RuntimeError, match="escaped"):
        tree.start(SimpleNamespace(role="task-station", argv=("child",)))
    assert bad.events[0] == "terminate"
    assert bad.returncode == 0
    assert tree.manifest.processes == ()

    child = Child(503)
    tree = WorkerOwnedProcessTree(
        popen=lambda *_args, **_kwargs: child,
        identity_probe=lambda _pid: (401, ("child",), 6),
        manifest_path=tmp_path / "owned.json",
    )
    tree._write_manifest = lambda: (_ for _ in ()).throw(OSError("fsync"))
    with pytest.raises(OSError, match="fsync"):
        tree.start(SimpleNamespace(role="task-station", argv=("child",)))
    assert child.events[0] == "terminate"
    assert child.returncode == 0
    assert tree.manifest.processes == ()


def test_worker_owned_tree_serializes_concurrent_shutdown_manifest_publication(
    monkeypatch, tmp_path: Path,
) -> None:
    import json
    import os
    import threading
    import time

    from so101_demo.runtime.parallel_worker_runtime import WorkerOwnedProcessTree

    path = tmp_path / "owned.json"
    tree = WorkerOwnedProcessTree(manifest_path=path)
    real_replace = os.replace
    entered = threading.Event()
    release = threading.Event()
    replace_calls = [0]
    replace_lock = threading.Lock()

    def blocking_first_replace(source, target):
        with replace_lock:
            replace_calls[0] += 1
            call = replace_calls[0]
        if call == 1:
            entered.set()
            assert release.wait(timeout=1.0)
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", blocking_first_replace)
    errors = []

    def shutdown():
        try:
            tree.shutdown()
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)

    first = threading.Thread(target=shutdown)
    second = threading.Thread(target=shutdown)
    first.start()
    assert entered.wait(timeout=1.0)
    second.start()
    time.sleep(0.05)
    release.set()
    first.join(timeout=1.0)
    second.join(timeout=1.0)

    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "processes": [],
        "schema_version": 1,
    }


def test_ros_planner_adapter_closes_owned_node_and_context() -> None:
    from so101_demo.runtime.parallel_worker_runtime import RosDynamicPlanPrefixAdapter

    events = []
    planner = SimpleNamespace(
        control=object(), close=lambda: events.append("planner-close")
    )
    node = SimpleNamespace(destroy_node=lambda: events.append("node-destroy"))
    context = SimpleNamespace(shutdown=lambda: events.append("context-shutdown"))
    template = SimpleNamespace(
        arm_joint_names=("shoulder",), planning_frame="world", planning_group="arm",
        tcp_link="tcp", position_tolerance_m=0.01,
        orientation_tolerance_rad=(0.1, 0.1, 0.1), planning_timeout_s=1.0,
        velocity_scaling=0.2, acceleration_scaling=0.2,
    )
    adapter = RosDynamicPlanPrefixAdapter(
        node, template, object(), planner_factory=lambda *_args: planner,
        target_resolver=lambda *_args: object(), plan_state=lambda **_kwargs: None,
        owned_context=context,
    )
    adapter.close()
    adapter.close()
    assert events == ["planner-close", "node-destroy", "context-shutdown"]


def test_execute_consumer_receives_integer_reset_epoch_not_wire_label(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181), RunMode.EXECUTE,
        process_group=_ProcessGroup(),
    )
    command = runtime.consumer_argv("reset-17", _lease())
    index = command.index("--expected-reset-epoch")
    assert command[index + 1] == "17"
    with pytest.raises(RuntimeError, match="reset epoch"):
        runtime.consumer_argv("not-an-epoch", _lease())


def test_generation_replacement_rebinds_runtime_ports_before_restart(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    original = _resources(tmp_path, "worker-1", 0, 181)
    replacement = _replacement(original)
    events = []
    runtime = build_worker_runtime(
        original, RunMode.PLAN_ONLY, process_group=_ProcessGroup(events=events),
        recovery=lambda *_args: True,
        replace_resources=lambda *_args, **_kwargs: replacement,
        rebind_resources=lambda value: events.append(("rebind", value.session_id)) or True,
        monotonic=lambda: 1.0,
    )
    runtime.start_physical_runtime()
    assert runtime.recover("worker-1", 1, 10.0) is True
    assert events[-2:] == [
        ("rebind", replacement.session_id),
        ("start", "task-station"),
    ]


def test_default_worker_process_tree_joins_outer_worker_pgid(monkeypatch, tmp_path: Path):
    from so101_demo.runtime.parallel_worker_runtime import WorkerOwnedProcessTree

    calls = []
    child = _Child(502)
    monkeypatch.setattr("os.getpgrp", lambda: 401)
    tree = WorkerOwnedProcessTree(
        popen=lambda argv, **kwargs: calls.append((tuple(argv), kwargs)) or child,
        identity_probe=lambda _pid: (401, ("child",), 99),
        signal_process=lambda *_args: None,
    )
    tree.start(SimpleNamespace(role="task-station", argv=("child",)), environment={"PATH": "/bin"})
    assert calls == [(("child",), {"start_new_session": False, "env": {"PATH": "/bin"}})]
    assert tree.manifest.processes[0].pgid == 401


def test_recover_does_not_restart_when_recovery_crosses_deadline(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    now = [9.0]
    processes = _ProcessGroup()
    resources = _resources(tmp_path, "worker-1", 0, 181)

    def recovery(*_args):
        now[0] = 10.0
        return True

    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=recovery,
        replace_resources=lambda *_args, **_kwargs: _replacement(resources),
        monotonic=lambda: now[0],
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 1, 10.0) is False
    assert [spec.role for spec in processes.specs] == ["task-station"]
