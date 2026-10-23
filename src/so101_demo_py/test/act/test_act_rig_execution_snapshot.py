"""The execution snapshot, the frozen inputs and the profile identity are recorded against the scene and files of their rig."""

import hashlib
import json

import mujoco
import pytest
from paths import PACKAGE_ROOT, REPOSITORY

from so101_demo.act import execution_snapshot
from so101_demo.act.diagnostic_episode_inputs import execution_snapshot_binding, profile_config_identity
from so101_demo.act.diagnostic_episode_inspection import _compiled_model_identity, _scene_file
from so101_demo.act.rig_files import foreign_files, rig_model_files
from so101_demo.act.rig_profile import HEAD_WRIST_RIG, SIDE_WRIST_RIG, rig_from_profile_sha256

SIDE = rig_model_files(SIDE_WRIST_RIG)
HEAD = rig_model_files(HEAD_WRIST_RIG)


@pytest.fixture(scope="module")
def snapshots(tmp_path_factory):
    base = tmp_path_factory.mktemp("rig-snapshots")
    return {"head": (execution_snapshot.freeze_execution_snapshot(REPOSITORY, base / "head"), base / "head"),
            "side": (execution_snapshot.freeze_execution_snapshot(REPOSITORY, base / "side", SIDE_WRIST_RIG), base / "side")}


def test_a_snapshot_names_the_scene_of_its_rig_and_compiles_that_model(snapshots):
    head, side = snapshots["head"][0], snapshots["side"][0]
    assert head["scene_path"] == HEAD.scene == execution_snapshot.SCENE and side["scene_path"] == SIDE.scene
    assert (head["nq"], head["nv"]) == (14, 13) and (side["nq"], side["nv"]) == (13, 12)
    assert head["model_sha256"] != side["model_sha256"]
    # the cup start of the reset keyframe is the same in both scenes
    assert head["targets"]["initial_target"] == side["targets"]["initial_target"]
    assert head["targets"]["final_target"] == side["targets"]["final_target"]
    assert side["targets"]["reset_recipe_sha256"] == side["files"][SIDE.scene]["sha256"]
    assert head["targets"]["reset_recipe_sha256"] == head["files"][HEAD.scene]["sha256"]
    # the whole asset and config tree is frozen, so every rig's files are in every snapshot
    for relative in (*HEAD.exclusive, *SIDE.exclusive):
        assert relative in head["files"] and relative in side["files"], relative


def test_a_snapshot_verifies_for_its_own_rig_and_refuses_a_scene_of_no_rig(snapshots):
    for _name, (document, root) in snapshots.items():
        assert execution_snapshot.verify_execution_snapshot(root) == document
    document, root = snapshots["side"]
    forged = dict(document, scene_path="assets/mujoco/act/head_search_scene.xml")
    forged.pop("snapshot_sha256")
    forged["snapshot_sha256"] = hashlib.sha256(execution_snapshot._canonical(forged)).hexdigest()
    path = root / "execution-manifest.json"
    original = path.read_bytes()
    try:
        path.write_bytes(execution_snapshot._canonical(forged))
        with pytest.raises(ValueError, match="EXECUTION_SNAPSHOT"):
            execution_snapshot.verify_execution_snapshot(root)
    finally:
        path.write_bytes(original)


def test_the_installed_station_assets_of_a_rig_are_that_rigs_files(snapshots):
    import copy

    for name, (document, _root) in snapshots.items():
        execution_snapshot.verify_installed_station_assets(PACKAGE_ROOT, document)
        files, other = (HEAD, SIDE) if name == "head" else (SIDE, HEAD)
        # the rig's own urdf, controllers and plugin config are bound byte for byte ...
        for relative in (files.urdf, files.controllers, files.plugins):
            tampered = copy.deepcopy(document)
            tampered["files"][relative]["sha256"] = "0" * 64
            with pytest.raises(ValueError, match="EPISODE_INSTALLED_ASSET_MISMATCH: " + relative):
                execution_snapshot.verify_installed_station_assets(PACKAGE_ROOT, tampered)
        # ... and another rig's are not part of this rig's requirement
        for relative in (other.urdf, other.controllers, other.plugins):
            tampered = copy.deepcopy(document)
            tampered["files"][relative]["sha256"] = "0" * 64
            execution_snapshot.verify_installed_station_assets(PACKAGE_ROOT, tampered)


def test_the_execution_binding_reads_the_physics_chunk_config_of_the_snapshots_rig(snapshots):
    import yaml

    for name, (document, root) in snapshots.items():
        binding = execution_snapshot_binding(document, root)
        files = HEAD if name == "head" else SIDE
        plugin_bytes = (root / files.plugins).read_bytes()
        assert binding["physics_chunks"]["config_sha256"] == hashlib.sha256(plugin_bytes).hexdigest()
        params = yaml.safe_load(plugin_bytes)["/**"]["ros__parameters"]
        assert binding["physics_chunks"]["max_samples"] == params["physics_step_chunk_size"]
        assert binding["model_identity"]["nq"] == (14 if name == "head" else 13)


def test_inspection_reads_the_scene_of_the_named_rig():
    assert _scene_file(None) == "src/so101_demo_py/" + HEAD.scene
    assert _scene_file(SIDE_WRIST_RIG) == "src/so101_demo_py/" + SIDE.scene
    assert _scene_file("side-wrist") == _scene_file(SIDE_WRIST_RIG)
    head_identity, side_identity = _compiled_model_identity(REPOSITORY), _compiled_model_identity(REPOSITORY, SIDE_WRIST_RIG)
    assert head_identity["model_sha256"] != side_identity["model_sha256"]
    assert side_identity["scene_sha256"] == hashlib.sha256((PACKAGE_ROOT / SIDE.scene).read_bytes()).hexdigest()


def test_the_profile_identity_of_a_rig_leaves_out_the_files_of_the_other_rig():
    """Adding the side+wrist files changed no head+wrist identity: the head+wrist digest covers exactly what it always did."""
    package = REPOSITORY / "src/so101_demo_py"
    roots = (package / "assets/mujoco/act", package / "config/mujoco/act")
    everything = {str(path.relative_to(package)) for root in roots for path in root.rglob("*") if path.is_file()}
    assert SIDE.exclusive <= everything and HEAD.exclusive <= everything
    head_files = {path: hashlib.sha256((package / path).read_bytes()).hexdigest() for path in sorted(everything - SIDE.exclusive)}
    expected = hashlib.sha256(json.dumps(head_files, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                         allow_nan=False).encode()).hexdigest()
    assert profile_config_identity(REPOSITORY) == profile_config_identity(REPOSITORY, HEAD_WRIST_RIG) == expected
    side_files = {path: hashlib.sha256((package / path).read_bytes()).hexdigest() for path in sorted(everything - HEAD.exclusive)}
    assert profile_config_identity(REPOSITORY, SIDE_WRIST_RIG) == hashlib.sha256(json.dumps(
        side_files, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    assert profile_config_identity(REPOSITORY, SIDE_WRIST_RIG) != expected
    assert foreign_files(HEAD_WRIST_RIG) == SIDE.exclusive


def test_a_campaign_config_names_its_rig_by_the_profile_digest():
    assert rig_from_profile_sha256(None) is HEAD_WRIST_RIG
    assert rig_from_profile_sha256(HEAD_WRIST_RIG.profile_sha256) is HEAD_WRIST_RIG
    assert rig_from_profile_sha256(SIDE_WRIST_RIG.profile_sha256) is SIDE_WRIST_RIG
    with pytest.raises(ValueError, match="RIG_PROFILE_UNKNOWN"):
        rig_from_profile_sha256("0" * 64)


def test_the_model_of_the_snapshot_loads_from_the_frozen_tree_alone(snapshots):
    document, root = snapshots["side"]
    model = mujoco.MjModel.from_xml_path(str(root / document["scene_path"]))
    assert model.nq == document["nq"] and model.ncam == 3
