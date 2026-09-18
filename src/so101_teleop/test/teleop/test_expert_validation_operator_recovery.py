"""An operator receipt must never turn a failed batch into execution success."""

import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from so101_teleop.expert_validation.models import (
    BatchBinding, CampaignBinding, ExecutionOwnerIntent, PreflightReceipt,
)
from so101_teleop.expert_validation.store import StoreConflict, SupervisorStore


SHA = "a" * 64


@pytest.fixture
def fenced(tmp_path):
    config = tmp_path / "parallel.yaml"
    config.write_text("ros_domain_ids: [181, 182]\n")
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
