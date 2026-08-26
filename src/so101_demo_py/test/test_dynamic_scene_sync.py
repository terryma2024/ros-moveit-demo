from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from so101_demo.core.domain import RunStatus, State
from so101_demo.core.task_geometry import TaskGeometry, load_task_geometry
from so101_demo.ports.cup_scene_observation import CupSceneObservation
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ports.planning_scene import SceneCommandReceipt
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
    assert "status=DONE" in capsys.readouterr().out


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
    assert "failure=PRIMARY_WORKFLOW_FAILED" in lines[0]
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
