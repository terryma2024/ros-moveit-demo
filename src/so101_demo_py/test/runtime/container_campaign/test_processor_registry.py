"""Registry rules for the processor role: launch ids, slot reuse and a stop proof that is the container's exit alone."""

from dataclasses import asdict

import pytest

from so101_demo.runtime.container_campaign.process_identity import (
    ContainerChildBinding, ContainerOwnerKey, ProcessOwnerKey, pid_namespace_inode)
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry

DIGEST = "sha256:" + "b" * 64


def launch(tmp_path, *, worker="p00", generation=1, **changes):
    root = tmp_path / "processing" / worker / f"g{generation}"
    root.mkdir(parents=True, exist_ok=True)
    fields = dict(launch_id=f"processing-{worker}-g{generation}", role="processor", worker_id=worker, wave_id=None,
                  launch_generation=generation, container_name=f"so101-act-{worker}-g{generation}", image_digest=DIGEST,
                  owned_root=str(root), session_id=None)
    fields.update(changes)
    return ContainerLaunch(**fields)


def owner(character="a", generation=1):
    return ContainerOwnerKey(character * 64, "2026-10-12T01:02:03.123Z", DIGEST, generation)


def exited(key, *, running=False):
    return dict(Id=key.container_id, Image=key.image_digest, State=dict(StartedAt=key.docker_started_at, Running=running,
                Restarting=False, Pid=500 if running else 0, Status="running" if running else "exited", ExitCode=0))


def test_processor_launch_record_shape(tmp_path):
    item = launch(tmp_path)
    assert item.role == "processor" and item.launcher == "container"
    for changes in (dict(worker_id="w00", launch_id="processing-w00-g1"), dict(worker_id=None),
                    dict(wave_id="wave-0"), dict(session_id="session"), dict(launch_id="wave-0-p00-g1"),
                    dict(launch_id="processing-p00-g2"), dict(launcher="native", container_name=None, image_digest=None)):
        with pytest.raises(ValueError, match="CONTAINER_LAUNCH_RECORD_INVALID"):
            launch(tmp_path, **changes)


def test_a_processor_stops_with_its_container_exit_and_needs_no_shard_receipt(tmp_path):
    registry = ContainerLaunchRegistry(tmp_path / "launches.sqlite3")
    item = launch(tmp_path)
    registry.register(item)
    key = owner()
    registry.bind_container(item.launch_id, key)
    with pytest.raises(ValueError, match="LAUNCH_STOP_UNCONFIRMED"):
        registry.prove_terminated(item.launch_id, exited(key, running=True))
    assert registry.prove_terminated(item.launch_id, exited(key)) is True
    assert registry.records()[0]["exit_inspect"] == exited(key)
    assert registry.role_terminated("processor", lambda cid: exited(key))
    assert registry.all_terminated(lambda cid: exited(key))
    registry.close()


def test_a_processor_is_bound_to_its_child_like_a_shard(tmp_path):
    registry = ContainerLaunchRegistry(tmp_path / "launches.sqlite3")
    item = launch(tmp_path)
    registry.register(item)
    key = owner()
    registry.bind_container(item.launch_id, key)
    process = ProcessOwnerKey(1, 1, 7, "e" * 64, "f" * 64)
    binding = ContainerChildBinding(key, process, pid_namespace_inode(), str(tmp_path / "processing/p00/g1/control/normal.sock"))
    registry.bind_child(item.launch_id, binding)
    assert registry.records()[0]["binding"] == asdict(binding)
    registry.close()


def test_a_slot_is_reused_only_after_the_predecessor_is_proven_stopped(tmp_path):
    registry = ContainerLaunchRegistry(tmp_path / "launches.sqlite3")
    first = launch(tmp_path)
    registry.register(first)
    key = owner()
    registry.bind_container(first.launch_id, key)
    second = launch(tmp_path, generation=2)
    with pytest.raises(ValueError, match="LAUNCH_COLLISION: slot not retired"):
        registry.register(second)
    registry.prove_terminated(first.launch_id, exited(key))
    registry.register(second)
    with pytest.raises(ValueError, match="LAUNCH_COLLISION"):
        registry.register(launch(tmp_path, generation=2))
    other = launch(tmp_path, worker="p01")
    registry.register(other)     # another slot never waits for this one
    assert [record["launch"]["launch_id"] for record in registry.records()] == [
        "processing-p00-g1", "processing-p00-g2", "processing-p01-g1"]
    registry.close()


def test_processor_launches_do_not_collide_with_shards_or_services(tmp_path):
    registry = ContainerLaunchRegistry(tmp_path / "launches.sqlite3")
    shard_root = tmp_path / "wave-0" / "w00" / "g1"
    shard_root.mkdir(parents=True)
    registry.register(ContainerLaunch(launch_id="wave-0-w00-g1", role="shard", worker_id="w00", wave_id="wave-0",
        launch_generation=1, container_name="so101-act-w00-g1", image_digest=DIGEST, owned_root=str(shard_root), session_id="s1"))
    registry.register(launch(tmp_path))
    registry.register(launch(tmp_path, worker="p01"))
    assert len(registry.records()) == 3
    registry.close()
