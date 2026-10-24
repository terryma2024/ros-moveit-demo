"""R3-a: the case inputs of a schema 6 campaign record each scene's derived Teacher diversity values (`<run>/inputs/diversity/<scene>.json`).

Real here, as in test_case_inputs.py: `freeze_inputs` through `freeze_campaign_inputs`, the scope writer and reader. The values are the
derivation of (the frozen policy's campaign seed, scene id); reading the case inputs back re-derives and compares them. A schema 3, 4 or 5
freeze writes no diversity record and its case inputs are what they were."""

import json
from pathlib import Path

import pytest

from so101_demo.act import teacher_diversity as td
from so101_demo.act.diagnostic_episode_inputs import verify_frozen_inputs
from so101_demo.runtime.container_campaign import case_inputs
from so101_demo.runtime.container_campaign.paths import make_campaign_paths
from test_act_formal_scene_scope import ROWS, scene_file
from test_act_diagnostic_episode_scope import _write_registry
from test_case_inputs import CONFIG, bound_registry, policies
from paths import REPOSITORY

SCHEMA6_FILE = CONFIG / "teacher_execution_policy_side_wrist_fast_carry_b_diversity.yaml"


def freeze_world(tmp_path_factory, name, policy_file):
    from so101_demo.act import execution_snapshot

    base = tmp_path_factory.mktemp(name)
    probe = execution_snapshot.freeze_execution_snapshot(REPOSITORY, base / "probe")
    scene_bytes = (base / "probe" / probe["scene_path"]).read_bytes()
    candidates = _write_registry(base, bound_registry(base, probe, scene_bytes))
    source = scene_file(base)
    root = base / "evidence"
    root.mkdir()
    run = make_campaign_paths(root, "run-1")["run"]
    original = execution_snapshot.freeze_execution_snapshot
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(execution_snapshot, "freeze_execution_snapshot", lambda _source_root, output: original(REPOSITORY, output))
        manifest = case_inputs.freeze_campaign_inputs(
            run, candidates=candidates, scene_manifest=source, **{**policies(), "teacher_execution_policy": policy_file})
    scopes = case_inputs.write_case_scopes(run, inputs_manifest=manifest)
    return dict(run=run, manifest=manifest, scopes=scopes, frozen=verify_frozen_inputs(Path(manifest["path"])))


@pytest.fixture(scope="module")
def schema6(tmp_path_factory):
    return freeze_world(tmp_path_factory, "case-diversity", SCHEMA6_FILE)


@pytest.fixture(scope="module")
def schema3(tmp_path_factory):
    return freeze_world(tmp_path_factory, "case-plain", CONFIG / "teacher_execution_policy.yaml")


def record_path(world, scene):
    return world["run"] / "inputs" / "diversity" / f"{scene}.json"


def test_each_scene_has_a_record_of_its_derived_values(schema6):
    policy = schema6["frozen"]["teacher_execution_policy"]
    for row in ROWS:
        document = json.loads(record_path(schema6, row["scene_id"]).read_bytes())
        assert document["scene_id"] == row["scene_id"] and document["inputs_sha256"] == schema6["frozen"]["inputs_sha256"]
        assert document["policy_sha256"] == policy["policy_sha256"]
        assert document["values"] == td.values_for_policy(policy["values"], row["scene_id"])
    assert json.loads(record_path(schema6, "scene-a").read_bytes())["values"] != json.loads(record_path(schema6, "scene-b").read_bytes())["values"]


def test_the_returned_case_inputs_keep_their_closed_shape(schema6):
    assert {scene: set(item) for scene, item in schema6["scopes"].items()} == {row["scene_id"]: {"scope", "inputs_manifest"} for row in ROWS}


def test_reading_the_case_inputs_back_checks_the_records(schema6):
    assert case_inputs.read_case_scopes(schema6["run"], inputs_manifest=schema6["manifest"]) == schema6["scopes"]


def test_a_missing_edited_or_foreign_record_is_refused_on_read(schema6, tmp_path):
    path = record_path(schema6, "scene-a")
    original = path.read_bytes()
    try:
        document = json.loads(original)
        document["values"]["speed_scale"] = 1.0
        path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
        with pytest.raises(ValueError, match="CASE_DIVERSITY_INVALID"):
            case_inputs.read_case_scopes(schema6["run"], inputs_manifest=schema6["manifest"])
        path.unlink()
        with pytest.raises(ValueError, match="CASE_DIVERSITY_INVALID"):
            case_inputs.read_case_scopes(schema6["run"], inputs_manifest=schema6["manifest"])
    finally:
        path.write_bytes(original)
    assert case_inputs.read_case_scopes(schema6["run"], inputs_manifest=schema6["manifest"]) == schema6["scopes"]


def test_the_records_are_written_once(schema6):
    with pytest.raises(ValueError, match="CASE_SCOPES_EXIST|CASE_DIVERSITY_EXIST"):
        case_inputs.write_case_scopes(schema6["run"], inputs_manifest=schema6["manifest"])


def test_a_freeze_without_a_diversity_block_writes_no_record_and_reads_back_as_before(schema3):
    assert not (schema3["run"] / "inputs" / "diversity").exists()
    assert case_inputs.read_case_scopes(schema3["run"], inputs_manifest=schema3["manifest"]) == schema3["scopes"]
