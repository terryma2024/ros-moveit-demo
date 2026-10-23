"""Launch configurations, the owned group, dry run, plan only and the plan prefix adapter."""

from pathlib import Path
from types import SimpleNamespace

from parallel_worker_runtime_support import (
    _Child,
    _lease,
    _plan_receipt,
    _ProcessGroup,
    _resources,
    _write_capture,
    _write_numeric,
)
import pytest

from so101_demo.core.dynamic_pick import DYNAMIC_REACHABILITY_STATES
from so101_demo.parallel_batch.contracts.common import RunMode, ValidationStatus


def test_worker_launch_configs_keep_resources_distinct(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_parts.station import headless_task_station_config

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


def test_task_station_config_keeps_linux_frozen_and_gives_darwin_a_visible_station(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_parts.station import (
        headless_task_station_config,
        task_station_config,
    )

    resources = _resources(tmp_path, "worker-1", 0, 181)

    linux = task_station_config(resources, platform="linux")
    assert linux == headless_task_station_config(resources)
    assert linux.headless is True

    darwin = task_station_config(resources, platform="darwin")
    assert darwin.headless is False
    assert darwin.session_id == resources.session_id
    assert darwin.evidence_root == resources.worker_root
    assert len(darwin.processes) == 1
    assert darwin.processes[0].argv[-5:] == (
        "headless:=false",
        "sensor_rendering:=true",
        "include_teleop:=false",
        "session_id:=session-worker-1",
        f"task_evidence_root:={resources.worker_root}",
    )


def test_task_station_config_refuses_a_platform_it_cannot_launch(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_parts.station import task_station_config

    with pytest.raises(RuntimeError, match="unsupported task station platform: win32"):
        task_station_config(_resources(tmp_path, "worker-1", 0, 181), platform="win32")


def test_physical_runtime_uses_the_injected_station_config(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_parts.station import task_station_config
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    resources = _resources(tmp_path, "worker-1", 0, 181)
    processes = _ProcessGroup()
    seen: list[object] = []

    def station_config(candidate):
        seen.append(candidate)
        return task_station_config(candidate, platform="darwin")

    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=processes,
        station_config=station_config,
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0,
            simulation_time_s=12.0,
            simulation_session_id="session-worker-1",
        ),
        initial_gate=lambda *_args: object(),
        capture_rgb=lambda *_args: None,
    )
    runtime.start_physical_runtime()

    assert seen == [resources]
    assert len(processes.specs) == 1
    assert processes.specs[0].argv[-5:] == (
        "headless:=false",
        "sensor_rendering:=true",
        "include_teleop:=false",
        "session_id:=session-worker-1",
        f"task_evidence_root:={resources.worker_root}",
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
    from so101_demo.runtime.parallel_worker_parts.plan_prefix import RosDynamicPlanPrefixAdapter

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
    from so101_demo.runtime.parallel_worker_parts.plan_prefix import RosDynamicPlanPrefixAdapter

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
