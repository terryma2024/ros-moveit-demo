"""Task 12: what a training bundle may contain, and what it must refuse."""

import json

import pytest

from so101_demo.act.bundle import resolve_committed_episodes, training_rows


def test_normalization_uses_only_train():
    rows = [{"split": "train", "state": [1.]}, {"split": "validation", "state": [100.]}]
    assert training_rows(rows) == [rows[0]]


def test_directory_seal_without_coordinator_commit_is_rejected(tmp_path):
    (tmp_path / "episode-001").mkdir()
    assert resolve_committed_episodes(
        manifest={"episodes": [{"scene_id": "001", "status": "PASSED"}]},
        campaign_index=tmp_path / "campaign-index.json",
    ) == ()


def test_only_verified_committed_episodes_resolve(tmp_path):
    index = tmp_path / "campaign-index.json"
    index.write_text(json.dumps({"schema_version": 1, "committed_episodes": [
        {"scene_id": "001", "journal_sha256": "a" * 64, "verifier_sha256": "a" * 64}]}))
    manifest = {"episodes": [{"scene_id": "001", "status": "PASSED"},
                             {"scene_id": "002", "status": "PASSED"},        # no commit
                             {"scene_id": "003", "status": "FAILED"}]}       # business failure
    resolved = resolve_committed_episodes(manifest=manifest, campaign_index=index)
    assert tuple(item["scene_id"] for item in resolved) == ("001",)

    # evidence outside the collection projection never enters a training bundle
    assert training_rows([{"split": "train"}, {"split": "rollout_test"},
                          {"split": "offline_test"}]) == [{"split": "train"}]
    for bad_rows in ("train", [{"state": [1.]}], [None]):
        with pytest.raises(ValueError, match="TRAINING_ROWS_INVALID"):
            training_rows(bad_rows)
    with pytest.raises(ValueError, match="MANIFEST_INVALID"):
        resolve_committed_episodes(manifest={}, campaign_index=index)
    with pytest.raises(ValueError, match="MANIFEST_INVALID"):
        resolve_committed_episodes(manifest={"episodes": [{"status": "PASSED"}]},
                                   campaign_index=index)
    with pytest.raises(ValueError, match="CAMPAIGN_INDEX_INVALID"):
        index.write_text("{not json")
        resolve_committed_episodes(manifest=manifest, campaign_index=index)


def test_conflicting_receipts_and_unverifiable_entries_are_refused(tmp_path):
    manifest = {"episodes": [{"scene_id": "001", "status": "PASSED"}]}
    index = tmp_path / "campaign-index.json"
    index.write_text(json.dumps({"committed_episodes": [
        {"scene_id": "001", "journal_sha256": "a" * 64, "verifier_sha256": "b" * 64}]}))
    with pytest.raises(ValueError, match="EPISODE_RECEIPT_CONFLICT"):
        resolve_committed_episodes(manifest=manifest, campaign_index=index)
    index.write_text(json.dumps({"committed_episodes": [
        {"scene_id": "001", "journal_sha256": "a" * 64, "verifier_sha256": "short"}]}))
    with pytest.raises(ValueError, match="EPISODE_RECEIPT_INVALID"):
        resolve_committed_episodes(manifest=manifest, campaign_index=index)


def _write_bundle(tmp_path, *, policy_bytes=b"model-bytes", normalization=None, **overrides):
    import hashlib

    (tmp_path / "policy.bin").write_bytes(policy_bytes)
    document = {"schema_version": 1, "kind": "act_bundle",
                "model_source": {"name": "act-v1", "sha256": "a" * 64},
                "dataset_sha256": "b" * 64, "config_sha256": "c" * 64,
                "policy_path": "policy.bin",
                "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
                # `normalization or {...}` would repair the deliberately empty normalisation,
                # so the case would never reach the guard it exists to exercise (as in CP-767)
                "normalization": ({"split": "train", "mean": [0.0]}
                                  if normalization is None else normalization),
                "action": {"chunk_size": 10, "execution_prefix": 1,
                           "temporal_ensembling": False, "tail_padding_mask": True}}
    document.update(overrides)
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(document))
    return path, document


def test_a_bundle_must_carry_the_policy_it_names(tmp_path):
    from so101_demo.act.bundle import BUNDLE_KEYS, load_bundle

    path, document = _write_bundle(tmp_path)
    loaded = load_bundle(path)
    assert set(loaded) == set(BUNDLE_KEYS)
    # the policy is checked against its bytes, so a swapped file cannot pass as the trained one
    (tmp_path / "policy.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="BUNDLE_POLICY_DIGEST_MISMATCH"):
        load_bundle(path)
    (tmp_path / "policy.bin").unlink()
    with pytest.raises(ValueError, match="BUNDLE_POLICY_MISSING"):
        load_bundle(path)
    with pytest.raises(ValueError, match="BUNDLE_MISSING"):
        load_bundle(tmp_path / "absent.json")


def test_normalization_must_come_from_the_train_split_alone(tmp_path):
    from so101_demo.act.bundle import load_bundle

    path, _ = _write_bundle(tmp_path, normalization={"split": "validation", "mean": [1.0]})
    with pytest.raises(ValueError, match="BUNDLE_NORMALIZATION_NOT_TRAIN_ONLY"):
        load_bundle(path)
    path, _ = _write_bundle(tmp_path, normalization={})
    with pytest.raises(ValueError, match="BUNDLE_NORMALIZATION_NOT_TRAIN_ONLY"):
        load_bundle(path)


def test_a_bundle_document_is_closed_and_its_policy_path_stays_inside(tmp_path):
    from so101_demo.act.bundle import load_bundle

    for overrides in ({"policy_path": "../outside.bin"}, {"policy_path": "/etc/passwd"},
                      {"policy_path": ""}, {"extra": 1}, {"model_source": {"name": "act-v1"}},
                      {"dataset_sha256": "short"}, {"kind": "other"}):
        path, _ = _write_bundle(tmp_path, **overrides)
        with pytest.raises(ValueError, match="BUNDLE_INVALID|BUNDLE_POLICY_PATH_INVALID"):
            load_bundle(path)


def test_the_policy_interface_is_required_before_a_runner_may_use_it(tmp_path):
    from so101_demo.act.bundle import load_policy, require_policy_interface

    path, _ = _write_bundle(tmp_path)

    class Model:
        def __init__(self):
            self.resets = 0

        def infer(self, observation):
            return ((0.0,) * 6,)

        def reset(self):
            self.resets += 1

    model = load_policy(path, loader=lambda bundle: Model())
    assert model.infer({"state": [0.0]}) == ((0.0,) * 6,)
    for bad in (object(), type("NoReset", (), {"infer": lambda self, o: ()})(),
                type("NoInfer", (), {"reset": lambda self: None})(),
                {"infer": lambda o: (), "reset": lambda: None}):
        with pytest.raises(ValueError, match="POLICY_INTERFACE_INVALID"):
            require_policy_interface(bad)
    with pytest.raises(ValueError, match="POLICY_LOADER_REQUIRED"):
        load_policy(path, loader=None)


def _committed(scene_ids=("act-1", "act-2"), *, split="train", status="PASSED", dataset_id=None):
    return tuple({"scene_id": scene_id, "split": split, "status": status,
                  "content": {"frames": 1, "state": [0.0] * 8},
                  **({} if dataset_id is None else {"dataset_id": dataset_id})}
                 for scene_id in scene_ids)


def test_the_export_is_written_once_in_the_resolved_order(tmp_path):
    import hashlib

    from so101_demo.act.bundle import EXPORT_KEYS, export_dataset

    output = tmp_path / "dataset"
    document = export_dataset(_committed(), output, source_manifest_sha256="a" * 64,
                              campaign_index_sha256="b" * 64)
    assert set(document) == set(EXPORT_KEYS) | {"manifest_path", "export_sha256"}
    assert document["scene_count"] == 2
    assert [episode["scene_id"] for episode in document["episodes"]] == ["act-1", "act-2"]
    manifest = output / "export-manifest.json"
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == document["export_sha256"]
    for episode in document["episodes"]:
        path = output / "episodes" / f"{episode['scene_id']}.json"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == episode["content_sha256"]
    assert not list(output.rglob("*.partial"))
    # a second export must not append into the first: the dataset cannot grow under a training run
    with pytest.raises(ValueError, match="EXPORT_OUTPUT_EXISTS"):
        export_dataset(_committed(), output, source_manifest_sha256="a" * 64,
                       campaign_index_sha256="b" * 64)


def test_the_export_refuses_what_must_not_enter_training(tmp_path):
    from so101_demo.act.bundle import export_dataset

    cases = ((_committed(()), "a" * 64, "b" * 64, "EXPORT_EMPTY"),
             (_committed(("act-0917a-1",)), "a" * 64, "b" * 64, "EXPORT_STALE_DATASET_ID"),
             (_committed(dataset_id="0917a-run"), "a" * 64, "b" * 64, "EXPORT_STALE_DATASET_ID"),
             (_committed(split="rollout_test"), "a" * 64, "b" * 64, "EXPORT_SPLIT_FORBIDDEN"),
             (_committed(split="functional"), "a" * 64, "b" * 64, "EXPORT_SPLIT_FORBIDDEN"),
             (_committed(status="FAILED"), "a" * 64, "b" * 64, "EXPORT_EPISODE_NOT_PASSED"),
             (_committed(("act-1", "act-1")), "a" * 64, "b" * 64, "EXPORT_DUPLICATE_SCENE"),
             (({"scene_id": "act-1", "content": {}},), "short", "b" * 64,
              "EXPORT_SOURCE_DIGEST_INVALID"),
             ((({"scene_id": "act-1"},)), "a" * 64, "b" * 64,
              "EXPORT_EPISODE_CONTENT_MISSING"),
             ({"scene_id": "act-1"}, "a" * 64, "b" * 64, "EXPORT_EPISODES_INVALID"))
    for index, (committed, source, index_digest, code) in enumerate(cases):
        target = tmp_path / f"refused-{index}"
        with pytest.raises(ValueError, match=code):
            export_dataset(committed, target, source_manifest_sha256=source,
                           campaign_index_sha256=index_digest)
        assert not target.exists()            # a refused export leaves nothing behind
