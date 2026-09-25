"""A Task 8 startup receipt is scoped, fresh, and consumed at most once."""

from dataclasses import asdict
import hashlib
import json
from types import SimpleNamespace

import pytest

from so101_teleop.unified.contracts import MutationError, OwnerKey
from so101_teleop.unified.task8_startup_proof import Task8StartupProofConsumer


NOW_NS = 1_000_000_000_000
CHECKS = (
    "mujoco_session", "advancing_physics", "controller_states",
    "moveit_graph", "physical_stop", "head_rgb", "wrist_rgb",
)


def prepared(tmp_path):
    context = SimpleNamespace(
        evidence_root=str(tmp_path), campaign_id="campaign-281", operation_id="operation-281",
        source_sha256="a" * 64, manifest_sha256="b" * 64,
        runtime_config_sha256="c" * 64, collection_config_sha256="d" * 64,
        contact_policy_fingerprint="e" * 64,
    )
    child = SimpleNamespace(
        campaign_id=context.campaign_id, worker_id="worker-1", execution_generation=7,
        mujoco_session_id="session-281", ros_domain_id=179,
    )
    stack = OwnerKey(12345, 12345, 101, "f" * 64, "1" * 64)
    child_owner = OwnerKey(23456, 23456, 202, "0" * 64, "2" * 64)
    root = tmp_path / "task8-live" / child.campaign_id / "stack"
    root.mkdir(parents=True)
    readiness = {
        "schema_version": 1, "session_id": child.mujoco_session_id,
        "ros_domain_id": child.ros_domain_id,
        "captured_monotonic_ns": NOW_NS - 10_000_000_000,
        "checks": {key: True for key in CHECKS},
    }
    ready_bytes = json.dumps(readiness, sort_keys=True).encode()
    (root / "readiness.json").write_bytes(ready_bytes)
    receipt = {
        "schema_version": 1, "campaign_id": context.campaign_id,
        "operation_id": context.operation_id, "worker_id": child.worker_id,
        "execution_generation": child.execution_generation,
        "session_id": child.mujoco_session_id, "ros_domain_id": child.ros_domain_id,
        "source_sha256": context.source_sha256,
        "manifest_sha256": context.manifest_sha256,
        "runtime_config_sha256": context.runtime_config_sha256,
        "collection_config_sha256": context.collection_config_sha256,
        "contact_policy_fingerprint": context.contact_policy_fingerprint,
        "stack_owner": asdict(stack), "child_owner": asdict(child_owner),
        "readiness_sha256": hashlib.sha256(ready_bytes).hexdigest(),
        "issued_monotonic_ns": NOW_NS - 5_000_000_000,
    }
    (root / "startup-receipt.json").write_text(json.dumps(receipt))
    consumer = Task8StartupProofConsumer(
        context, child, stack_owner=stack, child_owner=child_owner,
        live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS,
    )
    return consumer, root, receipt


def test_valid_startup_proof_is_consumed_once(tmp_path):
    consumer, root, _ = prepared(tmp_path)
    result = consumer.consume()
    assert result["operation_id"] == "operation-281"
    assert (root / "startup-consumed.json").is_file()
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_ALREADY_CONSUMED"):
        consumer.consume()


def test_hash_tamper_consumes_attempt_without_granting_replay(tmp_path):
    consumer, root, _ = prepared(tmp_path)
    (root / "readiness.json").write_text("{}")
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_INVALID"):
        consumer.consume()
    assert (root / "startup-consumed.json").is_file()
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_ALREADY_CONSUMED"):
        consumer.consume()


def test_missing_receipt_does_not_create_consumed_marker(tmp_path):
    consumer, root, _ = prepared(tmp_path)
    (root / "startup-receipt.json").unlink()
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_UNAVAILABLE"):
        consumer.consume()
    assert not (root / "startup-consumed.json").exists()


def test_symlinked_readiness_is_rejected_and_consumed(tmp_path):
    consumer, root, _ = prepared(tmp_path)
    (root / "readiness.json").rename(root / "readiness-real.json")
    (root / "readiness.json").symlink_to(root / "readiness-real.json")
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_INVALID"):
        consumer.consume()
    assert (root / "startup-consumed.json").is_file()


def test_stale_readiness_is_rejected_even_with_matching_hash(tmp_path):
    consumer, root, receipt = prepared(tmp_path)
    readiness = json.loads((root / "readiness.json").read_text())
    readiness["captured_monotonic_ns"] = NOW_NS - 31_000_000_000
    raw = json.dumps(readiness, sort_keys=True).encode()
    (root / "readiness.json").write_bytes(raw)
    receipt["readiness_sha256"] = hashlib.sha256(raw).hexdigest()
    receipt["issued_monotonic_ns"] = NOW_NS - 25_000_000_000
    (root / "startup-receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_INVALID"):
        consumer.consume()
    assert (root / "startup-consumed.json").is_file()


def test_retired_stack_owner_is_rejected(tmp_path):
    consumer, root, _ = prepared(tmp_path)
    consumer.live_probe = lambda owner: owner != consumer.stack_owner
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_INVALID"):
        consumer.consume()
    assert (root / "startup-consumed.json").is_file()


def test_owner_field_type_drift_is_rejected(tmp_path):
    consumer, root, receipt = prepared(tmp_path)
    receipt["stack_owner"]["started_ticks"] = 101.0
    (root / "startup-receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_INVALID"):
        consumer.consume()
    assert (root / "startup-consumed.json").is_file()


def test_foreign_stack_path_rejected_before_consumption(tmp_path):
    consumer, root, _ = prepared(tmp_path)
    consumer.context.campaign_id = "../foreign"
    with pytest.raises(MutationError, match="TASK8_STARTUP_SCOPE_INVALID"):
        consumer.consume()
    assert not (root / "startup-consumed.json").exists()
