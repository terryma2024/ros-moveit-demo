import json
import os
from pathlib import Path
import sys
import time

import pytest

import so101_teleop.expert_validation.process_owner as process_owner_module
from so101_teleop.expert_validation.adaptive import AdaptiveStartRequest
from so101_teleop.expert_validation.coordinator import CoordinatorStartRequest
from so101_teleop.expert_validation.process_owner import (
    CoordinatorOwnershipError,
    ExecutionProcessOwner,
    OwnedCoordinator,
)
from so101_teleop.owned_group import terminate_group


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
    root = (tmp_path / "batch-a").resolve()
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
    start_request = request(batch_root.parent)
    observed = {}

    def observe_spawn(*_args, **_kwargs):
        assert batch_root.parent.is_dir()
        assert not batch_root.exists()
        observed["stream"] = _kwargs["stdout"]
        assert Path(_kwargs["stdout"].name) == batch_root.parent / "batch-a.coordinator.log"
        assert _kwargs["stderr"] is process_owner_module.subprocess.STDOUT
        raise RuntimeError("SPAWN_OBSERVED")

    monkeypatch.setattr(process_owner_module.subprocess, "Popen", observe_spawn)

    with pytest.raises(RuntimeError, match="SPAWN_OBSERVED"):
        ExecutionProcessOwner().spawn(start_request)
    assert observed["stream"].closed
    assert (batch_root.parent / "batch-a.coordinator.log").stat().st_mode & 0o777 == 0o600


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


class OwnerTreeRecordingStore(RecordingStore):
    """A store that also persists the durable owner tree, in the order it was asked."""

    def __init__(self):
        super().__init__()
        self.intents = []
        self.confirmations = []

    def record_owner_intent(self, intent):
        self.events.append(("owner-intent", intent.spawn_token))
        self.intents.append(intent)
        return intent

    def confirm_owner_process(self, confirmed):
        self.events.append(("owner-confirmation", confirmed.spawn_token))
        self.confirmations.append(confirmed)
        return confirmed


def _wait_for_file(path, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path}")


ENV_KEYS = (
    "SO101_OWNER_TOKEN",
    "SO101_OWNER_PARENT_TOKEN",
    "SO101_OWNER_TREE_ROOT",
    "SO101_OWNER_CAMPAIGN_ID",
    "SO101_OWNER_BATCH_ID",
    "SO101_OWNER_GENERATION",
)


def _env_dump_request(tmp_path, output, *, extra_environment=None):
    """A coordinator whose only job is to dump the SO-101 owner binding it inherited."""

    script = (
        "import json,os,pathlib,sys,time;"
        "pathlib.Path(sys.argv[1]).write_text("
        "json.dumps({key: os.environ.get(key) for key in sys.argv[2:]}));"
        "time.sleep(60)"
    )
    root = (tmp_path / "env-batch").resolve()
    return CoordinatorStartRequest(
        campaign_id="campaign-a",
        batch_id="batch-a",
        execution_mode="PARALLEL",
        worker_count=2,
        max_points_per_worker=2,
        argv=(sys.executable, "-c", script, str(output), *ENV_KEYS),
        environment=dict(extra_environment or {}),
        batch_root=root,
        control_socket=root / "control.sock",
        control_token_sha256=SHA,
        coordinator_epoch=4,
    )


def test_owner_tree_intent_precedes_popen_and_confirmation_follows_the_readback(tmp_path, monkeypatch):
    store = OwnerTreeRecordingStore()
    tree_root = (tmp_path / "owner-tree").resolve()
    owner = ExecutionProcessOwner(
        store=store,
        owner_tree_root=tree_root,
        cleanup_checker=lambda _owned: True,
    )
    real_popen = process_owner_module.subprocess.Popen
    observed = {}

    def observing_popen(*args, **kwargs):
        observed["before_popen"] = [event[0] for event in store.events]
        observed["intent"] = store.intents[-1]
        directory = tree_root / "campaign-a" / "batch-a"
        observed["intent_path"] = directory / f"{observed['intent'].spawn_token}.intent.json"
        observed["intent_file_at_popen"] = observed["intent_path"].is_file()
        observed["confirmation_at_popen"] = (
            directory / f"{observed['intent'].spawn_token}.confirmed.json"
        ).exists()
        process = real_popen(*args, **kwargs)
        observed["confirmed_at_spawn"] = list(store.confirmations)
        return process

    monkeypatch.setattr(process_owner_module.subprocess, "Popen", observing_popen)
    running = owner.spawn(request(tmp_path))
    try:
        assert observed["before_popen"] == ["intent", "owner-intent"]
        intent = observed["intent"]
        assert intent.role == "ADAPTER"
        assert intent.parent_spawn_token is None
        assert intent.campaign_id == "campaign-a"
        assert intent.batch_id == "batch-a"
        assert intent.generation == 4
        assert intent.expected_executable == sys.executable
        assert intent.argv_sha256 == running.argv_sha256
        assert intent.own_session is True

        # The durable file is on disk before the process exists, and its confirmation is not.
        assert observed["intent_file_at_popen"] is True, "the intent file must precede Popen"
        assert observed["confirmation_at_popen"] is False
        document = json.loads(observed["intent_path"].read_text(encoding="utf-8"))
        assert document["schema"] == "so101.owner-intent/1"
        assert document["spawn_token"] == intent.spawn_token
        assert document["argv_sha256"] == intent.argv_sha256
        assert document["own_session"] is True

        assert observed["confirmed_at_spawn"] == [], "no confirmation may precede the readback"
        assert [event[0] for event in store.events] == [
            "intent",
            "owner-intent",
            "owner-confirmation",
            "running",
        ]
        confirmation = store.confirmations[0]
        assert confirmation.spawn_token == intent.spawn_token
        assert confirmation.pid == running.pid
        assert confirmation.pgid == running.pgid
        assert confirmation.started_ticks == running.started_ticks
        assert confirmation.command_sha256 == running.argv_sha256
        confirmation_document = json.loads(
            observed["intent_path"].with_name(
                f"{intent.spawn_token}.confirmed.json"
            ).read_text(encoding="utf-8")
        )
        assert confirmation_document["schema"] == "so101.owner-confirmation/1"
        assert confirmation_document["pid"] == running.pid
        assert confirmation_document["pgid"] == running.pgid
        assert confirmation_document["started_ticks"] == running.started_ticks
        assert confirmation_document["command_sha256"] == running.argv_sha256
    finally:
        owner.stop_after_cleanup(running)


def test_owner_tree_environment_is_exported_to_the_child(tmp_path):
    store = OwnerTreeRecordingStore()
    tree_root = (tmp_path / "owner-tree").resolve()
    output = (tmp_path / "child-env.json").resolve()
    owner = ExecutionProcessOwner(
        store=store, owner_tree_root=tree_root, cleanup_checker=lambda _owned: True
    )
    start = _env_dump_request(
        tmp_path, output, extra_environment={"OWNER_TEST": "1", "SO101_OWNER_TOKEN": "hijacked"}
    )
    running = owner.spawn(start)
    try:
        _wait_for_file(output)
        environment = json.loads(output.read_text(encoding="utf-8"))
        intent = store.intents[0]
        assert intent.spawn_token.startswith("spawn-")
        assert environment == {
            "SO101_OWNER_TOKEN": intent.spawn_token,
            "SO101_OWNER_PARENT_TOKEN": "",
            "SO101_OWNER_TREE_ROOT": str(tree_root),
            "SO101_OWNER_CAMPAIGN_ID": "campaign-a",
            "SO101_OWNER_BATCH_ID": "batch-a",
            "SO101_OWNER_GENERATION": "4",
        }
    finally:
        owner.stop_after_cleanup(running)


def test_no_owner_tree_record_is_written_without_a_configured_tree_root(tmp_path):
    store = OwnerTreeRecordingStore()
    owner = ExecutionProcessOwner(store=store, cleanup_checker=lambda _owned: True)
    running = owner.spawn(request(tmp_path))
    try:
        assert store.intents == []
        assert store.confirmations == []
        # The legacy records keep their exact order and shape.
        assert store.events == [("intent", "batch-a"), ("running", running.pid)]
    finally:
        owner.stop_after_cleanup(running)
    assert list(tmp_path.rglob("*.intent.json")) == []
    assert list(tmp_path.rglob("*.confirmed.json")) == []


def test_adaptive_spawn_records_generation_one_when_the_request_has_no_epoch(tmp_path):
    store = OwnerTreeRecordingStore()
    evidence_root = (tmp_path / "adaptive-evidence").resolve()
    runtime_root = evidence_root / "r" / "b001"
    start = AdaptiveStartRequest(
        campaign_id="campaign-a",
        batch_id="b001",
        preferred_worker_count=1,
        fallback_worker_counts=(),
        initial_points_per_worker=1,
        worker_start_timeout_s=5.0,
        max_infra_attempts_per_point=1,
        yolo_executor_count=1,
        argv=(
            sys.executable,
            str(HELPER),
            "--mode",
            "wrapper",
            "--root",
            str(runtime_root),
            "--batch-id",
            "b001",
        ),
        environment={},
        evidence_root=evidence_root,
        adaptive_config_sha256=SHA,
        catalog_sha256=SHA,
        yolo_weights_sha256=SHA,
        grounded_sam_manifest_sha256=SHA,
        broker_image_id="broker-image",
    )
    owner = ExecutionProcessOwner(
        store=store,
        owner_tree_root=(tmp_path / "owner-tree").resolve(),
        cleanup_checker=lambda _owned: True,
    )
    running = owner.spawn(start)
    try:
        assert len(store.intents) == 1
        assert store.intents[0].role == "ADAPTER"
        assert store.intents[0].generation == 1
        assert store.intents[0].batch_id == "b001"
        assert store.confirmations[0].pid == running.pid
        assert store.events[0][0] == "intent"
    finally:
        terminate_group(pgid=running.pgid, leader_pid=running.pid, timeout_s=1.0)


def test_owner_tree_files_are_written_even_when_the_store_cannot_index_them(tmp_path):
    """The shared tree root is the durable record, not a mirror of whatever the store supports."""

    store = RecordingStore()
    tree_root = (tmp_path / "owner-tree").resolve()
    owner = ExecutionProcessOwner(
        store=store, owner_tree_root=tree_root, cleanup_checker=lambda _owned: True
    )

    running = owner.spawn(request(tmp_path))
    try:
        directory = tree_root / "campaign-a" / "batch-a"
        intents = sorted(path.name for path in directory.glob("*.intent.json"))
        confirmations = sorted(path.name for path in directory.glob("*.confirmed.json"))
        assert len(intents) == 1 and len(confirmations) == 1
        token = intents[0][: -len(".intent.json")]
        assert confirmations[0] == f"{token}.confirmed.json"
        assert json.loads((directory / confirmations[0]).read_text())["pid"] == running.pid
        # The store without owner-tree support still sees exactly its legacy records.
        assert store.events == [("intent", "batch-a"), ("running", running.pid)]
    finally:
        owner.stop_after_cleanup(running)
