"""A frozen run reads the appearance pools from the frozen execution snapshot (manifests, bound by the freeze) and verifies the INSTALLED share's
texture files against them (goal 13 defect, EXP-7033: the Teacher consumer was handed the snapshot share, which holds no generated textures).

The snapshot copies `assets/mujoco/**` of the source tree (the committed manifests and the legacy PNGs), never the 250 MB of procedural and CC0 PNGs.
The authority is the frozen pool identity (it must equal the plan's); the installed files must be the frozen manifests' files, path plus sha256."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from so101_demo.act import appearance_plan as ap
from so101_demo.act import frozen_appearance, indoor_assets
from so101_demo.ros.dynamic_frozen_policy import _frozen_teacher_source
import test_frozen_appearance as frozen_tests
from test_frozen_appearance import frozen_set, rows

TEXTURES = "assets/mujoco/textures/indoor"


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def linked_copy(source: Path, target: Path) -> Path:
    """A copy of the tree `source` whose files are symlinks (replace a file, never write through one)."""
    for path in sorted(source.rglob("*")):
        destination = target / path.relative_to(source)
        if path.is_symlink() and path.is_dir():              # the pool tree links the model asset directories of the repository
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(path.resolve())
        elif path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(path.resolve())
    return target


def replace(path: Path, payload: bytes) -> None:
    path.unlink()
    path.write_bytes(payload)


class World:
    """An installed share (the pool tree: all textures) and a frozen inputs directory whose execution snapshot has the manifests but no PNGs."""

    def __init__(self, tmp_path: Path, pool_share: Path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.share = tmp_path / "installed"
        linked_copy((pool_share / "assets/mujoco").resolve(), self.share / "assets/mujoco")
        self.root = tmp_path / "inputs"
        self.root.mkdir()
        self.snapshot = self.root / "execution"
        self.snapshot_share = self.snapshot
        for path in sorted((self.share / "assets/mujoco").resolve().rglob("*")):
            relative = path.relative_to((self.share / "assets/mujoco").resolve())
            if path.is_dir() or relative.parts[:3] in (("textures", "indoor", "proc"), ("textures", "indoor", "cc0")):
                continue
            destination = self.snapshot / "assets/mujoco" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        self.write_descriptor()
        self.act = self.snapshot / "assets/mujoco/act"

    def write_descriptor(self) -> None:
        files = {path.relative_to(self.snapshot).as_posix(): {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
                 for path in sorted(self.snapshot.rglob("*")) if path.is_file() and path.name != "execution-manifest.json"}
        self.descriptor = {"kind": "ACT_DIAGNOSTIC_EPISODE_EXECUTION_INPUTS", "files": files,
                           "snapshot_sha256": hashlib.sha256(_canonical(files)).hexdigest()}
        (self.snapshot / "execution-manifest.json").write_bytes(_canonical(self.descriptor))

    def frozen(self):
        frozen, manifest = frozen_set(self.root)
        frozen = dict(frozen, execution_snapshot={"path": "execution", "sha256": self.descriptor["snapshot_sha256"]})
        return frozen, manifest

    def installed_texture(self, name: str) -> Path:
        return self.share / TEXTURES / name


@pytest.fixture()
def world(tmp_path, indoor_pool_share, monkeypatch):
    built = World(tmp_path, indoor_pool_share)
    monkeypatch.setattr(frozen_tests, "SHARE", built.share)
    monkeypatch.setattr(frozen_tests, "NOMINAL_DIR", built.share / "assets/mujoco/act")
    return built


def test_a_snapshot_without_textures_and_an_installed_share_with_them_passes(world):
    frozen, manifest = world.frozen()
    assert not (world.snapshot / TEXTURES / "proc").exists() and not (world.snapshot / TEXTURES / "cc0").exists()
    assert (world.snapshot / TEXTURES / "proc-manifest.json").is_file() and (world.snapshot / TEXTURES / "cc0-manifest.json").is_file()
    inventory = frozen_appearance.frozen_inventory(frozen, manifest, world.share)
    assert inventory["pool_identity"] == ap.scene_inventory(world.share / "assets/mujoco/act", verify_files=True)["pool_identity"]
    kinds = set()
    for row in rows():
        entry = _frozen_teacher_source(frozen, manifest, world.snapshot_share, row["scene_id"], world.share)
        assert entry["appearance"] == ap.derive(entry["plan"], row["scene_id"], inventory)
        kinds.add(entry["appearance"]["kind"])
    assert kinds == {ap.KIND_NOMINAL, ap.KIND_RANDOMISED}                  # a nominal and a randomised scene


def test_the_episode_identity_of_a_frozen_run_is_opened_on_the_installed_share_with_the_snapshot_manifests(world, tmp_path):
    """`episode_open.appearance_arguments` (the offline processor and the episode open): `share` is the installed one, the snapshot is the frozen one."""
    from so101_demo.act import episode_open

    frozen, manifest = world.frozen()
    nominal = randomised = None
    for row in rows():
        entry = frozen_appearance.scene_entry(frozen, manifest, row["scene_id"], inventory=frozen_appearance.frozen_inventory(frozen, manifest, world.share))
        if entry["appearance"]["kind"] == ap.KIND_NOMINAL and nominal is None:
            nominal = (row["scene_id"], entry)
        if entry["appearance"]["kind"] == ap.KIND_RANDOMISED and randomised is None:
            randomised = (row["scene_id"], entry)
    for scene, entry in (nominal, randomised):
        arguments = episode_open.appearance_arguments(frozen, manifest, scene, frozen_tests.teacher_record(entry, tmp_path), share=world.share,
                                                      declared_expected=frozen_tests.NOMINAL_MODEL)
        assert arguments["scene_appearance"]["plan_sha256"] == entry["appearance"]["plan_sha256"]
    world.installed_texture("proc/wood_000.png").unlink()
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_PROC_TEXTURE_MISSING: proc/wood_000"):
        episode_open.appearance_arguments(frozen, manifest, nominal[0], frozen_tests.teacher_record(nominal[1], tmp_path), share=world.share)


def test_the_old_reader_that_verifies_the_snapshot_share_itself_cannot_pass(world):
    """The defect: files are looked for in the snapshot, which never has them."""
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_PROC_TEXTURE_MISSING"):
        ap.scene_inventory(world.act, verify_files=True)


def test_a_missing_installed_file_is_refused_with_its_code(world):
    frozen, manifest = world.frozen()
    proc = world.installed_texture("proc/wood_000.png")
    original = proc.read_bytes()
    proc.unlink()
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_PROC_TEXTURE_MISSING: proc/wood_000"):
        _frozen_teacher_source(frozen, manifest, world.snapshot_share, "p3-000", world.share)
    proc.write_bytes(original)
    cc0 = sorted((world.share / TEXTURES / "cc0").glob("*.png"))[2]
    cc0.unlink()
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_CC0_PACK_MISSING: cc0/"):
        _frozen_teacher_source(frozen, manifest, world.snapshot_share, "p3-000", world.share)


def test_a_changed_installed_byte_is_refused_with_its_code(world):
    frozen, manifest = world.frozen()
    proc = world.installed_texture("proc/wood_000.png")
    data = proc.read_bytes()
    middle = len(data) // 2
    replace(proc, data[:middle] + bytes([data[middle] ^ 0xFF]) + data[middle + 1:])
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_PROC_TEXTURE_MISMATCH: proc/wood_000"):
        frozen_appearance.frozen_inventory(frozen, manifest, world.share)
    replace(proc, data)
    frozen_appearance.frozen_inventory(frozen, manifest, world.share)
    cc0 = sorted((world.share / TEXTURES / "cc0").glob("*.png"))[0]
    replace(cc0, cc0.read_bytes() + b"\0")
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_CC0_PACK_MISMATCH: cc0/"):
        frozen_appearance.frozen_inventory(frozen, manifest, world.share)


def test_a_wrong_manifest_in_the_snapshot_is_refused(world):
    """The snapshot's manifest names other files than the installed ones (its own hash chain is consistent): path plus sha256 fails closed."""
    cc0_path = world.snapshot / TEXTURES / "cc0-manifest.json"
    manifest_document = json.loads(cc0_path.read_text())
    manifest_document["textures"][1]["sha256_resized"] = "1" * 64
    manifest_document["pack_sha256"] = indoor_assets.cc0_pack_sha256(manifest_document)
    cc0_path.write_text(json.dumps(manifest_document, sort_keys=True))
    world.write_descriptor()
    frozen, manifest = world.frozen()
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_CC0_PACK_MISMATCH"):
        frozen_appearance.frozen_inventory(frozen, manifest, world.share)


def test_a_wrong_procedural_manifest_in_the_snapshot_is_refused(world):
    proc_path = world.snapshot / TEXTURES / "proc-manifest.json"
    document = json.loads(proc_path.read_text())
    document["textures"][0]["png_sha256"] = "2" * 64
    document["textures"][0]["pixel_sha256"] = "3" * 64
    proc_path.write_text(json.dumps(document, sort_keys=True))
    world.write_descriptor()
    frozen, manifest = world.frozen()
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_PROC_TEXTURE_MISMATCH: " + document["textures"][0]["id"]):
        frozen_appearance.frozen_inventory(frozen, manifest, world.share)


def test_a_manifest_changed_after_the_freeze_is_refused(world):
    frozen, manifest = world.frozen()
    path = world.snapshot / TEXTURES / "proc-manifest.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_FROZEN_SNAPSHOT_MISMATCH"):
        frozen_appearance.frozen_inventory(frozen, manifest, world.share)
    world.write_descriptor()                                            # a descriptor that no longer is the bound one
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_FROZEN_SNAPSHOT_MISMATCH"):
        frozen_appearance.frozen_inventory(frozen, manifest, world.share)


def test_a_plan_for_other_pools_than_the_frozen_ones_is_refused(world):
    frozen, manifest = world.frozen()
    frozen_document = json.loads((world.root / frozen["scene_manifest"]["path"]).read_text())
    inventory = frozen_appearance.frozen_inventory(frozen, manifest, world.share)
    other = ap.make_plan(seed=9, nominal_share=0.25, nominal_scene_sha256=inventory["scene_sha256"],
                         pool_identity={**inventory["pool_identity"], "cc0_pack_sha256": "4" * 64})
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_POOL_IDENTITY_MISMATCH"):
        ap.derive(other, "p3-000", inventory)
    assert frozen_document["appearance_plan"]["pool_identity"] == inventory["pool_identity"]


def test_a_snapshot_path_outside_the_inputs_or_without_a_scene_is_refused(world):
    frozen, manifest = world.frozen()
    for path in ("../execution", "/etc", "", "a/../../b"):
        bad = dict(frozen, execution_snapshot={"path": path, "sha256": "0" * 64})
        with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_FROZEN_SNAPSHOT_PATH_INVALID"):
            frozen_appearance.frozen_inventory(bad, manifest, world.share)
    missing = dict(frozen, execution_snapshot={"path": "elsewhere", "sha256": "0" * 64})
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_FROZEN_SNAPSHOT_MISSING"):
        frozen_appearance.frozen_inventory(missing, manifest, world.share)


def test_a_list_without_a_snapshot_binding_is_read_from_the_installed_share_and_still_verified(world):
    frozen, manifest = world.frozen()
    plain = {key: value for key, value in frozen.items() if key != "execution_snapshot"}
    frozen_appearance.frozen_inventory(plain, manifest, world.share)
    world.installed_texture("proc/wood_000.png").unlink()
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_PROC_TEXTURE_MISSING"):
        frozen_appearance.frozen_inventory(plain, manifest, world.share)
