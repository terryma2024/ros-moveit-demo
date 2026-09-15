import os
from pathlib import Path
import signal
import sys
import time

from so101_teleop.expert_validation.coordinator import CoordinatorStartRequest
from so101_teleop.expert_validation.process_owner import ExecutionProcessOwner


HELPER = Path(__file__).parents[1] / "fixtures/process_tree_helper.py"


def _wait(path, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {path}")


def test_real_process_identity_restart_reconnect_and_cleanup_gate(tmp_path):
    root = tmp_path.resolve()
    request = CoordinatorStartRequest(
        campaign_id="campaign-real",
        batch_id="b001",
        execution_mode="SEQUENTIAL",
        worker_count=1,
        max_points_per_worker=4,
        argv=(
            sys.executable,
            str(HELPER),
            "--mode",
            "coordinator",
            "--root",
            str(root),
            "--batch-id",
            "b001",
        ),
        environment={},
        batch_root=root,
        control_socket=root / "control.sock",
        control_token_sha256="c" * 64,
        coordinator_epoch=1,
    )
    cleanup_allowed = False
    first_owner = ExecutionProcessOwner(cleanup_checker=lambda _owned: cleanup_allowed)
    running = first_owner.spawn(request)
    _wait(root / "handshake.json")

    restarted_owner = ExecutionProcessOwner(cleanup_checker=lambda _owned: cleanup_allowed)
    assert restarted_owner.reconnect(running) == running
    assert restarted_owner.poll(running).running
    cleanup_allowed = True
    restarted_owner.stop_after_cleanup(running)
    assert not restarted_owner.poll(running).running


def test_leader_exit_is_not_mistaken_for_descendant_cleanup(tmp_path):
    root = tmp_path.resolve()
    request = CoordinatorStartRequest(
        campaign_id="campaign-leader",
        batch_id="b002",
        execution_mode="SEQUENTIAL",
        worker_count=1,
        max_points_per_worker=1,
        argv=(
            sys.executable,
            str(HELPER),
            "--mode",
            "coordinator",
            "--root",
            str(root),
            "--batch-id",
            "b002",
            "--leader-exits",
        ),
        environment={},
        batch_root=root,
        control_socket=root / "control.sock",
        control_token_sha256="d" * 64,
        coordinator_epoch=1,
    )
    owner = ExecutionProcessOwner(cleanup_checker=lambda _owned: False)
    running = owner.spawn(request)
    _wait(root / "handshake.json")
    for _ in range(150):
        if not owner.poll(running).running:
            break
        time.sleep(0.02)
    assert not owner.poll(running).running
    child_pid = int(__import__("json").loads((root / "handshake.json").read_text())["runner_pid"])
    try:
        assert os.kill(child_pid, 0) is None
    finally:
        os.kill(child_pid, signal.SIGTERM)
