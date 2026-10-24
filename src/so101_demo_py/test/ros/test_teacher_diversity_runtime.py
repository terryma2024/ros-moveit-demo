"""R3-a in the Teacher execution: the carry via-point waypoint of MOVE_ABOVE_PLACE, the speed scale, the OMPL attempts.

Fixture level, with the real repository URDF and the real mujoco policy template (like test_pick_horizon_precompute and
test_teacher_descend_stages). Without episode diversity every one of these behaves exactly as before: schema 3, 4 and 5 policies, and
a schema 6 policy whose run has no derived values, plan the six interpolated segments at the old scaling with one attempt."""

import hashlib
import math
from types import SimpleNamespace

import pytest

from so101_demo.act import teacher_diversity as td
from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.control.moveit.deterministic_horizon import descend_waypoints
from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import CupPoseSample, resolve_motion_targets
from so101_demo.core.task_geometry import Pose7
from so101_demo.ports.evidence import PoseEvidence

from test_pick_horizon_precompute import START, ik, targets, teacher, template  # noqa: F401 - fixtures
from test_teacher_moveit_execution import make_adapter
from paths import PACKAGE_ROOT

CONFIG = PACKAGE_ROOT / "config/act"
SCHEMA6 = CONFIG / "teacher_execution_policy_side_wrist_diversity.yaml"
SCHEMA5 = CONFIG / "teacher_execution_policy_side_wrist_fast_two_leg_open_1s.yaml"
SAMPLE = CupPoseSample("world", 1, 0.0, Pose7((0.051023, -0.339445, 0.165, 0.0, 0.0, 0.0, 1.0)))


@pytest.fixture(scope="module")
def policy6():
    return load_teacher_execution_policy(SCHEMA6)


def episode_values(policy, scene="act-0001"):
    return td.derive_episode_values(policy["diversity"], scene)


def diversity_targets(template, values):
    shifted = td.episode_template(template, values)
    return resolve_motion_targets(SAMPLE, shifted, carry_via_offset_m=tuple(values["carry_via_offset_m"])), shifted


def distance(a, b):
    return math.dist(a.position_m, b.position_m)


def same_pose(a, b):
    """Equal up to the rounding of the interpolation's quaternion normalisation (a fraction of 1 is not bit-exact)."""
    return distance(a, b) < 1e-12 and max(abs(x - y) for x, y in zip(a.orientation_xyzw, b.orientation_xyzw)) < 1e-12


# ---- the waypoints of MOVE_ABOVE_PLACE ---------------------------------------------------------------------------------------

def test_without_a_via_point_move_above_place_is_the_six_interpolated_waypoints_of_before(tmp_path, ik, template, targets):
    value = teacher(tmp_path, ik, template, targets, policy_path=SCHEMA5)
    start = value._ik.forward(START)
    target = targets.for_state(State.MOVE_ABOVE_PLACE)
    waypoints = value._motion_waypoints(State.MOVE_ABOVE_PLACE, start, target)
    assert waypoints == [value._interpolate_pose(start, target, step / 6.0) for step in range(1, 7)]
    assert value._motion_waypoints(State.DESCEND_TO_PLACE, start, target) == waypoints
    assert value._motion_waypoints(State.LIFT, start, target) == [target]
    assert value._motion_waypoints(State.RETREAT, start, target) == [target]


def test_descend_keeps_its_two_stage_waypoints(tmp_path, ik, template, targets):
    value = teacher(tmp_path, ik, template, targets, policy_path=SCHEMA5)
    start = targets.for_state(State.MOVE_ABOVE_OBJECT)
    grasp = targets.for_state(State.DESCEND)
    expected = [waypoint.target for waypoint in descend_waypoints(value._interpolate_pose, start, grasp, 0.02)]
    assert value._motion_waypoints(State.DESCEND, start, grasp) == expected and len(expected) == 2


def test_a_via_point_splits_move_above_place_into_two_straight_legs_of_three_waypoints(tmp_path, ik, template, policy6):
    values = episode_values(policy6)
    via_targets, shifted = diversity_targets(template, values)
    value = teacher(tmp_path, ik, shifted, via_targets, policy_path=SCHEMA6)
    start = value._ik.forward(START)
    target = via_targets.for_state(State.MOVE_ABOVE_PLACE)
    via = via_targets.carry_via
    waypoints = value._motion_waypoints(State.MOVE_ABOVE_PLACE, start, target)
    assert len(waypoints) == 6
    assert waypoints[:3] == [value._interpolate_pose(start, via, step / 3.0) for step in (1, 2, 3)]
    assert waypoints[3:] == [value._interpolate_pose(via, target, step / 3.0) for step in (1, 2, 3)]
    assert same_pose(waypoints[2], via) and same_pose(waypoints[5], target)
    # only MOVE_ABOVE_PLACE has a via-point
    assert value._motion_waypoints(State.DESCEND_TO_PLACE, start, target) == [
        value._interpolate_pose(start, target, step / 6.0) for step in range(1, 7)]


def test_the_via_waypoint_is_a_planned_segment_of_the_horizon_and_passes_the_ik(tmp_path, ik, template, policy6):
    """The horizon is solved from the arm state after LIFT, like the execution does, for many derived episodes."""
    base = teacher(tmp_path, ik, template, resolve_motion_targets(SAMPLE, template), policy_path=SCHEMA6)
    base._motion_horizon(State.MOVE_ABOVE_OBJECT, [], START)
    lift_joints = tuple(base._pick_horizon_steps[State.LIFT][0].receipt.joint_positions_rad)
    failures = []
    for number in range(40):
        values = episode_values(policy6, f"act-{number:04d}")
        via_targets, shifted = diversity_targets(template, values)
        value = teacher(tmp_path, ik, shifted, via_targets, policy_path=SCHEMA6, current=lift_joints)
        start = value._ik.forward(lift_joints)
        waypoints = value._motion_waypoints(State.MOVE_ABOVE_PLACE, start, via_targets.for_state(State.MOVE_ABOVE_PLACE))
        try:
            steps = value._motion_horizon(State.MOVE_ABOVE_PLACE, waypoints, lift_joints)
        except RuntimeError as error:
            failures.append((number, str(error)))
            continue
        assert [step.waypoint.segment_index for step in steps] == [0, 1, 2, 3, 4, 5]
        assert same_pose(steps[2].waypoint.target, via_targets.carry_via)
    # A via-point the IK cannot reach is not an execution failure: the reachability preflight sees the same waypoint and reports the scene
    # UNREACHABLE before any motion (and the sampling filter drops it). Here it is bounded: at most 10 % of the derived episodes, and
    # always the coded horizon failure.
    assert len(failures) <= 4 and {message for _, message in failures} <= {"DYNAMIC_IK_HORIZON_FAILED"}, failures


def test_every_derived_episode_keeps_the_held_cup_three_centimetres_above_the_table_on_the_real_template(template, policy6):
    """The real mujoco template and the shipped ranges: the via-point never lowers the carry and the clearance rule never fires."""
    from so101_demo.core.dynamic_pick import CARRY_VIA_MIN_CLEARANCE_M

    for number in range(300):
        values = episode_values(policy6, f"act-{number:04d}")
        via_targets, _ = diversity_targets(template, values)            # raises CARRY_VIA_CLEARANCE when the rule fires
        lift, above = via_targets.for_state(State.LIFT).position_m[2], via_targets.for_state(State.MOVE_ABOVE_PLACE).position_m[2]
        grasp = via_targets.for_state(State.DESCEND).position_m[2]
        assert via_targets.carry_via.position_m[2] >= (lift + above) / 2.0 - 1e-12
        assert min(lift, via_targets.carry_via.position_m[2], above) - grasp >= CARRY_VIA_MIN_CLEARANCE_M


# ---- the speed scale ---------------------------------------------------------------------------------------------------------

def scalings(tmp_path, policy, state, *, speed_scale=None, step=None, snapshot=True):
    value = make_adapter(tmp_path)
    value._template = SimpleNamespace(velocity_scaling=0.03, acceleration_scaling=0.03)
    if snapshot:
        value._execution_snapshot_root = tmp_path
    value._execution_policy = policy
    if speed_scale is not None:
        value._episode_diversity = {"speed_scale": speed_scale}
    return value._planning_scaling(state, step)


@pytest.mark.parametrize("state,keys", [
    (State.LIFT, ("carry_max_velocity_scaling", "carry_max_acceleration_scaling")),
    (State.MOVE_ABOVE_PLACE, ("carry_max_velocity_scaling", "carry_max_acceleration_scaling")),
    (State.MOVE_ABOVE_OBJECT, ("move_above_object_velocity_scaling", "move_above_object_acceleration_scaling")),
    (State.RETREAT, ("retreat_velocity_scaling", "retreat_acceleration_scaling")),
])
def test_the_speed_scale_multiplies_the_policy_scaling_keys(tmp_path, policy6, state, keys):
    base = scalings(tmp_path, policy6, state)
    assert base == (policy6[keys[0]], policy6[keys[1]])
    for scale in (0.7, 1.3):
        scaled = scalings(tmp_path, policy6, state, speed_scale=scale)
        assert scaled == pytest.approx((base[0] * scale, base[1] * scale))


def test_descend_to_place_keeps_the_calibrated_carry_scaling_whatever_the_speed_scale(tmp_path, policy6):
    """The place height was calibrated at the policy's carry speed: the touchdown must not follow the episode speed scale."""
    base = scalings(tmp_path, policy6, State.DESCEND_TO_PLACE)
    assert base == (policy6["carry_max_velocity_scaling"], policy6["carry_max_acceleration_scaling"])
    for scale in (0.7, 1.0, 1.3):
        assert scalings(tmp_path, policy6, State.DESCEND_TO_PLACE, speed_scale=scale) == base


def test_the_speed_scale_scales_the_descend_approach_stage_only(tmp_path, ik, template, targets, policy6):
    value = teacher(tmp_path, ik, template, targets, policy_path=SCHEMA6)
    value._episode_diversity = {"speed_scale": 1.3}
    grasp = targets.for_state(State.DESCEND)
    value._descend_grasp_target = grasp
    approach = SimpleNamespace(waypoint=SimpleNamespace(target=PoseEvidence((grasp.position_m[0], grasp.position_m[1], grasp.position_m[2] + 0.02),
                                                                           grasp.orientation_xyzw)))
    final = SimpleNamespace(waypoint=SimpleNamespace(target=grasp))
    assert value._planning_scaling(State.DESCEND, approach) == pytest.approx(
        (policy6["descend_approach_velocity_scaling"] * 1.3, policy6["descend_approach_acceleration_scaling"] * 1.3))
    assert value._planning_scaling(State.DESCEND, final) == (value._template.velocity_scaling, value._template.acceleration_scaling)


@pytest.mark.parametrize("state", [State.PREPARE_OPEN_GRIPPER, State.MICRO_LIFT, State.RECOVER_RETREAT])
def test_template_scaled_states_do_not_follow_the_speed_scale(tmp_path, policy6, state):
    assert scalings(tmp_path, policy6, state, speed_scale=1.3) == (0.03, 0.03)


def test_a_scaled_value_is_capped_at_one(tmp_path, policy6):
    fast = {**policy6, "carry_max_velocity_scaling": 0.9, "carry_max_acceleration_scaling": 1.0}
    assert scalings(tmp_path, fast, State.MOVE_ABOVE_PLACE, speed_scale=1.3) == (1.0, 1.0)


def test_without_derived_values_or_frozen_inputs_the_scaling_is_what_it_was(tmp_path, policy6):
    for state in (State.LIFT, State.MOVE_ABOVE_OBJECT, State.RETREAT):
        assert scalings(tmp_path, policy6, state) == scalings(tmp_path, policy6, state, speed_scale=None)
    assert scalings(tmp_path, policy6, State.LIFT, speed_scale=1.3, snapshot=False) == (0.03, 0.03)   # no frozen inputs: the template
    schema5 = load_teacher_execution_policy(SCHEMA5)
    assert scalings(tmp_path, schema5, State.LIFT) == (schema5["carry_max_velocity_scaling"], schema5["carry_max_acceleration_scaling"])


# ---- the OMPL attempts -------------------------------------------------------------------------------------------------------

def trajectory(*rows):
    points = [SimpleNamespace(positions=list(row), time_from_start=SimpleNamespace(sec=index, nanosec=0))
              for index, row in enumerate(rows)]
    return SimpleNamespace(joint_trajectory=SimpleNamespace(points=points))


def plan_once(tmp_path, *, diversity=None, plan_trajectory=None):
    value = make_adapter(tmp_path)
    value._template = SimpleNamespace(velocity_scaling=0.03, acceleration_scaling=0.03, planning_timeout_s=1.0,
                                      planning_group="arm", tcp_link="tcp", orientation_tolerance_rad=(0.1, 0.1, 0.1))
    if diversity is not None:
        value._execution_snapshot_root = tmp_path
        value._execution_policy = load_teacher_execution_policy(SCHEMA6)
        value._episode_diversity = diversity
    seen, records = [], []

    class Planning:
        def plan_joint_path(self, request, timeout_s):
            seen.append(request)
            if plan_trajectory is None:
                return SimpleNamespace(failure=SimpleNamespace(code="PLAN_REFUSED"), trajectory=None)
            return SimpleNamespace(failure=None, trajectory=plan_trajectory)

    value._planning = Planning()
    value._record_planning_attempt = records.append
    return value, seen, records


def test_the_default_request_is_one_attempt(tmp_path):
    value, seen, records = plan_once(tmp_path)
    with pytest.raises(RuntimeError, match="PLAN_REFUSED"):
        value._plan_candidate_set(state=State.MOVE_ABOVE_PLACE, step=SimpleNamespace(waypoint=SimpleNamespace(segment_index=0)),
                                  current=(0.0,) * 5, joint_target=(0.1,) * 5)
    assert [request.num_planning_attempts for request in seen] == [1]
    assert "num_planning_attempts" not in records[0]            # the record of a run without diversity is the record it was


def test_the_derived_attempts_reach_the_moveit_request_and_the_record(tmp_path):
    values = {"speed_scale": 1.0, "ompl": {"num_planning_attempts": 3, "seed": 7, "seed_applied": False}}
    value, seen, records = plan_once(tmp_path, diversity=values)
    with pytest.raises(RuntimeError, match="PLAN_REFUSED"):
        value._plan_candidate_set(state=State.MOVE_ABOVE_PLACE, step=SimpleNamespace(waypoint=SimpleNamespace(segment_index=0)),
                                  current=(0.0,) * 5, joint_target=(0.1,) * 5)
    assert [request.num_planning_attempts for request in seen] == [3]
    assert records[0]["num_planning_attempts"] == 3


def _accepting_corridor(monkeypatch):
    """The Cartesian corridor check is not under test: let it accept."""
    import so101_demo.ros.dynamic_execution.planning as planning

    monkeypatch.setattr(planning, "validate_cartesian_corridor", lambda *a, **k: SimpleNamespace(
        accepted=True, failure_code=None, to_document=lambda: {}))
    monkeypatch.setattr(planning, "cartesian_candidate_score", lambda *a, **k: (0,))


def test_an_accepted_plan_records_the_digest_of_the_planner_output_when_diversity_is_on(tmp_path, monkeypatch):
    _accepting_corridor(monkeypatch)
    values = {"speed_scale": 1.0, "ompl": {"num_planning_attempts": 2, "seed": 7, "seed_applied": False}}
    rows = ((0.0, 0.0), (0.1, 0.2), (0.2, 0.4))
    value, _, records = plan_once(tmp_path, diversity=values, plan_trajectory=trajectory(*rows))
    value._ik = SimpleNamespace()
    value._ARM_JOINTS = ("1", "2")
    value._plan_candidate_set(state=State.MOVE_ABOVE_PLACE, step=SimpleNamespace(waypoint=SimpleNamespace(segment_index=0, target=None)),
                              current=(0.0, 0.0), joint_target=(0.2, 0.4))
    accepted = [record for record in records if record.get("accepted") is True][0]
    expected = hashlib.sha256(repr([((0.0, 0.0), 0, 0), ((0.1, 0.2), 1, 0), ((0.2, 0.4), 2, 0)]).encode()).hexdigest()
    assert accepted["trajectory_sha256"] == expected and accepted["num_planning_attempts"] == 2


def test_an_accepted_plan_of_a_run_without_diversity_records_what_it_always_did(tmp_path, monkeypatch):
    _accepting_corridor(monkeypatch)
    value, _, records = plan_once(tmp_path, plan_trajectory=trajectory((0.0, 0.0), (0.1, 0.2)))
    value._ik = SimpleNamespace()
    value._ARM_JOINTS = ("1", "2")
    value._plan_candidate_set(state=State.MOVE_ABOVE_PLACE, step=SimpleNamespace(waypoint=SimpleNamespace(segment_index=0, target=None)),
                              current=(0.0, 0.0), joint_target=(0.1, 0.2))
    accepted = [record for record in records if record.get("accepted") is True][0]
    assert set(accepted) == {"kind", "state", "segment_index", "candidate_index", "candidate_count", "accepted", "failure_code",
                             "joint_target_rad", "trajectory_sample_count"}


# ---- the record and the start pose of an episode -----------------------------------------------------------------------------

def start_value(tmp_path, policy, scene="act-0001", *, joints=None, start_draw=0):
    value = make_adapter(tmp_path)
    value._execution_policy = policy
    value._document = {}
    value._write = lambda: None
    values = td.values_for_policy(policy, scene, start_draw)
    value._record_episode_diversity(values)
    measured = joints if joints is not None else td.reset_joint_positions(
        values["start_pose"]["offsets_rad"], ("1", "2", "3", "4", "5", "6"))
    value._positions = {name: measured[index] for index, name in enumerate(("1", "2", "3", "4", "5", "6"))}
    value._ARM_JOINTS = ("1", "2", "3", "4", "5")
    value._joint_state = lambda *a, **k: tuple(value._positions[name] for name in value._ARM_JOINTS)
    return value, values


def test_the_values_and_their_digest_are_on_the_teacher_document(tmp_path, policy6):
    import json

    value, values = start_value(tmp_path, policy6)
    record = value._document["teacher_diversity"]
    assert record["values"] == values and value._episode_diversity is values
    assert record["values_sha256"] == hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_the_measured_start_pose_is_matched_to_its_draw_and_recorded(tmp_path, policy6):
    value, values = start_value(tmp_path, policy6)
    value._check_episode_start_pose()
    record = value._document["teacher_diversity"]
    assert record["start_pose_draw_index"] == 0 and len(record["start_pose_measured_rad"]) == 6
    later = td.start_pose_candidates(policy6["diversity"], "act-0001")[2]
    value, _ = start_value(tmp_path, policy6, joints=td.reset_joint_positions(later, ("1", "2", "3", "4", "5", "6")), start_draw=2)
    value._check_episode_start_pose()
    assert value._document["teacher_diversity"]["start_pose_draw_index"] == 2
    # the pose of draw 2 is not accepted for an episode whose selected draw is 0
    value, _ = start_value(tmp_path, policy6, joints=td.reset_joint_positions(later, ("1", "2", "3", "4", "5", "6")))
    with pytest.raises(RuntimeError, match="TEACHER_DIVERSITY_START_POSE_MISMATCH"):
        value._check_episode_start_pose()


def test_a_start_pose_that_matches_no_draw_fails_closed_and_is_recorded(tmp_path, policy6):
    value, _ = start_value(tmp_path, policy6, joints=(0.0,) * 6)         # the reset was not given the pose
    with pytest.raises(RuntimeError, match="TEACHER_DIVERSITY_START_POSE_MISMATCH"):
        value._check_episode_start_pose()
    assert value._document["teacher_diversity"]["start_pose_draw_index"] is None


def test_without_episode_diversity_the_start_pose_is_not_looked_at(tmp_path):
    value = make_adapter(tmp_path)
    value._joint_state = lambda *a, **k: pytest.fail("a run without diversity reads no joint state for this")
    value._check_episode_start_pose()
    assert "teacher_diversity" not in value._document


def test_the_start_pose_mismatch_is_a_failed_teacher_execution_not_a_stop():
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution

    result = SimpleNamespace(status=SimpleNamespace(value="ERROR"), failure=SimpleNamespace(code="TEACHER_DIVERSITY_START_POSE_MISMATCH"))
    assert RosDynamicMujocoExecution._teacher_execution_status(result, {}) == "FAILED"


def test_the_start_pose_is_checked_before_the_start_snapshot_in_the_capture(tmp_path, policy6, monkeypatch):
    value, _ = start_value(tmp_path, policy6, joints=(0.0,) * 6)
    value._teacher_config_error = None
    value._teacher_endpoint_policy = {"tolerances": {}}
    value._teacher_targets = lambda: ({"position": [0, 0, 0]}, {"position": [1, 1, 0]})
    value._snapshot = lambda: pytest.fail("the start snapshot must not be taken for a mismatching start pose")
    import so101_demo.act.teacher_endpoint as endpoint

    monkeypatch.setattr(endpoint, "validate_task_targets", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="TEACHER_DIVERSITY_START_POSE_MISMATCH"):
        value._capture_teacher_start()
