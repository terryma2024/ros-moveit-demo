"""Steps 10 and 11 of the minimal-runtime-gates design (2026-10-10 section 7):

* collision, contact and force data never enter training: an exported sample and the training loader see only ``observation``
  (joint state, head and wrist image) and ``action``;
* an episode whose Teacher process summary has an oracle flag (cup overload, collision) or is incomplete is not training-eligible:
  the resolver and ``export_dataset`` refuse it with ``EXPORT_EPISODE_ORACLE_EXCLUDED`` (flag and phase), the episode stays committed.
"""
import copy
import hashlib
import json

import pytest

from act_export_fixture import ROW_CONTENT, complete_export_entries
from so101_demo.core.process_summary import ProcessSummary

FORBIDDEN = ("audit", "contact", "force", "collision", "oracle", "teacher_process", "compression", "pair", "hazard")


def keys_of(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from keys_of(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from keys_of(item)


def row(index):
    return {"observation": {"sim_time_s": index * 0.02, "state": [0.1] * 8, "head_png": f"frames/{index:06d}-head.png",
                            "wrist_png": f"frames/{index:06d}-wrist.png"},
            "action": [0.0] * 6,
            "audit": {"contacts": [{"geom1": "gripper", "normal_force_n": 3.5}], "release_epoch": 1,
                      "mujoco_truth": {"sample": {"total_normal_force_n": 3.5}}}}


def dirty_content():
    return {"frames": 2, "rows": [row(0), row(1)], "teacher_process_summary": {"flags": {"ORACLE_COLLISION": ["LIFT"]}},
            "oracle_flags": ["ORACLE_COLLISION"], "collision_pairs": [["table_collision", "upper_arm_collision"]],
            "peak_force_n": 4.4, "audit": {"contacts": []}}


# ---- step 10: the training whitelist ------------------------------------------------------------------------------------------

def test_an_exported_training_sample_has_no_contact_force_or_collision_field(tmp_path, monkeypatch):
    from so101_demo.act.bundle import export_dataset
    entries = complete_export_entries(tmp_path, monkeypatch, content=dirty_content())
    output = tmp_path / "dataset"
    export_dataset(entries, output, source_manifest_sha256="a" * 64, campaign_index_sha256="b" * 64)
    for episode in (output / "episodes").glob("*.json"):
        sample = json.loads(episode.read_text())
        names = set(keys_of(sample))
        assert not [name for name in names if any(word in name.lower() for word in FORBIDDEN)], names
        assert set(sample) <= {"frames", "rows", "state", "observation", "action"}
        assert all(set(item) == {"observation", "action"} and set(item["observation"]) <= {"sim_time_s", "state", "head_png", "wrist_png"}
                   for item in sample["rows"])
        assert [item["action"] for item in sample["rows"]] == [[0.0] * 6] * 2


def test_the_manifest_digest_covers_the_sanitised_bytes_and_a_plain_content_is_unchanged(tmp_path, monkeypatch):
    from so101_demo.act.bundle import export_dataset
    entries = complete_export_entries(tmp_path, monkeypatch)                      # the fixture's rows content
    document = export_dataset(entries, tmp_path / "dataset", source_manifest_sha256="a" * 64, campaign_index_sha256="b" * 64)
    for item in document["episodes"]:
        path = tmp_path / "dataset" / "episodes" / f"{item['scene_id']}.json"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["content_sha256"]
        expected = copy.deepcopy(ROW_CONTENT)                       # only the frame names change: they become dataset-relative
        for row_ in expected["rows"]:
            for key in ("head_png", "wrist_png"):
                row_["observation"][key] = f"episodes/{item['scene_id']}/{row_['observation'][key]}"
        assert json.loads(path.read_text()) == expected


@pytest.mark.parametrize("bad", [
    {"rows": [{"observation": {"sim_time_s": 0.0, "state": [0.0], "head_png": "h", "wrist_png": "w"}}]},       # no action
    {"rows": [{"observation": {"sim_time_s": 0.0, "state": [{"normal_force_n": 1.0}], "head_png": "h", "wrist_png": "w"},
               "action": [0.0]}]},                                                                              # a mapping hidden in the state
    {"rows": [{"observation": {"sim_time_s": 0.0, "state": [0.0], "head_png": "h", "wrist_png": "w"}, "action": [{"x": 1}]}]},
    {"rows": "nope"}])
def test_a_row_that_is_not_an_observation_and_an_action_of_numbers_is_refused(tmp_path, monkeypatch, bad):
    from so101_demo.act.bundle import export_dataset
    entries = complete_export_entries(tmp_path, monkeypatch, content=bad)
    with pytest.raises(ValueError, match="EXPORT_EPISODE_CONTENT_INVALID"):
        export_dataset(entries, tmp_path / "dataset", source_manifest_sha256="a" * 64, campaign_index_sha256="b" * 64)
    assert not (tmp_path / "dataset").exists()


def test_the_training_loader_reads_only_whitelisted_keys(tmp_path, monkeypatch):
    from so101_demo.act.bundle import export_dataset
    from so101_demo.act.training import load_training_samples
    entries = complete_export_entries(tmp_path, monkeypatch, content=dirty_content())
    output = tmp_path / "dataset"
    export_dataset(entries, output, source_manifest_sha256="a" * 64, campaign_index_sha256="b" * 64)
    samples = load_training_samples(output)
    assert [item["scene_id"] for item in samples] == ["act-1", "act-2"]
    for item in samples:
        assert set(item) == {"scene_id", "split", "rows"} and len(item["rows"]) == 2
        assert all(set(record) == {"observation", "action"} for record in item["rows"])
        assert not [name for name in keys_of(item) if any(word in name.lower() for word in FORBIDDEN)]


def test_the_training_loader_drops_what_a_tampered_but_correctly_hashed_export_added(tmp_path, monkeypatch):
    """An export file edited together with its manifest digest is still read through the whitelist."""
    from so101_demo.act.bundle import export_dataset
    from so101_demo.act.training import load_training_samples
    entries = complete_export_entries(tmp_path, monkeypatch, content={"frames": 1, "rows": [row(0)]})
    output = tmp_path / "dataset"
    export_dataset(entries, output, source_manifest_sha256="a" * 64, campaign_index_sha256="b" * 64)
    manifest = json.loads((output / "export-manifest.json").read_text())
    for item in manifest["episodes"]:
        path = output / "episodes" / f"{item['scene_id']}.json"
        document = json.loads(path.read_text())
        document["rows"][0]["audit"] = {"contacts": [1]}
        document["rows"][0]["observation"]["normal_force_n"] = 9.0
        document["teacher_process_summary"] = {"x": 1}
        payload = json.dumps(document, sort_keys=True, indent=2).encode() + b"\n"
        path.write_bytes(payload)
        item["content_sha256"] = hashlib.sha256(payload).hexdigest()
    (output / "export-manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2))
    for item in load_training_samples(output):
        assert set(item["rows"][0]) == {"observation", "action"}
        assert "normal_force_n" not in item["rows"][0]["observation"]


def test_the_loader_still_checks_the_export_digests(tmp_path, monkeypatch):
    from so101_demo.act.bundle import export_dataset
    from so101_demo.act.training import load_training_samples
    entries = complete_export_entries(tmp_path, monkeypatch, content={"frames": 1, "rows": [row(0)]})
    output = tmp_path / "dataset"
    export_dataset(entries, output, source_manifest_sha256="a" * 64, campaign_index_sha256="b" * 64)
    (output / "episodes" / "act-1.json").write_text("{}")
    with pytest.raises(ValueError, match="TRAINING_EPISODE_DIGEST_MISMATCH"):
        load_training_samples(output)


# ---- step 11: oracle exclusion ------------------------------------------------------------------------------------------------

POLICY = {"schema_version": 3, "policy_sha256": "e" * 64, "cup_pose_source": "broker_rgbd", "verdict_source": "sim_truth"}


def teacher_manifest(*, overload=None, collision=None, incomplete=False, limits=True):
    value = ProcessSummary()
    if limits:
        value.limits = type("L", (), {"maximum_safe_force_n": 3.0, "maximum_compression_distance_m": 1e-4})()
    value.phase_begin("LIFT", 1.0)
    value.phase_finish("LIFT", 2.0, "SUCCEEDED")
    value.phase_begin("DESCEND_TO_PLACE", 2.0)
    value.phase_finish("DESCEND_TO_PLACE", 3.0, "SUCCEEDED")
    if overload == "force":
        value.offer_step(1, 1.5, 3.0 + 1e-9, 1e-5)
    if overload == "compression":
        value.offer_step(1, 2.5, 0.5, 1e-4 + 1e-12)
    if collision:
        value.offer_collision(2, 2.6, "table_collision", "upper_arm_collision", -1e-4, 0.4)
    if incomplete:
        value.note_incomplete("PHYSICS_GAP")
    return {"schema": "so101-teacher-execute", "schema_version": 1, "teacher_process_summary": value.build(policy=POLICY)}


def export(entries, tmp_path):
    from so101_demo.act.bundle import export_dataset
    return export_dataset(entries, tmp_path / "dataset", source_manifest_sha256="a" * 64, campaign_index_sha256="b" * 64)


def resolve(entries, tmp_path):
    from so101_demo.act.bundle import resolve_committed_episodes
    index = tmp_path / "campaign-index.json"
    index.write_text(json.dumps({"schema_version": 2, "committed_episodes": list(entries)}))
    return resolve_committed_episodes(manifest={"episodes": [{"scene_id": e["scene_id"], "status": "PASSED", "split": "train"} for e in entries]},
                                      campaign_index=index)


@pytest.mark.parametrize("manifest,flag,phase", [
    (teacher_manifest(overload="force"), "ORACLE_CUP_OVERLOAD", "LIFT"),
    (teacher_manifest(overload="compression"), "ORACLE_CUP_OVERLOAD", "DESCEND_TO_PLACE"),
    (teacher_manifest(collision=True), "ORACLE_COLLISION", "DESCEND_TO_PLACE"),
    (teacher_manifest(incomplete=True), "INCOMPLETE", "PHYSICS_GAP"),
    (teacher_manifest(limits=False), "INCOMPLETE", "THRESHOLDS_UNAVAILABLE"),
], ids=["force-overload", "compression-overload", "collision", "incomplete", "no-thresholds"])
@pytest.mark.parametrize("direct", [False, True])
def test_an_oracle_flagged_or_incomplete_episode_is_refused_by_both_boundaries_and_stays_committed(
        tmp_path, monkeypatch, manifest, flag, phase, direct):
    entries = complete_export_entries(tmp_path, monkeypatch, ("act-1",), teacher_manifests={"act-1": manifest})
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in tmp_path.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match=f"EXPORT_EPISODE_ORACLE_EXCLUDED: {flag} {phase}"):
        export(entries, tmp_path) if direct else resolve(entries, tmp_path)
    assert not (tmp_path / "dataset").exists()
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before}
    assert after == before                                             # the sealed episode and its evidence are untouched


@pytest.mark.parametrize("manifest", [teacher_manifest(), {"schema": "so101-dynamic-execute", "schema_version": 1}], ids=["clean-teacher", "general-no-summary"])
def test_a_clean_episode_and_a_policy_episode_are_accepted(tmp_path, monkeypatch, manifest):
    entries = complete_export_entries(tmp_path, monkeypatch, ("act-1",), teacher_manifests={"act-1": manifest})
    assert len(resolve(entries, tmp_path)) == 1
    assert export(entries, tmp_path)["scene_count"] == 1


def test_a_tampered_summary_that_hides_its_flag_is_refused(tmp_path, monkeypatch):
    manifest = teacher_manifest(collision=True)
    manifest["teacher_process_summary"]["flags"]["ORACLE_COLLISION"] = []
    entries = complete_export_entries(tmp_path, monkeypatch, ("act-1",), teacher_manifests={"act-1": manifest})
    with pytest.raises(ValueError, match="EXPORT_EPISODE_ORACLE_EXCLUDED: INCOMPLETE"):
        export(entries, tmp_path)


def test_the_teacher_manifest_must_be_the_one_the_qc_bound(tmp_path, monkeypatch):
    entries = complete_export_entries(tmp_path, monkeypatch, ("act-1",), teacher_manifests={"act-1": teacher_manifest()})
    location = tmp_path / "controlled-v2-export-0" / "sealed"
    (location / "dynamic" / "dynamic-execute-manifest.json").write_text(json.dumps(teacher_manifest(collision=True)))
    with pytest.raises(ValueError, match="EXPORT_EPISODE_TEACHER_MANIFEST_UNBOUND"):
        export(entries, tmp_path)
    (location / "dynamic" / "dynamic-execute-manifest.json").unlink()
    with pytest.raises(ValueError, match="EXPORT_EPISODE_TEACHER_MANIFEST_UNREADABLE"):
        export(entries, tmp_path)


@pytest.mark.parametrize("direct", [False, True])
def test_the_diagnostic_mode_refusal_keeps_precedence_over_the_oracle_exclusion(tmp_path, monkeypatch, direct):
    entries = complete_export_entries(tmp_path, monkeypatch, ("act-1",), teacher_manifests={"act-1": teacher_manifest(collision=True)},
                                      proof_overrides={"act-1": {"collection_mode": "preselected_target_diagnostic"}})
    from so101_demo.act import collection_scope
    real = collection_scope.read_collection_scope
    monkeypatch.setattr(collection_scope, "read_collection_scope",
                        lambda path: {**real(path), "mode": "preselected_target_diagnostic"})
    with pytest.raises(ValueError, match="DIAGNOSTIC_EPISODE_NOT_TRAINABLE"):
        export(entries, tmp_path) if direct else resolve(entries, tmp_path)


def test_a_failed_qc_or_teacher_status_still_reports_its_own_refusal_first(tmp_path, monkeypatch):
    entries = complete_export_entries(tmp_path, monkeypatch, ("act-1",), teacher_manifests={"act-1": teacher_manifest(collision=True)},
                                      proof_overrides={"act-1": {"result_status": "FAILED"}})
    with pytest.raises(ValueError, match="EXPORT_EPISODE_NOT_PASSED"):
        export(entries, tmp_path)


# ---- review changes 5 and 6 --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [{"frames": 2, "state": [0.0] * 8}, {"observation": {"state": [0.0]}}, {"action": [0.0]},
                                 {"frames": 1}])
def test_a_content_with_neither_rows_nor_an_observation_and_an_action_is_refused(tmp_path, monkeypatch, bad):
    entries = complete_export_entries(tmp_path, monkeypatch, content=bad)
    with pytest.raises(ValueError, match="EXPORT_EPISODE_CONTENT_INVALID"):
        export(entries, tmp_path)


def test_a_single_observation_with_its_action_is_a_valid_content(tmp_path, monkeypatch):
    content = {"observation": row(0)["observation"], "action": [0.0] * 6, "audit": {"contacts": [1]}}
    entries = complete_export_entries(tmp_path, monkeypatch, content=content)
    export(entries, tmp_path)
    stored = json.loads((tmp_path / "dataset" / "episodes" / "act-1.json").read_text())
    assert set(stored) == {"observation", "action"}


def _train(tmp_path, monkeypatch, content, trainer):
    from so101_demo.act.bundle import export_dataset
    from so101_demo.act.training import train_act
    dataset = tmp_path / "dataset"
    export_dataset(complete_export_entries(tmp_path, monkeypatch, content=content), dataset, source_manifest_sha256="a" * 64,
                   campaign_index_sha256="b" * 64)
    return dataset, train_act(config={"action": {}}, requirements={"status": "RESOLVED"}, dataset=dataset,
                              owner={"device": "cuda", "run_root": str(tmp_path)}, output=tmp_path / "bundle", trainer=trainer)


def test_the_trainer_is_given_a_view_that_never_holds_contact_force_or_audit_fields(tmp_path, monkeypatch):
    seen = {}

    def trainer(config, dataset, output):
        files = sorted(path.name for path in dataset.rglob("*") if path.is_file())
        seen["files"] = files
        seen["text"] = "".join((dataset / name).read_text() for name in files)
        seen["samples"] = json.loads((dataset / "training-samples.json").read_text())
        return {"kind": "act_bundle", "schema_version": 1}

    dataset, outcome = _train(tmp_path, monkeypatch, dirty_content(), trainer)
    assert outcome["status"] == "COMPLETED"
    assert seen["files"] == ["export-manifest.json", "training-samples.json"]                 # the episodes directory is not reachable
    names = set(keys_of(seen["samples"]))
    assert not [name for name in names if any(word in name.lower() for word in FORBIDDEN)], names
    assert "normal_force" not in seen["text"] and "oracle" not in seen["text"].lower() and "audit" not in seen["text"]
    assert (dataset / "export-manifest.json").read_bytes() == (tmp_path / "bundle.training-view" / "export-manifest.json").read_bytes()


def test_a_correctly_hashed_but_tampered_export_still_reaches_the_trainer_only_through_the_whitelist(tmp_path, monkeypatch):
    from so101_demo.act.bundle import export_dataset
    from so101_demo.act.training import train_act
    dataset = tmp_path / "dataset"
    export_dataset(complete_export_entries(tmp_path, monkeypatch, content={"frames": 1, "rows": [row(0)]}), dataset,
                   source_manifest_sha256="a" * 64, campaign_index_sha256="b" * 64)
    manifest = json.loads((dataset / "export-manifest.json").read_text())
    for item in manifest["episodes"]:
        path = dataset / "episodes" / f"{item['scene_id']}.json"
        document = json.loads(path.read_text())
        document["rows"][0]["audit"] = {"contacts": [1], "normal_force_n": 9.0}
        document["rows"][0]["observation"]["normal_force_n"] = 9.0
        payload = json.dumps(document, sort_keys=True, indent=2).encode() + b"\n"
        path.write_bytes(payload)
        item["content_sha256"] = hashlib.sha256(payload).hexdigest()
    (dataset / "export-manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2))
    seen = {}

    def trainer(config, view, output):
        seen["text"] = (view / "training-samples.json").read_text()
        return {"kind": "act_bundle", "schema_version": 1}

    train_act(config={"action": {}}, requirements={"status": "RESOLVED"}, dataset=dataset,
              owner={"device": "cuda", "run_root": str(tmp_path)}, output=tmp_path / "bundle", trainer=trainer)
    assert "audit" not in seen["text"] and "normal_force_n" not in seen["text"]


def test_train_act_refuses_before_the_trainer_when_the_view_or_the_output_already_exists(tmp_path, monkeypatch):
    calls = []
    (tmp_path / "bundle.training-view").mkdir()
    with pytest.raises(ValueError, match="TRAINING_OUTPUT_EXISTS"):
        _train(tmp_path, monkeypatch, {"frames": 1, "rows": [row(0)]}, lambda *a: calls.append(a))
    assert calls == []


def test_the_trainer_entry_points_receive_the_view_path_and_hash_the_export_manifest_it_carries(tmp_path, monkeypatch):
    """The bundle's dataset digest is the export manifest's: the view carries a byte-identical copy of it."""
    from so101_demo.adapters.act.lerobot import _dataset_digest
    seen = {}

    def trainer(config, view, output):
        seen["digest"] = _dataset_digest(view)
        return {"kind": "act_bundle", "schema_version": 1}

    dataset, _ = _train(tmp_path, monkeypatch, {"frames": 1, "rows": [row(0)]}, trainer)
    assert seen["digest"] == _dataset_digest(dataset)
