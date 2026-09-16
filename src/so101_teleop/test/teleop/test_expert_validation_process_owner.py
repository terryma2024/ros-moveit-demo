import os
from pathlib import Path
import sys

import pytest

import so101_teleop.expert_validation.process_owner as process_owner_module
from so101_teleop.expert_validation.coordinator import CoordinatorStartRequest
from so101_teleop.expert_validation.process_owner import (
    CoordinatorOwnershipError,
    ExecutionProcessOwner,
    OwnedCoordinator,
)


HELPER = Path(__file__).parents[1] / "fixtures/process_tree_helper.py"
SHA = "a" * 64


class RecordingStore:
    def __init__(self):
        self.events = []

    def record_execution_owner_intent(self, request):
        self.events.append(("intent", request.batch_id))

    def acknowledge_execution_owner(self, owned):
        self.events.append(("running", owned.pid))


def request(tmp_path):
    root = tmp_path.resolve()
    return CoordinatorStartRequest(
        campaign_id="campaign-a",
        batch_id="batch-a",
        execution_mode="PARALLEL",
        worker_count=2,
        max_points_per_worker=2,
        argv=(
            sys.executable,
            str(HELPER),
            "--mode",
            "coordinator",
            "--root",
            str(root),
            "--batch-id",
            "batch-a",
        ),
        environment={"OWNER_TEST": "1"},
        batch_root=root,
        control_socket=root / "control.sock",
        control_token_sha256=SHA,
        coordinator_epoch=4,
    )


def test_spawn_records_intent_before_running_ack(tmp_path):
    store = RecordingStore()
    owner = ExecutionProcessOwner(store=store, cleanup_checker=lambda _owned: True)
    running = owner.spawn(request(tmp_path))
    try:
        assert isinstance(running, OwnedCoordinator)
        assert store.events == [("intent", "batch-a"), ("running", running.pid)]
    finally:
        owner.stop_after_cleanup(running)


def test_fixed_spawn_leaves_batch_root_for_coordinator_to_create(tmp_path, monkeypatch):
    batch_root = tmp_path / "campaign-a" / "batch-a"
    start_request = request(batch_root)

    def observe_spawn(*_args, **_kwargs):
        assert batch_root.parent.is_dir()
        assert not batch_root.exists()
        raise RuntimeError("SPAWN_OBSERVED")

    monkeypatch.setattr(process_owner_module.subprocess, "Popen", observe_spawn)

    with pytest.raises(RuntimeError, match="SPAWN_OBSERVED"):
        ExecutionProcessOwner().spawn(start_request)


def test_owner_reconnects_only_to_exact_recorded_coordinator(tmp_path):
    owner = ExecutionProcessOwner(cleanup_checker=lambda _owned: True)
    running = owner.spawn(request(tmp_path))
    try:
        assert owner.reconnect(running) == running
        stale = OwnedCoordinator(
            **{
                **running.__dict__,
                "started_ticks": running.started_ticks + 1,
            }
        )
        with pytest.raises(CoordinatorOwnershipError, match="PROCESS_IDENTITY_MISMATCH"):
            owner.reconnect(stale)
    finally:
        owner.stop_after_cleanup(running)


def test_fixed_stop_requires_cleanup_and_never_signals_before_gate(tmp_path):
    cleanup = False
    owner = ExecutionProcessOwner(cleanup_checker=lambda _owned: cleanup)
    running = owner.spawn(request(tmp_path))
    try:
        with pytest.raises(CoordinatorOwnershipError, match="CLEANUP_NOT_CONFIRMED"):
            owner.stop_after_cleanup(running)
        assert os.kill(running.pid, 0) is None
        cleanup = True
        owner.stop_after_cleanup(running)
    finally:
        if owner.poll(running).running:
            os.kill(running.pid, 9)


def test_only_one_campaign_can_own_execution(tmp_path):
    owner = ExecutionProcessOwner(cleanup_checker=lambda _owned: True)
    first = owner.spawn(request(tmp_path / "one"))
    try:
        with pytest.raises(CoordinatorOwnershipError, match="EXECUTION_OWNER_EXISTS"):
            owner.spawn(request(tmp_path / "two"))
    finally:
        owner.stop_after_cleanup(first)
