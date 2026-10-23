"""Launch only fixed role images with private mounts and namespace boundaries."""

import importlib
import os
from pathlib import Path

import pytest

from so101_demo.runtime.container_campaign.paths import make_campaign_paths

#: The retired per-worker field; built from fragments so the source-tree absence test keeps matching nothing.
NS_FIELD = "ros" + "_namespace"


GPU = "GPU-28221cec-9d21-7753-fd5a-da645740df19"


def fixture(tmp_path, role):
    module = importlib.import_module("so101_demo.runtime.container_campaign.launch")
    paths = make_campaign_paths(tmp_path, "campaign")
    config = paths["run"] / "role.json"
    config.write_text("{}")
    weights = tmp_path / "weights.pt"
    weights.write_bytes(b"weights")
    sockets = paths["socket_roots"].copy()
    if role == "shard":
        owned = paths["run"] / "wave-00" / "w00" / "g1"
        owned.mkdir(parents=True)
        (owned / "control").mkdir(mode=0o700)
        sockets["control"] = owned / "control"
        entry = module.ShardLaunchArgs(spec=config, mujoco_session_id="campaign-wave00-w00-g1")
    else:
        owned = paths["services"][role]
        descriptor = paths["run"] / "head-descriptor.json"
        descriptor.write_text("{}")
        import hashlib
        entry = module.InferenceLaunchArgs(config=config, generation="campaign-head-g1",
            startup_deadline_monotonic_ns=123456, receive_budget_s=0.5,
            head_descriptor=descriptor if role == "head" else None,
            head_descriptor_sha256=hashlib.sha256(descriptor.read_bytes()).hexdigest() if role == "head" else None)
    (owned / "tmp").mkdir(mode=0o700)
    images = {name: dict(digest="sha256:"+digest*64,
        package_source_sha256="c"*64, install_sha256="d"*64)
        for name, digest in (("head", "a"), ("teacher", "a"), ("shard", "b"))}
    inputs = (weights,)
    configs = (config, entry.head_descriptor) if role == "head" else (config,)
    host_paths = dict(owned_root=owned, approved_inputs=inputs, socket_roots=sockets,
                      config_paths=configs, entry=entry)
    return module, images, host_paths


def build(module, images, paths, role="shard", **changes):
    kwargs = dict(role=role, image=images, gpu_uuid=GPU, host_paths=paths,
                  container_name="so101-campaign-w00-g1", uid=os.getuid(), gid=os.getgid())
    kwargs.update(changes)
    return module.build_container_argv(**kwargs)


@pytest.mark.parametrize("role", ["head", "teacher", "shard"])
def test_only_shards_are_raised_in_the_kernel_oom_order(tmp_path, role):
    module, images, paths = fixture(tmp_path, role)
    argv = build(module, images, paths, role)
    if role != "shard":
        assert not any(value.startswith("--oom") for value in argv)   # services keep the default
        return
    assert argv.count("--oom-score-adj") == 1
    adjustment = int(argv[argv.index("--oom-score-adj")+1])
    assert adjustment == module.SHARD_OOM_SCORE_ADJ == 900
    assert 500 <= adjustment < 1000          # above other user processes and the default 0, below the kernel's maximum
    assert argv.index("--oom-score-adj") < argv.index(images["shard"]["digest"])   # a docker option, not a container command
    assert not any(value.startswith("--memory") for value in argv)   # no memory limit chosen


@pytest.mark.parametrize("role", ["head", "teacher", "shard"])
def test_fixed_image_private_namespaces_and_mounts(tmp_path, role):
    module, images, paths = fixture(tmp_path, role)
    argv = build(module, images, paths, role)
    assert argv[:3] == ["docker", "run", "--detach"]
    assert argv[argv.index("--gpus")+1] == "device="+GPU
    assert argv[argv.index("--user")+1] == f"{os.getuid()}:{os.getgid()}"
    assert argv[argv.index("--network")+1] == "none"
    assert argv[argv.index("--ipc")+1] == "private"
    assert argv[argv.index("--restart")+1] == "no"
    assert "--read-only" in argv
    assert not {"--privileged", "--pid", "--rm", "--entrypoint", "--volume"}.intersection(argv)
    digest_index = argv.index(images[role]["digest"])
    assert argv[digest_index+1] == "campaign_shard" if role == "shard" else argv[digest_index+1] == "campaign_inference"
    mounts = [argv[i+1] for i, value in enumerate(argv) if value == "--mount"]
    owned = str(paths["owned_root"])
    assert f"type=bind,src={owned},dst={owned}" in mounts
    assert f"type=bind,src={paths['config_paths'][0]},dst={paths['config_paths'][0]},readonly" in mounts
    assert not any("docker.sock" in mount or "dst=/act/source" in mount or "dst=/act/install" in mount for mount in mounts)
    environment = [argv[index+1] for index,value in enumerate(argv) if value == '--env']
    assert 'ROS_HOME='+str(paths['owned_root']/'tmp/ros-home') in environment
    assert 'XDG_CONFIG_HOME='+str(paths['owned_root']/'tmp/config') in environment
    assert 'MPLCONFIGDIR='+str(paths['owned_root']/'tmp/matplotlib') in environment
    if role == "shard":
        assert any("dst=/act/control" in mount for mount in mounts)
        assert all(any(f"dst=/act/ipc/{name},readonly" in mount for mount in mounts) for name in ("head", "teacher"))
        env = [argv[i+1] for i, value in enumerate(argv) if value == "--env"]
        # the fixed identity: one domain for every shard, no namespace, localhost-only discovery; the container is the isolation
        assert env.count("ROS_DOMAIN_ID=181") == 1 and not [item for item in env if item.startswith("ROS_NAMESPACE")]
        assert "SO101_MUJOCO_SESSION_ID=campaign-wave00-w00-g1" in env
        assert "ROS_LOCALHOST_ONLY=1" in env and "ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST" in env and "MUJOCO_GL=egl" in env
        # the Fast DDS collection profile at its in-image install path; QoS-from-XML is never switched on
        assert env.count("FASTRTPS_DEFAULT_PROFILES_FILE=/act/install/share/so101_demo_py/config/dds/fastdds-collection.xml") == 1
        assert not [item for item in env if item.startswith("RMW_FASTRTPS_USE_QOS_FROM_XML")]
    else:
        # the Teacher (head) and the processor join no ROS graph and get no DDS profile
        assert not [item for item in environment if item.startswith(("FASTRTPS", "RMW_"))]
        assert len([mount for mount in mounts if "dst=/act/ipc" in mount]) == 1
        assert not any("wave-00" in mount or "dst=/act/control" in mount for mount in mounts)


@pytest.mark.parametrize("problem", ["role", "gpu", "root_user", "bool_uid", "name", "different_head_image", "image_tag", "extra_image", "host_mount", "arbitrary_command", "missing_config", "missing_temp"])
def test_launch_rejects_unbound_image_mount_gpu_or_entry(tmp_path, problem):
    module, images, paths = fixture(tmp_path, "shard")
    changes = {}
    if problem == "role": changes["role"] = "broker"
    elif problem == "gpu": changes["gpu_uuid"] = "all"
    elif problem == "root_user": changes["uid"] = 0
    elif problem == "bool_uid": changes["uid"] = True
    elif problem == "name": changes["container_name"] = "--privileged"
    elif problem == "different_head_image": images["teacher"] = images["shard"]
    elif problem == "image_tag": images["shard"]["digest"] = "image:latest"
    elif problem == "extra_image": images["unknown"] = images["shard"]
    elif problem == "host_mount": paths["approved_inputs"] = (paths["owned_root"].parents[2]/"host",)
    elif problem == "arbitrary_command": paths["entry"] = ["bash", "-c", "anything"]
    elif problem == "missing_config": paths["config_paths"] = ()
    elif problem == "missing_temp": paths["owned_root"] = paths["owned_root"]/"tmp"
    with pytest.raises(ValueError, match="CONTAINER_LAUNCH_INVALID"):
        build(module, images, paths, **changes)


def test_shard_isolation_is_the_container_alone_in_every_launch(tmp_path):
    """Identical ROS identity in every shard is safe only while the network and IPC namespaces are private."""
    module, images, paths = fixture(tmp_path, "shard")
    argv = build(module, images, paths)
    assert argv.count("--network") == 1 and argv[argv.index("--network")+1] == "none"
    assert argv.count("--ipc") == 1 and argv[argv.index("--ipc")+1] == "private"
    assert not {"--pid", "--uts", "--userns", "--cgroupns", "--net", "--publish", "-p", "--add-host"}.intersection(argv)
    assert not any(value.startswith(("--network=", "--ipc=", "--pid=")) for value in argv)
    assert not any("/dev/shm" in value or "docker.sock" in value for value in argv)
    environment = [argv[i+1] for i, value in enumerate(argv) if value == "--env"]
    assert "ROS_LOCALHOST_ONLY=1" in environment and "ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST" in environment


@pytest.mark.parametrize("extra", [dict(ros_domain_id=181), {NS_FIELD: "/act/campaign/w00"}])
def test_a_shard_entry_no_longer_carries_a_domain_or_namespace(tmp_path, extra):
    module, _images, paths = fixture(tmp_path, "shard")
    with pytest.raises(TypeError):
        module.ShardLaunchArgs(spec=paths["entry"].spec, mujoco_session_id="campaign-wave00-w00-g1", **extra)


@pytest.mark.parametrize("problem", ["session", "relative_spec"])
def test_shard_identity_is_explicit_and_closed(tmp_path, problem):
    module, _images, paths = fixture(tmp_path, "shard")
    kwargs = dict(spec=paths["entry"].spec, mujoco_session_id="campaign-wave00-w00-g1")
    if problem == "session": kwargs["mujoco_session_id"] = "../other"
    elif problem == "relative_spec": kwargs["spec"] = Path("spec.json")
    with pytest.raises(ValueError, match="CONTAINER_LAUNCH_INVALID"):
        module.ShardLaunchArgs(**kwargs)
