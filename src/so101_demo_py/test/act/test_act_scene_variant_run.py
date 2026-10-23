"""The run side of a scene variant: the file, the record, the owned scene, the identity, and the physics check (goal 35-R0)."""

import hashlib
import json
from pathlib import Path

import pytest

from paths import PACKAGE_ROOT
from so101_demo.act import scene_variant as sv
from so101_demo.act import scene_variant_run as run

SHARE = PACKAGE_ROOT
VARIANT = {"schema_version": 1, "kind": "ACT_SCENE_VARIANT", "name": "light_0p5x",
           "set": {"key_light.diffuse": [0.35, 0.35, 0.35]}}


def _file(tmp_path, document=VARIANT, name="variant.json"):
    path = tmp_path / name
    path.write_text(json.dumps(document))
    return path


def test_a_variant_file_is_read_validated_and_hashed_by_its_bytes(tmp_path):
    path = _file(tmp_path)
    loaded = run.read_variant_file(path)
    assert loaded == sv.normalize_variant(VARIANT)
    assert run.file_ref(path) == {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.mark.parametrize("text", ['{"schema_version": 1, "schema_version": 1}', "[]", "not json", '{"a": NaN}'])
def test_a_malformed_variant_file_is_refused(tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text)
    with pytest.raises(sv.SceneVariantRefused):
        run.read_variant_file(path)


def test_a_physics_field_in_the_file_is_refused(tmp_path):
    path = _file(tmp_path, dict(VARIANT, set={"geom.friction": [1.0]}))
    with pytest.raises(sv.SceneVariantRefused, match="SCENE_VARIANT_FIELD_REFUSED"):
        run.read_variant_file(path)


def test_the_record_carries_the_variant_the_applied_values_the_hashes_and_the_equal_physics_fingerprints(tmp_path):
    record = run.realize_into(tmp_path / "owned", SHARE, sv.normalize_variant(VARIANT))
    scene = tmp_path / "owned" / run.SCENE_FILE
    assert Path(record["scene_path"]) == scene and scene.is_file()
    assert record["name"] == "light_0p5x" and record["variant"] == sv.normalize_variant(VARIANT)
    assert record["applied"]["key_light.diffuse"] == {"nominal": [0.7, 0.7, 0.7], "value": [0.35] * 3}
    assert record["physics_fingerprint"] == record["nominal_physics_fingerprint"]
    again = run.realize_into(tmp_path / "owned2", SHARE, sv.normalize_variant(VARIANT))
    assert again["realized_sha256"] == record["realized_sha256"] and again["physics_fingerprint"] == record["physics_fingerprint"]


def test_a_variant_whose_physics_differs_from_the_nominal_is_refused_and_the_scene_is_not_kept(tmp_path, monkeypatch):
    calls = []

    def fingerprint(path):
        calls.append(Path(path).name)
        return "a" * 64 if len(calls) == 1 else "b" * 64
    monkeypatch.setattr(run, "physics_fingerprint_of_file", fingerprint)
    with pytest.raises(sv.SceneVariantRefused, match="SCENE_VARIANT_PHYSICS_MISMATCH"):
        run.realize_into(tmp_path / "owned", SHARE, sv.normalize_variant(VARIANT))
    assert not (tmp_path / "owned" / run.SCENE_FILE).exists()


def test_the_identity_entry_binds_the_names_and_hashes_and_nothing_else(tmp_path):
    record = run.realize_into(tmp_path / "owned", SHARE, sv.normalize_variant(VARIANT))
    identity = run.identity_entry(record)
    assert set(identity) == {"name", "variant_sha256", "realized_sha256", "physics_fingerprint"}
    assert identity["realized_sha256"] == record["realized_sha256"] and identity["name"] == "light_0p5x"


def test_the_host_record_is_computed_in_a_scratch_directory_and_leaves_nothing_behind(tmp_path):
    path = _file(tmp_path)
    before = sorted(item.name for item in tmp_path.iterdir())
    record = run.host_record(path, SHARE)
    assert sorted(item.name for item in tmp_path.iterdir()) == before
    assert "scene_path" not in record and record["file"] == run.file_ref(path)
    assert record["realized_sha256"] == sv.realize(SHARE / "assets/mujoco/act", VARIANT).realized_sha256


def test_binding_a_variant_into_an_identity_adds_one_entry_and_none_without_a_variant(tmp_path):
    identity = {"bundle_sha256": "a" * 64}
    assert run.bind_variant(None, SHARE, identity) is None and identity == {"bundle_sha256": "a" * 64}
    record = run.bind_variant(_file(tmp_path), SHARE, identity)
    assert identity["scene_variant"] == run.identity_entry(record) and identity["bundle_sha256"] == "a" * 64
    assert record["file"]["sha256"] == hashlib.sha256((tmp_path / "variant.json").read_bytes()).hexdigest()


def test_a_variant_of_other_values_gives_another_identity_entry(tmp_path):
    one = run.host_record(_file(tmp_path), SHARE)
    other_document = dict(VARIANT, set={"key_light.diffuse": [0.525, 0.525, 0.525]})
    other = run.host_record(_file(tmp_path, other_document, "other.json"), SHARE)
    assert run.identity_entry(one) != run.identity_entry(other)
    assert one["physics_fingerprint"] == other["physics_fingerprint"]


def test_the_shard_realizes_the_scene_of_its_spec_into_its_owned_root_and_refuses_a_drifted_hash(tmp_path):
    path = _file(tmp_path)
    host = run.host_record(path, SHARE)
    spec = {"owned_root": str(tmp_path / "owned-root"), "scene_variant": run.spec_entry(host)}
    (tmp_path / "owned-root").mkdir()
    scene, record = run.prepare_shard_scene(spec, SHARE)
    assert scene == tmp_path / "owned-root" / "scene-variant" / run.SCENE_FILE and scene.is_file()
    assert record["realized_sha256"] == host["realized_sha256"]
    written = json.loads((tmp_path / "owned-root" / run.RECORD_FILE).read_text())
    assert written["realized_sha256"] == host["realized_sha256"] and written["scene_path"] == str(scene)
    drifted = {"owned_root": str(tmp_path / "owned-root2"), "scene_variant": dict(run.spec_entry(host), realized_sha256="0" * 64)}
    (tmp_path / "owned-root2").mkdir()
    with pytest.raises(sv.SceneVariantRefused, match="SCENE_VARIANT_REALIZED_MISMATCH"):
        run.prepare_shard_scene(drifted, SHARE)


def test_a_spec_without_a_variant_has_no_scene_to_prepare(tmp_path):
    assert run.prepare_shard_scene({"owned_root": str(tmp_path)}, SHARE) == (None, None)


def test_the_spec_entry_is_closed(tmp_path):
    host = run.host_record(_file(tmp_path), SHARE)
    entry = run.spec_entry(host)
    assert set(entry) == {"file", "realized_sha256", "physics_fingerprint"}
    assert run.valid_spec_entry(entry)
    for broken in ({**entry, "extra": 1}, {**entry, "realized_sha256": "xyz"}, {**entry, "file": {"path": "rel", "sha256": "0" * 64}},
                   {k: v for k, v in entry.items() if k != "file"}, [], None):
        assert not run.valid_spec_entry(broken)
