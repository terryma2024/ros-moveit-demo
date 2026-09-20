"""Contract tests for the persistent global mutation arbiter.

These tests exercise the real SQLite-backed store and the real arbiter. They do not
import ROS and do not touch any existing Validation journal.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from so101_teleop.unified.arbiter import GlobalMutationArbiter
from so101_teleop.unified.contracts import (
    ActionKey,
    ActionTerminal,
    DispatchAck,
    Domain,
    MutationError,
    OperationSpec,
    OwnerKey,
)
from so101_teleop.unified.intent_store import IntentStore


def teleop_spec(command_id: str, payload: dict | None = None, *, deadline_ns: int = 1000) -> OperationSpec:
    return OperationSpec(
        command_id, Domain.TELEOP, "execute", payload if payload is not None else {"plan_id": "p1"}, "R1", 1, deadline_ns
    )


def validation_spec(command_id: str) -> OperationSpec:
    return OperationSpec(command_id, Domain.VALIDATION, "start", {}, "R1", 1, 1000)


def owner() -> OwnerKey:
    return OwnerKey(11, 11, 9, "a", "e")


def test_durable_reservation_survives_restart_and_idempotency(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 100)
    spec = OperationSpec("arm-1", Domain.TELEOP, "execute", {"plan_id": "p1"}, "R1", 1, 1000)
    first = arbiter.begin(spec)
    assert arbiter.begin(spec).operation_id == first.operation_id
    with pytest.raises(MutationError, match="COMMAND_ID_REUSED"):
        arbiter.begin(
            OperationSpec("arm-1", Domain.TELEOP, "execute", {"plan_id": "p2"}, "R1", 1, 1000)
        )
    store.close()
    store = IntentStore.open(tmp_path / "state")
    restored = GlobalMutationArbiter(store, clock_ns=lambda: 101)
    with pytest.raises(MutationError, match="BLOCKED"):
        restored.begin(OperationSpec("v1", Domain.VALIDATION, "start", {}, "R1", 1, 1000))
    assert restored.projection(first.operation_id).phase == "BLOCKED"
    store.close()


def test_fresh_store_starts_idle_and_records_the_owning_domain(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    assert arbiter.is_idle()
    reservation = arbiter.begin(validation_spec("v1"))
    assert reservation.spec.domain is Domain.VALIDATION
    assert not arbiter.is_idle()
    with pytest.raises(MutationError, match="GLOBAL_MUTATION_BUSY"):
        arbiter.begin(teleop_spec("arm-1"))
    store.close()


def test_payload_fingerprint_is_canonical_and_rejects_nan(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    arbiter.begin(teleop_spec("arm-1", {"plan_id": "p1", "target": 1.5}))
    assert arbiter.begin(teleop_spec("arm-1", {"target": 1.5, "plan_id": "p1"})).operation_id
    with pytest.raises(MutationError, match="PAYLOAD_NOT_CANONICAL"):
        arbiter.begin(teleop_spec("nan-1", {"target": float("nan")}))
    store.close()


def test_confirmed_terminal_and_cleanup_settle_back_to_idle(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    parent = arbiter.begin(teleop_spec("arm-1"))
    token = arbiter.prepare_child(parent.operation_id, "arm")
    key = ActionKey(parent.operation_id, "arm", "goal-arm", owner(), "R1", 1)
    arbiter.record_ack(token, DispatchAck(key, True))
    arbiter.record_terminal(ActionTerminal(key, True, True, True))
    projection = arbiter.settle(parent.operation_id, cleanup_confirmed=True)
    assert projection.phase == "COMPLETE"
    assert [terminal.key.goal_uuid for terminal in projection.children] == ["goal-arm"]
    assert arbiter.is_idle()


def test_terminal_without_cleanup_proof_keeps_the_reservation_blocked(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    parent = arbiter.begin(teleop_spec("arm-1"))
    token = arbiter.prepare_child(parent.operation_id, "arm")
    key = ActionKey(parent.operation_id, "arm", "goal-arm", owner(), "R1", 1)
    arbiter.record_ack(token, DispatchAck(key, True))
    arbiter.record_terminal(ActionTerminal(key, True, True, False))
    with pytest.raises(MutationError, match="CLEANUP_NOT_CONFIRMED"):
        arbiter.settle(parent.operation_id, cleanup_confirmed=False)
    assert arbiter.projection(parent.operation_id).phase == "BLOCKED"
    assert not arbiter.is_idle()


def test_prepared_child_without_ack_cannot_be_settled(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    parent = arbiter.begin(teleop_spec("arm-1"))
    arbiter.prepare_child(parent.operation_id, "arm")
    with pytest.raises(MutationError, match="UNCONVERGED_CHILD"):
        arbiter.settle(parent.operation_id, cleanup_confirmed=True)
    assert arbiter.projection(parent.operation_id).phase == "BLOCKED"


def test_pause_keeps_the_reservation_and_blocks_the_other_domain(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    parent = arbiter.begin(OperationSpec("wf-1", Domain.TELEOP, "workflow", {}, "R1", 1, 1000))
    arbiter.pause(parent.operation_id)
    assert arbiter.projection(parent.operation_id).phase == "PAUSED"
    assert not arbiter.is_idle()
    with pytest.raises(MutationError, match="PAUSED"):
        arbiter.prepare_child(parent.operation_id, "arm")
    store.close()


def test_prepare_child_refuses_expired_deadline(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 5000)
    parent = arbiter.begin(teleop_spec("arm-1", deadline_ns=1000))
    with pytest.raises(MutationError, match="DEADLINE_EXPIRED"):
        arbiter.prepare_child(parent.operation_id, "arm")
    store.close()


def test_second_service_instance_cannot_open_the_same_store(tmp_path):
    root = tmp_path / "state"
    store = IntentStore.open(root)
    try:
        with pytest.raises(MutationError, match="SERVICE_INSTANCE_LOCKED"):
            IntentStore.open(root)
    finally:
        store.close()
    reopened = IntentStore.open(root)
    reopened.close()


def test_second_process_cannot_open_the_same_store(tmp_path):
    root = tmp_path / "state"
    store = IntentStore.open(root)
    try:
        program = textwrap.dedent(
            """
            import sys
            from pathlib import Path
            from so101_teleop.unified.intent_store import IntentStore
            from so101_teleop.unified.contracts import MutationError
            try:
                IntentStore.open(Path(sys.argv[1]))
            except MutationError as error:
                assert "SERVICE_INSTANCE_LOCKED" in str(error)
                raise SystemExit(7)
            raise SystemExit(0)
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", program, str(root)], capture_output=True, text=True, check=False
        )
        assert completed.returncode == 7, completed.stderr
    finally:
        store.close()


def test_concurrent_begin_admits_exactly_one_domain(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    guard = threading.Lock()

    def attempt(spec: OperationSpec) -> None:
        barrier.wait()
        try:
            arbiter.begin(spec)
        except MutationError as error:
            with guard:
                outcomes.append(f"refused:{error}")
        else:
            with guard:
                outcomes.append("admitted")

    threads = [
        threading.Thread(target=attempt, args=(teleop_spec("arm-1"),)),
        threading.Thread(target=attempt, args=(validation_spec("v1"),)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcomes.count("admitted") == 1
    assert len(outcomes) == 2
    refused = next(item for item in outcomes if item.startswith("refused:"))
    assert refused.split("refused:GLOBAL_MUTATION_BUSY: ")[1] in {"TELEOP_ACTIVE", "VALIDATION_ACTIVE"}
    store.close()


def test_cancel_between_prepare_and_ack_still_registers_the_late_goal(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    parent = arbiter.begin(OperationSpec("all-1", Domain.TELEOP, "execute_all", {}, "R1", 1, 1000))
    token = arbiter.prepare_child(parent.operation_id, "arm")
    intent = arbiter.cancel_parent(parent.operation_id)
    assert [target.key.child_id for target in intent.targets] == ["arm"]
    with pytest.raises(MutationError, match="INTENT_REVOKED"):
        arbiter.prepare_child(parent.operation_id, "gripper")
    key = ActionKey(parent.operation_id, "arm", "goal-late", owner(), "R1", 1)
    arbiter.record_ack(token, DispatchAck(key, True))
    children = arbiter.projection(parent.operation_id).children
    assert [child.key.goal_uuid for child in children] == ["goal-late"]


def test_blocked_state_survives_restart_until_an_explicit_recovery(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    arbiter.block("OWNER_UNKNOWN")
    assert arbiter.is_blocked()
    store.close()
    store = IntentStore.open(tmp_path / "state")
    restored = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    assert restored.is_blocked()
    with pytest.raises(MutationError, match="BLOCKED"):
        restored.begin(teleop_spec("arm-9"))
    store.close()


def test_intent_store_leaves_existing_history_bytes_untouched(tmp_path):
    legacy = tmp_path / "state" / "expert_validation"
    legacy.mkdir(parents=True)
    journal = legacy / "campaign-journal.json"
    journal.write_text(json.dumps({"campaign": "old", "points": [1, 2, 3]}))
    before = hashlib.sha256(journal.read_bytes()).hexdigest()

    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    parent = arbiter.begin(teleop_spec("arm-1"))
    arbiter.prepare_child(parent.operation_id, "arm")
    arbiter.cancel_parent(parent.operation_id)
    store.close()

    assert hashlib.sha256(journal.read_bytes()).hexdigest() == before
    assert json.loads(journal.read_text())["campaign"] == "old"


def test_store_directory_is_private_and_lock_is_not_followed(tmp_path):
    root = tmp_path / "state"
    store = IntentStore.open(root)
    try:
        assert (root.stat().st_mode & 0o777) == 0o700
        lock_path = root / "service.lock"
        assert lock_path.is_file()
        assert (lock_path.stat().st_mode & 0o777) == 0o600
    finally:
        store.close()
