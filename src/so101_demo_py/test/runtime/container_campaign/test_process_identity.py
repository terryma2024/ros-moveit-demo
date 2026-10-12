"""Host container identity and inner process identity are distinct ownership proofs."""

from dataclasses import asdict, replace
import importlib
import os

import pytest


def module():
    return importlib.import_module("so101_demo.runtime.container_campaign.process_identity")


def container():
    return module().ContainerOwnerKey("a"*64, "2026-10-12T01:02:03.123456789Z", "sha256:"+"b"*64, 7)


def process():
    return module().ProcessOwnerKey(1, 1, 99, "c"*64, "d"*64)


def inspect_document(*, running=True):
    return {"Id": "a"*64, "Image": "sha256:"+"b"*64,
            "State": {"StartedAt": "2026-10-12T01:02:03.123456789Z", "Running": running,
                      "Restarting": False, "Pid": 481 if running else 0,
                      "Status": "running" if running else "exited"}}


def test_keys_are_distinct_even_when_host_cli_pid_equals_inner_pid():
    value = module().ContainerChildBinding(container(), process(), 200,
                                            "/data/private/normal.sock")
    assert value.container != value.process
    with pytest.raises(ValueError, match="CONTAINER_CHILD_BINDING_INVALID"):
        module().ContainerChildBinding(process(), container(), 200, "/data/private/normal.sock")


@pytest.mark.parametrize("field, value", [("container_id", "short-id"), ("image_digest", "latest"),
    ("docker_started_at", "0001-01-01T00:00:00Z"), ("launch_generation", True)])
def test_container_key_requires_actual_start_and_immutable_identity(field, value):
    with pytest.raises(ValueError, match="CONTAINER_OWNER_KEY_INVALID"):
        replace(container(), **{field: value})


def test_namespace_process_key_reads_real_kernel_start_argv_and_environment():
    owner = module().read_process_owner(os.getpid())
    assert owner.pid == os.getpid() and owner.pgid == os.getpgid(os.getpid())
    assert owner.started_ticks > 0
    assert len(owner.argv_sha256) == len(owner.environment_sha256) == 64
    assert module().process_owner_matches(owner) is True
    assert module().process_owner_matches(replace(owner, started_ticks=owner.started_ticks+1)) is False


def test_docker_inspect_identity_does_not_use_host_cli_pid():
    actual = module().container_key_from_inspect(inspect_document(), launch_generation=7)
    assert actual == container()
    assert module().container_exit_proven(container(), inspect_document()) is False
    assert module().container_exit_proven(container(), inspect_document(running=False)) is True
    changed = inspect_document(running=False)
    changed["State"]["StartedAt"] = "2026-10-12T01:03:00Z"
    assert module().container_exit_proven(container(), changed) is False


def test_stop_proof_requires_same_generation_process_and_actual_container_exit():
    binding = module().ContainerChildBinding(container(), process(), 200, "/data/private/normal.sock")
    receipt = {"schema_version": 1, "kind": "shard_stop_receipt", "generation": 7,
        "process_owner": asdict(process()), "pid_namespace_inode": 200,
        "goals_stopped": True, "controllers_stopped": True,
        "ros_children_exited": True, "ros_graph_empty": True, "forced": False}
    assert module().shard_stop_proven(binding, receipt, inspect_document(running=False)) is True
    assert module().shard_stop_proven(binding, receipt, inspect_document()) is False
    for field, value in (("generation", 8), ("controllers_stopped", False), ("ros_graph_empty", False),
                         ("forced", True), ("pid_namespace_inode", 201)):
        assert module().shard_stop_proven(binding, receipt | {field: value}, inspect_document(running=False)) is False
    assert module().shard_stop_proven(binding, receipt | {"host_pid": 1}, inspect_document(running=False)) is False
    forged = receipt | {"process_owner": asdict(process()) | {"pid": True}}
    assert module().shard_stop_proven(binding, forged, inspect_document(running=False)) is False
