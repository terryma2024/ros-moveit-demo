"""The persistent owner tree and leaf-first recovery (design section 11).

Every real spawn persists an intent before ``Popen`` and a readback confirmation after it. Recovery
walks the tree leaf-first (station, worker, broker, campaign, adapter), signals only processes whose
live identity still matches the confirmation, and keeps the fence whenever an identity cannot be
proven. Foreign processes are never part of a tree and are never touched.

The module is imported lazily so a missing implementation fails as an assertion rather than a
collection error.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest


def _owner_tree():
    spec = importlib.util.find_spec("so101_teleop.expert_validation.owner_tree")
    assert spec is not None, "so101_teleop.expert_validation.owner_tree is not implemented yet"
    return importlib.import_module("so101_teleop.expert_validation.owner_tree")


def _store(tmp_path, *, provision=True):
    """A real supervisor store, optionally with the campaign/batch a fence needs."""

    from so101_teleop.expert_validation.store import SupervisorStore

    store = SupervisorStore.open(tmp_path / "supervisor")
    if provision:
        _provision_campaign_batch(store, tmp_path)
    return store


def _provision_campaign_batch(store, tmp_path):
    """The real campaign/batch binding, because a recovery fence is refused without it."""

    import hashlib

    from so101_teleop.expert_validation.models import (
        BatchBinding,
        CampaignBinding,
        PreflightReceipt,
    )

    digest = "a" * 64
    config = tmp_path / "parallel.yaml"
    config.write_text("ros_domain_ids: [181, 182]\n", encoding="utf-8")
    store.record_manifest("manifest-1", {"points": []}, source_config_sha256=digest, created_at_ns=1)
    store.record_preflight_receipt(
        PreflightReceipt(
            "receipt-1",
            "campaign-1",
            "manifest-1",
            digest,
            {"parallel_config_sha256": hashlib.sha256(config.read_bytes()).hexdigest()},
            10_000,
        )
    )
    store.consume_preflight_and_bind_campaign_batch(
        "receipt-1",
        digest,
        CampaignBinding(
            "campaign-1",
            "manifest-1",
            "operator",
            "operation-1",
            digest,
            "PARALLEL",
            {"worker_count": 2, "max_points_per_worker": 10},
            "receipt-1",
        ),
        BatchBinding(
            "b001", "campaign-1", "FIRST_PASS", None, tmp_path / "b001", coordinator_epoch=1
        ),
        now_monotonic_ns=1,
    )


class _Identity:
    """The readback surface the recovery consumes."""

    def __init__(self, pid, pgid, start_marker, command_sha256, state="S"):
        self.pid = pid
        self.pgid = pgid
        self.start_marker = start_marker
        self.command_sha256 = command_sha256
        self.state = state


class _Receipt:
    def __init__(self, clear, detail="pgid cleared"):
        self.clear = clear
        self._detail = detail

    def describe(self):
        return self._detail


class _SpyStore:
    """A store proxy that records which operations a recovery asked for."""

    def __init__(self, store):
        self._store = store
        self.calls = []

    def __getattr__(self, name):
        target = getattr(self._store, name)
        if not callable(target):
            return target

        def wrapper(*args, **kwargs):
            self.calls.append(name)
            return target(*args, **kwargs)

        return wrapper


class _Recorder:
    """A terminator that records what it was asked to stop without touching the host."""

    def __init__(self, module, *, clear=True, identities=None):
        self.calls = []
        self._module = module
        self._clear = clear
        self._identities = identities or {}

    def identity_reader(self, pid):
        identity = self._identities.get(pid)
        if identity is None:
            from so101_teleop.process_identity import ProcessIdentityError

            raise ProcessIdentityError("PROCESS_IDENTITY_MISMATCH")
        return identity

    def __call__(self, *, pgid, leader_pid, timeout_s):
        self.calls.append({"pgid": pgid, "leader_pid": leader_pid, "timeout_s": timeout_s})
        return _Receipt(self._clear)


def _recovery(module, store, tmp_path, *, identities=None, clear=True, receipt_root=None):
    recorder = _Recorder(module, clear=clear, identities=identities)
    recovery = module.OwnerTreeRecovery(
        store=store,
        receipt_root=tmp_path / "receipts" if receipt_root is None else receipt_root,
        identity_reader=recorder.identity_reader,
        terminator=recorder,
        stop_timeout_s=0.5,
    )
    return recovery, recorder


def _intent(module, **overrides):
    values = {
        "campaign_id": "campaign-1",
        "batch_id": "b001",
        "role": "WORKER",
        "generation": 1,
        "spawn_token": "spawn-worker-1",
        "parent_spawn_token": "spawn-campaign-1",
        "argv": ("/usr/bin/env", "python3", "-m", "so101_w2_worker"),
        "own_session": True,
    }
    values.update(overrides)
    return module.OwnerIntent.for_argv(**values)


def _confirm(module, store, intent, *, pid=4321, pgid=None, started_ticks=900, command_sha256="a" * 64):
    confirmed = module.ConfirmedOwnerProcess(
        spawn_token=intent.spawn_token,
        pid=pid,
        pgid=pid if pgid is None else pgid,
        started_ticks=started_ticks,
        command_sha256=command_sha256,
        confirmed_at_ns=time.time_ns(),
    )
    store.confirm_owner_process(confirmed)
    return confirmed


def _binding(module, *, generation=1, owner="service-session-1"):
    return module.OwnerParentBinding(
        campaign_id="campaign-1",
        batch_id="b001",
        generation=generation,
        recovery_owner=owner,
    )


# -- the durable two-step -----------------------------------------------------------------


def test_intent_is_durable_before_the_process_exists(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        intent = _intent(module, role="CAMPAIGN", spawn_token="spawn-campaign-1")

        store.record_owner_intent(intent)

        records = store.owner_tree("campaign-1", "b001")
        assert [(record.intent.spawn_token, record.confirmed) for record in records] == [
            ("spawn-campaign-1", None)
        ]
    finally:
        store.close()


def test_confirmation_is_refused_without_an_intent(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        with pytest.raises(Exception) as error:
            store.confirm_owner_process(
                module.ConfirmedOwnerProcess(
                    spawn_token="spawn-unknown",
                    pid=1,
                    pgid=1,
                    started_ticks=1,
                    command_sha256="a" * 64,
                    confirmed_at_ns=time.time_ns(),
                )
            )
        assert "OWNER_INTENT_MISSING" in str(error.value)
    finally:
        store.close()


def test_intent_document_round_trips_and_validates(tmp_path):
    module = _owner_tree()
    intent = _intent(module)
    assert module.OwnerIntent.from_document(intent.as_document()) == intent
    with pytest.raises(module.OwnerTreeError, match="OWNER_ROLE_INVALID"):
        _intent(module, role="DAEMON")
    with pytest.raises(module.OwnerTreeError, match="OWNER_FIELD_INVALID"):
        _intent(module, generation=0)
    with pytest.raises(module.OwnerTreeError, match="OWNER_FIELD_INVALID"):
        module.OwnerIntent(
            campaign_id="campaign-1",
            batch_id="b001",
            role="WORKER",
            generation=1,
            spawn_token="spawn-1",
            parent_spawn_token=None,
            expected_executable="/usr/bin/env",
            argv_sha256="not-a-hash",
            own_session=True,
            created_at_ns=1,
        )


# -- leaf-first reclamation ---------------------------------------------------------------


def test_recovery_stops_station_then_worker_then_campaign_then_adapter(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        identities = {}
        for index, role in enumerate(("ADAPTER", "CAMPAIGN", "WORKER", "STATION"), start=1):
            intent = _intent(
                module,
                role=role,
                spawn_token=f"spawn-{role.lower()}",
                created_at_ns=index,
            )
            store.record_owner_intent(intent)
            pid = 5000 + index
            command = f"{index:064x}"[-64:]
            _confirm(module, store, intent, pid=pid, command_sha256=command)
            identities[pid] = _Identity(pid, pid, 900, command)
        recovery, recorder = _recovery(module, store, tmp_path, identities=identities)
        binding = _binding(module)

        receipt = recovery.recover_leaf_first(parent_binding=binding)

        assert [call["leader_pid"] for call in recorder.calls] == [5004, 5003, 5002, 5001]
        assert [entry["role"] for entry in receipt.reclaimed] == [
            "STATION",
            "WORKER",
            "CAMPAIGN",
            "ADAPTER",
        ]
        assert receipt.fence_released is True
        assert receipt.receipt_sha256
        document = json.loads(
            (
                tmp_path
                / "receipts/campaign-1/b001/generation-1.owner-cleanup-receipt.json"
            ).read_text(encoding="utf-8")
        )
        assert document["receipt_sha256"] == receipt.receipt_sha256
        assert document["unresolved"] == []
    finally:
        store.close()


def test_station_in_its_own_session_is_reclaimed_through_its_own_group(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        worker = _intent(module, role="WORKER", spawn_token="spawn-worker", created_at_ns=1)
        station = _intent(
            module,
            role="STATION",
            spawn_token="spawn-station",
            parent_spawn_token="spawn-worker",
            own_session=True,
            created_at_ns=2,
        )
        store.record_owner_intent(worker)
        store.record_owner_intent(station)
        _confirm(module, store, worker, pid=6001, command_sha256="1" * 64)
        # The station leads its own group, so its pgid differs from the worker's on purpose.
        _confirm(module, store, station, pid=6002, pgid=6002, command_sha256="2" * 64)
        identities = {
            6001: _Identity(6001, 6001, 900, "1" * 64),
            6002: _Identity(6002, 6002, 900, "2" * 64),
        }
        recovery, recorder = _recovery(module, store, tmp_path, identities=identities)

        receipt = recovery.recover_leaf_first(parent_binding=_binding(module))

        assert [(call["leader_pid"], call["pgid"]) for call in recorder.calls] == [
            (6002, 6002),
            (6001, 6001),
        ]
        assert receipt.fence_released is True
    finally:
        store.close()


# -- refusals: unknown identity, unconfirmed intent, wrong generation ---------------------


def test_unconfirmed_intent_is_never_guessed_at_and_keeps_the_fence(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        store.record_owner_intent(_intent(module, role="WORKER", spawn_token="spawn-worker"))
        recovery, recorder = _recovery(module, store, tmp_path)

        receipt = recovery.recover_leaf_first(parent_binding=_binding(module))

        assert recorder.calls == []
        assert receipt.fence_released is False
        assert [entry["reason"] for entry in receipt.unresolved] == ["INTENT_UNCONFIRMED"]
        assert store.owner_cleanup_receipt("campaign-1", "b001", 1) is None
        fence = store.recovery_fence("campaign-1")
        assert fence is not None and "INTENT_UNCONFIRMED" in fence["reason"]
        assert (
            tmp_path / "receipts/campaign-1/b001/generation-1.owner-cleanup-receipt.json"
        ).exists() is False
    finally:
        store.close()


def test_recycled_pid_or_rebirth_is_never_signalled(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        intent = _intent(module, role="WORKER", spawn_token="spawn-worker")
        store.record_owner_intent(intent)
        _confirm(module, store, intent, pid=7001, started_ticks=900, command_sha256="a" * 64)
        # Same pid, different birth marker and command: a recycled pid, not our worker.
        identities = {7001: _Identity(7001, 7001, 4242, "b" * 64)}
        recovery, recorder = _recovery(module, store, tmp_path, identities=identities)

        receipt = recovery.recover_leaf_first(parent_binding=_binding(module))

        assert recorder.calls == []
        assert receipt.fence_released is False
        assert receipt.unresolved[0]["reason"] == "OWNER_IDENTITY_MISMATCH"
        assert receipt.unresolved[0]["observed"]["started_ticks"] == 4242
        assert store.recovery_fence("campaign-1") is not None
    finally:
        store.close()


def test_a_group_that_survives_the_stop_keeps_the_fence(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        intent = _intent(module, role="WORKER", spawn_token="spawn-worker")
        store.record_owner_intent(intent)
        _confirm(module, store, intent, pid=7101, command_sha256="c" * 64)
        identities = {7101: _Identity(7101, 7101, 900, "c" * 64)}
        recovery, recorder = _recovery(module, store, tmp_path, identities=identities, clear=False)

        receipt = recovery.recover_leaf_first(parent_binding=_binding(module))

        assert len(recorder.calls) == 1
        assert receipt.fence_released is False
        assert receipt.unresolved[0]["reason"] == "OWNER_GROUP_SURVIVORS"
        assert store.owner_cleanup_receipt("campaign-1", "b001", 1) is None
    finally:
        store.close()


def test_wrong_generation_binding_is_refused_before_any_signal(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        intent = _intent(module, generation=2, spawn_token="spawn-worker-2")
        store.record_owner_intent(intent)
        _confirm(module, store, intent, pid=7201, command_sha256="d" * 64)
        identities = {7201: _Identity(7201, 7201, 900, "d" * 64)}
        recovery, recorder = _recovery(module, store, tmp_path, identities=identities)

        with pytest.raises(module.OwnerTreeError, match="OWNER_RECOVERY_GENERATION_MISMATCH"):
            recovery.recover_leaf_first(
                parent_binding=_binding(module, generation=1), generation=2
            )

        assert recorder.calls == []
    finally:
        store.close()


def test_receipt_of_another_generation_never_releases_this_generation(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        first = _intent(module, generation=1, spawn_token="spawn-worker-1")
        store.record_owner_intent(first)
        _confirm(module, store, first, pid=7301, command_sha256="e" * 64)
        identities = {7301: _Identity(7301, 7301, 900, "e" * 64)}
        recovery, recorder = _recovery(module, store, tmp_path, identities=identities)
        committed = recovery.recover_leaf_first(parent_binding=_binding(module, generation=1))
        assert committed.fence_released is True

        second = _intent(module, generation=2, spawn_token="spawn-worker-2")
        store.record_owner_intent(second)

        receipt = recovery.recover_leaf_first(parent_binding=_binding(module, generation=2))

        assert receipt.generation == 2
        assert receipt.fence_released is False
        assert receipt.receipt_sha256 == ""
        assert receipt.unresolved[0]["spawn_token"] == "spawn-worker-2"
    finally:
        store.close()


def test_duplicate_reaper_returns_the_committed_receipt_without_signalling_again(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        intent = _intent(module, role="WORKER", spawn_token="spawn-worker")
        store.record_owner_intent(intent)
        _confirm(module, store, intent, pid=7401, command_sha256="f" * 64)
        identities = {7401: _Identity(7401, 7401, 900, "f" * 64)}
        recovery, recorder = _recovery(module, store, tmp_path, identities=identities)

        first = recovery.recover_leaf_first(parent_binding=_binding(module))
        second = recovery.recover_leaf_first(parent_binding=_binding(module))

        assert len(recorder.calls) == 1
        assert second.receipt_sha256 == first.receipt_sha256
        assert second.reclaimed == first.reclaimed
        assert second.fence_released is True
    finally:
        store.close()


def test_a_clean_recovery_only_records_a_receipt_and_never_touches_the_fence(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        intent = _intent(module, role="STATION", spawn_token="spawn-station")
        store.record_owner_intent(intent)
        _confirm(module, store, intent, pid=7501, command_sha256="1" * 64)
        identities = {7501: _Identity(7501, 7501, 900, "1" * 64)}
        spy = _SpyStore(store)
        recovery, _ = _recovery(module, spy, tmp_path, identities=identities)

        receipt = recovery.recover_leaf_first(parent_binding=_binding(module))

        assert receipt.fence_released is True
        # The reaper may record a receipt, never release a fence: only the caller, after committing
        # CLEANUP_COMMITTED through the operator-recovery path, may do that.
        assert set(spy.calls) <= {
            "owner_tree",
            "owner_cleanup_receipt",
            "record_owner_cleanup_receipt",
        }
    finally:
        store.close()


def test_already_exited_processes_are_reported_not_signalled(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        intent = _intent(module, role="BROKER", spawn_token="spawn-broker")
        store.record_owner_intent(intent)
        _confirm(module, store, intent, pid=7601, command_sha256="2" * 64)
        recovery, recorder = _recovery(module, store, tmp_path)

        receipt = recovery.recover_leaf_first(parent_binding=_binding(module))

        assert recorder.calls == []
        assert receipt.fence_released is True
        assert [entry["outcome"] for entry in receipt.already_exited] == ["ALREADY_EXITED"]
    finally:
        store.close()


def test_empty_tree_is_a_clean_receipt_because_intent_precedes_spawn(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        recovery, recorder = _recovery(module, store, tmp_path)

        receipt = recovery.recover_leaf_first(parent_binding=_binding(module))

        assert recorder.calls == []
        assert receipt.reclaimed == ()
        assert receipt.fence_released is True
        assert store.owner_cleanup_receipt("campaign-1", "b001", 1) is not None
    finally:
        store.close()


# -- real processes: an owner SIGKILL leaves sessions that must still be reclaimed ---------


def _spawn_sleeper():
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def _cleanup_pids(pids):
    for pid in pids:
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def test_real_sigkill_of_the_owning_campaign_leaves_sessions_that_recovery_reclaims(tmp_path):
    module = _owner_tree()
    from so101_teleop.process_identity import read_identity

    store = _store(tmp_path)
    children = []
    try:
        campaign = _spawn_sleeper()
        worker = _spawn_sleeper()  # its own session, like a Worker spawned by the campaign
        station = _spawn_sleeper()  # its own session: outside the Worker PGID on purpose
        children = [campaign, worker, station]
        assert len({child.pid for child in children}) == 3
        assert os.getpgid(station.pid) == station.pid
        assert os.getpgid(worker.pid) == worker.pid
        assert os.getpgid(worker.pid) != os.getpgid(station.pid)

        for role, child in (
            ("CAMPAIGN", campaign),
            ("WORKER", worker),
            ("STATION", station),
        ):
            intent = _intent(
                module,
                role=role,
                spawn_token=f"spawn-{role.lower()}",
                argv=(sys.executable, "-c", "import time; time.sleep(60)"),
            )
            store.record_owner_intent(intent)
            identity = read_identity(child.pid)
            store.confirm_owner_process(
                module.ConfirmedOwnerProcess(
                    spawn_token=intent.spawn_token,
                    pid=identity.pid,
                    pgid=identity.pgid,
                    started_ticks=identity.start_marker,
                    command_sha256=identity.command_sha256,
                    confirmed_at_ns=time.time_ns(),
                )
            )

        # The service or adapter dies: SIGKILL to the process that owned the tree.
        os.kill(campaign.pid, signal.SIGKILL)
        campaign.wait(timeout=5)
        assert worker.poll() is None and station.poll() is None

        recovery = module.OwnerTreeRecovery(
            store=store,
            receipt_root=tmp_path / "receipts",
            stop_timeout_s=3.0,
        )
        receipt = recovery.recover_leaf_first(parent_binding=_binding(module))

        assert [entry["role"] for entry in receipt.already_exited] == ["CAMPAIGN"]
        assert [entry["role"] for entry in receipt.reclaimed] == ["STATION", "WORKER"]
        assert receipt.fence_released is True
        worker.wait(timeout=5)
        station.wait(timeout=5)
        assert worker.poll() is not None and station.poll() is not None
        for child in (worker, station):
            with pytest.raises(ProcessLookupError):
                os.kill(child.pid, 0)
        children = []
    finally:
        _cleanup_pids([child.pid for child in children])
        store.close()


def test_real_process_that_never_confirmed_is_reported_and_never_signalled(tmp_path):
    module = _owner_tree()

    store = _store(tmp_path)
    child = None
    try:
        intent = _intent(
            module,
            role="WORKER",
            spawn_token="spawn-worker-unconfirmed",
            argv=(sys.executable, "-c", "import time; time.sleep(60)"),
        )
        # The crash window this test pins down: the process exists, the intent is durable, and the
        # readback confirmation was never written.
        child = _spawn_sleeper()
        store.record_owner_intent(intent)

        recovery = module.OwnerTreeRecovery(
            store=store, receipt_root=tmp_path / "receipts", stop_timeout_s=3.0
        )
        receipt = recovery.recover_leaf_first(parent_binding=_binding(module))

        assert receipt.fence_released is False
        assert receipt.unresolved[0]["reason"] == "INTENT_UNCONFIRMED"
        assert child.poll() is None, "an unconfirmed process must never be signalled"
        assert store.recovery_fence("campaign-1") is not None
    finally:
        if child is not None:
            _cleanup_pids([child.pid])
        store.close()


# -- the file-backed source the demo-side spawn boundaries write (frozen documents) ---------

INTENT_SCHEMA = "so101.owner-intent/1"
CONFIRMATION_SCHEMA = "so101.owner-confirmation/1"


def _owner_root(tmp_path):
    return tmp_path / "owner-tree"


def _write_document(path, document):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return path


def _intent_document(**overrides):
    """Exactly the document a demo-side spawn boundary writes before ``Popen``."""

    document = {
        "schema": INTENT_SCHEMA,
        "campaign_id": "campaign-1",
        "batch_id": "b001",
        "role": "WORKER",
        "generation": 1,
        "spawn_token": "spawn-worker-1",
        "parent_spawn_token": "spawn-campaign-1",
        "expected_executable": "/usr/bin/env",
        "argv_sha256": "a" * 64,
        "own_session": True,
        "created_at_ns": 1,
    }
    document.update(overrides)
    return document


def _confirmation_document(
    spawn_token,
    *,
    pid,
    pgid=None,
    started_ticks=900,
    command_sha256="a" * 64,
    confirmed_at_ns=1,
    schema=CONFIRMATION_SCHEMA,
):
    """Exactly the readback document a demo-side spawn boundary writes after ``Popen``."""

    return {
        "schema": schema,
        "spawn_token": spawn_token,
        "pid": pid,
        "pgid": pid if pgid is None else pgid,
        "started_ticks": started_ticks,
        "command_sha256": command_sha256,
        "confirmed_at_ns": confirmed_at_ns,
    }


def _write_tree_record(root, *, intent, confirmed=None):
    directory = root / intent["campaign_id"] / intent["batch_id"]
    token = intent["spawn_token"]
    _write_document(directory / f"{token}.intent.json", intent)
    if confirmed is not None:
        _write_document(directory / f"{token}.confirmed.json", confirmed)
    return directory


def _record_path(tmp_path, name, *, campaign_id="campaign-1", batch_id="b001"):
    return _owner_root(tmp_path) / campaign_id / batch_id / name


def test_directory_source_reads_the_frozen_intent_and_confirmation_documents(tmp_path):
    module = _owner_tree()
    _write_tree_record(
        _owner_root(tmp_path),
        intent=_intent_document(),
        confirmed=_confirmation_document("spawn-worker-1", pid=4321),
    )
    _write_tree_record(
        _owner_root(tmp_path),
        intent=_intent_document(
            role="STATION", spawn_token="spawn-station-1", generation=2, created_at_ns=2
        ),
    )

    source = module.DirectoryOwnerRecords(root=_owner_root(tmp_path))
    records = source.owner_tree("campaign-1", "b001")

    assert [record.intent.spawn_token for record in records] == [
        "spawn-worker-1",
        "spawn-station-1",
    ]
    first = records[0]
    assert first.intent.campaign_id == "campaign-1"
    assert first.intent.batch_id == "b001"
    assert first.intent.role == "WORKER"
    assert first.intent.generation == 1
    assert first.intent.parent_spawn_token == "spawn-campaign-1"
    assert first.intent.expected_executable == "/usr/bin/env"
    assert first.intent.argv_sha256 == "a" * 64
    assert first.intent.own_session is True
    assert first.intent.created_at_ns == 1
    assert first.confirmed == module.ConfirmedOwnerProcess(
        spawn_token="spawn-worker-1",
        pid=4321,
        pgid=4321,
        started_ticks=900,
        command_sha256="a" * 64,
        confirmed_at_ns=1,
    )
    assert records[1].confirmed is None
    # The generation filter is the recovery's, and it never widens the answer.
    assert [record.intent.spawn_token for record in source.owner_tree("campaign-1", "b001", 2)] == [
        "spawn-station-1"
    ]
    assert source.owner_tree("campaign-1", "b001", 7) == ()
    assert source.owner_tree("campaign-1", "b999") == ()
    assert source.owner_tree("campaign-2", "b001") == ()
    assert source.owner_cleanup_receipt("campaign-1", "b001", 1) is None


def test_directory_source_without_a_root_yet_is_an_empty_tree(tmp_path):
    module = _owner_tree()

    source = module.DirectoryOwnerRecords(root=_owner_root(tmp_path))

    assert source.owner_tree("campaign-1", "b001") == ()
    assert source.owner_cleanup_receipt("campaign-1", "b001", 1) is None


def test_directory_source_maps_a_missing_confirmation_to_an_unconfirmed_record(tmp_path):
    module = _owner_tree()
    _write_tree_record(_owner_root(tmp_path), intent=_intent_document(role="WORKER"))

    source = module.DirectoryOwnerRecords(root=_owner_root(tmp_path))
    records = source.owner_tree("campaign-1", "b001")

    assert [(record.intent.spawn_token, record.confirmed) for record in records] == [
        ("spawn-worker-1", None)
    ]

    recovery, recorder = _recovery(module, source, tmp_path)
    receipt = recovery.recover_leaf_first(parent_binding=_binding(module))

    assert recorder.calls == []
    assert receipt.fence_released is False
    assert [entry["reason"] for entry in receipt.unresolved] == ["INTENT_UNCONFIRMED"]
    assert (
        _record_path(tmp_path, "generation-1.owner-cleanup-receipt.json").exists() is False
    )
    fence = json.loads(
        _record_path(tmp_path, "generation-1.unresolved-owner-tree.json").read_text(
            encoding="utf-8"
        )
    )
    assert fence["campaign_id"] == "campaign-1"
    assert fence["batch_id"] == "b001"
    assert fence["generation"] == 1
    assert fence["command_id"] == "service-session-1-1"
    assert "INTENT_UNCONFIRMED" in fence["reason"]


@pytest.mark.parametrize(
    ("filename", "payload"),
    [
        ("spawn-1.intent.json", b"{not json"),
        ("spawn-2.intent.json", b"\xff\xfe\x00binary"),
        ("spawn-3.intent.json", b"[1, 2, 3]"),
        (
            "spawn-4.intent.json",
            json.dumps(_intent_document(schema="so101.owner-intent/9")).encode("utf-8"),
        ),
        (
            "spawn-5.intent.json",
            json.dumps(_intent_document(role="DAEMON", spawn_token="spawn-5")).encode("utf-8"),
        ),
        (
            "spawn-6.intent.json",
            json.dumps(_intent_document(generation="1", spawn_token="spawn-6")).encode("utf-8"),
        ),
        (
            "spawn-7.intent.json",
            json.dumps(_intent_document(own_session="yes", spawn_token="spawn-7")).encode("utf-8"),
        ),
        (
            "spawn-8.intent.json",
            json.dumps(_intent_document(argv_sha256="not-a-hash", spawn_token="spawn-8")).encode(
                "utf-8"
            ),
        ),
        (
            "spawn-9.intent.json",
            json.dumps(
                {
                    key: value
                    for key, value in _intent_document(spawn_token="spawn-9").items()
                    if key != "created_at_ns"
                }
            ).encode("utf-8"),
        ),
        (
            "spawn-a.intent.json",
            json.dumps(_intent_document(spawn_token="spawn-other")).encode("utf-8"),
        ),
        (
            "spawn-b.intent.json",
            json.dumps(_intent_document(campaign_id="campaign-2", spawn_token="spawn-b")).encode(
                "utf-8"
            ),
        ),
        (
            "spawn-c.confirmed.json",
            json.dumps(_confirmation_document("spawn-c", pid=1234)).encode("utf-8"),
        ),
    ],
    ids=[
        "invalid-json",
        "invalid-utf8",
        "not-an-object",
        "wrong-schema",
        "wrong-role",
        "wrong-generation-type",
        "wrong-own-session-type",
        "wrong-argv-hash",
        "missing-created-at",
        "token-mismatch",
        "foreign-campaign",
        "confirmation-without-intent",
    ],
)
def test_directory_source_refuses_a_malformed_or_unreadable_record(tmp_path, filename, payload):
    module = _owner_tree()
    directory = _owner_root(tmp_path) / "campaign-1" / "b001"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    (directory / filename).write_bytes(payload)

    with pytest.raises(module.OwnerTreeError, match="OWNER_RECORD_INVALID"):
        module.DirectoryOwnerRecords(root=_owner_root(tmp_path)).owner_tree("campaign-1", "b001")


def test_directory_source_refuses_a_malformed_confirmation(tmp_path):
    module = _owner_tree()
    root = _owner_root(tmp_path)
    _write_tree_record(
        root,
        intent=_intent_document(),
        confirmed=_confirmation_document("spawn-worker-1", pid=0),
    )

    with pytest.raises(module.OwnerTreeError, match="OWNER_RECORD_INVALID"):
        module.DirectoryOwnerRecords(root=root).owner_tree("campaign-1", "b001")


def test_directory_source_refuses_a_record_whose_spawn_token_is_not_a_safe_name(tmp_path):
    module = _owner_tree()
    root = _owner_root(tmp_path)

    with pytest.raises(module.OwnerTreeError, match="OWNER_RECORD_INVALID"):
        module.DirectoryOwnerRecords(root=root).owner_tree("campaign-1", "../escape")


def test_directory_source_refuses_a_symlinked_root(tmp_path):
    module = _owner_tree()
    real = tmp_path / "real-owner-tree"
    _write_tree_record(
        real, intent=_intent_document(), confirmed=_confirmation_document("spawn-worker-1", pid=1)
    )
    link = tmp_path / "linked-owner-tree"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(module.OwnerTreeError, match="OWNER_RECORD_INVALID"):
        module.DirectoryOwnerRecords(root=link).owner_tree("campaign-1", "b001")


def test_directory_source_refuses_a_symlinked_record_file(tmp_path):
    module = _owner_tree()
    root = _owner_root(tmp_path)
    _write_tree_record(root, intent=_intent_document())
    outside = _write_document(tmp_path / "elsewhere" / "intent.json", _intent_document())
    record = root / "campaign-1" / "b001" / "spawn-worker-1.intent.json"
    record.unlink()
    record.symlink_to(outside)

    with pytest.raises(module.OwnerTreeError, match="OWNER_RECORD_INVALID"):
        module.DirectoryOwnerRecords(root=root).owner_tree("campaign-1", "b001")


def test_directory_source_refuses_a_symlinked_campaign_or_batch_directory(tmp_path):
    module = _owner_tree()
    root = _owner_root(tmp_path)
    elsewhere = _write_tree_record(
        tmp_path / "elsewhere",
        intent=_intent_document(),
        confirmed=_confirmation_document("spawn-worker-1", pid=1),
    )
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    (root / "campaign-1").symlink_to(elsewhere.parent, target_is_directory=True)

    with pytest.raises(module.OwnerTreeError, match="OWNER_RECORD_INVALID"):
        module.DirectoryOwnerRecords(root=root).owner_tree("campaign-1", "b001")

    # The batch directory itself is checked too: a symlinked batch must not be traversed.
    (root / "campaign-1").unlink()
    (root / "campaign-1").mkdir()
    (root / "campaign-1" / "b001").symlink_to(elsewhere, target_is_directory=True)

    with pytest.raises(module.OwnerTreeError, match="OWNER_RECORD_INVALID"):
        module.DirectoryOwnerRecords(root=root).owner_tree("campaign-1", "b001")


def test_directory_source_refuses_a_generation_that_is_not_a_positive_int(tmp_path):
    module = _owner_tree()
    source = module.DirectoryOwnerRecords(root=_owner_root(tmp_path))

    with pytest.raises(module.OwnerTreeError, match="OWNER_RECORD_INVALID"):
        source.owner_tree("campaign-1", "b001", 0)


# -- the composite source: SQLite rows and demo-side files are one tree ---------------------


def test_composite_merges_sqlite_and_directory_records_leaf_first(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        adapter = _intent(
            module,
            role="ADAPTER",
            spawn_token="spawn-adapter-1",
            parent_spawn_token=None,
            created_at_ns=1,
        )
        store.record_owner_intent(adapter)
        _confirm(module, store, adapter, pid=5001, command_sha256="1" * 64)
        _write_tree_record(
            _owner_root(tmp_path),
            intent=_intent_document(
                role="WORKER", spawn_token="spawn-worker-1", created_at_ns=2
            ),
            confirmed=_confirmation_document("spawn-worker-1", pid=5002, command_sha256="2" * 64),
        )
        _write_tree_record(
            _owner_root(tmp_path),
            intent=_intent_document(
                role="STATION", spawn_token="spawn-station-1", created_at_ns=3
            ),
            confirmed=_confirmation_document("spawn-station-1", pid=5003, command_sha256="3" * 64),
        )
        composite = module.CompositeOwnerRecords(
            store, module.DirectoryOwnerRecords(root=_owner_root(tmp_path))
        )
        identities = {
            5001: _Identity(5001, 5001, 900, "1" * 64),
            5002: _Identity(5002, 5002, 900, "2" * 64),
            5003: _Identity(5003, 5003, 900, "3" * 64),
        }
        recovery, recorder = _recovery(module, composite, tmp_path, identities=identities)

        receipt = recovery.recover_leaf_first(parent_binding=_binding(module))

        assert [entry["role"] for entry in receipt.reclaimed] == ["STATION", "WORKER", "ADAPTER"]
        assert [call["leader_pid"] for call in recorder.calls] == [5003, 5002, 5001]
        assert receipt.fence_released is True
        # The committed outcome reached every durable sink the composite was given.
        committed = composite.owner_cleanup_receipt("campaign-1", "b001", 1)
        assert committed is not None and committed["fence_released"] is True
        directory_receipt = module.DirectoryOwnerRecords(
            root=_owner_root(tmp_path)
        ).owner_cleanup_receipt("campaign-1", "b001", 1)
        assert directory_receipt is not None
        assert directory_receipt["reclaimed"] == committed["reclaimed"]
        assert (
            _record_path(tmp_path, "generation-1.owner-cleanup-receipt.json").exists() is True
        )
    finally:
        store.close()


def test_composite_reports_one_record_per_spawn_token_and_signals_it_once(tmp_path):
    module = _owner_tree()
    store = _store(tmp_path)
    try:
        shared = _intent(
            module,
            role="ADAPTER",
            spawn_token="spawn-adapter-1",
            parent_spawn_token=None,
            created_at_ns=1,
        )
        store.record_owner_intent(shared)
        _confirm(module, store, shared, pid=5101, command_sha256="1" * 64)
        # The same boundary record also exists as a file: one tree, two durable copies.
        _write_tree_record(
            _owner_root(tmp_path),
            intent=_intent_document(
                role="ADAPTER", spawn_token="spawn-adapter-1", parent_spawn_token=None, created_at_ns=1
            ),
            confirmed=_confirmation_document("spawn-adapter-1", pid=5101, command_sha256="1" * 64),
        )
        composite = module.CompositeOwnerRecords(
            store, module.DirectoryOwnerRecords(root=_owner_root(tmp_path))
        )

        records = composite.owner_tree("campaign-1", "b001")
        assert [record.intent.spawn_token for record in records] == ["spawn-adapter-1"]

        identities = {5101: _Identity(5101, 5101, 900, "1" * 64)}
        recovery, recorder = _recovery(module, composite, tmp_path, identities=identities)
        receipt = recovery.recover_leaf_first(parent_binding=_binding(module))

        assert len(recorder.calls) == 1
        assert receipt.fence_released is True
    finally:
        store.close()


class _BareSource:
    """A record source that implements only the one method a source must have."""

    def __init__(self, records=()):
        self._records = tuple(records)
        self.asked = []

    def owner_tree(self, campaign_id, batch_id, generation=None):
        self.asked.append((campaign_id, batch_id, generation))
        return self._records


def test_composite_returns_the_first_committed_receipt_and_skips_absent_writers(tmp_path):
    module = _owner_tree()
    bare = _BareSource()
    source = module.DirectoryOwnerRecords(root=_owner_root(tmp_path))
    composite = module.CompositeOwnerRecords(bare, source)

    receipt = module.OwnerCleanupReceipt(
        campaign_id="campaign-1",
        batch_id="b001",
        generation=1,
        reclaimed=(),
        already_exited=(),
        unresolved=(),
        receipt_sha256="f" * 64,
    )
    # A source without the optional writers must be skipped, never called blindly.
    composite.record_owner_cleanup_receipt(receipt)
    composite.record_recovery_fence(
        "campaign-1", "b001", reason="OWNER_TREE_UNRESOLVED generation 1", command_id="op-1"
    )
    # Idempotent: the second write of the same receipt leaves the durable answer alone.
    composite.record_owner_cleanup_receipt(receipt)

    committed = composite.owner_cleanup_receipt("campaign-1", "b001", 1)
    assert committed is not None
    assert committed["campaign_id"] == "campaign-1"
    assert committed["generation"] == 1
    assert len(committed["receipt_sha256"]) == 64
    assert composite.owner_cleanup_receipt("campaign-1", "b001", 2) is None
    fence = json.loads(
        _record_path(tmp_path, "generation-1.unresolved-owner-tree.json").read_text(
            encoding="utf-8"
        )
    )
    assert fence["reason"] == "OWNER_TREE_UNRESOLVED generation 1"
    assert fence["command_id"] == "op-1"


def test_duplicate_reaper_through_the_directory_source_returns_the_committed_receipt(tmp_path):
    module = _owner_tree()
    root = _owner_root(tmp_path)
    _write_tree_record(
        root,
        intent=_intent_document(role="WORKER"),
        confirmed=_confirmation_document("spawn-worker-1", pid=7401, command_sha256="f" * 64),
    )
    source = module.DirectoryOwnerRecords(root=root)
    identities = {7401: _Identity(7401, 7401, 900, "f" * 64)}
    # The receipt root is the shared tree root: the first reaper's receipt is what the second reads.
    recovery, recorder = _recovery(
        module, source, tmp_path, identities=identities, receipt_root=root
    )

    first = recovery.recover_leaf_first(parent_binding=_binding(module))
    second = recovery.recover_leaf_first(parent_binding=_binding(module))

    assert len(recorder.calls) == 1
    assert first.fence_released is True
    assert second.receipt_sha256 == first.receipt_sha256
    assert second.reclaimed == first.reclaimed
    assert second.fence_released is True
    assert (
        _record_path(tmp_path, "generation-1.owner-cleanup-receipt.json").exists() is True
    )
    committed = source.owner_cleanup_receipt("campaign-1", "b001", 1)
    assert committed is not None and committed["receipt_sha256"] == first.receipt_sha256
    assert committed["unresolved"] == []


def test_directory_recovery_writes_the_unresolved_document_and_keeps_the_fence(tmp_path):
    module = _owner_tree()
    root = _owner_root(tmp_path)
    _write_tree_record(
        root,
        intent=_intent_document(role="WORKER"),
        confirmed=_confirmation_document("spawn-worker-1", pid=7001, started_ticks=900),
    )
    source = module.DirectoryOwnerRecords(root=root)
    # The pid is live but re-birthed: never signalled, never guessed at.
    identities = {7001: _Identity(7001, 7001, 4242, "b" * 64)}
    recovery, recorder = _recovery(module, source, tmp_path, identities=identities)

    receipt = recovery.recover_leaf_first(parent_binding=_binding(module))

    assert recorder.calls == []
    assert receipt.unresolved[0]["reason"] == "OWNER_IDENTITY_MISMATCH"
    assert (
        _record_path(tmp_path, "generation-1.owner-cleanup-receipt.json").exists() is False
    )
    fence = json.loads(
        _record_path(tmp_path, "generation-1.unresolved-owner-tree.json").read_text(
            encoding="utf-8"
        )
    )
    assert fence["generation"] == 1
    assert fence["command_id"] == "service-session-1-1"
    assert "OWNER_IDENTITY_MISMATCH" in fence["reason"]
    assert fence["recorded_at_ns"] >= 1


def test_real_process_recorded_in_the_directory_tree_is_reclaimed(tmp_path):
    module = _owner_tree()
    from so101_teleop.process_identity import read_identity

    root = _owner_root(tmp_path)
    child = _spawn_sleeper()
    try:
        identity = read_identity(child.pid)
        _write_tree_record(
            root,
            intent=_intent_document(
                role="WORKER",
                spawn_token="spawn-worker-real",
                expected_executable=sys.executable,
                argv_sha256=identity.command_sha256,
            ),
            confirmed=_confirmation_document(
                "spawn-worker-real",
                pid=identity.pid,
                pgid=identity.pgid,
                started_ticks=identity.start_marker,
                command_sha256=identity.command_sha256,
            ),
        )
        recovery = module.OwnerTreeRecovery(
            store=module.DirectoryOwnerRecords(root=root),
            receipt_root=root,
            stop_timeout_s=3.0,
        )

        receipt = recovery.recover_leaf_first(parent_binding=_binding(module))

        assert receipt.fence_released is True
        assert [entry["role"] for entry in receipt.reclaimed] == ["WORKER"]
        child.wait(timeout=5)
        assert child.poll() is not None
        with pytest.raises(ProcessLookupError):
            os.kill(child.pid, 0)
    finally:
        _cleanup_pids([child.pid])


# -- the directory source as a writer: the service's own ADAPTER record ---------------------


def test_directory_source_writes_the_intent_and_confirmation_of_its_own_spawn(tmp_path):
    module = _owner_tree()
    from so101_teleop.process_identity import read_identity

    source = module.DirectoryOwnerRecords(root=_owner_root(tmp_path))
    intent = module.OwnerIntent.for_argv(
        campaign_id="campaign-1",
        batch_id="b001",
        role="ADAPTER",
        generation=1,
        spawn_token="spawn-adapter-1",
        argv=("/usr/bin/env", "python3", "-m", "so101_adapter"),
        parent_spawn_token=None,
    )

    source.record_owner_intent(intent)

    records = source.owner_tree("campaign-1", "b001")
    assert [(record.intent.spawn_token, record.confirmed) for record in records] == [
        ("spawn-adapter-1", None)
    ]
    document = json.loads(
        _record_path(tmp_path, "spawn-adapter-1.intent.json").read_text(encoding="utf-8")
    )
    assert document["schema"] == INTENT_SCHEMA
    assert document["role"] == "ADAPTER"
    assert document["parent_spawn_token"] is None
    assert document["generation"] == 1
    assert document["argv_sha256"] == intent.argv_sha256
    assert document["own_session"] is True
    # Writing the same intent twice is idempotent; a different intent under the same token is not.
    source.record_owner_intent(intent)
    with pytest.raises(module.OwnerTreeError, match="OWNER_INTENT_CONFLICT"):
        source.record_owner_intent(
            module.OwnerIntent.for_argv(
                campaign_id="campaign-1",
                batch_id="b001",
                role="ADAPTER",
                generation=1,
                spawn_token="spawn-adapter-1",
                argv=("/usr/bin/env", "python3", "-m", "another_adapter"),
                parent_spawn_token=None,
            )
        )

    identity = read_identity(os.getpid())
    confirmed = module.ConfirmedOwnerProcess(
        spawn_token="spawn-adapter-1",
        pid=identity.pid,
        pgid=identity.pgid,
        started_ticks=identity.start_marker,
        command_sha256=intent.argv_sha256,
        confirmed_at_ns=time.time_ns(),
    )
    source.confirm_owner_process(confirmed)

    records = source.owner_tree("campaign-1", "b001")
    assert records[0].confirmed == confirmed
    source.confirm_owner_process(confirmed)  # idempotent
    with pytest.raises(module.OwnerTreeError, match="OWNER_CONFIRMATION_CONFLICT"):
        source.confirm_owner_process(
            module.ConfirmedOwnerProcess(
                spawn_token="spawn-adapter-1",
                pid=identity.pid + 1,
                pgid=identity.pgid,
                started_ticks=identity.start_marker,
                command_sha256=intent.argv_sha256,
                confirmed_at_ns=time.time_ns(),
            )
        )


def test_directory_source_refuses_a_confirmation_for_a_spawn_it_never_intended(tmp_path):
    module = _owner_tree()
    source = module.DirectoryOwnerRecords(root=_owner_root(tmp_path))

    with pytest.raises(module.OwnerTreeError, match="OWNER_INTENT_MISSING"):
        source.confirm_owner_process(
            module.ConfirmedOwnerProcess(
                spawn_token="spawn-unknown",
                pid=os.getpid(),
                pgid=os.getpgid(0),
                started_ticks=1,
                command_sha256="a" * 64,
                confirmed_at_ns=1,
            )
        )


# -- the fence document never presents a guessed generation as fact -------------------------


def test_directory_fence_document_records_the_exact_generation(tmp_path):
    module = _owner_tree()
    source = module.DirectoryOwnerRecords(root=_owner_root(tmp_path))

    source.record_recovery_fence(
        "campaign-1",
        "b001",
        reason="OWNER_TREE_UNRESOLVED generation 2: WORKER INTENT_UNCONFIRMED",
        command_id="recover-7-2",
        generation=2,
    )

    document = json.loads(
        _record_path(tmp_path, "generation-2.unresolved-owner-tree.json").read_text(
            encoding="utf-8"
        )
    )
    assert document["schema"] == "so101.unresolved-owner-tree/1"
    assert document["generation"] == 2
    assert document["generation_derived"] is False
    assert document["generation_source"] == "caller"
    assert document["command_id"] == "recover-7-2"
    # The command id is never the source of a file name, not even when it ends in a number.
    assert (_record_path(tmp_path, "generation-7.unresolved-owner-tree.json")).exists() is False


def test_directory_fence_document_marks_a_derived_generation_as_derived(tmp_path):
    module = _owner_tree()
    root = _owner_root(tmp_path)
    _write_tree_record(
        root, intent=_intent_document(generation=3, spawn_token="spawn-worker-3")
    )
    source = module.DirectoryOwnerRecords(root=root)

    # A pid-shaped command id must never name the fence file: the recorded tree answers instead.
    source.record_recovery_fence("campaign-1", "b001", reason="orphan", command_id="spawn-501")

    document = json.loads(
        _record_path(tmp_path, "generation-3.unresolved-owner-tree.json").read_text(
            encoding="utf-8"
        )
    )
    assert document["generation"] == 3
    assert document["generation_derived"] is True
    assert document["generation_source"] == "recorded_intents"
    assert (_record_path(tmp_path, "generation-501.unresolved-owner-tree.json")).exists() is False

    # With no recorded tree at all, the module-wide default is used and still marked derived.
    empty_root = tmp_path / "empty-owner-tree"
    empty = module.DirectoryOwnerRecords(root=empty_root)
    empty.record_recovery_fence("campaign-1", "b001", reason="orphan", command_id="spawn-502")
    empty_directory = empty_root / "campaign-1" / "b001"
    default = json.loads(
        (empty_directory / "generation-1.unresolved-owner-tree.json").read_text(encoding="utf-8")
    )
    assert default["generation"] == 1
    assert default["generation_derived"] is True
    assert default["generation_source"] == "default"
    assert (empty_directory / "generation-502.unresolved-owner-tree.json").exists() is False

    # A number the recorded tree corroborates is attributed to the command id that carried it.
    corroborated_root = tmp_path / "corroborated-owner-tree"
    _write_tree_record(
        corroborated_root, intent=_intent_document(generation=2, spawn_token="spawn-worker-2")
    )
    corroborated = module.DirectoryOwnerRecords(root=corroborated_root)
    corroborated.record_recovery_fence(
        "campaign-1", "b001", reason="orphan", command_id="recover-1-2"
    )
    document = json.loads(
        (
            corroborated_root / "campaign-1" / "b001" / "generation-2.unresolved-owner-tree.json"
        ).read_text(encoding="utf-8")
    )
    assert document["generation"] == 2
    assert document["generation_derived"] is True
    assert document["generation_source"] == "command_id"


def test_recovery_fence_names_the_exact_generation_it_was_reaping(tmp_path):
    module = _owner_tree()
    root = _owner_root(tmp_path)
    _write_tree_record(
        root, intent=_intent_document(generation=2, spawn_token="spawn-worker-2", created_at_ns=2)
    )
    source = module.DirectoryOwnerRecords(root=root)
    recovery, recorder = _recovery(module, source, tmp_path, receipt_root=root)

    receipt = recovery.recover_leaf_first(parent_binding=_binding(module, generation=2))

    assert recorder.calls == []
    assert receipt.fence_released is False
    document = json.loads(
        _record_path(tmp_path, "generation-2.unresolved-owner-tree.json").read_text(
            encoding="utf-8"
        )
    )
    assert document["generation"] == 2
    assert document["generation_derived"] is False
    assert document["generation_source"] == "caller"
    assert document["command_id"] == "service-session-1-2"
    assert (_record_path(tmp_path, "generation-1.unresolved-owner-tree.json")).exists() is False
