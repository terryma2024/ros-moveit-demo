from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from so101_demo.application.task_reachability import (
    ReachabilityReport,
    ReachabilityStatus,
)
from so101_demo.core.domain import ActionResult, ActionStatus, RunStatus, State
from so101_demo.core.runner import ExecutionContext
from so101_demo.core.task_geometry import TaskGeometry, load_task_geometry
from so101_demo.ports.cup_scene_observation import CupSceneObservation
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ports.planning_scene import SceneCommandReceipt
from so101_demo.profiling.model import ProfilingConfig, ProfilingMode
from so101_demo.profiling.session import build_profiler
from so101_demo.runtime.workflow_events import EventDecoder, EventEmitter
from test_dynamic_pick import _sample, _template

PACKAGE = Path(__file__).parents[1]


def _geometry() -> TaskGeometry:
    return load_task_geometry(PACKAGE / "assets/common/geometry-manifest.yaml")


def _observation(
    *,
    simulator_x: float = 0.02,
    moveit_x: float | None = None,
    attached: bool = False,
) -> CupSceneObservation:
    simulator = PoseEvidence(
        (simulator_x, -0.28, 0.165),
        (0.0, 0.0, 0.0, 1.0),
    )
    moveit = PoseEvidence(
        (simulator_x if moveit_x is None else moveit_x, -0.28, 0.165),
        (0.0, 0.0, 0.0, 1.0),
    )
    return CupSceneObservation(
        simulator,
        1.0,
        moveit,
        1.1,
        attached,
        simulation_session_id="task-5",
        reset_epoch=3,
        paused=False,
    )


def _identity_observation(**changes):
    observation = _observation(simulator_x=-0.03, moveit_x=-0.03)
    values = {
        "simulator_pose_world": observation.simulator_pose_world,
        "simulator_received_monotonic_s": observation.simulator_received_monotonic_s,
        "moveit_pose_world": observation.moveit_pose_world,
        "moveit_received_monotonic_s": observation.moveit_received_monotonic_s,
        "moveit_attached": observation.moveit_attached,
        "simulation_session_id": "task-5",
        "reset_epoch": 3,
        "paused": False,
        **changes,
    }
    return SimpleNamespace(**values)


def _receipt(
    phase: str,
    success: bool,
    *,
    failure_code: str | None = None,
    evidence: dict[str, object] | None = None,
) -> SceneCommandReceipt:
    return SceneCommandReceipt(
        backend="mujoco",
        phase=phase,
        success=success,
        failure_code=None if success else failure_code or f"SCENE_{phase}_FAILED",
        evidence={} if evidence is None else evidence,
    )


class RecordingTaskScenePort:
    def __init__(
        self,
        *,
        apply_success: bool = True,
        observe_success: bool = True,
        apply_failure_code: str | None = None,
        observe_failure_code: str | None = None,
        apply_evidence: dict[str, object] | None = None,
        observe_evidence: dict[str, object] | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.apply_success = apply_success
        self.observe_success = observe_success
        self.apply_failure_code = apply_failure_code
        self.observe_failure_code = observe_failure_code
        self.apply_evidence = apply_evidence
        self.observe_evidence = observe_evidence
        self.events = events
        self.calls: list[str] = []
        self.applied_geometry: TaskGeometry | None = None
        self.closed = False

    def apply_task_scene(self, geometry: TaskGeometry) -> SceneCommandReceipt:
        self.calls.append("apply")
        if self.events is not None:
            self.events.append("task_scene.apply")
        self.applied_geometry = geometry
        return _receipt(
            "APPLY",
            self.apply_success,
            failure_code=self.apply_failure_code,
            evidence=self.apply_evidence,
        )

    def observe_task_scene(
        self,
        geometry: TaskGeometry,
        *,
        expected_cup_attachment: str | None,
    ) -> SceneCommandReceipt:
        self.calls.append("observe")
        if self.events is not None:
            self.events.append("task_scene.observe")
        assert geometry is self.applied_geometry
        assert expected_cup_attachment is None
        return _receipt(
            "READ_BACK",
            self.observe_success,
            failure_code=self.observe_failure_code,
            evidence=self.observe_evidence,
        )


def test_divergent_perception_rejects_before_any_scene_mutation() -> None:
    from so101_demo.application.cup_pose_preflight import CupPosePreflightError
    from so101_demo.application.dynamic_scene_sync import prepare_dynamic_cup_scene

    scene = RecordingTaskScenePort()
    with pytest.raises(CupPosePreflightError, match="topic_vs_simulator") as captured:
        prepare_dynamic_cup_scene(
            _sample(0.07),
            _observation(simulator_x=0.02),
            _template(),
            _geometry(),
            scene,
        )

    assert captured.value.code == "CUP_POSE_SCENE_DIVERGENCE"
    assert scene.calls == []


def test_attached_cup_rejects_before_any_scene_mutation() -> None:
    from so101_demo.application.cup_pose_preflight import CupPosePreflightError
    from so101_demo.application.dynamic_scene_sync import prepare_dynamic_cup_scene

    scene = RecordingTaskScenePort()
    with pytest.raises(CupPosePreflightError, match="world object") as captured:
        prepare_dynamic_cup_scene(
            _sample(),
            _observation(attached=True),
            _template(),
            _geometry(),
            scene,
        )

    assert captured.value.code == "CUP_POSE_SCENE_DIVERGENCE"
    assert scene.calls == []


def test_confirmed_perception_updates_only_plastic_cup_and_reads_back() -> None:
    from so101_demo.application.dynamic_scene_sync import prepare_dynamic_cup_scene

    original = _geometry()
    scene = RecordingTaskScenePort()

    updated = prepare_dynamic_cup_scene(
        _sample(-0.03),
        _observation(simulator_x=-0.03),
        _template(),
        original,
        scene,
    )

    assert scene.calls == ["apply", "observe"]
    assert updated is not original
    assert updated.object("plastic_cup").pose.values == (
        -0.03,
        -0.28,
        0.165,
        0.0,
        0.0,
        0.0,
        1.0,
    )
    assert original.object("plastic_cup").pose != updated.object("plastic_cup").pose
    assert updated.object("table") == original.object("table")
    assert updated.object("pedestal") == original.object("pedestal")
    assert tuple(item for item in updated.objects if item.object_id != "plastic_cup") == tuple(
        item for item in original.objects if item.object_id != "plastic_cup"
    )


@pytest.mark.parametrize(
    ("apply_success", "observe_success", "expected_calls", "message"),
    (
        (False, True, ["apply"], "scene apply failed"),
        (True, False, ["apply", "observe"], "scene readback failed"),
    ),
)
def test_scene_transaction_failures_stop_at_the_failed_boundary(
    apply_success: bool,
    observe_success: bool,
    expected_calls: list[str],
    message: str,
) -> None:
    from so101_demo.application.cup_pose_preflight import CupPosePreflightError
    from so101_demo.application.dynamic_scene_sync import prepare_dynamic_cup_scene

    scene = RecordingTaskScenePort(
        apply_success=apply_success,
        observe_success=observe_success,
    )
    with pytest.raises(CupPosePreflightError, match=message) as captured:
        prepare_dynamic_cup_scene(
            _sample(),
            _observation(),
            _template(),
            _geometry(),
            scene,
        )

    assert captured.value.code == "CUP_POSE_SCENE_DIVERGENCE"
    assert scene.calls == expected_calls


def test_scene_apply_failure_preserves_service_and_timeout_diagnostics() -> None:
    from so101_demo.application.cup_pose_preflight import CupPosePreflightError
    from so101_demo.application.dynamic_scene_sync import prepare_dynamic_cup_scene

    scene = RecordingTaskScenePort(
        apply_success=False,
        apply_failure_code="SCENE_SERVICE_UNAVAILABLE",
        apply_evidence={
            "service": "/apply_planning_scene",
            "timeout_s": 5.0,
            "detail": "service discovery deadline expired",
        },
    )

    with pytest.raises(CupPosePreflightError) as captured:
        prepare_dynamic_cup_scene(
            _sample(),
            _observation(),
            _template(),
            _geometry(),
            scene,
        )

    message = str(captured.value)
    assert "SCENE_SERVICE_UNAVAILABLE" in message
    assert "/apply_planning_scene" in message
    assert "timeout_s" in message
    assert "5.0" in message
    assert "service discovery deadline expired" in message


def test_scene_readback_failure_identifies_mismatched_object_property_and_membership() -> None:
    from so101_demo.application.cup_pose_preflight import CupPosePreflightError
    from so101_demo.application.dynamic_scene_sync import prepare_dynamic_cup_scene

    scene = RecordingTaskScenePort(
        observe_success=False,
        observe_failure_code="SCENE_READBACK_MISMATCH",
        observe_evidence={
            "mismatches": ["plastic_cup.pose"],
            "world_ids": ["pedestal", "plastic_cup", "table"],
            "attached_ids": [],
            "detail": "expected perceived pose was not observed",
        },
    )

    with pytest.raises(CupPosePreflightError) as captured:
        prepare_dynamic_cup_scene(
            _sample(),
            _observation(),
            _template(),
            _geometry(),
            scene,
        )

    message = str(captured.value)
    assert "SCENE_READBACK_MISMATCH" in message
    assert "plastic_cup.pose" in message
    assert "world_ids" in message
    assert "attached_ids" in message
    assert "expected perceived pose was not observed" in message


@pytest.mark.parametrize("objects", ((), ("duplicate",)))
def test_missing_or_duplicate_plastic_cup_fails_closed_without_scene_mutation(
    objects: tuple[str, ...],
) -> None:
    from so101_demo.application.cup_pose_preflight import CupPosePreflightError
    from so101_demo.application.dynamic_scene_sync import prepare_dynamic_cup_scene

    geometry = _geometry()
    if objects:
        invalid = replace(
            geometry,
            objects=geometry.objects + (geometry.object("plastic_cup"),),
        )
    else:
        invalid = replace(
            geometry,
            objects=tuple(item for item in geometry.objects if item.object_id != "plastic_cup"),
        )
    scene = RecordingTaskScenePort()

    with pytest.raises(CupPosePreflightError, match="exactly one plastic_cup") as captured:
        prepare_dynamic_cup_scene(
            _sample(),
            _observation(),
            _template(),
            invalid,
            scene,
        )

    assert captured.value.code == "CUP_POSE_SCENE_DIVERGENCE"
    assert scene.calls == []


class _FakeNode:
    def __init__(self, events: list[str], faults: frozenset[str]) -> None:
        self._events = events
        self._faults = faults

    def destroy_node(self) -> None:
        self._events.append("node.close")
        if "node.destroy" in self._faults:
            raise RuntimeError("node destroy failed")


class _FakeRclpy:
    def __init__(self, events: list[str], faults: frozenset[str]) -> None:
        self._events = events
        self._faults = faults

    def init(self) -> None:
        self._events.append("ros.init")
        if "rclpy.init" in self._faults:
            raise RuntimeError("RCLPY_INIT_FAILED: context init failed")

    def create_node(self, _name: str, *, parameter_overrides) -> _FakeNode:
        assert len(parameter_overrides) == 1
        self._events.append("node.create")
        if "node.create" in self._faults:
            raise RuntimeError("NODE_CREATE_FAILED: node construction failed")
        return _FakeNode(self._events, self._faults)

    def ok(self) -> bool:
        return True

    def shutdown(self) -> None:
        self._events.append("ros.shutdown")
        if "rclpy.shutdown" in self._faults:
            raise RuntimeError("rclpy shutdown failed")


class _FakeSource:
    def __init__(self, events: list[str], sample) -> None:
        self._events = events
        self._sample = sample

    def get_one(self, timeout_s: float):
        assert timeout_s == 2.0
        self._events.append("sample.acquire")
        return self._sample


class _FakeObserver:
    def __init__(
        self,
        events: list[str],
        observations,
        faults: frozenset[str],
    ) -> None:
        self._events = events
        self._observations = iter(observations)
        self._faults = faults

    def observe(self, timeout_s: float) -> CupSceneObservation:
        assert timeout_s == 5.0
        self._events.append("truth.observe")
        return next(self._observations)

    def close(self) -> None:
        self._events.append("truth.close")
        if "observer.close" in self._faults:
            raise RuntimeError("truth observer close failed")


class _FakeExecution:
    def __init__(self, events: list[str], faults: frozenset[str]) -> None:
        self._events = events
        self._faults = faults
        self.observer = object()

    def finish(self, _result) -> None:
        self._events.append("execution.finish")
        if "execution.finish" in self._faults:
            raise RuntimeError("execution finish failed")

    def close(self) -> None:
        self._events.append("execution.close")
        if "execution.close" in self._faults:
            raise RuntimeError("execution close failed")


class _FakeRunner:
    def __init__(self, events: list[str], result, faults: frozenset[str]) -> None:
        self._events = events
        self._result = result
        self._faults = faults

    def run(self, request):
        assert request.mode.value == "execute"
        self._events.append("runner.run")
        if "runner.run" in self._faults:
            raise RuntimeError("PRIMARY_WORKFLOW_FAILED: runner exploded")
        return self._result


def _runtime(
    events: list[str],
    *,
    observations: tuple[CupSceneObservation, ...],
    scene: RecordingTaskScenePort,
    faults: frozenset[str] = frozenset(),
    reachability_status: ReachabilityStatus = ReachabilityStatus.REACHABLE,
):
    scene.events = events
    sample = _sample(-0.03)
    template = _template()
    loaded = SimpleNamespace(
        template=template,
        execution_allowed=True,
        path=Path("policy.yaml"),
        sha256="a" * 64,
    )
    result = SimpleNamespace(
        status=RunStatus.DONE,
        current_state=State.DONE,
        transition_count=17,
        state_trace=(State.IDLE, State.DONE),
        failure=None,
    )

    def load_geometry(_path: Path) -> TaskGeometry:
        assert _path == PACKAGE / "assets/common/geometry-manifest.yaml"
        events.append("geometry.load")
        return _geometry()

    def source_factory(_node, _template):
        events.append("source.create")
        return _FakeSource(events, sample)

    def observer_factory(_node, session_id: str, expected_reset_epoch: int):
        assert session_id == "task-5"
        assert expected_reset_epoch == 3
        events.append("truth.create")
        return _FakeObserver(events, observations, faults)

    def scene_factory(_node, backend: str, timeout_s: float):
        assert (backend, timeout_s) == ("mujoco", template.planning_timeout_s)
        events.append("task_scene.create")
        return scene

    def resolve(sample_arg, template_arg):
        assert sample_arg is sample
        assert template_arg is template
        events.append("targets.resolve")
        return SimpleNamespace(input_pose=sample, targets={})

    def execution_factory(_node, _template, _targets, **_kwargs):
        events.append("execution.create")
        return _FakeExecution(events, faults)

    def reachability_preflight(_node, sample_arg, template_arg, scene_revision):
        assert sample_arg is sample
        assert template_arg is template
        assert scene_revision == 3
        events.append("reachability.check")
        return ReachabilityReport(
            point_id="perceived_cup",
            status=reachability_status,
            segments=(),
            first_failure_code=(
                None
                if reachability_status is ReachabilityStatus.REACHABLE
                else "MOVEIT_PLAN_FAILED"
            ),
            scene_revision=scene_revision,
        )

    def build_actions(_execution, _targets):
        events.append("actions.build")
        return object()

    def runner_factory(_actions, **_kwargs):
        events.append("runner.create")
        return _FakeRunner(events, result, faults)

    def cleanup_task_scene(scene_arg) -> None:
        assert scene_arg is scene
        events.append("task_scene.cleanup")
        scene.closed = True
        if "task_scene.cleanup" in faults:
            raise RuntimeError("task scene cleanup failed")

    return SimpleNamespace(
        rclpy=_FakeRclpy(events, faults),
        parameter=lambda name, value: (name, value),
        get_package_share_directory=lambda _name: str(PACKAGE),
        load_policy=lambda _share, backend: loaded,
        load_geometry=load_geometry,
        cup_pose_source=source_factory,
        cup_scene_observer=observer_factory,
        task_scene_port=scene_factory,
        cleanup_task_scene=cleanup_task_scene,
        resolve_motion_targets=resolve,
        reachability_preflight=reachability_preflight,
        execution=execution_factory,
        build_actions=build_actions,
        runner=runner_factory,
    )


def _options(tmp_path: Path):
    return SimpleNamespace(
        session_id="task-5",
        expected_reset_epoch=3,
        evidence_root=tmp_path,
        cup_pose_timeout_s=2.0,
    )


def test_run_dynamic_execute_orders_scene_convergence_before_motion_construction(
    tmp_path,
    capsys,
) -> None:
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events: list[str] = []
    scene = RecordingTaskScenePort()
    runtime = _runtime(
        events,
        observations=(
            _observation(simulator_x=-0.03, moveit_x=0.02),
            _observation(simulator_x=-0.03, moveit_x=-0.03),
            _observation(simulator_x=-0.03, moveit_x=-0.03),
        ),
        scene=scene,
    )

    assert run_dynamic_execute(_options(tmp_path), _runtime=runtime) == 0

    assert events == [
        "geometry.load",
        "ros.init",
        "node.create",
        "source.create",
        "sample.acquire",
        "truth.create",
        "truth.observe",
        "task_scene.create",
        "task_scene.apply",
        "task_scene.observe",
        "truth.observe",
        "truth.observe",
        "targets.resolve",
        "reachability.check",
        "execution.create",
        "actions.build",
        "runner.create",
        "runner.run",
        "execution.finish",
        "execution.close",
        "task_scene.cleanup",
        "truth.close",
        "node.close",
        "ros.shutdown",
    ]
    assert scene.calls[:2] == ["apply", "observe"]
    output = capsys.readouterr().out
    assert "status=READY subscription=/cup_pose" in output
    assert "status=POSE_ACCEPTED source_stamp_ns=1000000000" in output
    assert "status=DONE" in output


def test_run_dynamic_execute_emits_ready_after_subscription_before_pose_wait(
    tmp_path,
) -> None:
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events: list[str] = []
    lines: list[str] = []

    def write(line: str) -> None:
        lines.append(line)
        document = json.loads(line.removeprefix("SO101_EVENT "))
        events.append(f"workflow.{document['event']}")

    emitter = EventEmitter("w1", "dynamic_runtime", write, lambda: 100)
    emitter.emit(
        "RUNTIME_STARTED",
        payload={"request_id": "r1", "session_id": "task-5", "reset_epoch": 3},
    )
    scene = RecordingTaskScenePort()
    runtime = _runtime(
        events,
        observations=(
            _observation(simulator_x=-0.03, moveit_x=0.02),
            _observation(simulator_x=-0.03, moveit_x=-0.03),
            _observation(simulator_x=-0.03, moveit_x=-0.03),
        ),
        scene=scene,
    )

    assert run_dynamic_execute(
        _options(tmp_path), event_emitter=emitter, _runtime=runtime
    ) == 0

    assert events.index("source.create") < events.index("workflow.RUNTIME_READY")
    assert events.index("workflow.RUNTIME_READY") < events.index("sample.acquire")
    assert events.index("ros.shutdown") < events.index("workflow.RUNTIME_COMPLETED")
    decoded = EventDecoder("w1", frozenset({"dynamic_runtime"})).feed(
        "".join(lines).encode(), now_ns=100
    )
    assert [event.event for event in decoded] == [
        "RUNTIME_STARTED",
        "RUNTIME_READY",
        "RUNTIME_COMPLETED",
    ]
    assert decoded[-1].payload == {
        "manifest_path": str(tmp_path / "dynamic-execute-manifest.json"),
        "runtime_exit_code": 0,
    }


def test_run_dynamic_execute_emits_one_fixed_terminal_failure(
    tmp_path,
    capsys,
) -> None:
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events: list[str] = []
    lines: list[str] = []
    emitter = EventEmitter("w1", "dynamic_runtime", lines.append, lambda: 100)
    emitter.emit(
        "RUNTIME_STARTED",
        payload={"request_id": "r1", "session_id": "task-5", "reset_epoch": 3},
    )
    runtime = _runtime(
        events,
        observations=(
            _observation(simulator_x=-0.03, moveit_x=0.02),
            _observation(simulator_x=-0.03, moveit_x=-0.03),
            _observation(simulator_x=-0.03, moveit_x=-0.03),
        ),
        scene=RecordingTaskScenePort(),
        faults=frozenset({"runner.run"}),
    )

    assert run_dynamic_execute(
        _options(tmp_path), event_emitter=emitter, _runtime=runtime
    ) == 1

    decoded = EventDecoder("w1", frozenset({"dynamic_runtime"})).feed(
        "".join(lines).encode(), now_ns=100
    )
    assert [event.event for event in decoded] == [
        "RUNTIME_STARTED",
        "RUNTIME_READY",
        "RUNTIME_FAILED",
    ]
    assert decoded[-1].failure_code == "DYNAMIC_RUNTIME_INTERNAL_ERROR"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "failure=PRIMARY_WORKFLOW_FAILED" in captured.err


def test_run_dynamic_execute_passes_verified_workflow_and_request_identity(
    tmp_path,
) -> None:
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events: list[str] = []
    runtime = _runtime(
        events,
        observations=(
            _observation(simulator_x=-0.03, moveit_x=0.02),
            _observation(simulator_x=-0.03, moveit_x=-0.03),
            _observation(simulator_x=-0.03, moveit_x=-0.03),
        ),
        scene=RecordingTaskScenePort(),
    )
    captured: dict[str, object] = {}
    original_execution = runtime.execution

    def execution(*args, **kwargs):
        captured.update(kwargs)
        return original_execution(*args, **kwargs)

    runtime.execution = execution
    options = _options(tmp_path)
    options.workflow_id = "w1"
    options.request_id = "r1"

    assert run_dynamic_execute(options, _runtime=runtime) == 0

    assert captured["workflow_id"] == "w1"
    assert captured["request_id"] == "r1"


def test_run_dynamic_execute_profiles_setup_state_and_cleanup(tmp_path) -> None:
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events: list[str] = []
    runtime = _runtime(
        events,
        observations=(
            _observation(simulator_x=-0.03, moveit_x=0.02),
            _observation(simulator_x=-0.03, moveit_x=-0.03),
            _observation(simulator_x=-0.03, moveit_x=-0.03),
        ),
        scene=RecordingTaskScenePort(),
    )

    class Action:
        def run(self, context: ExecutionContext) -> ActionResult:
            assert context.state is State.PREPARE_OPEN_GRIPPER
            return ActionResult(ActionStatus.SUCCEEDED)

    original_runner = runtime.runner
    runtime.build_actions = lambda _execution, _targets: {
        State.PREPARE_OPEN_GRIPPER: Action()
    }

    def runner_factory(actions, **kwargs):
        delegate = original_runner(actions, **kwargs)

        class Runner:
            def run(self, request):
                actions[State.PREPARE_OPEN_GRIPPER].run(
                    ExecutionContext(request, State.PREPARE_OPEN_GRIPPER, 0)
                )
                return delegate.run(request)

        return Runner()

    runtime.runner = runner_factory
    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.TRACE,
            output_root=tmp_path / "profiling",
            session_id="task-5",
            process_role="dynamic-runtime",
        )
    )
    assert profiler is not None

    assert run_dynamic_execute(
        _options(tmp_path),
        profiler=profiler,
        _runtime=runtime,
    ) == 0
    profiler.close()

    complete_events = [
        json.loads(line)
        for line in (
            tmp_path / "profiling/processes/dynamic-runtime.events.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if '"event_type":"span_complete"' in line
    ]
    assert [event["name"] for event in complete_events] == [
        "runtime.setup",
        "runtime.state.PREPARE_OPEN_GRIPPER",
        "runtime.cleanup",
    ]
    assert complete_events[0]["outcome"] == "accepted"
    assert complete_events[1]["outcome"] == "SUCCEEDED"
    assert complete_events[2]["outcome"] == "ok"


def test_unreachable_preflight_writes_evidence_and_never_constructs_motion(
    tmp_path,
    capsys,
) -> None:
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events: list[str] = []
    scene = RecordingTaskScenePort()
    runtime = _runtime(
        events,
        observations=(
            _observation(simulator_x=-0.03, moveit_x=0.02),
            _observation(simulator_x=-0.03, moveit_x=-0.03),
            _observation(simulator_x=-0.03, moveit_x=-0.03),
        ),
        scene=scene,
        reachability_status=ReachabilityStatus.UNREACHABLE,
    )

    assert run_dynamic_execute(_options(tmp_path), _runtime=runtime) == 1

    document = __import__("json").loads(
        (tmp_path / "reachability-observed.json").read_text()
    )
    assert document["reports"][0]["status"] == "UNREACHABLE"
    assert "reachability.check" in events
    assert "execution.create" not in events
    assert "actions.build" not in events
    assert "runner.run" not in events
    assert "DYNAMIC_TARGET_UNREACHABLE" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("changes", "failure_code"),
    (
        ({"simulation_session_id": None}, "CUP_POSE_SCENE_IDENTITY_MISSING"),
        ({"reset_epoch": None}, "CUP_POSE_SCENE_IDENTITY_MISSING"),
        ({"paused": None}, "CUP_POSE_SCENE_IDENTITY_MISSING"),
        ({"simulation_session_id": "other"}, "CUP_POSE_SCENE_SESSION_MISMATCH"),
        ({"reset_epoch": 4}, "CUP_POSE_SCENE_RESET_EPOCH_MISMATCH"),
        ({"paused": True}, "CUP_POSE_SCENE_PAUSED"),
    ),
)
def test_run_dynamic_execute_rejects_invalid_identity_before_scene_mutation(
    tmp_path,
    capsys,
    changes,
    failure_code: str,
) -> None:
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events: list[str] = []
    scene = RecordingTaskScenePort()
    observation = _identity_observation(**changes)

    assert (
        run_dynamic_execute(
            _options(tmp_path),
            _runtime=_runtime(
                events,
                observations=(observation, observation, observation),
                scene=scene,
            ),
        )
        == 1
    )

    assert failure_code in capsys.readouterr().out
    assert "task_scene.create" not in events
    assert "task_scene.apply" not in events
    assert "targets.resolve" not in events
    assert scene.calls == []


@pytest.mark.parametrize(
    ("observations", "apply_success", "observe_success"),
    (
        ((_observation(simulator_x=0.02),), True, True),
        ((_observation(simulator_x=-0.03),), False, True),
        ((_observation(simulator_x=-0.03),), True, False),
        (
            (
                _observation(simulator_x=-0.03),
                _observation(simulator_x=-0.03, moveit_x=0.02),
            ),
            True,
            True,
        ),
        (
            (
                _observation(simulator_x=-0.03),
                _observation(simulator_x=-0.03, moveit_x=-0.03),
                _observation(simulator_x=-0.03, moveit_x=0.02),
            ),
            True,
            True,
        ),
    ),
)
def test_run_dynamic_execute_scene_failures_never_resolve_targets_or_construct_motion(
    tmp_path,
    capsys,
    observations: tuple[CupSceneObservation, ...],
    apply_success: bool,
    observe_success: bool,
) -> None:
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events: list[str] = []
    scene = RecordingTaskScenePort(
        apply_success=apply_success,
        observe_success=observe_success,
    )

    assert (
        run_dynamic_execute(
            _options(tmp_path),
            _runtime=_runtime(events, observations=observations, scene=scene),
        )
        == 1
    )

    assert "targets.resolve" not in events
    assert "execution.create" not in events
    assert "CUP_POSE_SCENE_DIVERGENCE" in capsys.readouterr().out
    assert scene.closed
    assert events[-3:] == ["truth.close", "node.close", "ros.shutdown"]


def test_rclpy_init_failure_is_actionable_without_claiming_context_ownership(
    tmp_path,
    capsys,
) -> None:
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events: list[str] = []
    scene = RecordingTaskScenePort()

    assert (
        run_dynamic_execute(
            _options(tmp_path),
            _runtime=_runtime(
                events,
                observations=(),
                scene=scene,
                faults=frozenset({"rclpy.init"}),
            ),
        )
        == 1
    )

    assert events == ["geometry.load", "ros.init"]
    assert "failure=RCLPY_INIT_FAILED" in capsys.readouterr().out


def test_node_creation_failure_after_init_still_shuts_down_owned_context(
    tmp_path,
    capsys,
) -> None:
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events: list[str] = []
    scene = RecordingTaskScenePort()

    assert (
        run_dynamic_execute(
            _options(tmp_path),
            _runtime=_runtime(
                events,
                observations=(),
                scene=scene,
                faults=frozenset({"node.create"}),
            ),
        )
        == 1
    )

    assert events == ["geometry.load", "ros.init", "node.create", "ros.shutdown"]
    assert "failure=NODE_CREATE_FAILED" in capsys.readouterr().out


def test_cleanup_attempts_every_owned_resource_and_aggregates_all_failures(
    tmp_path,
    capsys,
) -> None:
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events: list[str] = []
    scene = RecordingTaskScenePort()
    faults = frozenset(
        {
            "execution.close",
            "task_scene.cleanup",
            "observer.close",
            "node.destroy",
            "rclpy.shutdown",
        }
    )

    assert (
        run_dynamic_execute(
            _options(tmp_path),
            _runtime=_runtime(
                events,
                observations=(
                    _observation(simulator_x=-0.03, moveit_x=0.02),
                    _observation(simulator_x=-0.03, moveit_x=-0.03),
                    _observation(simulator_x=-0.03, moveit_x=-0.03),
                ),
                scene=scene,
                faults=faults,
            ),
        )
        == 1
    )

    assert not hasattr(scene, "close")
    assert scene.closed
    assert events[-6:] == [
        "execution.finish",
        "execution.close",
        "task_scene.cleanup",
        "truth.close",
        "node.close",
        "ros.shutdown",
    ]
    output = capsys.readouterr().out
    assert "failure=DYNAMIC_EXECUTION_CLEANUP_FAILED" in output
    for detail in (
        "execution close failed",
        "task scene cleanup failed",
        "truth observer close failed",
        "node destroy failed",
        "rclpy shutdown failed",
    ):
        assert detail in output


def test_primary_workflow_failure_survives_finish_and_cleanup_failures(
    tmp_path,
    capsys,
) -> None:
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events: list[str] = []
    scene = RecordingTaskScenePort()
    faults = frozenset(
        {
            "runner.run",
            "execution.finish",
            "execution.close",
            "task_scene.cleanup",
            "observer.close",
            "node.destroy",
            "rclpy.shutdown",
        }
    )

    assert (
        run_dynamic_execute(
            _options(tmp_path),
            _runtime=_runtime(
                events,
                observations=(
                    _observation(simulator_x=-0.03, moveit_x=0.02),
                    _observation(simulator_x=-0.03, moveit_x=-0.03),
                    _observation(simulator_x=-0.03, moveit_x=-0.03),
                ),
                scene=scene,
                faults=faults,
            ),
        )
        == 1
    )

    lines = capsys.readouterr().out.splitlines()
    failure_line = next(line for line in lines if "failure=PRIMARY_WORKFLOW_FAILED" in line)
    assert "failure=PRIMARY_WORKFLOW_FAILED" in failure_line
    assert any("failure=DYNAMIC_EXECUTION_FINISH_FAILED" in line for line in lines[1:])
    assert any("failure=DYNAMIC_EXECUTION_CLEANUP_FAILED" in line for line in lines[1:])
    assert events[-6:] == [
        "execution.finish",
        "execution.close",
        "task_scene.cleanup",
        "truth.close",
        "node.close",
        "ros.shutdown",
    ]


def test_finish_failure_after_done_is_actionable_and_cleanup_still_completes(
    tmp_path,
    capsys,
) -> None:
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events: list[str] = []
    scene = RecordingTaskScenePort()

    assert (
        run_dynamic_execute(
            _options(tmp_path),
            _runtime=_runtime(
                events,
                observations=(
                    _observation(simulator_x=-0.03, moveit_x=0.02),
                    _observation(simulator_x=-0.03, moveit_x=-0.03),
                    _observation(simulator_x=-0.03, moveit_x=-0.03),
                ),
                scene=scene,
                faults=frozenset({"execution.finish"}),
            ),
        )
        == 1
    )

    output = capsys.readouterr().out
    assert "failure=DYNAMIC_EXECUTION_FINISH_FAILED" in output
    assert output.count("execution finish failed") == 1
    assert events[-6:] == [
        "execution.finish",
        "execution.close",
        "task_scene.cleanup",
        "truth.close",
        "node.close",
        "ros.shutdown",
    ]
