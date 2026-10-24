"""R3-a: the start joint pose of an episode reaches the reset through `MujocoReset.reset(joint_overrides=...)`, is drawn deterministically
from (campaign seed, scene id), is rejected when it breaks a joint limit or collides (bounded redraws), and the initial gate expects it.

Without a schema 6 policy the reset call, its keyword arguments and the all-zero initial gate are exactly what they were."""

import json
from types import SimpleNamespace

import pytest

from so101_demo.act import teacher_diversity as td
from so101_demo.act.joints import ARM_JOINTS
from so101_demo.act.rig_profile import HEAD_WRIST_RIG, SIDE_WRIST_RIG
from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.runtime.parallel_ros_ports.observations import InitialGateObservation, ResetBoundaryReceipt
from paths import PACKAGE_ROOT

from parallel_ros_runtime_support import _valid_worker_nodes

SCHEMA6 = load_teacher_execution_policy(PACKAGE_ROOT / "config/act/teacher_execution_policy_side_wrist_diversity.yaml")
SCHEMA5 = load_teacher_execution_policy(PACKAGE_ROOT / "config/act/teacher_execution_policy_side_wrist_fast_two_leg_open_1s.yaml")
CUP = [0.02, -0.28, 0.165]


def lease(point="act-0001", attempt="act-0001-lease-1"):
    return SimpleNamespace(batch_id="b", coordinator_epoch=1, worker_id="w", worker_generation=1, point_id=point,
                           attempt_id=attempt, lease_generation=1)


class Checker:
    def __init__(self, reject=()):
        self.reject, self.seen = set(reject), []

    def check(self, joints, cup_position=None):
        self.seen.append((tuple(joints), cup_position))
        index = len(self.seen) - 1
        return (False, "COLLISION: fixture") if index in self.reject else (True, "")


def ports(tmp_path, *, policy=SCHEMA6, rig=SIDE_WRIST_RIG, checker=None, calls=None):
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    calls = [] if calls is None else calls

    def execute(session_id, *, keyframe, cup_position_world_m, **kwargs):
        calls.append({"keyframe": keyframe, "cup": cup_position_world_m, **kwargs})
        return SimpleNamespace(simulation_session_id="s", new_epoch=2), SimpleNamespace(success=True)

    dependencies = {"act_profile": True, "execute_reset": execute,
                    "current_evidence": lambda _session: SimpleNamespace(simulation_session_id="s", reset_epoch=2, simulation_time_s=1.0)}
    if rig is not None:
        dependencies["rig"] = rig
    if policy is not None:
        dependencies["teacher_execution_policy"] = policy
    if checker is not None:
        dependencies["start_pose_check"] = lambda _rig: checker
    resources = SimpleNamespace(session_id="s", worker_id="w", generation=1, worker_root=tmp_path)
    value = ParallelRosRuntimePorts(resources, catalog={"act-0001": {"cup_position_world_m": CUP}}, dependencies=dependencies)
    return value, calls


def expected_vector(offsets):
    return td.reset_joint_positions(offsets, ARM_JOINTS)


# ---- the reset call ----------------------------------------------------------------------------------------------------------

def test_a_schema_6_policy_resets_to_the_first_accepted_draw_and_says_so(tmp_path):
    checker = Checker()
    value, calls = ports(tmp_path, checker=checker)
    value.reset_point(lease())
    draw0 = td.start_pose_candidates(SCHEMA6["diversity"], "act-0001")[0]
    assert len(calls) == 1 and calls[0]["act_profile"] is True and calls[0]["rig"] is SIDE_WRIST_RIG
    assert calls[0]["start_joint_positions"] == expected_vector(draw0) and calls[0]["cup"] == tuple(CUP)
    assert checker.seen == [(expected_vector(draw0), tuple(CUP))]            # the check saw the pose and this episode's cup position
    selection = json.loads((tmp_path / "start-pose-act-0001-lease-1.json").read_text())
    assert selection["draw_index"] == 0 and selection["rejected"] == [] and selection["joints_rad"] == list(expected_vector(draw0))
    assert selection["scene_id"] == "act-0001" and selection["policy_sha256"] == SCHEMA6["policy_sha256"]


def test_a_rejected_draw_is_redrawn_and_the_rejections_are_recorded(tmp_path):
    checker = Checker(reject={0, 1})
    value, calls = ports(tmp_path, checker=checker)
    value.reset_point(lease())
    candidates = td.start_pose_candidates(SCHEMA6["diversity"], "act-0001")
    assert calls[0]["start_joint_positions"] == expected_vector(candidates[2])
    selection = json.loads((tmp_path / "start-pose-act-0001-lease-1.json").read_text())
    assert selection["draw_index"] == 2 and [item["draw_index"] for item in selection["rejected"]] == [0, 1]
    assert all("COLLISION" in item["reason"] for item in selection["rejected"])


def test_a_pose_beyond_a_joint_limit_is_rejected_before_the_collision_check(tmp_path, monkeypatch):
    checker = Checker()
    asked = []

    def limits(positions, **kwargs):
        asked.append(tuple(positions))
        return len(asked) > 1                                   # the first draw is out of range, the second is not

    monkeypatch.setattr(td, "joints_within_limits", limits)
    value, calls = ports(tmp_path, checker=checker)
    value.reset_point(lease())
    selection = json.loads((tmp_path / "start-pose-act-0001-lease-1.json").read_text())
    assert selection["draw_index"] == 1 and selection["rejected"][0]["reason"].startswith("JOINT_LIMIT")
    assert len(asked) == 2 and len(checker.seen) == 1           # the rejected draw never reached the collision check
    assert calls[0]["start_joint_positions"] == expected_vector(td.start_pose_candidates(SCHEMA6["diversity"], "act-0001")[1])


def test_every_draw_rejected_fails_closed_before_any_reset(tmp_path):
    checker = Checker(reject=set(range(20)))
    value, calls = ports(tmp_path, checker=checker)
    with pytest.raises(ValueError, match="TEACHER_DIVERSITY_START_POSE_REJECTED"):
        value.reset_point(lease())
    assert calls == [] and len(checker.seen) == SCHEMA6["diversity"]["start_pose"]["max_redraws"] + 1


def test_the_same_scene_gets_the_same_pose_and_another_scene_another(tmp_path):
    for name in ("a", "b", "c"):
        (tmp_path / name).mkdir()
    first, calls_a = ports(tmp_path / "a", checker=Checker())
    first.reset_point(lease())
    second, calls_b = ports(tmp_path / "b", checker=Checker())
    second.reset_point(lease(attempt="act-0001-lease-2"))
    assert calls_a[0]["start_joint_positions"] == calls_b[0]["start_joint_positions"]
    third, calls_c = ports(tmp_path / "c", checker=Checker())
    third.catalog["act-0002"] = {"cup_position_world_m": CUP}
    third.reset_point(lease("act-0002", "act-0002-lease-1"))
    assert calls_c[0]["start_joint_positions"] != calls_a[0]["start_joint_positions"]


def test_a_head_wrist_rig_gets_the_neck_at_zero(tmp_path):
    value, calls = ports(tmp_path, rig=HEAD_WRIST_RIG, checker=Checker())
    value.reset_point(lease())
    vector = calls[0]["start_joint_positions"]
    assert len(vector) == 7 and vector[5] == 0.0 and vector[6] == 0.0 and any(vector[:5])


@pytest.mark.parametrize("policy", [SCHEMA5, None])
def test_without_a_schema_6_policy_the_reset_call_is_the_call_it_always_was(tmp_path, policy):
    checker = Checker()
    value, calls = ports(tmp_path, policy=policy, checker=checker)
    value.reset_point(lease())
    assert calls == [{"keyframe": "task_start", "cup": tuple(CUP), "act_profile": True, "rig": SIDE_WRIST_RIG}]
    assert checker.seen == [] and not list(tmp_path.glob("start-pose-*"))
    assert getattr(value, "_start_poses", {}) == {}


def test_a_schema_6_policy_needs_the_act_profile(tmp_path):
    value, calls = ports(tmp_path, checker=Checker())
    value.dependencies["act_profile"] = False
    with pytest.raises(RuntimeError, match="TEACHER_DIVERSITY_REQUIRES_ACT_PROFILE"):
        value.reset_point(lease())
    assert calls == []


# ---- the model the check ran on ------------------------------------------------------------------------------------------------

IDENTITY = {"scene_sha256": "a" * 64, "model_sha256": "b" * 64, "physics_fingerprint": "c" * 64, "physics_fingerprint_stripped": "d" * 64,
            "mujoco_version": "3.12.0"}


class IdentifiedChecker(Checker):
    def identity(self):
        return dict(IDENTITY)


def test_the_selection_record_names_the_model_and_says_whether_it_was_verified(tmp_path):
    value, _ = ports(tmp_path, checker=IdentifiedChecker())
    value.dependencies["start_pose_frozen_scene"] = {"scene_sha256": "a" * 64, "model_sha256": "b" * 64}
    value.reset_point(lease())
    selection = json.loads((tmp_path / "start-pose-act-0001-lease-1.json").read_text())
    assert selection["model"] == IDENTITY and selection["frozen_identity_verified"] is True


def test_without_a_frozen_identity_the_record_says_it_was_not_verified(tmp_path):
    value, _ = ports(tmp_path, checker=IdentifiedChecker())
    value.reset_point(lease())
    selection = json.loads((tmp_path / "start-pose-act-0001-lease-1.json").read_text())
    assert selection["model"] == IDENTITY and selection["frozen_identity_verified"] is False


@pytest.mark.parametrize("field", ["scene_sha256", "model_sha256"])
def test_a_model_that_is_not_the_frozen_scene_is_refused_before_any_reset(tmp_path, field):
    value, calls = ports(tmp_path, checker=IdentifiedChecker())
    value.dependencies["start_pose_frozen_scene"] = {"scene_sha256": "a" * 64, "model_sha256": "b" * 64, field: "e" * 64}
    with pytest.raises(RuntimeError, match="TEACHER_DIVERSITY_START_POSE_MODEL_MISMATCH"):
        value.reset_point(lease())
    assert calls == [] and not list(tmp_path.glob("start-pose-*"))


def test_a_checker_that_cannot_name_its_model_is_refused_when_a_frozen_identity_is_required(tmp_path):
    value, calls = ports(tmp_path, checker=Checker())
    value.dependencies["start_pose_frozen_scene"] = {"scene_sha256": "a" * 64, "model_sha256": "b" * 64}
    with pytest.raises(RuntimeError, match="TEACHER_DIVERSITY_START_POSE_MODEL_MISMATCH"):
        value.reset_point(lease())
    assert calls == []


def test_the_frozen_scene_identity_is_read_from_the_scene_model_role():
    frozen = {"roles": {"scene_model": {"sha256": "a" * 64, "identity": {"scene_sha256": "a" * 64, "model_sha256": "b" * 64,
                                                                         "mujoco_version": "3.12.0"}}}}
    assert td.frozen_scene_identity(frozen) == {"scene_sha256": "a" * 64, "model_sha256": "b" * 64}
    assert td.frozen_scene_identity({}) is None and td.frozen_scene_identity({"roles": {"scene_model": {}}}) is None


def test_the_real_check_records_the_scene_file_hash(tmp_path):
    import hashlib

    pytest.importorskip("mujoco")
    value, _ = ports(tmp_path, checker=None)
    value.dependencies["start_pose_model_root"] = PACKAGE_ROOT
    value.reset_point(lease())
    selection = json.loads((tmp_path / "start-pose-act-0001-lease-1.json").read_text())
    scene = PACKAGE_ROOT / "assets/mujoco/act/scene_side_wrist.xml"
    assert selection["model"]["scene_sha256"] == hashlib.sha256(scene.read_bytes()).hexdigest()
    assert len(selection["model"]["physics_fingerprint"]) == 64


# ---- the initial gate --------------------------------------------------------------------------------------------------------

def gate_observation(joints):
    return InitialGateObservation(
        reset_epoch="reset-2", simulation_session_id="session-1", source_frame_monotonic_s=11.0, joint_positions=tuple(joints),
        active_controller_goal_ids=(), moveit_attached_object_ids=(), has_contact=False, worker_node_fqns=_valid_worker_nodes())


def gate_ports(joints, start=None):
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    value = ParallelRosRuntimePorts.for_test(
        resources=SimpleNamespace(session_id="session-1"), catalog={"act-0001": {"cup_position_world_m": CUP}},
        observe_initial=lambda _boundary: gate_observation(joints))
    if start is not None:
        value._start_poses = {"act-0001-lease-1": tuple(start)}
    return value


RESET = ResetBoundaryReceipt("reset-2", "session-1", 10.0, 12.0)


def test_the_initial_gate_expects_the_drawn_start_pose_and_not_the_zero_pose():
    start = expected_vector(td.start_pose_candidates(SCHEMA6["diversity"], "act-0001")[0])
    assert gate_ports(start, start).initial_gate(lease(), RESET).canonical_joints is True
    with pytest.raises(RuntimeError, match="POINT_INITIAL_GATE_OBSERVATION_REJECTED:joints"):
        gate_ports((0.0,) * 6, start).initial_gate(lease(), RESET)
    off = (start[0] + 0.01, *start[1:])
    with pytest.raises(RuntimeError, match="joints"):
        gate_ports(off, start).initial_gate(lease(), RESET)


def test_the_initial_gate_without_a_drawn_pose_still_expects_zeros():
    assert gate_ports((0.0,) * 6).initial_gate(lease(), RESET).canonical_joints is True
    with pytest.raises(RuntimeError, match="joints"):
        gate_ports((0.1, 0, 0, 0, 0, 0)).initial_gate(lease(), RESET)


# ---- the real collision check on the real model ----------------------------------------------------------------------------

def test_the_default_check_loads_the_rig_scene_and_accepts_the_drawn_poses_of_many_scenes(tmp_path):
    pytest.importorskip("mujoco")
    value, calls = ports(tmp_path, checker=None)
    value.dependencies["start_pose_model_root"] = PACKAGE_ROOT
    rejected = 0
    for number in range(60):
        value.catalog[f"act-{number:04d}"] = {"cup_position_world_m": CUP}
        value.reset_point(lease(f"act-{number:04d}", f"act-{number:04d}-lease-1"))
        selection = json.loads((tmp_path / f"start-pose-act-{number:04d}-lease-1.json").read_text())
        rejected += len(selection["rejected"])
    assert len(calls) == 60 and rejected == 0           # +-0.15 rad around task_start never touches the table or the arm (60 scenes)


def test_the_default_check_rejects_a_pose_that_drives_the_arm_into_the_table(tmp_path):
    pytest.importorskip("mujoco")
    value, _ = ports(tmp_path, checker=None)
    value.dependencies["start_pose_model_root"] = PACKAGE_ROOT
    checker = value._start_pose_checker(SIDE_WRIST_RIG)
    assert checker.check((0.0,) * 6, tuple(CUP)) == (True, "")
    accepted, reason = checker.check((0.0, 1.7, 0.0, 0.0, 0.0, 0.0), tuple(CUP))
    assert accepted is False and reason.startswith("COLLISION:") and "table_collision" in reason
    assert value._start_pose_checker(SIDE_WRIST_RIG) is checker                 # loaded once per process
