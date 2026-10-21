"""Mount mode: the config key, the trees' commit records, the launch argv and the container readback. Default off, image mode unchanged."""

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from so101_demo.runtime.container_campaign import mount_build as mb
from so101_demo.runtime.container_campaign.launch import ShardLaunchArgs, build_container_argv
from so101_demo.runtime.container_campaign.paths import make_campaign_paths
from so101_demo.runtime.inference import config as config_module

GPU = "GPU-28221cec-9d21-7753-fd5a-da645740df19"
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def make_trees(tmp_path, commit=COMMIT):
    root = tmp_path / "mount" / commit[:12]
    for name in ("install", "source"):
        (root / name).mkdir(parents=True)
        (root / name / "BUILD-COMMIT").write_text(commit + "\n")
    (root / "install" / "so101_demo_py").mkdir()
    return mb.MountBuild(commit=commit, root=root)


def mounted_config(tmp_path, mount):
    expected = mb.verify_records(mount)
    image = {"digest": "sha256:" + "e" * 64, **expected}
    return {"shard_image": dict(image), "head_service": {"image": dict(image)}, "teacher_service": {"image": dict(image)},
            "mount_build": mount.document()}


def test_the_key_is_absent_by_default_and_names_a_commit_and_a_root(tmp_path):
    assert mb.mount_from_config({}) is None
    mount = make_trees(tmp_path)
    assert mb.mount_from_config({"mount_build": mount.document()}) == mount
    for bad in (dict(commit="abc", root=str(mount.root)), dict(commit=COMMIT, root="relative"),
                dict(commit=COMMIT, root=str(tmp_path / "mount" / "other")), dict(commit=COMMIT, root=str(mount.root) + "/../x"),
                dict(commit=COMMIT), dict(commit=COMMIT, root=str(mount.root), extra=1)):
        with pytest.raises(ValueError):
            mb.mount_from_config({"mount_build": bad})


def test_both_trees_must_carry_the_commit_of_the_launch(tmp_path):
    mount = make_trees(tmp_path)
    hashes = mb.verify_records(mount)
    assert set(hashes) == {"package_source_sha256", "install_sha256"}
    assert hashes["install_sha256"] == hashlib.sha256((COMMIT + "\n").encode()).hexdigest()
    (mount.source / "BUILD-COMMIT").write_text("f" * 40 + "\n")
    with pytest.raises(ValueError, match="MOUNT_COMMIT_MISMATCH"):
        mb.verify_records(mount)
    (mount.source / "BUILD-COMMIT").write_text("garbage\n")
    with pytest.raises(ValueError, match="MOUNT_COMMIT_MISMATCH"):
        mb.verify_records(mount)
    (mount.source / "BUILD-COMMIT").unlink()
    with pytest.raises(ValueError, match="MOUNT_COMMIT_MISSING"):
        mb.verify_records(mount)


def test_the_three_image_records_are_the_one_base_and_the_record_hashes(tmp_path):
    mount = make_trees(tmp_path)
    config = mounted_config(tmp_path, mount)
    assert mb.verify_images(config, mount) == mb.verify_records(mount)
    for place in (("shard_image",), ("head_service", "image"), ("teacher_service", "image")):
        for field, value in (("install_sha256", "1" * 64), ("package_source_sha256", "2" * 64), ("digest", "sha256:" + "3" * 64)):
            broken = copy.deepcopy(config)
            record = broken
            for key in place:
                record = record[key]
            record[field] = value
            with pytest.raises(ValueError, match="MOUNT_IMAGE_RECORD_MISMATCH"):
                mb.verify_images(broken, mount)


def campaign_config(tmp_path, **extra):
    from test_config_identity import campaign_fixture
    return campaign_fixture(tmp_path) | extra


def test_the_campaign_config_accepts_the_key_only_with_one_base_image(tmp_path):
    mount = make_trees(tmp_path)
    document = campaign_config(tmp_path)
    document["shard_image"] = dict(document["head_service"]["image"])
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(document | {"mount_build": mount.document()}))
    assert config_module.load_campaign_config(path)["mount_build"] == mount.document()
    different = campaign_config(tmp_path, mount_build=mount.document())      # the fixture's shard image differs from its services'
    path.write_text(json.dumps(different))
    with pytest.raises(ValueError, match="CAMPAIGN_CONFIG_INVALID"):
        config_module.load_campaign_config(path)
    path.write_text(json.dumps(document))
    assert "mount_build" not in config_module.load_campaign_config(path)


def argv_fixture(tmp_path, mount):
    paths = make_campaign_paths(tmp_path, "campaign")
    spec = paths["run"] / "role.json"
    spec.write_text("{}")
    owned = paths["run"] / "wave-00" / "w00" / "g1"
    owned.mkdir(parents=True)
    (owned / "control").mkdir(mode=0o700)
    (owned / "tmp").mkdir(mode=0o700)
    sockets = paths["socket_roots"] | {"control": owned / "control"}
    entry = ShardLaunchArgs(spec=spec, mujoco_session_id="campaign-wave00-w00-g1")
    image = {"digest": "sha256:" + "e" * 64, "package_source_sha256": "c" * 64, "install_sha256": "d" * 64}
    images = {"head": image, "teacher": image, "shard": image}
    host_paths = dict(owned_root=owned, approved_inputs=(), socket_roots=sockets, config_paths=(spec,), entry=entry)
    return images, host_paths


def launch(tmp_path, mount, **changes):
    images, host_paths = argv_fixture(tmp_path, mount)
    return images, build_container_argv(role="shard", image=images, gpu_uuid=GPU, host_paths=host_paths,
        container_name="so101-campaign-w00-g1", uid=os.getuid(), gid=os.getgid(), **changes)


def test_image_mode_has_no_mount_and_is_unchanged(tmp_path):
    images, argv = launch(tmp_path, None)
    assert not [value for value in argv if "SO101_MOUNT" in value or "SO101_EXPECTED" in value or "so101-build" in value]
    assert argv[argv.index(images["shard"]["digest"]) + 1:] == ["campaign_shard", "--spec", argv[-1]]


def test_mount_mode_adds_the_two_read_only_trees_and_runs_the_bootstrap_through_the_base_interpreter(tmp_path):
    mount = make_trees(tmp_path)
    images, argv = launch(tmp_path, mount, mount_build=mount)
    mounts = [argv[i + 1] for i, value in enumerate(argv) if value == "--mount"]
    for tree in (mount.install, mount.source):
        assert f"type=bind,src={tree},dst={tree},readonly" in mounts
    environment = [argv[i + 1] for i, value in enumerate(argv) if value == "--env"]
    assert f"SO101_MOUNT_INSTALL={mount.install}" in environment and f"SO101_MOUNT_SOURCE={mount.source}" in environment
    assert f"SO101_EXPECTED_COMMIT={COMMIT}" in environment
    profile = f"FASTRTPS_DEFAULT_PROFILES_FILE={mount.install}/so101_demo_py/share/so101_demo_py/config/dds/fastdds-collection.xml"
    assert environment.count(profile) == 1
    tail = argv[argv.index(images["shard"]["digest"]) + 1:]
    assert tail[:5] == ["/act/venv/bin/python", "-I", "-B", "-m", "so101_demo.runtime.container_campaign.image_bootstrap"]
    assert tail[5] == "campaign_shard"
    for flag in ("--read-only", "--cap-drop", "--security-opt"):
        assert flag in argv
    assert argv[argv.index("--network") + 1] == "none"


def test_an_input_inside_the_mounted_root_is_refused(tmp_path):
    mount = make_trees(tmp_path)
    images, host_paths = argv_fixture(tmp_path, mount)
    inside = mount.source / "BUILD-COMMIT"
    with pytest.raises(ValueError, match="CONTAINER_LAUNCH_INVALID"):
        build_container_argv(role="shard", image=images, gpu_uuid=GPU, host_paths=dict(host_paths, approved_inputs=(inside,)),
            container_name="x", uid=os.getuid(), gid=os.getgid(), mount_build=mount)


def test_the_bootstrap_derives_the_role_from_the_program_in_mount_mode(tmp_path, monkeypatch, capsys):
    from so101_demo.runtime.container_campaign import image_bootstrap

    mount = make_trees(tmp_path)
    monkeypatch.setenv("SO101_MOUNT_INSTALL", str(mount.install))
    roles, executed = [], []
    monkeypatch.setattr(image_bootstrap, "read_mounted_image", lambda role: roles.append(role) or {"ok": 1})
    monkeypatch.setattr(image_bootstrap.os, "execv", lambda exe, args: executed.append(args))
    monkeypatch.setattr(image_bootstrap.sys, "executable", "/act/venv/bin/python")
    assert image_bootstrap.main(["campaign_processor", "--spec", "x"]) == 0
    assert image_bootstrap.main(["campaign_inference", "--config", "y"]) == 0
    assert roles == ["shard", "inference"]
    assert executed[0] == ["/act/venv/bin/python", "-I", "-B", "-m", "so101_demo.cli.campaign_processor", "--spec", "x"]
    assert image_bootstrap.main(["not_a_program"]) == 2
    assert image_bootstrap.main([]) == 2


def test_the_mounted_readback_reports_the_commit_and_the_record_hashes(tmp_path, monkeypatch):
    from so101_demo.runtime.container_campaign import provenance

    mount = make_trees(tmp_path)
    monkeypatch.setenv("SO101_MOUNT_INSTALL", str(mount.install))
    monkeypatch.setenv("SO101_MOUNT_SOURCE", str(mount.source))
    monkeypatch.setenv("SO101_EXPECTED_COMMIT", COMMIT)
    seen = {}

    def fake_readback(contract, install_root="/act/install"):
        seen.update(contract=contract, install_root=install_root)
        return dict(interpreter="/act/venv/bin/python", dependencies={"torch": "1"},
                    module_origins={name: str(mount.install / "so101_demo_py" / "x.py") for name in contract["module_origins"]},
                    package_prefixes={name: str(mount.install / name) for name in contract["package_prefixes"]})

    monkeypatch.setattr(provenance, "runtime_readback", fake_readback)
    report = provenance.read_mounted_image("shard")
    assert report["git_commit"] == COMMIT and report["submodules"] == {}
    assert report["install_sha256"] == mb.record_sha256(mount.install) and report["package_source_sha256"] == mb.record_sha256(mount.source)
    assert seen["install_root"] == str(mount.install) and set(seen["contract"]["module_origins"]) == {"so101_demo", "so101_teleop", "so101_quik"}
    provenance._report(report, str(mount.install))
    assert set(provenance.read_mounted_image("inference")["runtime"]["module_origins"]) == {"so101_demo"}
    (mount.source / "BUILD-COMMIT").write_text("f" * 40 + "\n")
    with pytest.raises(ValueError):
        provenance.read_mounted_image("shard")



# ---- identity, preflight, recompute and merge --------------------------------------------------------------------------------

def preflight(mount, image, **changes):
    record = {"schema_version": 1, "kind": "MOUNT_PREFLIGHT", "result": "PASS", "commit": mount["commit"], "base_image_id": image["digest"],
              "base_manifest_sha256": "9" * 64, "install_record_sha256": image["install_sha256"], "must_failures": 0, "warnings": 3,
              "exceptions": {"libqt5core5t64": "esm"}, "host": "antzb"}
    return record | changes


def identity_parts(tmp_path):
    mount = make_trees(tmp_path)
    config = mounted_config(tmp_path, mount)
    return mount, config["shard_image"], config


def test_the_preflight_must_pass_for_this_commit_and_this_base_image(tmp_path):
    mount, image, _config = identity_parts(tmp_path)
    assert mb.preflight_problem(preflight(mount.document(), image), mount.document(), image) is None
    for change in (dict(result="FAIL"), dict(must_failures=1), dict(commit="f" * 40), dict(base_image_id="sha256:" + "0" * 64),
                   dict(install_record_sha256="0" * 64), dict(kind="OTHER"), dict(base_manifest_sha256="short"), dict(warnings="3")):
        assert mb.preflight_problem(preflight(mount.document(), image, **change), mount.document(), image) is not None, change
    assert mb.preflight_problem({"result": "PASS"}, mount.document(), image) == "shape"


def test_a_start_reads_the_record_beside_the_evidence_root(tmp_path):
    mount, image, config = identity_parts(tmp_path)
    config["evidence_root"] = str(tmp_path)
    with pytest.raises(ValueError, match="MOUNT_PREFLIGHT_MISSING"):
        mb.read_preflight(tmp_path, mount, config)
    path = mb.preflight_path(tmp_path, mount)
    assert path.name == "mount-preflight-" + COMMIT[:12] + ".json"
    path.write_text(json.dumps(preflight(mount.document(), image, result="FAIL", must_failures=20)))
    with pytest.raises(ValueError, match="MOUNT_PREFLIGHT_REFUSED"):
        mb.read_preflight(tmp_path, mount, config)
    path.write_text(json.dumps(preflight(mount.document(), image)))
    payload, record = mb.read_preflight(tmp_path, mount, config)
    assert record["result"] == "PASS" and json.loads(payload) == record


def test_the_contract_identity_accepts_a_valid_mount_key_and_refuses_a_malformed_one(tmp_path):
    from so101_demo.act.parallel_collection_contracts import validate_controlled_identity

    mount, image, _config = identity_parts(tmp_path)
    identity = dict(source_sha256="1" * 64, runtime_config_sha256="2" * 64, collection_config_sha256="3" * 64,
                    contact_policy_fingerprint="4" * 64, gpu_uuid=GPU, image_source_install=dict(inference=image, shard=image))
    validate_controlled_identity(identity)
    assert validate_controlled_identity(identity | dict(mount_build=mount.document()))["mount_build"] == mount.document()
    with pytest.raises(ValueError):
        validate_controlled_identity(identity | dict(mount_build=dict(commit="short", root="/x")))


def provenance_document(mount, image, **changes):
    runtime = dict(interpreter="/act/venv/bin/python", dependencies={"torch": "1"},
                   module_origins={"so101_demo": str(mount.install / "so101_demo_py" / "x.py")},
                   package_prefixes={"so101_demo_py": str(mount.install / "so101_demo_py")})
    report = dict(schema_version=1, kind="ACT_CONTAINER_IMAGE_READBACK", package_source_sha256=image["package_source_sha256"],
                  install_sha256=image["install_sha256"], git_commit=mount.commit, submodules={}, runtime=runtime)
    return dict(container_id="a" * 64, image_digest=image["digest"], provenance=report, mount_build=mount.document()) | changes


def test_recompute_accepts_a_mounted_readback_of_the_identity_and_refuses_the_others(tmp_path):
    from so101_demo.act.collection_qualification_recompute import _image_problem

    mount, image, _config = identity_parts(tmp_path)
    document = provenance_document(mount, image)
    assert _image_problem(document, image, mount.document()) is False
    wrong_commit = copy.deepcopy(document)
    wrong_commit["provenance"]["git_commit"] = "f" * 40
    assert _image_problem(wrong_commit, image, mount.document()) is True
    assert _image_problem(dict(document, mount_build=None), image, mount.document()) is True
    assert _image_problem({k: v for k, v in document.items() if k != "mount_build"}, image, mount.document()) is True
    assert _image_problem(document, image, None) is True          # a mount record under an image identity
    outside = copy.deepcopy(document)
    outside["provenance"]["runtime"]["module_origins"]["so101_demo"] = "/elsewhere/x.py"
    assert _image_problem(outside, image, mount.document()) is True
    assert _image_problem(dict(document, image_digest="sha256:" + "0" * 64), image, mount.document()) is True


def merge_item(tmp_path, name, mount, image, record):
    root = tmp_path / name
    (root / "host").mkdir(parents=True)
    if record is not None:
        (root / "host" / "mount-preflight.json").write_text(json.dumps(record))
    return dict(name=name, run_root=root)


def test_the_merge_requires_the_same_checked_base_manifest_from_every_mounted_source(tmp_path):
    from so101_demo.act.collection_merge import MergeRefused, _mount_preflights

    mount, image, _config = identity_parts(tmp_path)
    reference = dict(mount_build=mount.document(), image_source_install=dict(inference=image, shard=image))
    good = [merge_item(tmp_path, "a", mount, image, preflight(mount.document(), image)),
            merge_item(tmp_path, "b", mount, image, preflight(mount.document(), image, host="ai-station"))]
    found = _mount_preflights(good, reference)
    assert set(found) == {"a", "b"} and found["b"]["host_label"] == "ai-station"
    different = [good[0], merge_item(tmp_path, "c", mount, image, preflight(mount.document(), image, base_manifest_sha256="8" * 64))]
    with pytest.raises(MergeRefused, match="different base image manifests"):
        _mount_preflights(different, reference)
    with pytest.raises(MergeRefused, match="MERGE_MOUNT_PREFLIGHT_MISSING"):
        _mount_preflights([good[0], merge_item(tmp_path, "d", mount, image, None)], reference)
    with pytest.raises(MergeRefused, match="MERGE_MOUNT_PREFLIGHT_REFUSED"):
        _mount_preflights([good[0], merge_item(tmp_path, "e", mount, image, preflight(mount.document(), image, result="FAIL"))], reference)
    assert _mount_preflights([merge_item(tmp_path, "f", mount, image, None)], dict(image_source_install={})) is None
    with pytest.raises(MergeRefused, match="MERGE_IDENTITY_MISMATCH"):
        _mount_preflights(good[:1], dict(image_source_install={}))


def test_the_shard_shell_takes_the_mounted_package_prefix_and_the_base_ros2(tmp_path, monkeypatch):
    from so101_demo.cli import campaign_shard

    spec = {"owned_root": str(tmp_path)}
    monkeypatch.delenv("SO101_MOUNT_INSTALL", raising=False)
    image_layout = campaign_shard.container_layout(spec)
    assert (image_layout.install_prefix, image_layout.ros2_executable) == (Path("/act/install"), Path("/act/install/bin/ros2"))
    mount = make_trees(tmp_path)
    monkeypatch.setenv("SO101_MOUNT_INSTALL", str(mount.install))
    layout = campaign_shard.container_layout(spec)
    assert layout.install_prefix == mount.install / "so101_demo_py" and layout.ros2_executable == Path("/opt/ros/jazzy/bin/ros2")
    assert layout.output_root == image_layout.output_root and layout.control_root == image_layout.control_root

