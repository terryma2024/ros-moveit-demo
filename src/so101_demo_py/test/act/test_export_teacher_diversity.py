"""R3-a review fix 8: each exported episode's applied diversity values ride in the export manifest; an episode without them (schema 3, 4, 5)
has exactly the manifest entry it always had."""

import json

import pytest

from so101_demo.act import bundle, teacher_diversity as td
from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from paths import PACKAGE_ROOT

POLICY = load_teacher_execution_policy(PACKAGE_ROOT / "config/act/teacher_execution_policy_side_wrist_fast_carry_b_diversity.yaml")


def write_identity(root, scene, values=None, extra=None):
    audit = root / "audit"
    audit.mkdir(parents=True, exist_ok=True)
    document = {"session_id": "s", "attempt_id": "a", "scene_id": scene, **({} if values is None else {"teacher_diversity": values}), **(extra or {})}
    (audit / "episode.json").write_text(json.dumps(document))


def test_the_applied_values_are_read_from_the_episode_identity(tmp_path):
    values = td.values_for_policy(POLICY, "act-0001", 2)
    write_identity(tmp_path, "act-0001", values)
    assert bundle.episode_diversity_record(tmp_path, "act-0001") == values


def test_an_episode_without_diversity_has_no_record(tmp_path):
    write_identity(tmp_path, "act-0001")
    assert bundle.episode_diversity_record(tmp_path, "act-0001") is None
    assert bundle.episode_diversity_record(tmp_path / "missing", "act-0001") is None


def test_values_of_another_scene_in_the_identity_are_refused(tmp_path):
    write_identity(tmp_path, "act-0002", td.values_for_policy(POLICY, "act-0002"))
    with pytest.raises(ValueError, match="EXPORT_EPISODE_DIVERSITY_UNBOUND"):
        bundle.episode_diversity_record(tmp_path, "act-0001")
    write_identity(tmp_path / "b", "act-0001", td.values_for_policy(POLICY, "act-0002"))
    with pytest.raises(ValueError, match="EXPORT_EPISODE_DIVERSITY_UNBOUND"):
        bundle.episode_diversity_record(tmp_path / "b", "act-0001")


def test_the_manifest_entry_gains_the_values_only_when_the_episode_has_them():
    values = td.values_for_policy(POLICY, "act-0001")
    base = {"scene_id": "act-0001", "split": "train", "content_sha256": "a" * 64, "frames": {"f": ("n", "b" * 64)}}
    plain = bundle._manifest_episodes([base])
    assert plain == [{"scene_id": "act-0001", "split": "train", "content_sha256": "a" * 64, "frames": {"f": "b" * 64}}]
    rich = bundle._manifest_episodes([{**base, "teacher_diversity": values}])
    assert rich == [{**plain[0], "teacher_diversity": values}]


# --- indoor P3: the appearance and the Teacher source of an episode ride in the export manifest --------------------------------------
def appearance_identity(kind="randomised"):
    source = "privileged_pose" if kind == "randomised" else "camera_rgbd"
    return {"plan_sha256": "a" * 64, "kind": kind, "layout": "A", "draw_sha256": "b" * 64,
            "variant_sha256": "c" * 64 if kind == "randomised" else None, "cup_family": "red" if kind == "randomised" else None}, source


def test_the_appearance_and_the_source_are_read_from_the_episode_identity(tmp_path):
    record, source = appearance_identity()
    write_identity(tmp_path, "act-0001", extra={"scene_appearance": record, "teacher_source": source})
    assert bundle.episode_appearance_record(tmp_path, "act-0001") == (record, source)
    record, source = appearance_identity("nominal")
    write_identity(tmp_path / "n", "act-0001", extra={"scene_appearance": record, "teacher_source": source})
    assert bundle.episode_appearance_record(tmp_path / "n", "act-0001") == (record, source)


def test_an_episode_without_an_appearance_has_none_and_the_manifest_entry_it_always_had(tmp_path):
    write_identity(tmp_path, "act-0001")
    assert bundle.episode_appearance_record(tmp_path, "act-0001") == (None, None)
    assert bundle.episode_appearance_record(tmp_path / "missing", "act-0001") == (None, None)
    base = {"scene_id": "act-0001", "split": "train", "content_sha256": "a" * 64, "frames": {"f": ("n", "b" * 64)}}
    assert bundle._manifest_episodes([{**base, "scene_appearance": None, "teacher_source": None}]) == bundle._manifest_episodes([base])


def test_the_manifest_entry_gains_the_appearance_and_the_source_when_the_episode_has_them():
    record, source = appearance_identity()
    base = {"scene_id": "act-0001", "split": "train", "content_sha256": "a" * 64, "frames": {"f": ("n", "b" * 64)}}
    entry = bundle._manifest_episodes([{**base, "scene_appearance": record, "teacher_source": source}])[0]
    assert entry["scene_appearance"] == record and entry["teacher_source"] == "privileged_pose"


def test_an_identity_whose_source_does_not_follow_its_kind_or_names_another_scene_is_refused(tmp_path):
    record, _ = appearance_identity()
    write_identity(tmp_path, "act-0001", extra={"scene_appearance": record, "teacher_source": "camera_rgbd"})
    with pytest.raises(ValueError, match="EXPORT_EPISODE_APPEARANCE_UNBOUND"):
        bundle.episode_appearance_record(tmp_path, "act-0001")
    write_identity(tmp_path / "b", "act-0002", extra={"scene_appearance": record, "teacher_source": "privileged_pose"})
    with pytest.raises(ValueError, match="EXPORT_EPISODE_APPEARANCE_UNBOUND"):
        bundle.episode_appearance_record(tmp_path / "b", "act-0001")
    broken = dict(record, variant_sha256=None)
    write_identity(tmp_path / "c", "act-0001", extra={"scene_appearance": broken, "teacher_source": "privileged_pose"})
    with pytest.raises(ValueError, match="EXPORT_EPISODE_APPEARANCE_UNBOUND"):
        bundle.episode_appearance_record(tmp_path / "c", "act-0001")
