"""Teacher policy v3 at the runtime entry: the perceived-vs-truth difference (S05) is telemetry, the safety limits are non-gating,
the watches record instead of stopping (design 2026-10-10 sections 2, 3 and 7). The v1/v2 entry is covered by the untouched tests."""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.application.cup_pose_preflight import (
    CupPosePreflightError, perception_error, validate_cup_scene)
from so101_demo.core.process_summary import ProcessSummary
from so101_demo.ports.cup_scene_observation import CupSceneObservation
from so101_demo.ports.evidence import PoseEvidence
from test_dynamic_pick import _sample, _template
from test_dynamic_scene_sync import RecordingTaskScenePort, _observation, _options, _runtime

PACKAGE = Path(__file__).resolve().parents[1]


def observation(x=0.02, moveit_x=None, quaternion=(0.0, 0.0, 0.0, 1.0)):
    simulator = PoseEvidence((x, -0.28, 0.165), quaternion)
    moveit = PoseEvidence((x if moveit_x is None else moveit_x, -0.28, 0.165), (0.0, 0.0, 0.0, 1.0))
    return CupSceneObservation(simulator, 1.0, moveit, 1.1, False)


# ---- the preflight without the perception gate ----------------------------------------------------------------------------

def test_the_perceived_pose_far_from_truth_is_refused_with_the_gate_and_accepted_without_it():
    far = observation(x=0.2, moveit_x=0.02)                       # the MoveIt shadow is built from the perceived pose
    with pytest.raises(CupPosePreflightError, match="CUP_POSE_SCENE_DIVERGENCE|exceeds"):
        validate_cup_scene(_sample(), far, _template())
    validate_cup_scene(_sample(), far, _template(), perception_gate=False)


def test_the_shadow_must_still_be_the_perceived_pose_and_a_world_object_without_the_gate():
    with pytest.raises(CupPosePreflightError):
        validate_cup_scene(_sample(), observation(x=0.2, moveit_x=0.1), _template(), perception_gate=False)
    attached = CupSceneObservation(PoseEvidence((0.02, -0.28, 0.165), (0.0, 0.0, 0.0, 1.0)), 1.0,
                                   PoseEvidence((0.02, -0.28, 0.165), (0.0, 0.0, 0.0, 1.0)), 1.1, True)
    with pytest.raises(CupPosePreflightError):
        validate_cup_scene(_sample(), attached, _template(), perception_gate=False)


def test_the_perception_error_is_xy_z_and_yaw_free_tilt():
    half = math.sin(math.radians(2.0) / 2)                          # a 2 degree tilt about x
    truth = observation(x=0.0, quaternion=(half, 0.0, 0.0, math.cos(math.radians(2.0) / 2)))
    value = perception_error(_sample(0.003), truth)
    assert value["xy_mm"] == pytest.approx(3.0) and value["z_mm"] == pytest.approx(0.0)
    assert value["tilt_deg"] == pytest.approx(2.0, abs=1e-6)
    yawed = observation(x=0.003, quaternion=(0.0, 0.0, math.sin(0.4), math.cos(0.4)))
    assert perception_error(_sample(0.003), yawed)["tilt_deg"] == pytest.approx(0.0, abs=1e-6)


# ---- run_dynamic_execute with a v3 freeze ---------------------------------------------------------------------------------

class V3Execution:
    """The `_FakeExecution` of the shared fixtures plus what the v3 entry touches."""

    def __init__(self, events, faults):
        self.events = events
        self.observer = object()
        self._teacher_execution_policy = {"schema_version": 3, "execution_deadline_s": 180.0}
        self._process_summary = ProcessSummary()
        self._monotonic = lambda: 1.0
        self._safety_state = None

    def _select_execution_policy(self, name):
        self.policy_name = name

    def finish(self, result):
        self.events.append("execution.finish")

    def close(self):
        self.events.append("execution.close")


def v3_run(tmp_path, monkeypatch, *, name="teacher_execution_policy_v3", safety_fails=False, simulator_x=-0.2):
    from so101_demo.act import frozen_runtime_inputs
    from so101_demo.ros import teacher_safety
    events, built, attached = [], {}, []
    runtime = _runtime(events, observations=tuple(_observation(simulator_x=simulator_x, moveit_x=-0.03) for _ in range(3)),
                       scene=RecordingTaskScenePort())

    def execution(*args, **kwargs):
        built["execution"] = V3Execution(events, frozenset())
        built["execution"]._teacher_execution_policy["schema_version"] = 3 if name.endswith("v3") else 2
        return built["execution"]
    runtime.execution = execution
    plain_actions, plain_runner = runtime.build_actions, runtime.runner
    runtime.build_actions = lambda exec_, targets, **kwargs: (built.__setitem__("actions_workflow", kwargs.get("workflow")),
                                                             plain_actions(exec_, targets))[1]
    runtime.runner = lambda actions, **kwargs: (built.__setitem__("runner_workflow", kwargs.get("workflow")),
                                                plain_runner(actions, **{k: v for k, v in kwargs.items() if k != "workflow"}))[1]
    runtime.bind_scene_source = lambda *a, **k: None
    frozen = {"runtime_policy": {"sha256": "x", "kind": "k"}}
    monkeypatch.setattr(frozen_runtime_inputs, "load_teacher_frozen_inputs",
                        lambda path: (frozen, {"scene_path": "assets/mujoco/act/scene.xml"}, PACKAGE))
    monkeypatch.setattr(frozen_runtime_inputs, "frozen_execution_policy_name", lambda value: name)

    def load(path):
        if safety_fails:
            raise RuntimeError("TEACHER_SAFETY_INPUTS_MISMATCH: x")
        return SimpleNamespace(limits=teacher_safety.CupSafetyLimits(3.2, 1e-4), process_pairs=frozenset(), known_geoms=frozenset())
    monkeypatch.setattr(teacher_safety, "load_frozen_safety", load)
    monkeypatch.setattr(teacher_safety.CollisionWatch, "attach", lambda self, node: attached.append(("collision", self)))
    monkeypatch.setattr(teacher_safety.PhysicsHazardWatch, "attach", lambda self, node: attached.append(("hazard", self)))
    options = _options(tmp_path)
    options.frozen_inputs_manifest = tmp_path / "inputs-manifest.json"
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute
    code = run_dynamic_execute(options, _runtime=runtime)
    run.workflows = (built.get("actions_workflow"), built.get("runner_workflow"))
    return code, built.get("execution"), dict(attached), events


def run():
    """placeholder attribute holder"""


def test_a_v3_run_does_not_refuse_a_perceived_pose_far_from_truth_and_records_the_error(tmp_path, monkeypatch):
    code, execution, watches, events = v3_run(tmp_path, monkeypatch)
    assert code == 0 and "runner.run" in events
    assert execution._perception_error["xy_mm"] == pytest.approx(170.0, abs=1.0) and execution._perception_error["tilt_deg"] == 0.0


def test_a_v3_run_builds_actions_and_runner_with_the_v3_workflow(tmp_path, monkeypatch):
    from so101_demo.core.workflow import SO101_WORKFLOW_V3
    v3_run(tmp_path, monkeypatch)
    assert run.workflows == (SO101_WORKFLOW_V3, SO101_WORKFLOW_V3)
    v3_run(tmp_path, monkeypatch, name="teacher_execution_policy_v2", simulator_x=-0.03)
    assert run.workflows == (None, None)


def test_the_same_divergence_still_refuses_before_motion_with_a_v2_freeze(tmp_path, monkeypatch):
    code, execution, _watches, events = v3_run(tmp_path, monkeypatch, name="teacher_execution_policy_v2")
    assert code == 1 and "runner.run" not in events and execution is None


def test_the_v3_watches_subscribe_but_only_record(tmp_path, monkeypatch):
    code, execution, watches, _events = v3_run(tmp_path, monkeypatch)
    assert code == 0 and set(watches) == {"collision", "hazard"}
    assert watches["collision"]._record_only and watches["hazard"]._record_only
    assert watches["hazard"].limits is None and execution._physics_hazard_watch is watches["hazard"]
    assert execution._safety_limits is execution._process_summary.limits


def test_a_safety_load_failure_is_not_a_refusal_in_v3_but_marks_the_summary_incomplete(tmp_path, monkeypatch):
    code, execution, watches, _events = v3_run(tmp_path, monkeypatch, safety_fails=True)
    assert code == 0 and set(watches) == {"hazard"}
    assert execution._safety_limits_error.startswith("SAFETY_LOAD_FAILED")
    assert "COLLISION_GEOMETRY_UNAVAILABLE" in execution._process_summary.build()["incomplete_reasons"]


def test_a_safety_load_failure_still_refuses_with_a_v2_freeze(tmp_path, monkeypatch):
    code, _execution, _watches, events = v3_run(tmp_path, monkeypatch, name="teacher_execution_policy_v2", safety_fails=True,
                                               simulator_x=-0.03)
    assert code == 1 and "runner.run" not in events


def test_a_degenerate_quaternion_never_refuses_the_run_and_marks_the_summary_incomplete(tmp_path, monkeypatch):
    """The perception error is telemetry: a truth pose that cannot be compared is recorded as PERCEPTION_ERROR_UNAVAILABLE."""
    import test_dynamic_scene_sync as fixtures
    original = fixtures._observation

    def degenerate(**kwargs):
        value = original(**kwargs)
        pose = PoseEvidence(value.simulator_pose_world.position_m, (0.0, 0.0, 0.0, 1.0))
        object.__setattr__(pose, "orientation_xyzw", (0.0, 0.0, 0.0, 0.0))        # the constructor refuses it; the truth bridge could still deliver it
        return value.__class__(**{**{name: getattr(value, name) for name in value.__dataclass_fields__}, "simulator_pose_world": pose})
    monkeypatch.setattr(sys.modules[__name__], "_observation", degenerate)
    code, execution, _watches, events = v3_run(tmp_path, monkeypatch)
    assert code == 0 and "runner.run" in events
    assert execution._perception_error is None
    assert "PERCEPTION_ERROR_UNAVAILABLE" in execution._process_summary.build()["incomplete_reasons"]


@pytest.mark.parametrize("field", ["position", "orientation"])
def test_a_non_finite_truth_pose_is_refused_by_the_perception_error_instead_of_returning_garbage(field):
    """NaN slips through min/max clamping (a NaN axis would read as a 180 degree tilt), so the telemetry function refuses it and the
    runtime records PERCEPTION_ERROR_UNAVAILABLE (review change 3)."""
    nan = float("nan")
    pose = PoseEvidence((0.02, -0.28, 0.165), (0.0, 0.0, 0.0, 1.0))
    object.__setattr__(pose, "position_m" if field == "position" else "orientation_xyzw",
                       (nan, -0.28, 0.165) if field == "position" else (nan, 0.0, 0.0, 1.0))
    truth = CupSceneObservation(pose, 1.0, PoseEvidence((0.02, -0.28, 0.165), (0.0, 0.0, 0.0, 1.0)), 1.1, False)
    with pytest.raises(ValueError, match="PERCEPTION_ERROR_NON_FINITE"):
        perception_error(_sample(0.003), truth)
