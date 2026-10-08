"""Frozen source, model assets and recipe-derived targets for the actual child."""

import hashlib
import json
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
SOURCE = PACKAGE.parents[1]


def _snapshot(tmp_path):
    from so101_demo.act.execution_snapshot import freeze_execution_snapshot
    return freeze_execution_snapshot(SOURCE, tmp_path / "execution")


def test_frozen_scene_loads_without_original_asset_tree(tmp_path):
    import mujoco
    from so101_demo.adapters.act.physics import model_sha256
    document = _snapshot(tmp_path)
    root = tmp_path / "execution"
    model = mujoco.MjModel.from_xml_path(str(root / document["scene_path"]))
    assert model_sha256(model) == document["model_sha256"]
    assert document["nq"] == model.nq and document["nv"] == model.nv
    assert (root / "assets/mujoco/act/so101.xml").is_file()
    assert (root / "assets/mujoco/assets/target_landing_tolerance_ring.obj").is_file()
    assert document["source_sha256"] != hashlib.sha256(b"UNRECORDED_SOURCE").hexdigest()
    assert document["source_files"]["src/so101_demo_py/src/cli/dynamic_cup_pick_place.py"]["sha256"] == hashlib.sha256(
        (PACKAGE / "src/cli/dynamic_cup_pick_place.py").read_bytes()).hexdigest()


def test_targets_derive_from_reset_and_place_recipe_before_execution(tmp_path):
    from so101_demo.core.dynamic_pick import compose_pose, inverse_pose
    from so101_demo.core.dynamic_pick_policy import load_dynamic_pick_template
    document = _snapshot(tmp_path)
    root = tmp_path / "execution"
    targets = document["targets"]
    template = load_dynamic_pick_template(root / document["motion_policy_path"])
    assert targets["initial_target"] == pytest.approx([.02, -.28, .165, 0, 0, 0, 1])
    assert targets["final_target"] == pytest.approx(
        compose_pose(template.place_tcp_world, inverse_pose(template.cup_to_tcp_grasp)).values)
    assert targets["frame_id"] == "world" and targets["body_name"] == "plastic_cup"
    assert targets["reset_recipe_sha256"] == document["files"][document["scene_path"]]["sha256"]
    assert targets["place_recipe_sha256"] == document["files"][document["motion_policy_path"]]["sha256"]


@pytest.mark.parametrize("mutation", ["asset", "source", "target", "unknown", "version", "symlink"])
def test_snapshot_reader_rejects_tamper_with_positive_control(tmp_path, mutation):
    from so101_demo.act.execution_snapshot import verify_execution_snapshot
    document = _snapshot(tmp_path)
    root = tmp_path / "execution"
    assert verify_execution_snapshot(root) == document
    manifest_path = root / "execution-manifest.json"
    if mutation in ("asset", "source", "symlink"):
        relative = ("assets/mujoco/act/so101.xml" if mutation != "source" else
                    "source/src/so101_demo_py/src/act/recorder.py")
        path = root / relative
        if mutation == "symlink":
            path.rename(root / "original.xml")
            path.symlink_to(root / "original.xml")
        else:
            path.write_bytes(path.read_bytes() + b"tampered")
    else:
        if mutation == "target":
            document["targets"]["final_target"][0] += .5
        elif mutation == "unknown":
            document["extra"] = True
        else:
            document["schema_version"] = 2
        manifest_path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="EXECUTION_SNAPSHOT"):
        verify_execution_snapshot(root)


def test_snapshot_rejects_existing_root_without_changing_it(tmp_path):
    from so101_demo.act.execution_snapshot import freeze_execution_snapshot
    document = _snapshot(tmp_path)
    raw = (tmp_path / "execution/execution-manifest.json").read_bytes()
    with pytest.raises(ValueError, match="EXECUTION_SNAPSHOT_EXISTS"):
        freeze_execution_snapshot(SOURCE, tmp_path / "execution")
    assert (tmp_path / "execution/execution-manifest.json").read_bytes() == raw
    assert document["kind"] == "ACT_FIRST_EPISODE_EXECUTION_INPUTS"


def test_resigned_motion_recipe_cannot_override_retained_approved_variant(tmp_path):
    import yaml
    from so101_demo.act.execution_snapshot import verify_execution_snapshot
    from so101_demo.core.dynamic_pick import compose_pose, inverse_pose
    from so101_demo.core.dynamic_pick_policy import load_dynamic_pick_template
    document = _snapshot(tmp_path)
    root = tmp_path / "execution"
    relative = document["motion_policy_path"]
    path = root / relative
    policy = yaml.safe_load(path.read_bytes())
    policy["place"]["tcp_world_xyz_xyzw"][0] += .1
    payload = yaml.safe_dump(policy).encode()
    metadata = {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
    source_relative = "src/so101_demo_py/" + relative
    for copied in (relative, "source/" + source_relative):
        (root / copied).write_bytes(payload)
        document["files"][copied] = metadata
    document["source_files"][source_relative] = metadata
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    document["source_sha256"] = hashlib.sha256(canonical({"kind": "ACT_FIRST_EPISODE_SOURCE",
        "schema_version": 1, "files": document["source_files"]})).hexdigest()
    template = load_dynamic_pick_template(path)
    document["targets"]["final_target"] = list(compose_pose(
        template.place_tcp_world, inverse_pose(template.cup_to_tcp_grasp)).values)
    document["targets"]["place_recipe_sha256"] = metadata["sha256"]
    document["snapshot_sha256"] = hashlib.sha256(canonical({key: value for key, value in
        document.items() if key != "snapshot_sha256"})).hexdigest()
    (root / "execution-manifest.json").write_bytes(canonical(document))
    with pytest.raises(ValueError, match="EXECUTION_SNAPSHOT|DYNAMIC_POLICY_INVALID"):
        verify_execution_snapshot(root)
