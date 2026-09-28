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
