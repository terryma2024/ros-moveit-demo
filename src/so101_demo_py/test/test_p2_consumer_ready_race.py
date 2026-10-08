"""CP-3441 live pilot 271xMMUN: the worker read the Teacher's READY receipt while it was being written and failed the
gate ("dynamic consumer subscription is not ready"); the Teacher, waiting for a pose that never came, did not obey the
stop request. The receipt is published atomically, a partial or empty receipt means "not yet", and the pose wait obeys
the stop flags."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.ports.cup_pose_source import acquire_one

LEASE = {"batch_id": "b", "coordinator_epoch": 1, "worker_id": "w", "worker_generation": 1,
         "point_id": "p", "attempt_id": "a", "lease_generation": 1}


def _document():
    return {"schema_version": 1, "kind": "dynamic_consumer_ready", "session_id": "s", "reset_epoch": 1,
            "parallel_lease_identity": LEASE, "ready_ros_ns": 22_104_000_000, "ready_monotonic_s": 1.0}


def test_the_ready_receipt_is_never_visible_before_it_is_complete(tmp_path, monkeypatch):
    from so101_demo.ros import dynamic_runtime

    target = tmp_path / "dynamic" / "consumer-ready.json"
    seen = []
    real_fsync = os.fsync

    def spying_fsync(descriptor):
        # the moment the content is being made durable: a reader polling the final path must see nothing or everything
        seen.append(target.read_bytes() if target.exists() else None)
        return real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", spying_fsync)
    dynamic_runtime._write_consumer_ready_receipt(target, _document())
    assert all(item is None or json.loads(item) == _document() for item in seen), seen
    assert json.loads(target.read_text()) == _document() and oct(target.stat().st_mode & 0o777) == "0o600"
    assert sorted(path.name for path in target.parent.iterdir()) == ["consumer-ready.json"], "no temporary file left"


def test_the_ready_receipt_is_still_exclusive(tmp_path):
    from so101_demo.ros import dynamic_runtime

    target = tmp_path / "consumer-ready.json"
    dynamic_runtime._write_consumer_ready_receipt(target, _document())
    with pytest.raises(FileExistsError):
        dynamic_runtime._write_consumer_ready_receipt(target, _document())
    assert json.loads(target.read_text()) == _document()


def _ports(tmp_path):
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    ports = object.__new__(ParallelRosRuntimePorts)
    ports.resources = SimpleNamespace(worker_root=str(tmp_path))
    receipt = tmp_path / "attempts" / "p" / "a" / "working/dynamic/consumer-ready.json"
    command = ["python", "--batch-id", "b", "--coordinator-epoch", "1", "--worker-id", "w", "--worker-generation", "1",
               "--point-id", "p", "--attempt-id", "a", "--lease-generation", "1", "--session-id", "s",
               "--expected-reset-epoch", "1", "--ready-receipt", str(receipt)]
    return ports, SimpleNamespace(cmdline=tuple(command)), receipt


def _create(receipt, payload):
    receipt.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(descriptor, payload)
    os.close(descriptor)


@pytest.mark.parametrize("partial", [b"", b'{"kind":"dynamic_consumer_re'])
def test_an_empty_or_partial_ready_receipt_means_not_yet_not_failed(tmp_path, partial):
    ports, child, receipt = _ports(tmp_path)
    _create(receipt, partial)
    assert ports._consumer_ready_fence(child) is None


def test_a_complete_ready_receipt_is_accepted(tmp_path):
    ports, child, receipt = _ports(tmp_path)
    _create(receipt, (json.dumps(_document()) + "\n").encode())
    assert ports._consumer_ready_fence(child) == 22_104_000_000


def test_a_complete_but_foreign_receipt_still_fails_closed(tmp_path):
    ports, child, receipt = _ports(tmp_path)
    document = _document()
    document["session_id"] = "other"
    _create(receipt, (json.dumps(document) + "\n").encode())
    with pytest.raises(RuntimeError, match="DYNAMIC_READY_RECEIPT_IDENTITY"):
        ports._consumer_ready_fence(child)


def test_the_pose_wait_obeys_the_stop_check():
    class Stop(Exception):
        pass

    spins = []

    def stop_check():
        if len(spins) >= 2:
            raise Stop()

    with pytest.raises(Stop):
        acquire_one(receive=lambda: None, spin_once=lambda d: spins.append(d), convert=lambda m: m,
                    on_invalid=lambda e: None, timeout_s=240.0, stop_check=stop_check)
    assert len(spins) == 2


def test_the_ros_cup_pose_source_wait_reads_the_runtimes_stop_check(monkeypatch):
    import rclpy
    from so101_demo.ros.cup_pose_source import RosCupPoseSource

    class Stop(Exception):
        pass

    source = object.__new__(RosCupPoseSource)
    source._messages, source._node = [], SimpleNamespace(destroy_subscription=lambda subscription: None)
    source._subscription = object()
    monkeypatch.setattr(rclpy, "spin_once", lambda node, timeout_sec=0.0: None)
    calls = []

    def stop_check():
        calls.append(1)
        if len(calls) > 2:
            raise Stop()

    source.stop_check = stop_check
    with pytest.raises(Stop):
        source.get_one(240.0)


def test_the_dynamic_runtime_hands_its_stop_flags_to_the_pose_source():
    import inspect
    from so101_demo.ros import dynamic_runtime

    text = inspect.getsource(dynamic_runtime.run_dynamic_execute)
    assert "source.stop_check = stop_flags.raise_if_stopped" in text
