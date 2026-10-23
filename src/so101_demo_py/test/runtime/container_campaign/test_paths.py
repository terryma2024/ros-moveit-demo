"""Catch root drift, run reuse, and broad or writable input mounts."""

import importlib
import os
from pathlib import Path

import pytest


def paths_module():
    return importlib.import_module("so101_demo.runtime.container_campaign.paths")


def registered(root):
    return {"path": str(root), "uid": os.getuid(), "gid": os.getgid()}


@pytest.mark.parametrize("machine", ["station", "mac"])
def test_new_run_uses_registered_absolute_root_without_rewriting_inputs(tmp_path, machine):
    root = tmp_path / machine
    root.mkdir()
    validated = paths_module().validate_registered_evidence_root(str(root), str(root), registration=registered(root))
    paths = paths_module().make_campaign_paths(validated, "run-new")
    assert paths["run"] == root / "run-new"
    assert paths["host"] == root / "run-new" / "host"
    input_file = tmp_path / "original.json"
    input_file.write_bytes(b'{"path":"/original/source","sha256":"original"}\n')
    shard = paths["run"] / "wave-00" / "w00" / "g1"
    shard.mkdir(parents=True)
    control = shard / "control"
    control.mkdir()
    sockets = paths["socket_roots"] | {"control": control}
    mounts = paths_module().build_role_mounts("shard", owned_root=shard,
        approved_inputs=(input_file,), socket_roots=sockets, config_paths=())
    evidence = [mount for mount in mounts if mount.purpose == "evidence"]
    assert [(mount.source, mount.target, mount.read_only) for mount in evidence] == [(shard, shard, False)]
    inputs = [mount for mount in mounts if mount.purpose == "input"]
    assert [(mount.source, mount.target, mount.read_only) for mount in inputs] == [(input_file, input_file, True)]
    assert inputs[0].target.read_bytes() == b'{"path":"/original/source","sha256":"original"}\n'
    with pytest.raises(ValueError, match="CAMPAIGN_RUN_EXISTS"):
        paths_module().make_campaign_paths(validated, "run-new")


@pytest.mark.parametrize("problem", ["payload", "registration", "owner", "relative", "symlink"])
def test_root_rejects_mismatch_unknown_owner_and_escape(tmp_path, problem):
    root = tmp_path / "root"
    root.mkdir()
    config, payload, registration = str(root), str(root), registered(root)
    if problem == "payload": payload = str(tmp_path)
    elif problem == "registration": registration["path"] = str(tmp_path)
    elif problem == "owner": registration["uid"] = os.getuid() + 1
    elif problem == "relative": config = payload = "root"
    elif problem == "symlink":
        link = tmp_path / "linked"
        link.symlink_to(root, target_is_directory=True)
        config = payload = registration["path"] = str(link)
    with pytest.raises(ValueError, match="REGISTERED_EVIDENCE_ROOT_INVALID"):
        paths_module().validate_registered_evidence_root(config, payload, registration=registration)


@pytest.mark.parametrize("role", ["head", "teacher"])
def test_services_mount_only_own_logs_socket_and_approved_inputs(tmp_path, role):
    paths = paths_module().make_campaign_paths(tmp_path, "run-new")
    weights = tmp_path / (role + ".pt")
    weights.write_bytes(b"weights")
    mounts = paths_module().build_role_mounts(role, owned_root=paths["services"][role],
        approved_inputs=(weights,), socket_roots=paths["socket_roots"], config_paths=())
    assert all(mount.purpose != "evidence" for mount in mounts)
    assert all(mount.source != paths["host"] for mount in mounts)
    assert [(m.source, m.target) for m in mounts if m.purpose == "ipc"] == [
        (paths["socket_roots"][role], Path("/act/ipc"))]


@pytest.mark.parametrize("problem", ["root_input", "host_input", "wrong_owned", "symlink_input", "unknown_role"])
def test_broad_root_host_journal_and_wrong_role_are_not_mountable(tmp_path, problem):
    paths = paths_module().make_campaign_paths(tmp_path, "run-new")
    file = tmp_path / "config.json"
    file.write_text("{}")
    inputs, role, owned = (file,), "head", paths["services"]["head"]
    if problem == "root_input": inputs = (tmp_path,)
    elif problem == "host_input": inputs = (paths["host"],)
    elif problem == "wrong_owned": owned = paths["run"]
    elif problem == "symlink_input":
        link = tmp_path / "linked.json"
        link.symlink_to(file)
        inputs = (link,)
    elif problem == "unknown_role": role = "broker"
    with pytest.raises(ValueError, match="ROLE_MOUNT_INVALID"):
        paths_module().build_role_mounts(role, owned_root=owned,
            approved_inputs=inputs, socket_roots=paths["socket_roots"], config_paths=())


def test_frozen_config_inside_run_can_be_mounted_without_exposing_private_evidence(tmp_path):
    paths = paths_module().make_campaign_paths(tmp_path, "run-new")
    config = paths["run"] / "campaign.json"
    config.write_bytes(b"frozen-config")
    mounts = paths_module().build_role_mounts("head", owned_root=paths["services"]["head"],
        approved_inputs=(), socket_roots=paths["socket_roots"], config_paths=(config,))
    assert [(m.source, m.target, m.read_only) for m in mounts if m.purpose == "input"] == [
        (config, config, True)]


def test_other_shard_evidence_cannot_be_disguised_as_approved_input(tmp_path):
    paths = paths_module().make_campaign_paths(tmp_path, "run-new")
    private = paths["run"] / "wave-00" / "w01" / "g1"
    private.mkdir(parents=True)
    evidence = private / "episode.json"
    evidence.write_text("{}")
    with pytest.raises(ValueError, match="ROLE_MOUNT_INVALID"):
        paths_module().build_role_mounts("head", owned_root=paths["services"]["head"],
            approved_inputs=(evidence,), socket_roots=paths["socket_roots"], config_paths=())
