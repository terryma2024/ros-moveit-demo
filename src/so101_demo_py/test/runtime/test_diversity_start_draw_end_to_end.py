"""R3-a review fix 3: the start pose actually applied (draw k, possibly > 0 after rejected draws) is the one the Teacher expects, the one
the episode identity records, and the one the case record lists as a candidate.

Chain, with a forced k = 2: the reset draws it (draws 0 and 1 rejected) and writes the selection beside the task; the consumer command
carries `--start-pose-draw 2`; the Teacher derives the values with that draw and requires the measured start to match exactly that draw
(draw 0 is refused); the episode identity of the offline processor carries draw 2 with its pose."""

import json
from types import SimpleNamespace

import pytest

from so101_demo.act import teacher_diversity as td
from so101_demo.act.rig_profile import SIDE_WRIST_RIG
from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.cli.dynamic_cup_pick_place import build_parser
from so101_demo.ros.dynamic_frozen_policy import _frozen_run_inputs
from paths import PACKAGE_ROOT

from test_diversity_start_pose_reset import Checker, lease, ports
from test_dynamic_pick import _template

POLICY = load_teacher_execution_policy(PACKAGE_ROOT / "config/act/teacher_execution_policy_side_wrist_fast_carry_b_diversity.yaml")
SCHEMA5 = load_teacher_execution_policy(PACKAGE_ROOT / "config/act/teacher_execution_policy_side_wrist_fast_two_leg_open_1s.yaml")
SCENE = "act-0001"
FROZEN6 = {"teacher_execution_policy": {"values": {key: value for key, value in POLICY.items() if key != "policy_sha256"}}}
FROZEN5 = {"teacher_execution_policy": {"values": {key: value for key, value in SCHEMA5.items() if key != "policy_sha256"}}}
ARM = ("1", "2", "3", "4", "5", "6")


def candidates():
    return td.start_pose_candidates(POLICY["diversity"], SCENE)


def measured(draw):
    return td.reset_joint_positions(candidates()[draw], ARM)


# ---- the values carry the selected draw ----------------------------------------------------------------------------------------

def test_values_for_a_selected_draw_carry_that_draw_and_its_pose_and_nothing_else_changes():
    base = td.values_for_policy(POLICY, SCENE)
    chosen = td.values_for_policy(POLICY, SCENE, start_draw=2)
    assert chosen["start_pose"] == {"draw_index": 2, "joints": ["1", "2", "3", "4", "5"], "offsets_rad": list(candidates()[2])}
    assert {key: value for key, value in chosen.items() if key != "start_pose"} == {key: value for key, value in base.items() if key != "start_pose"}
    assert td.values_for_policy(POLICY, SCENE, start_draw=0) == base


@pytest.mark.parametrize("draw", [-1, 9, 2.0, True, "1"])
def test_a_draw_outside_the_bounded_list_is_refused(draw):
    with pytest.raises(ValueError, match="TEACHER_DIVERSITY_INVALID"):
        td.values_for_policy(POLICY, SCENE, start_draw=draw)


def test_the_teacher_requires_exactly_the_selected_draw():
    diversity = POLICY["diversity"]
    assert td.start_pose_matches(diversity, SCENE, measured(2), 2) is True
    assert td.start_pose_matches(diversity, SCENE, measured(0), 2) is False       # draw 0 is not what was selected
    assert td.start_pose_matches(diversity, SCENE, (0.0,) * 6, 2) is False
    assert td.start_pose_matches(diversity, SCENE, measured(2)[:5], 2) is False


# ---- the reset writes the selection, the command carries it ------------------------------------------------------------------

def test_a_forced_k_greater_than_zero_is_applied_recorded_and_read_back(tmp_path):
    value, calls = ports(tmp_path, checker=Checker(reject={0, 1}))
    value.reset_point(lease())
    assert calls[0]["start_joint_positions"] == measured(2)
    selection = td.read_start_pose_selection(tmp_path, "act-0001-lease-1")
    assert selection["draw_index"] == 2 and selection["joints_rad"] == list(measured(2))
    assert td.read_start_pose_selection(tmp_path, "no-such-attempt") is None


def test_a_selection_file_that_is_not_the_closed_document_is_refused(tmp_path):
    path = tmp_path / "start-pose-a1.json"
    path.write_text(json.dumps({"kind": "SOMETHING", "draw_index": 1}))
    with pytest.raises(ValueError, match="TEACHER_DIVERSITY_START_POSE_RECORD_INVALID"):
        td.read_start_pose_selection(tmp_path, "a1")
    path.write_text("not json")
    with pytest.raises(ValueError, match="TEACHER_DIVERSITY_START_POSE_RECORD_INVALID"):
        td.read_start_pose_selection(tmp_path, "a1")


def test_the_consumer_command_carries_the_selected_draw_only_when_there_is_a_selection(tmp_path):
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime
    from test_parallel_worker_runtime_tree_replacement import _ProcessGroup, _lease, _resources
    from so101_demo.parallel_batch.contracts.common import RunMode

    runtime = build_worker_runtime(_resources(tmp_path, "worker-1", 0, 181), RunMode.EXECUTE, process_group=_ProcessGroup())
    plain = runtime.consumer_argv("reset-17", _lease())
    assert "--start-pose-draw" not in plain
    root = tmp_path / "worker-1"
    root.mkdir(exist_ok=True)
    value, _ = ports(root, checker=Checker(reject={0, 1}))
    value.catalog[_lease().point_id] = {"cup_position_world_m": [0.02, -0.28, 0.165]}
    point = _lease()
    value.reset_point(point)
    command = runtime.consumer_argv("reset-17", point)
    assert command[command.index("--start-pose-draw") + 1] == "2"
    assert command[:command.index("--start-pose-draw")] == plain       # appended at the end; nothing else moves


def test_the_consumer_parser_takes_the_draw():
    options = build_parser().parse_args(["--start-pose-draw", "3"])
    assert options.start_pose_draw == 3 and build_parser().parse_args([]).start_pose_draw is None


# ---- the Teacher's entry ----------------------------------------------------------------------------------------------------

def test_a_schema_6_run_needs_the_selected_draw_and_gets_values_with_it():
    template = _template()
    values, run_template, offset = _frozen_run_inputs(FROZEN6, SCENE, template, 2)
    assert values["start_pose"]["draw_index"] == 2 and values["start_pose"]["offsets_rad"] == list(candidates()[2])
    assert offset == tuple(values["carry_via_offset_m"]) and run_template != template
    with pytest.raises(RuntimeError, match="TEACHER_DIVERSITY_START_DRAW_REQUIRED"):
        _frozen_run_inputs(FROZEN6, SCENE, template, None)
    with pytest.raises(ValueError, match="TEACHER_DIVERSITY_INVALID"):
        _frozen_run_inputs(FROZEN6, SCENE, template, 99)
    assert _frozen_run_inputs(FROZEN5, SCENE, template, 2) == (None, template, None)        # older schemas ignore it


def test_the_teacher_start_check_accepts_the_selected_draw_and_refuses_another(tmp_path):
    from test_teacher_diversity_runtime import start_value

    value, values = start_value(tmp_path, POLICY, SCENE, joints=measured(2), start_draw=2)
    value._check_episode_start_pose()
    assert value._document["teacher_diversity"]["start_pose_draw_index"] == 2
    value, _ = start_value(tmp_path, POLICY, SCENE, joints=measured(0), start_draw=2)
    with pytest.raises(RuntimeError, match="TEACHER_DIVERSITY_START_POSE_MISMATCH"):
        value._check_episode_start_pose()


# ---- the episode identity ------------------------------------------------------------------------------------------------------

def test_the_episode_identity_carries_the_selected_draw_and_pose(tmp_path):
    from test_teacher_diversity_identity import open_episode

    values = td.values_for_policy(POLICY, SCENE, start_draw=2)
    episode = open_episode(tmp_path / "episode", diversity=values, diversity_policy=POLICY)
    written = json.loads((tmp_path / "episode" / "audit" / "episode.json").read_bytes())
    assert written["teacher_diversity"]["start_pose"]["draw_index"] == 2
    assert written["teacher_diversity"]["start_pose"]["offsets_rad"] == list(candidates()[2])
    assert episode.identity["teacher_diversity"] == values


def test_the_recorder_open_requires_the_draw_for_a_schema_6_freeze():
    from so101_demo.act.episode_open import diversity_arguments

    frozen = {"teacher_execution_policy": {"values": FROZEN6["teacher_execution_policy"]["values"]}}
    chosen = diversity_arguments(frozen, SCENE, 2)
    assert chosen["diversity"]["start_pose"]["draw_index"] == 2 and chosen["diversity_policy"] is not None
    with pytest.raises(ValueError, match="TEACHER_DIVERSITY_START_DRAW_REQUIRED"):
        diversity_arguments(frozen, SCENE, None)
    assert diversity_arguments(FROZEN5, SCENE, None) == {}
    assert diversity_arguments({}, SCENE, 3) == {}


def test_the_offline_processor_reads_the_draw_from_the_teacher_manifest(tmp_path):
    from so101_demo.act.offline.processor import teacher_start_draw

    path = tmp_path / "dynamic-execute-manifest.json"
    values = td.values_for_policy(POLICY, SCENE, start_draw=2)
    path.write_text(json.dumps({"teacher_diversity": {"values": values, "start_pose_draw_index": 2}}))
    assert teacher_start_draw(path) == 2
    path.write_text(json.dumps({"teacher_diversity": {"values": values, "start_pose_draw_index": 1}}))
    with pytest.raises(ValueError, match="TEACHER_DIVERSITY_START_POSE_MISMATCH"):
        teacher_start_draw(path)                     # the Teacher's matched draw and its values disagree
    path.write_text(json.dumps({}))
    assert teacher_start_draw(path) is None
    assert teacher_start_draw(tmp_path / "missing.json") is None


def test_the_case_record_lists_every_candidate_so_the_selected_draw_can_be_checked():
    from so101_demo.runtime.container_campaign.case_inputs import _diversity_document

    frozen = {"inputs_sha256": "a" * 64, "teacher_execution_policy": {"policy_sha256": POLICY["policy_sha256"],
              "values": FROZEN6["teacher_execution_policy"]["values"]}}
    document = _diversity_document(frozen, SCENE)
    assert document["start_pose_candidates"] == [list(item) for item in candidates()]
    assert document["values"]["start_pose"]["draw_index"] == 0          # the derivation's head; the applied draw is in episode.json
