"""The processor role (phase 2): the shard image without a GPU, Teacher socket or ROS identity, reading assigned phase-1 attempts."""

import os
from pathlib import Path

import pytest

from so101_demo.runtime.container_campaign import launch as launch_module
from so101_demo.runtime.container_campaign.launch import ProcessorLaunchArgs, build_container_argv
from so101_demo.runtime.container_campaign.paths import build_role_mounts, make_campaign_paths

ATTEMPT = "wave-0/w01/g1/output/tasks/task-1/attempts/scene-01/scene-01-lease-1/sealed"


def fixture(tmp_path):
    paths = make_campaign_paths(tmp_path, "campaign")
    run = paths["run"]
    owned = run / "processing" / "p00" / "g1"
    for name in ("tmp", "control", "output", "task-inputs"):
        (owned / name).mkdir(parents=True, mode=0o700)
    attempt = run / ATTEMPT
    attempt.mkdir(parents=True)
    spec = run / "processor-p00-g1.json"
    spec.write_text("{}")
    weights = tmp_path / "inputs-manifest.json"
    weights.write_text("{}")
    images = {name: dict(digest="sha256:" + digest * 64, package_source_sha256="c" * 64, install_sha256="d" * 64)
              for name, digest in (("head", "a"), ("teacher", "a"), ("shard", "b"))}
    host_paths = dict(owned_root=owned, approved_inputs=(weights,), socket_roots={"control": owned / "control"},
                      config_paths=(spec,), entry=ProcessorLaunchArgs(spec=spec), phase1_attempts=(attempt,),
                      processing_root=run / "processing")
    return paths, images, host_paths, attempt


def build(images, host_paths, **changes):
    kwargs = dict(role="processor", image=images, gpu_uuid=None, host_paths=host_paths,
                  container_name="so101-act-p00-g1", uid=os.getuid(), gid=os.getgid())
    kwargs.update(changes)
    return build_container_argv(**kwargs)


def mounts_of(argv):
    return [argv[i + 1] for i, value in enumerate(argv) if value == "--mount"]


def test_processor_argv_has_no_gpu_teacher_socket_or_ros_identity(tmp_path):
    paths, images, host_paths, attempt = fixture(tmp_path)
    argv = build(images, host_paths)
    assert argv[:3] == ["docker", "run", "--detach"]
    assert "--gpus" not in argv
    assert argv[argv.index("--network") + 1] == "none" and argv[argv.index("--ipc") + 1] == "private"
    assert "--read-only" in argv and argv[argv.index("--cap-drop") + 1] == "ALL"
    assert argv[argv.index("--restart") + 1] == "no" and argv[argv.index("--security-opt") + 1] == "no-new-privileges"
    assert not {"--privileged", "--pid", "--rm", "--entrypoint", "--volume"}.intersection(argv)
    assert argv[argv.index("--oom-score-adj") + 1] == str(launch_module.SHARD_OOM_SCORE_ADJ) == "900"
    assert argv[argv.index("--oom-score-adj")] != argv[-1]
    digest = images["shard"]["digest"]
    assert argv[-3:] == ["campaign_processor", "--spec", str(host_paths["entry"].spec)]
    assert argv[-4] == digest and digest != images["teacher"]["digest"], "the processor runs the shard image"
    environment = [argv[i + 1] for i, value in enumerate(argv) if value == "--env"]
    assert not [item for item in environment if item.startswith(("ROS_DOMAIN_ID", "ROS_NAMESPACE", "ROS_LOCALHOST", "ROS_AUTOMATIC", "SO101_MUJOCO", "NVIDIA", "MUJOCO_GL"))]
    assert "TMPDIR=" + str(host_paths["owned_root"] / "tmp") in environment
    assert not any("/act/ipc" in mount or "inference.sock" in mount for mount in mounts_of(argv))


def test_processor_mounts_assigned_attempts_read_only_and_one_writable_output_tree(tmp_path):
    paths, images, host_paths, attempt = fixture(tmp_path)
    run, owned = paths["run"], host_paths["owned_root"]
    mounts = mounts_of(build(images, host_paths))
    assert f"type=bind,src={attempt},dst={attempt},readonly" in mounts
    assert f"type=bind,src={run / 'processing'},dst={run / 'processing'}" in mounts
    assert f"type=bind,src={owned},dst={owned}" in mounts
    assert f"type=bind,src={owned / 'control'},dst=/act/control" in mounts
    writable = [mount for mount in mounts if not mount.endswith(",readonly")]
    assert {mount.split(",")[1][4:] for mount in writable} == {str(owned), str(run / "processing"), str(owned / "control")}
    assert not any(str(run / "host") in mount or str(run / "wave-0") + "," in mount for mount in mounts)
    assert any(mount.endswith("inputs-manifest.json,readonly") for mount in mounts)


def test_build_role_mounts_purposes(tmp_path):
    paths, images, host_paths, attempt = fixture(tmp_path)
    mounts = build_role_mounts("processor", owned_root=host_paths["owned_root"], approved_inputs=host_paths["approved_inputs"],
                               socket_roots=host_paths["socket_roots"], config_paths=host_paths["config_paths"],
                               phase1_attempts=(attempt,), processing_root=paths["run"] / "processing")
    assert {mount.purpose for mount in mounts} == {"evidence", "processing_output", "phase1_attempt", "input", "control"}
    assert [mount.read_only for mount in mounts if mount.purpose == "phase1_attempt"] == [True]


@pytest.mark.parametrize("problem", [
    "gpu", "attempt_not_sealed", "attempt_in_host", "attempt_wave_root", "attempt_other_run", "attempt_symlink",
    "attempts_missing", "processing_root_other", "input_under_processing", "input_under_wave", "shard_args",
    "wrong_owned", "attempt_duplicate", "task_output_for_processor"])
def test_processor_refusals(tmp_path, problem):
    paths, images, host_paths, attempt = fixture(tmp_path)
    run = paths["run"]
    if problem == "gpu":
        with pytest.raises(ValueError, match="CONTAINER_LAUNCH_INVALID"):
            build(images, host_paths, gpu_uuid="GPU-28221cec-9d21-7753-fd5a-da645740df19")
        return
    if problem == "attempt_not_sealed":
        host_paths["phase1_attempts"] = (attempt.parent,)
    elif problem == "attempt_in_host":
        host_paths["phase1_attempts"] = (paths["host"],)
    elif problem == "attempt_wave_root":
        host_paths["phase1_attempts"] = (run / "wave-0",)
    elif problem == "attempt_other_run":
        (tmp_path / "x").mkdir()
        other = make_campaign_paths(tmp_path / "x", "other")["run"] / ATTEMPT
        other.mkdir(parents=True)
        host_paths["phase1_attempts"] = (other,)
    elif problem == "attempt_symlink":
        link = run / "wave-0/w01/g1/output/tasks/task-1/attempts/scene-01/linked-lease/sealed"
        link.parent.mkdir(parents=True)
        link.symlink_to(attempt, target_is_directory=True)
        host_paths["phase1_attempts"] = (link,)
    elif problem == "attempts_missing":
        host_paths["phase1_attempts"] = None
    elif problem == "processing_root_other":
        host_paths["processing_root"] = run
    elif problem == "input_under_processing":
        host_paths["approved_inputs"] = (host_paths["owned_root"] / "task-inputs",)
    elif problem == "input_under_wave":
        host_paths["approved_inputs"] = (attempt,)
    elif problem == "shard_args":
        host_paths["entry"] = launch_module.ShardLaunchArgs(spec=host_paths["entry"].spec, mujoco_session_id="session")
    elif problem == "wrong_owned":
        wrong = run / "processing" / "w00" / "g1"
        for name in ("tmp", "control"):
            (wrong / name).mkdir(parents=True)
        host_paths["owned_root"] = wrong
        host_paths["socket_roots"] = {"control": wrong / "control"}
    elif problem == "attempt_duplicate":
        host_paths["phase1_attempts"] = (attempt, attempt)
    elif problem == "task_output_for_processor":
        with pytest.raises(ValueError, match="ROLE_MOUNT_INVALID"):
            build_role_mounts("processor", owned_root=host_paths["owned_root"], approved_inputs=(), socket_roots=host_paths["socket_roots"],
                              config_paths=(), task_output_root=host_paths["owned_root"] / "output",
                              phase1_attempts=(attempt,), processing_root=run / "processing")
        return
    with pytest.raises(ValueError, match="CONTAINER_LAUNCH_INVALID"):
        build(images, host_paths)


def test_other_roles_cannot_mount_phase1_attempts_or_processing(tmp_path):
    paths = make_campaign_paths(tmp_path, "campaign")
    run = paths["run"]
    attempt = run / ATTEMPT
    attempt.mkdir(parents=True)
    (run / "processing").mkdir()
    weights = tmp_path / "w.pt"
    weights.write_bytes(b"w")
    for role in ("head", "teacher"):
        with pytest.raises(ValueError, match="ROLE_MOUNT_INVALID"):
            build_role_mounts(role, owned_root=paths["services"][role], approved_inputs=(weights,),
                              socket_roots=paths["socket_roots"], config_paths=(), phase1_attempts=(attempt,),
                              processing_root=run / "processing")
    for forbidden in (attempt, run / "processing"):
        with pytest.raises(ValueError, match="ROLE_MOUNT_INVALID"):
            build_role_mounts("teacher", owned_root=paths["services"]["teacher"], approved_inputs=(forbidden,),
                              socket_roots=paths["socket_roots"], config_paths=())
