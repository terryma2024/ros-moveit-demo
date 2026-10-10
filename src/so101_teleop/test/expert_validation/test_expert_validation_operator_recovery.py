"""An operator receipt must never turn a failed batch into execution success."""

import hashlib
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

from so101_teleop.expert_validation.models import (
    BatchBinding, CampaignBinding, ExecutionOwnerIntent, PreflightReceipt,
)
from so101_teleop.expert_validation.store import StoreConflict, SupervisorStore


SHA = "a" * 64


@pytest.fixture(params=[
    "ros_domain_ids: [181, 182]\n",
    "schema_version: 3\nexecution:\n  ros_domain_ids: [181, 182]\n",
])
def fenced(tmp_path, request):
    config = tmp_path / "parallel.yaml"
    config.write_text(request.param)
    store = SupervisorStore.open((tmp_path / "store").resolve())
    store.record_manifest("manifest-1", {"points": []}, source_config_sha256=SHA, created_at_ns=1)
    receipt = PreflightReceipt(
        "receipt-1", "campaign-1", "manifest-1", SHA,
        {"parallel_config_sha256": hashlib.sha256(config.read_bytes()).hexdigest()}, 10_000,
    )
    store.record_preflight_receipt(receipt)
    campaign = CampaignBinding(
        "campaign-1", "manifest-1", "operator", "operation-1", SHA, "PARALLEL",
        {"worker_count": 2, "max_points_per_worker": 10}, "receipt-1",
    )
    batch = BatchBinding("b001", "campaign-1", "FIRST_PASS", None, tmp_path / "b001", coordinator_epoch=1)
    store.consume_preflight_and_bind_campaign_batch("receipt-1", SHA, campaign, batch, now_monotonic_ns=1)
    store.record_execution_owner_intent(ExecutionOwnerIntent(
        "b001", "COORDINATOR", "spawn-1", "coordinator", SHA, SHA, "1" * 40,
        Path("/opt/validation"), SHA,
    ))
    store.acknowledge_execution_owner(batch_id="b001", pid=90001, pgid=90001,
                                      started_ticks=100, coordinator_epoch=1)
    store.record_recovery_fence("campaign-1", "b001", reason="OWNER_UNAVAILABLE", command_id="stop-1")
    try:
        yield store, config, tmp_path
    finally:
        store.close()


def recovery_module():
    name = "so101_teleop.expert_validation.operator_recovery"
    assert importlib.util.find_spec(name) is not None, "formal operator recovery entry is missing"
    return importlib.import_module(name)


def inspector(module, tmp_path, *, container_ids=(), busy_domain=None):
    proc = tmp_path / "proc"
    proc.mkdir(exist_ok=True)
    return module.RuntimeInspector(
        proc_root=proc,
        container_probe=lambda batch: list(container_ids),
        domain_probe=lambda domain: domain == busy_domain,
    )


def recover(fenced, **changes):
    store, config, root = fenced
    module = recovery_module()
    values = dict(store=store, campaign_id="campaign-1", command_id="recover-1",
                  parallel_config=config, inspector=inspector(module, root), source_commit="2" * 40,
                  apply=True)
    values.update(changes)
    return module.recover(**values)


def historical_rows(store):
    return {table: [tuple(row) for row in store._connection.execute(f"SELECT * FROM {table}")]
            for table in ("campaigns", "campaign_batches", "owned_execution", "recovery_fences")}


def test_recovery_unblocks_without_rewriting_history_or_claiming_cleanup(fenced):
    store, _, _ = fenced
    before = historical_rows(store)
    result = recover(fenced)
    assert result["status"] == "OPERATOR_RECOVERED_ABORTED"
    assert result["execution_success"] is False
    assert result["upstream_cleanup_claimed"] is False
    assert store.has_recovery_fence() is False
    assert store.recovery_fence("campaign-1")["reason"] == "OWNER_UNAVAILABLE"
    assert historical_rows(store) == before
    assert store.batch("b001").cleanup_receipt_sha256 is None
    assert store.owned_execution("b001").state == "RUNNING"
    assert Path(result["report_path"]).is_file()
    assert Path(result["backup_path"]).is_file()


def test_preview_cannot_resolve_the_fence(fenced):
    result = recover(fenced, apply=False)
    assert result["status"] == "RECOVERY_ELIGIBLE_PREVIEW"
    assert fenced[0].has_recovery_fence() is True


def test_repeat_is_idempotent_and_another_command_cannot_replace_receipt(fenced):
    first = recover(fenced)
    assert recover(fenced) == first
    with pytest.raises(StoreConflict, match="RECOVERY_ALREADY_RESOLVED"):
        recover(fenced, command_id="recover-other")


def test_recovery_survives_restart_and_still_preserves_original_fence(fenced):
    store, _, _ = fenced
    recover(fenced)
    root = store.root
    store.close()
    reopened = SupervisorStore.open(root)
    try:
        assert reopened.has_recovery_fence() is False
        assert reopened.recovery_fence("campaign-1")["command_id"] == "stop-1"
    finally:
        reopened.close()


@pytest.mark.parametrize("mutation", ["report", "fence", "owner", "receipt"])
def test_tampered_evidence_or_binding_reinstates_the_fence(fenced, mutation):
    store, _, _ = fenced
    result = recover(fenced)
    if mutation == "report":
        Path(result["report_path"]).write_text("{}")
    elif mutation == "fence":
        store._connection.execute("UPDATE recovery_fences SET reason='OTHER'")
    elif mutation == "owner":
        store._connection.execute("UPDATE owned_execution SET pgid=90002")
    else:
        store._connection.execute("UPDATE operator_recoveries SET receipt_json='{}'")
    assert store.has_recovery_fence() is True


def test_live_recorded_leader_is_refused_even_if_process_group_changed(fenced):
    module = recovery_module()
    store, _, root = fenced
    proc = root / "proc"
    proc.mkdir()
    (proc / "90001").mkdir()
    with pytest.raises(module.RecoveryError, match="RECOVERY_LEADER_PRESENT"):
        recover(fenced, inspector=inspector(module, root))
    assert store.has_recovery_fence() is True


def test_descendant_in_recorded_group_is_refused(fenced):
    module = recovery_module()
    _, _, root = fenced
    process = root / "proc" / "90002"
    process.mkdir(parents=True)
    # /proc stat tail: state, ppid, pgrp, session, followed by remaining fields.
    (process / "stat").write_text("90002 (worker) S 1 90001 1 " + "0 " * 20)
    with pytest.raises(module.RecoveryError, match="RECOVERY_PROCESS_GROUP_PRESENT"):
        recover(fenced, inspector=inspector(module, root))


@pytest.mark.parametrize("boundary", ["container", "domain", "probe"])
def test_uncleared_or_unverifiable_runtime_is_refused(fenced, boundary):
    module = recovery_module()
    _, _, root = fenced
    probe = inspector(module, root, container_ids=("container-1",) if boundary == "container" else (),
                      busy_domain=182 if boundary == "domain" else None)
    if boundary == "probe":
        def unreadable(_domain):
            raise OSError("domain inventory unavailable")
        probe.domain_probe = unreadable
    with pytest.raises(module.RecoveryError):
        recover(fenced, inspector=probe)
    assert fenced[0].has_recovery_fence() is True


def test_unacknowledged_spawn_intent_cannot_be_declared_clean(fenced):
    module = recovery_module()
    fenced[0]._connection.execute("UPDATE owned_execution SET state='INTENT'")
    with pytest.raises(module.RecoveryError, match="RECOVERY_OWNER_UNACKNOWLEDGED"):
        recover(fenced)


def test_config_not_bound_to_original_receipt_cannot_choose_clear_domains(fenced):
    module = recovery_module()
    fenced[1].write_text("ros_domain_ids: [201, 202]\n")
    with pytest.raises(module.RecoveryError, match="RECOVERY_CONFIG_MISMATCH"):
        recover(fenced)


def test_lock_cannot_be_bypassed_by_recovery_cli(fenced, capsys):
    module = recovery_module()
    store, config, _ = fenced
    rc = module.main(["--store-root", str(store.root), "--campaign-id", "campaign-1",
                      "--command-id", "recover-1", "--parallel-config", str(config),
                      "--source-commit", "2" * 40, "--apply"])
    assert rc != 0
    assert "VALIDATION_SUPERVISOR_ACTIVE" in capsys.readouterr().err
    assert store.has_recovery_fence() is True


def test_real_live_process_is_refused_without_sending_a_signal(fenced):
    module = recovery_module()
    store, _, _ = fenced
    process = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(20)"], start_new_session=True)
    try:
        store._connection.execute("UPDATE owned_execution SET pid=?,pgid=?", (process.pid, process.pid))
        probe = module.RuntimeInspector(container_probe=lambda _: [], domain_probe=lambda _: False)
        with pytest.raises(module.RecoveryError, match="RECOVERY_LEADER_PRESENT"):
            recover(fenced, inspector=probe)
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=3)


def test_new_fence_after_recovery_still_blocks_execution(fenced):
    store, _, _ = fenced
    recover(fenced)
    store._connection.execute("UPDATE recovery_fences SET command_id='stop-new'")
    assert store.has_recovery_fence() is True


def test_recovery_command_uses_the_standard_completed_command_protocol(fenced):
    store, _, _ = fenced
    result = recover(fenced)
    request_sha = store._connection.execute(
        "SELECT request_sha256 FROM commands WHERE command_id='recover-1'"
    ).fetchone()[0]
    assert store.repeat_command("recover-1", request_sha) == result


def test_batch_with_no_recorded_owner_cannot_be_ignored(fenced):
    module = recovery_module()
    store, _, root = fenced
    store._connection.execute(
        "INSERT INTO campaign_batches SELECT 'b002',campaign_id,batch_kind,point_id,state,"
        "coordinator_epoch,pool_generation,?,terminal_summary_sha256,cleanup_receipt_sha256 "
        "FROM campaign_batches WHERE batch_id='b001'", (str(root / "b002"),)
    )
    with pytest.raises(module.RecoveryError, match="RECOVERY_OWNER_UNACKNOWLEDGED"):
        recover(fenced)


def test_formal_recovery_entry_exists():
    from importlib.util import find_spec
    assert find_spec('so101_teleop.expert_validation.operator_recovery') is not None


def test_recover_defaults_to_keyword_only_preview_without_writes(fenced):
    import inspect
    store, config, root = fenced
    module = recovery_module()
    signature = inspect.signature(module.recover)
    assert signature.parameters['store'].kind == inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters['apply'].default is False
    probe = inspector(module, root)
    before_rows = historical_rows(store)
    before_files = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in root.rglob('*') if p.is_file()}
    result = module.recover(store=store, campaign_id='campaign-1',
        command_id='preview-default', parallel_config=config, inspector=probe,
        source_commit='2' * 40)
    assert result['status'] == 'RECOVERY_ELIGIBLE_PREVIEW'
    assert historical_rows(store) == before_rows
    assert store.has_recovery_fence() is True
    assert store.operator_recovery('campaign-1') is None
    assert {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()} == before_files
    with pytest.raises(TypeError):
        module.recover(store, campaign_id='campaign-1', command_id='invalid-positional',
            parallel_config=config, inspector=probe, source_commit='2' * 40)


# --------------------------------------------------------------------------------------
# Task 6: the formal recovery entry reclaims the durable owner tree, leaf first
# --------------------------------------------------------------------------------------


def _sleeper():
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _kill(pids):
    for pid in pids:
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _record_tree_process(root, role, token, child):
    """One durable record exactly as the spawn boundary and the service write it."""

    from so101_teleop.expert_validation.owner_tree import (
        ConfirmedOwnerProcess,
        DirectoryOwnerRecords,
        OwnerIntent,
    )
    from so101_teleop.process_identity import read_identity

    source = DirectoryOwnerRecords(root=root)
    argv = (sys.executable, "-c", "import time; time.sleep(60)")
    intent = OwnerIntent.for_argv(
        campaign_id="campaign-1",
        batch_id="b001",
        role=role,
        generation=1,
        spawn_token=token,
        argv=argv,
    )
    source.record_owner_intent(intent)
    identity = read_identity(child.pid)
    source.confirm_owner_process(
        ConfirmedOwnerProcess(
            spawn_token=token,
            pid=identity.pid,
            pgid=identity.pgid,
            started_ticks=identity.start_marker,
            command_sha256=identity.command_sha256,
            confirmed_at_ns=time.time_ns(),
        )
    )
    return source


def test_owner_tree_root_reclaims_the_recorded_tree_leaf_first_and_resolves_the_fence(fenced):
    module = recovery_module()
    store, _, tmp_path = fenced
    tree_root = (tmp_path / "owner-tree").resolve()
    children = []
    try:
        for role in ("WORKER", "STATION"):
            child = _sleeper()
            children.append(child)
            _record_tree_process(tree_root, role, f"spawn-{role.lower()}", child)
        assert all(child.poll() is None for child in children)

        result = recover(fenced, owner_tree_root=tree_root, apply=True)

        assert result["status"] == "OPERATOR_RECOVERED_ABORTED"
        assert store.operator_recovery("campaign-1") is not None
        committed = store.owner_cleanup_receipt("campaign-1", "b001", 1)
        assert committed is not None
        assert [entry["role"] for entry in committed["reclaimed"]] == ["STATION", "WORKER"]
        assert committed["fence_released"] is True
        assert (
            tree_root / "campaign-1" / "b001" / "generation-1.owner-cleanup-receipt.json"
        ).is_file()
        for child in children:
            child.wait(timeout=5)
            assert child.poll() is not None
        assert not any(os.path.lexists(tmp_path / "proc" / str(child.pid)) for child in children)
    finally:
        _kill([child.pid for child in children if child.poll() is None])


def test_owner_tree_root_refuses_an_unproven_identity_and_keeps_the_fence(fenced):
    module = recovery_module()
    store, _, tmp_path = fenced
    from so101_teleop.expert_validation.owner_tree import (
        ConfirmedOwnerProcess,
        DirectoryOwnerRecords,
        OwnerIntent,
    )
    from so101_teleop.process_identity import read_identity

    tree_root = (tmp_path / "owner-tree").resolve()
    source = DirectoryOwnerRecords(root=tree_root)
    child = _sleeper()
    try:
        identity = read_identity(child.pid)
        intent = OwnerIntent.for_argv(
            campaign_id="campaign-1",
            batch_id="b001",
            role="WORKER",
            generation=1,
            spawn_token="spawn-worker-reused",
            argv=(sys.executable, "-c", "import time; time.sleep(60)"),
        )
        source.record_owner_intent(intent)
        # The pid is live but the birth marker is not the confirmed one: a reused pid, never ours.
        source.confirm_owner_process(
            ConfirmedOwnerProcess(
                spawn_token=intent.spawn_token,
                pid=identity.pid,
                pgid=identity.pgid,
                started_ticks=identity.start_marker + 1,
                command_sha256=identity.command_sha256,
                confirmed_at_ns=time.time_ns(),
            )
        )
        # And an intent that never confirmed a process at all.
        source.record_owner_intent(
            OwnerIntent.for_argv(
                campaign_id="campaign-1",
                batch_id="b001",
                role="STATION",
                generation=1,
                spawn_token="spawn-station-unconfirmed",
                argv=(sys.executable, "-c", "import time; time.sleep(60)"),
            )
        )

        with pytest.raises(module.RecoveryError) as error:
            recover(fenced, owner_tree_root=tree_root, apply=True)

        message = str(error.value)
        assert "RECOVERY_OWNER_TREE_UNRESOLVED" in message
        assert "WORKER" in message and "OWNER_IDENTITY_MISMATCH" in message
        assert "STATION" in message and "INTENT_UNCONFIRMED" in message
        assert child.poll() is None, "an unproven identity must never be signalled"
        assert store.operator_recovery("campaign-1") is None
        assert store.has_recovery_fence() is True
        assert store.recovery_fence("campaign-1")["reason"] == "OWNER_UNAVAILABLE"
        assert store.owner_cleanup_receipt("campaign-1", "b001", 1) is None
        fence_document = json.loads(
            (
                tree_root / "campaign-1" / "b001" / "generation-1.unresolved-owner-tree.json"
            ).read_text(encoding="utf-8")
        )
        assert fence_document["generation_derived"] is False
        assert fence_document["command_id"] == "recover-1-1"
    finally:
        _kill([child.pid])


def test_owner_tree_root_preview_signals_nothing_and_writes_nothing(fenced):
    module = recovery_module()
    store, _, tmp_path = fenced
    tree_root = (tmp_path / "owner-tree").resolve()
    child = _sleeper()
    try:
        _record_tree_process(tree_root, "WORKER", "spawn-worker", child)

        result = recover(fenced, owner_tree_root=tree_root, apply=False)

        assert result["status"] == "RECOVERY_ELIGIBLE_PREVIEW"
        assert child.poll() is None
        directory = tree_root / "campaign-1" / "b001"
        assert list(directory.glob("*owner-cleanup-receipt.json")) == []
        assert list(directory.glob("*unresolved-owner-tree.json")) == []
        assert store.owner_cleanup_receipt("campaign-1", "b001", 1) is None
        assert store.operator_recovery("campaign-1") is None
        assert store.has_recovery_fence() is True
    finally:
        _kill([child.pid])


def test_operator_recovery_cli_accepts_an_owner_tree_root(tmp_path, capsys):
    module = recovery_module()
    store_root = tmp_path / "store"
    store_root.mkdir()
    rc = module.main([
        "--store-root", str(store_root), "--campaign-id", "campaign-1",
        "--command-id", "recover-1", "--parallel-config", str(tmp_path / "parallel.yaml"),
        "--source-commit", "2" * 40, "--owner-tree-root", str(tmp_path / "owner-tree"),
    ])
    assert rc == 1
    assert "RECOVERY_STORE_NOT_FOUND" in capsys.readouterr().err


# --------------------------------------------------------------------------------------
# Portable runtime inventory (remediation Task 5)
#
# Darwin has no /proc. The inspector therefore reads the host through a port: procfs on Linux,
# psutil on Darwin. An unreadable process, a broken psutil or a reused pid must never be read as
# "the process is gone", and the fence has to survive exactly as it does on Linux.
# --------------------------------------------------------------------------------------


class _FakePsutilProcess:
    def __init__(self, pid, created_at):
        self.pid = pid
        self._created_at = created_at

    def create_time(self):
        return self._created_at


class _FakePsutil:
    class NoSuchProcess(Exception):
        pass

    class AccessDenied(Exception):
        pass

    class ZombieProcess(Exception):
        pass

    def __init__(self, table, *, denied=(), broken=False):
        self.table = dict(table)
        self.denied = set(denied)
        self.broken = broken

    def pids(self):
        if self.broken:
            raise RuntimeError("psutil inventory unavailable")
        return list(self.table)

    def Process(self, pid):
        if self.broken:
            raise RuntimeError("psutil inventory unavailable")
        if pid in self.denied:
            raise self.AccessDenied(pid)
        if pid not in self.table:
            raise self.NoSuchProcess(pid)
        return _FakePsutilProcess(pid, self.table[pid])


def _psutil_inspector(module, table, *, groups, denied=(), broken=False, container_ids=(),
                      busy_domain=None):
    port = module.PsutilInventory(
        psutil_module=_FakePsutil(table, denied=denied, broken=broken),
        group_probe=lambda pid: groups[pid],
    )
    return module.RuntimeInspector(
        inventory=port,
        container_probe=lambda batch: list(container_ids),
        domain_probe=lambda domain: domain == busy_domain,
    )


def test_darwin_inventory_refuses_a_leader_that_is_still_present(fenced) -> None:
    module = recovery_module()
    store, _, _ = fenced

    # A pid that is present - including a reused pid with a different birth time - is not absent.
    with pytest.raises(module.RecoveryError, match="RECOVERY_LEADER_PRESENT"):
        recover(fenced, inspector=_psutil_inspector(
            module, {90001: 1234.5}, groups={90001: 90001}))
    assert store.has_recovery_fence() is True


def test_darwin_inventory_allows_a_clean_recovery_without_procfs(fenced) -> None:
    module = recovery_module()
    store, _, _ = fenced

    result = recover(fenced, inspector=_psutil_inspector(module, {}, groups={}))

    assert result["status"] == "OPERATOR_RECOVERED_ABORTED"
    assert store.has_recovery_fence() is False


def test_darwin_inventory_refuses_a_descendant_in_a_recorded_group(fenced) -> None:
    module = recovery_module()
    _, _, root = fenced
    owners = [{"pid": 90001, "runner_pid": 90002, "pgid": 90001}]

    with pytest.raises(module.RecoveryError, match="RECOVERY_PROCESS_GROUP_PRESENT"):
        _psutil_inspector(module, {91000: 7.0}, groups={91000: 90001}).inspect(
            owners, [181], [])
    _psutil_inspector(module, {91000: 7.0}, groups={91000: 91000}).inspect(owners, [181], [])


@pytest.mark.parametrize(
    "kwargs, code",
    [
        ({"broken": True}, "RECOVERY_RUNTIME_UNVERIFIABLE"),
        # A leader whose identity cannot be read is unverifiable, never absent.
        ({"denied": (90001,)}, "RECOVERY_RUNTIME_UNVERIFIABLE"),
    ],
)
def test_darwin_inventory_fails_closed_when_identity_cannot_be_proven(fenced, kwargs, code) -> None:
    module = recovery_module()
    store, _, _ = fenced
    table = {91000: 7.0}

    with pytest.raises(module.RecoveryError, match=code):
        recover(fenced, inspector=_psutil_inspector(
            module, table, groups={91000: 91000}, **kwargs))
    # A failed inspection keeps the fence: it never reads as a clean runtime.
    assert store.has_recovery_fence() is True


def test_missing_psutil_is_unverifiable_not_clean(monkeypatch) -> None:
    module = recovery_module()
    import builtins

    real_import = builtins.__import__

    def refusing_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("psutil is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refusing_import)
    with pytest.raises(module.RecoveryError, match="RECOVERY_RUNTIME_UNVERIFIABLE"):
        module.PsutilInventory()


def test_default_inventory_uses_procfs_when_it_exists(tmp_path) -> None:
    module = recovery_module()
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "90001").mkdir()
    port = module.default_process_inventory(proc)
    assert isinstance(port, module.ProcfsInventory)
    assert port.is_present(90001) is True
    assert port.is_present(90002) is False
    assert isinstance(
        module.default_process_inventory(tmp_path / "absent"), module.PsutilInventory)


def test_a_recovery_receipt_records_exactly_what_it_signalled(fenced):
    """Zero signals is a claim the receipt has to carry, not something a reader infers.

    Any refusal - an unprovable identity, an unresolved tree, a foreign sentinel - happens before a
    signal exists, so the receipt of a refused recovery cannot report one. A completed reclaim names
    the pids it re-proved and stopped.
    """
    module = recovery_module()
    store, _, tmp_path = fenced

    # A refused recovery raises before a receipt exists; the fence stays and nothing was signalled.
    with pytest.raises(module.RecoveryError, match="RECOVERY_RUNTIME_UNVERIFIABLE"):
        recover(fenced, inspector=_psutil_inspector(
            module, {91000: 7.0}, groups={91000: 91000}, broken=True))
    assert store.has_recovery_fence() is True

    # A completed recovery carries the field, and an abort recovery with no owner tree reports none.
    result = recover(fenced, inspector=_psutil_inspector(module, {}, groups={}))
    assert result["status"] == "OPERATOR_RECOVERED_ABORTED"
    assert result["signals_sent"] == []
    assert store.has_recovery_fence() is False


def test_a_host_without_a_container_runtime_has_no_batch_containers(monkeypatch):
    """No runtime is a proven fact; a runtime that cannot list is an unknown inventory.

    ``docker ps`` failing with ``FileNotFoundError`` on macOS was converted by ``recover()`` into
    ``RECOVERY_RUNTIME_UNVERIFIABLE``, so the operator entry could never complete on a host without
    Docker - even though a host without a container runtime cannot be running a batch container.
    A Docker that *is* installed but fails to list keeps the fail-closed refusal.
    """
    module = recovery_module()

    monkeypatch.setattr(module.shutil, "which", lambda _name: None)
    assert module._containers("b001") == []

    monkeypatch.setattr(module.shutil, "which", lambda _name: "/usr/local/bin/docker")

    def failing(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "docker", stderr="cannot connect")

    monkeypatch.setattr(module.subprocess, "run", failing)
    with pytest.raises(subprocess.CalledProcessError):
        module._containers("b001")
