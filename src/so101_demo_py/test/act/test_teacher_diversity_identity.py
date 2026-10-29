"""R3-a: the derived values are part of the run identity: `episode.json` (the audit identity) carries them, and so do the case inputs.

A freeze without a diversity block (schema 3, 4, 5) writes exactly the identity and the case inputs it always wrote."""

import json

import pytest

from so101_demo.act import teacher_diversity as td
from so101_demo.act.episode_assembly import episode_audit_pair, open_point_episode
from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from paths import PACKAGE_ROOT

from test_act_recorder import PROVENANCE
from test_act_seal_and_downgrade import SCOPE

SCHEMA6 = load_teacher_execution_policy(PACKAGE_ROOT / "config/act/teacher_execution_policy_side_wrist_fast_carry_b_diversity.yaml")


def open_episode(root, **options):
    return open_point_episode(
        episode_root=root, session_id="session-1", attempt_id="attempt-1", reset_epoch=2, release_epoch=1,
        scene_id="act-0001", seed=0, mode="preselected_target_diagnostic", scope=SCOPE,
        scope_path=str(episode_audit_pair(root)[1]), inputs={"inputs_sha256": "a" * 64}, provenance=PROVENANCE,
        monotonic=lambda: 0.0, **options)


def test_the_episode_identity_and_episode_json_carry_the_derived_values(tmp_path):
    values = td.values_for_policy(SCHEMA6, "act-0001")
    episode = open_episode(tmp_path / "episode", diversity=values)
    assert episode.identity["teacher_diversity"] == values
    written = json.loads((tmp_path / "episode" / "audit" / "episode.json").read_bytes())
    assert written["teacher_diversity"] == values and written["scene_id"] == "act-0001"


def test_without_diversity_the_identity_is_the_identity_it_always_was(tmp_path):
    episode = open_episode(tmp_path / "episode")
    assert "teacher_diversity" not in episode.identity
    assert "teacher_diversity" not in json.loads((tmp_path / "episode" / "audit" / "episode.json").read_bytes())


def test_values_that_are_not_the_derivation_of_the_scene_are_refused_at_open(tmp_path):
    values = td.values_for_policy(SCHEMA6, "act-0002")             # another scene's values under this scene id
    with pytest.raises(ValueError, match="TEACHER_DIVERSITY_INVALID"):
        open_episode(tmp_path / "episode", diversity=values, diversity_policy=SCHEMA6)
    assert not (tmp_path / "episode" / "audit").exists()


def test_a_derivation_check_passes_for_the_right_scene(tmp_path):
    values = td.values_for_policy(SCHEMA6, "act-0001")
    assert open_episode(tmp_path / "episode", diversity=values, diversity_policy=SCHEMA6).identity["teacher_diversity"] == values


def test_the_episode_identity_carries_the_appearance_and_the_teacher_source_only_when_given(tmp_path):
    record = {"plan_sha256": "a" * 64, "kind": "randomised", "layout": "A", "draw_sha256": "b" * 64, "variant_sha256": "c" * 64,
              "cup_family": "red", "realized_sha256": "d" * 64}
    episode = open_episode(tmp_path / "episode", scene_appearance=record, teacher_source="privileged_pose")
    assert episode.identity["scene_appearance"] == record and episode.identity["teacher_source"] == "privileged_pose"
    written = json.loads((tmp_path / "episode" / "audit" / "episode.json").read_bytes())
    assert written["scene_appearance"] == record and written["teacher_source"] == "privileged_pose" and written["scene_id"] == "act-0001"
    plain = open_episode(tmp_path / "plain")
    assert "scene_appearance" not in plain.identity and "teacher_source" not in plain.identity
    assert "scene_appearance" not in json.loads((tmp_path / "plain" / "audit" / "episode.json").read_bytes())
