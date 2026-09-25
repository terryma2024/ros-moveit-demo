"""The admitted child consumes its exact owner proof before Task 8 begins."""

from dataclasses import asdict
import json
from types import SimpleNamespace

import pytest

from so101_teleop.unified.contracts import MutationError, OwnerKey
from so101_teleop.unified.task8_child_startup import consume_child_task8_startup
from so101_teleop.unified.task8_startup_issuer import Task8StartupProofIssuer


NOW_NS = 1_000_000_000_000
STACK = OwnerKey(12345, 12345, 101, "a" * 64, "b" * 64)
CHILD_OWNER = OwnerKey(23456, 23456, 202, "c" * 64, "d" * 64)
CHECKS = (
    "mujoco_session", "advancing_physics", "controller_states",
    "moveit_graph", "physical_stop", "head_rgb", "wrist_rgb",
)


def prepared(tmp_path):
    context = SimpleNamespace(
        evidence_root=str(tmp_path), campaign_id="campaign-294",
        operation_id="operation-294", source_sha256="1" * 64,
        manifest_sha256="2" * 64, runtime_config_sha256="3" * 64,
        collection_config_sha256="4" * 64,
        contact_policy_fingerprint="5" * 64,
    )
    child = SimpleNamespace(
        campaign_id=context.campaign_id, worker_id="w00", execution_generation=7,
        mujoco_session_id="session-294", ros_domain_id=179,
    )
    root = tmp_path / "task8-live" / context.campaign_id / "stack"
    root.mkdir(parents=True)
    readiness = json.dumps({
        "schema_version": 1, "session_id": child.mujoco_session_id,
        "ros_domain_id": child.ros_domain_id,
        "captured_monotonic_ns": NOW_NS - 1_000_000_000,
        "checks": {name: True for name in CHECKS},
    }).encode()
    receipt = Task8StartupProofIssuer(
        context, child, STACK, CHILD_OWNER,
        live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS,
    ).issue(readiness)
    environment = {
        "SO101_ACT_EVIDENCE_ROOT": context.evidence_root,
        "SO101_ACT_CAMPAIGN_ID": context.campaign_id,
        "SO101_ACT_OPERATION_ID": context.operation_id,
        "SO101_ACT_WORKER_ID": child.worker_id,
        "SO101_SIMULATION_SESSION_ID": child.mujoco_session_id,
        "SO101_ACT_GENERATION": str(child.execution_generation),
        "ROS_DOMAIN_ID": str(child.ros_domain_id),
        "SO101_ACT_SOURCE_SHA256": context.source_sha256,
        "SO101_ACT_MANIFEST_SHA256": context.manifest_sha256,
        "SO101_ACT_RUNTIME_CONFIG_SHA256": context.runtime_config_sha256,
        "SO101_ACT_COLLECTION_CONFIG_SHA256": context.collection_config_sha256,
        "SO101_ACT_POLICY_FINGERPRINT": context.contact_policy_fingerprint,
    }
    request = SimpleNamespace(
        operation="task8_phase", campaign_id=context.campaign_id,
        worker_id=child.worker_id, session_id=child.mujoco_session_id,
        execution_generation=child.execution_generation,
        token=SimpleNamespace(operation_id=context.operation_id),
        payload={"stack_owner": asdict(STACK)},
    )
    return request, environment, receipt, root


def test_child_consumes_exact_issued_proof_once(tmp_path):
    request, environment, receipt, root = prepared(tmp_path)
    consume = lambda: consume_child_task8_startup(
        request, CHILD_OWNER, environment,
        live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS,
    )
    assert consume() == receipt
    assert (root / "startup-consumed.json").is_file()
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_ALREADY_CONSUMED"):
        consume()


def test_child_rejects_wrong_owner_and_scope_before_consumption(tmp_path):
    request, environment, _, root = prepared(tmp_path)
    wrong_owner = {**request.payload["stack_owner"], "pid": 99999, "pgid": 99999}
    request.payload["stack_owner"] = wrong_owner
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_INVALID"):
        consume_child_task8_startup(
            request, CHILD_OWNER, environment,
            live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS,
        )
    assert (root / "startup-consumed.json").is_file()


def test_child_rejects_cross_worker_scope_without_claim(tmp_path):
    request, environment, _, root = prepared(tmp_path)
    request.worker_id = "w01"
    with pytest.raises(MutationError, match="TASK8_STARTUP_SCOPE_INVALID"):
        consume_child_task8_startup(
            request, CHILD_OWNER, environment,
            live_probe=lambda _owner: True, clock_ns=lambda: NOW_NS,
        )
    assert not (root / "startup-consumed.json").exists()
