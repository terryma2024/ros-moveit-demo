"""Design 2026-10-10 section 3.2 / 3.0: the export carries content AND frames, and both are digest-bound.

The content source is the sealed recorder directory of a committed episode (`episode/records.jsonl`, frame digests in the
seal `files` map). The seal itself is bound by the coordinator commit proof. These tests need no torch and no imaging library.
"""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from act_export_fixture import ROW_CONTENT, complete_export_entries, tiny_png

KW = dict(source_manifest_sha256="a" * 64, campaign_index_sha256="b" * 64)


def _rows(count, state=8, action=6):
    return {"frames": count, "rows": [
        {"observation": {"sim_time_s": index * 0.1, "state": [0.1 * index] * state,
                         "head_png": f"frames/{index:06d}-head.png", "wrist_png": f"frames/{index:06d}-wrist.png"},
         "action": [0.01 * index] * action} for index in range(count)]}


def _sealed(tmp_path, entry):
    return Path(entry["collection_evidence"]["result_location"]) / "episode"


def _export(entries, tmp_path, name="dataset"):
    from so101_demo.act.bundle import export_dataset
    return export_dataset(entries, tmp_path / name, **KW)


def test_export_copies_every_frame_with_its_digest_and_points_rows_at_dataset_relative_paths(tmp_path, monkeypatch):
    entries = complete_export_entries(tmp_path, monkeypatch, content=_rows(3))
    document = _export(entries, tmp_path)
    dataset = tmp_path / "dataset"
    for entry in entries:
        scene = entry["scene_id"]
        sealed = _sealed(tmp_path, entry)
        stored = json.loads((dataset / "episodes" / f"{scene}.json").read_text())
        item = next(item for item in document["episodes"] if item["scene_id"] == scene)
        assert len(item["frames"]) == 6
        for row in stored["rows"]:
            for key, camera in (("head_png", "head"), ("wrist_png", "wrist")):
                relative = row["observation"][key]
                assert relative.startswith(f"episodes/{scene}/frames/") and relative.endswith(f"-{camera}.png")
                copied = (dataset / relative).read_bytes()
                assert copied == (sealed / "frames" / Path(relative).name).read_bytes()
                assert item["frames"][relative] == hashlib.sha256(copied).hexdigest()


def test_require_exported_dataset_re_verifies_the_frames(tmp_path, monkeypatch):
    from so101_demo.act.training import require_exported_dataset
    _export(complete_export_entries(tmp_path, monkeypatch, content=_rows(2)), tmp_path)
    dataset = tmp_path / "dataset"
    assert require_exported_dataset(dataset)["scene_count"] == 2
    frame = dataset / "episodes" / "act-1" / "frames" / "000001-wrist.png"
    original = frame.read_bytes()
    frame.write_bytes(original + b"x")
    with pytest.raises(ValueError, match="TRAINING_EPISODE_FRAME_DIGEST_MISMATCH"):
        require_exported_dataset(dataset)
    frame.unlink()
    with pytest.raises(ValueError, match="TRAINING_EPISODE_FRAME_MISSING"):
        require_exported_dataset(dataset)


def test_the_manifest_must_carry_frame_digests(tmp_path, monkeypatch):
    from so101_demo.act.training import require_exported_dataset
    _export(complete_export_entries(tmp_path, monkeypatch, content=_rows(1)), tmp_path)
    dataset = tmp_path / "dataset"
    manifest = json.loads((dataset / "export-manifest.json").read_text())
    del manifest["episodes"][0]["frames"]
    (dataset / "export-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="TRAINING_DATASET_MANIFEST_INVALID"):
        require_exported_dataset(dataset)


def test_a_sealed_frame_that_changed_after_the_seal_refuses_the_export_and_leaves_nothing(tmp_path, monkeypatch):
    entries = complete_export_entries(tmp_path, monkeypatch, content=_rows(2))
    frame = _sealed(tmp_path, entries[1]) / "frames" / "000001-head.png"
    frame.write_bytes(tiny_png(seed=99))
    with pytest.raises(ValueError, match="EXPORT_EPISODE_FRAME_DIGEST_MISMATCH"):
        _export(entries, tmp_path)
    assert not (tmp_path / "dataset").exists() and not (tmp_path / "dataset.partial").exists()


def test_a_missing_sealed_frame_refuses_the_export(tmp_path, monkeypatch):
    entries = complete_export_entries(tmp_path, monkeypatch, content=_rows(2))
    (_sealed(tmp_path, entries[0]) / "frames" / "000000-wrist.png").unlink()
    with pytest.raises(ValueError, match="EXPORT_EPISODE_FRAME_MISSING"):
        _export(entries, tmp_path)
    assert not (tmp_path / "dataset").exists()


def test_a_row_without_both_frames_or_naming_an_unsealed_frame_is_refused(tmp_path, monkeypatch):
    content = _rows(1)
    del content["rows"][0]["observation"]["wrist_png"]
    with pytest.raises(ValueError, match="EXPORT_EPISODE_FRAME_MISSING"):
        _export(complete_export_entries(tmp_path, monkeypatch, content=content), tmp_path)
    other = tmp_path / "second"
    other.mkdir()
    entries = complete_export_entries(other, monkeypatch, content=_rows(1))
    # the stored content names a frame the seal does not list
    renamed = copy.deepcopy(entries[0])
    renamed["content"]["rows"][0]["observation"]["head_png"] = "frames/000009-head.png"
    with pytest.raises(ValueError, match="EXPORT_EPISODE_FRAME_MISSING"):
        _export([renamed, *entries[1:]], other)


@pytest.mark.parametrize("state,action", [(7, 6), (8, 5), (9, 6), (8, 7)])
def test_the_state_and_action_widths_are_checked_at_export(tmp_path, monkeypatch, state, action):
    entries = complete_export_entries(tmp_path, monkeypatch, content=_rows(2, state=state, action=action))
    with pytest.raises(ValueError, match="EXPORT_EPISODE_DIMENSION_INVALID"):
        _export(entries, tmp_path)
    assert not (tmp_path / "dataset").exists()


def test_a_single_observation_content_is_dimension_checked_too(tmp_path, monkeypatch):
    row = _rows(1, state=8, action=5)["rows"][0]
    entries = complete_export_entries(tmp_path, monkeypatch, content={"observation": row["observation"], "action": row["action"]})
    with pytest.raises(ValueError, match="EXPORT_EPISODE_DIMENSION_INVALID"):
        _export(entries, tmp_path)


def test_a_scene_id_that_is_not_a_plain_name_cannot_become_a_directory(tmp_path, monkeypatch):
    entries = complete_export_entries(tmp_path, monkeypatch, ("act-1",), content=_rows(1))
    entries[0]["scene_id"] = "../escape"
    with pytest.raises(ValueError, match="EXPORT_EPISODES_INVALID"):
        _export(entries, tmp_path)


# ---- attach_episode_content: sealed source, content hash always verified ----------------------------------------------------------


def _bare(entries):
    return tuple({key: value for key, value in entry.items() if key not in ("content", "content_path", "content_sha256")}
                 for entry in entries)


def test_the_sealed_recorder_rows_are_the_content_source(tmp_path, monkeypatch):
    from so101_demo.act.training import attach_episode_content
    entries = complete_export_entries(tmp_path, monkeypatch, content=_rows(3))
    attached = attach_episode_content(_bare(entries), root=tmp_path)
    assert [item["scene_id"] for item in attached] == ["act-1", "act-2"]
    content = attached[0]["content"]
    assert content["frames"] == 3 and len(content["rows"]) == 3
    assert all(set(row) == {"observation", "action"} and set(row["observation"]) == {"sim_time_s", "state", "head_png", "wrist_png"}
               for row in content["rows"])
    assert content["rows"][2]["observation"]["head_png"] == "frames/000002-head.png"
    assert "audit" not in json.dumps(content)
    # and the attached episodes export, end to end
    document = _export(attached, tmp_path)
    assert document["scene_count"] == 2


def test_a_sealed_source_whose_seal_is_not_the_one_the_commit_bound_is_refused(tmp_path, monkeypatch):
    from so101_demo.act.training import attach_episode_content
    entries = complete_export_entries(tmp_path, monkeypatch, content=_rows(1))
    seal = _sealed(tmp_path, entries[0]) / "seal.json"
    document = json.loads(seal.read_text())
    document["record_count"] = 5
    seal.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="EXPORT_EPISODE_SEAL_UNBOUND"):
        attach_episode_content(_bare(entries), root=tmp_path)


def test_rows_that_changed_after_the_seal_are_refused(tmp_path, monkeypatch):
    from so101_demo.act.training import attach_episode_content
    entries = complete_export_entries(tmp_path, monkeypatch, content=_rows(2))
    records = _sealed(tmp_path, entries[0]) / "records.jsonl"
    records.write_bytes(records.read_bytes().replace(b"0.01", b"0.02"))
    with pytest.raises(ValueError, match="TRAINING_EPISODE_CONTENT_DIGEST_MISMATCH"):
        attach_episode_content(_bare(entries), root=tmp_path)


def test_a_content_path_without_a_recorded_hash_is_refused_and_a_wrong_hash_too(tmp_path, monkeypatch):
    from so101_demo.act.training import attach_episode_content
    entries = complete_export_entries(tmp_path, monkeypatch, content=ROW_CONTENT)
    plain = [{key: value for key, value in entry.items() if key != "content"} for entry in entries]
    assert len(attach_episode_content(plain, root=tmp_path)) == 2
    unhashed = [{key: value for key, value in entry.items() if key != "content_sha256"} for entry in plain]
    with pytest.raises(ValueError, match="TRAINING_EPISODE_CONTENT_DIGEST_MISSING"):
        attach_episode_content(unhashed, root=tmp_path)
    wrong = [{**entry, "content_sha256": "0" * 64} for entry in plain]
    with pytest.raises(ValueError, match="TRAINING_EPISODE_CONTENT_DIGEST_MISMATCH"):
        attach_episode_content(wrong, root=tmp_path)


def test_inline_content_must_match_its_recorded_hash(tmp_path, monkeypatch):
    from so101_demo.act.training import attach_episode_content
    entries = complete_export_entries(tmp_path, monkeypatch, content=ROW_CONTENT)
    canonical = hashlib.sha256(json.dumps(entries[0]["content"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    ok = [{**entries[0], "content_sha256": canonical}]
    assert attach_episode_content(ok, root=tmp_path)[0]["content"] == entries[0]["content"]
    with pytest.raises(ValueError, match="TRAINING_EPISODE_CONTENT_DIGEST_MISMATCH"):
        attach_episode_content([{**entries[0], "content_sha256": "1" * 64}], root=tmp_path)
    with pytest.raises(ValueError, match="TRAINING_EPISODE_CONTENT_DIGEST_MISSING"):
        attach_episode_content([{key: value for key, value in entries[0].items() if key not in ("content_sha256", "content_path")}],
                               root=tmp_path)
