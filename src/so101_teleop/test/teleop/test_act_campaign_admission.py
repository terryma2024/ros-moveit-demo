"""ACT admission freezes identity before any child can start."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import os
import time

import pytest

from so101_teleop.unified.contracts import AdmittedCampaignContext
from so101_teleop.unified.bridge import ActChildLaunch, ActChildRegistry
from so101_teleop.unified.admission import UnifiedWorkloadService
from so101_teleop.unified.arbiter import GlobalMutationArbiter
from so101_teleop.unified.contracts import Domain, OperationSpec
from so101_teleop.unified.gpu_workload import ActGpuWorkloadArbiter
from so101_teleop.unified.intent_store import IntentStore


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _write_policy(tmp_path):
    payload = {
        "schema_version": 1,
        "policy_id": "synthetic-admission-test",
        "thresholds": {
            "minimum_bilateral_force_n": 0.1,
            "maximum_compression_distance_m": 0.001,
            "maximum_safe_force_n": 2.0,
            "maximum_hold_linear_speed_m_s": 0.01,
            "minimum_stable_hold_duration_s": 0.1,
        },
        "evaluation": {"maximum_observation_age_s": 0.2, "minimum_consecutive_samples": 2},
        "allowed_other_contact_bodies": [],
        "mujoco_version": "3.12.0",
        "model_sha256": "1" * 64,
        "scene_sha256": "2" * 64,
        "motion_policy_sha256": "3" * 64,
        "source_evidence_sha256": "4" * 64,
        "collector_sha256": "5" * 64,
        "live_collector_sha256": "6" * 64,
        "analyzer_sha256": "7" * 64,
        "config_sha256": "8" * 64,
    }
    fingerprint = hashlib.sha256(_canonical(payload)).hexdigest()
    regimes = ("no_contact", "bilateral_touch", "over_compression", "micro_lift_slip", "stable_hold")
    proposal = {
        "status": "DISABLED", "payload": payload, "policy_fingerprint": fingerprint,
        "source_evidence_sha256": payload["source_evidence_sha256"],
        "counts": {name: {"offline": 20, "live": 5} for name in regimes},
        "negative_controls": {"table_only": ["no_contact"], "post_release": ["no_contact"],
                              "left_only": ["left_only"], "right_only": ["right_only"]},
        "confusion_matrix": {name: {name: 5} for name in regimes},
        "false_positive_rate": 0, "false_negative_rate": 0,
    }
    proposal["proposal_sha256"] = hashlib.sha256(_canonical(proposal)).hexdigest()
    receipt = {
        "policy_fingerprint": fingerprint,
        "source_evidence_sha256": payload["source_evidence_sha256"],
        "approved_by": "synthetic-test", "approval_reference": "test-only",
        "approved_at": "2026-09-25T00:00:00+00:00", "evidence_root": str(tmp_path),
    }
    proposal_path = tmp_path / "proposal.json"
    receipt_path = tmp_path / "activation.json"
    proposal_path.write_text(json.dumps(proposal))
    return fingerprint, proposal_path, receipt_path, receipt


def _start_spec(tmp_path, fingerprint, proposal_path, receipt_path, *, backend="mujoco"):
    artifacts = {}
    for name in ("source", "manifest", "runtime_config", "collection_config"):
        path = tmp_path / f"{name}.json"
        if not path.exists():
            path.write_bytes(_canonical({"artifact": name, "campaign_id": "campaign-1"}))
        artifacts[f"{name}_path"] = str(path)
        artifacts[f"{name}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return OperationSpec(
        command_id="start-1", domain=Domain.VALIDATION, kind="task8_phase",
        payload={
            "campaign_id": "campaign-1", "backend": backend, "worker_count": 1,
            **artifacts,
            "contact_policy_fingerprint": fingerprint, "proposal_path": str(proposal_path),
            "activation_receipt_path": str(receipt_path), "evidence_root": str(tmp_path),
            "service_epoch": "epoch-1", "resource_binding_id": "binding-1",
            "qualification_mode": False,
            "qualification_receipt_path": None,
            "children": [launch("w00", 40, "session-0").__dict__],
        },
        runtime_id="runtime-1", execution_generation=3, deadline_ns=time.monotonic_ns() + 10**12,
    )


def _service(store):
    clock = time.monotonic_ns
    return UnifiedWorkloadService(
        arbiter=GlobalMutationArbiter(store, clock_ns=clock),
        gpu_arbiter=ActGpuWorkloadArbiter(store, clock_ns=clock),
        child_registry=ActChildRegistry(),
        service_epoch="epoch-1", runtime_id="runtime-1",
        stable_host_id="ai-station-1", gpu_selector="INDEX:0",
        visible_physical_uuids=("GPU-physical-a",), resource_binding_id="binding-1",
        owner_pid=os.getpid(), owner_started_ticks=1,
        owner_identity_valid=lambda pid, start: pid == os.getpid() and start == 1,
        clock_ns=clock,
    )


def context() -> AdmittedCampaignContext:
    return AdmittedCampaignContext(
        campaign_id="campaign-1",
        operation_id="operation-1",
        workload_kind="task8_phase",
        service_epoch="epoch-1",
        execution_generation=3,
        stable_host_id="ai-station-1",
        physical_gpu_uuid="GPU-physical-a",
        worker_count=8,
        source_sha256="f" * 64,
        manifest_sha256="a" * 64,
        runtime_config_sha256="b" * 64,
        collection_config_sha256="c" * 64,
        contact_policy_fingerprint="d" * 64,
        domain_session_map_sha256="e" * 64,
        resource_binding_id="binding-1",
        evidence_root="/data/work/so101-evidence/act-data/task",
        admitted_at_monotonic_s=12.5,
        deadline_monotonic_s=30.0,
    )


def test_admitted_context_round_trips_without_identity_loss():
    original = context()
    assert AdmittedCampaignContext.from_dict(original.to_dict()) == original
    with pytest.raises(FrozenInstanceError):
        original.worker_count = 1
    with pytest.raises(ValueError, match="CAMPAIGN_CONTEXT_SCHEMA"):
        AdmittedCampaignContext.from_dict({**original.to_dict(), "unreviewed": True})


def launch(worker_id: str, domain_id: int, session_id: str) -> ActChildLaunch:
    return ActChildLaunch(
        campaign_id="campaign-1",
        worker_id=worker_id,
        execution_generation=3,
        ros_domain_id=domain_id,
        namespace=f"/act/{worker_id}",
        controller_name=f"{worker_id}_controller",
        mujoco_session_id=session_id,
        socket_root=f"/tmp/act-child/{worker_id}",
    )


def test_one_child_per_campaign_worker_generation_and_isolated_resources():
    registry = ActChildRegistry()
    for index in range(8):
        registry.register(launch(f"w{index:02d}", 40 + index, f"session-{index}"))
    assert len(registry.launches()) == 8
    with pytest.raises(ValueError, match="DUPLICATE_CHILD"):
        registry.register(launch("w00", 60, "new-session"))
    with pytest.raises(ValueError, match="ROS_DOMAIN_SHARED"):
        registry.register(launch("w08", 40, "session-8"))
    with pytest.raises(ValueError, match="MUJOCO_SESSION_SHARED"):
        registry.register(launch("w08", 48, "session-0"))


def test_start_without_activation_receipt_creates_no_owner_resources(tmp_path):
    fingerprint, proposal_path, receipt_path, _ = _write_policy(tmp_path)
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="POLICY_NOT_ACTIVATED"):
            service.start(_start_spec(tmp_path, fingerprint, proposal_path, receipt_path))
        assert service.child_registry.launches() == ()
        assert service.arbiter.is_idle()
        assert store._query_one("SELECT * FROM gpu_workload_leases") is None
    finally:
        store.close()


def test_start_refuses_gazebo_before_reserving_resources(tmp_path):
    fingerprint, proposal_path, receipt_path, receipt = _write_policy(tmp_path)
    receipt_path.write_text(json.dumps(receipt))
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="MUJOCO_ONLY"):
            service.start(_start_spec(tmp_path, fingerprint, proposal_path, receipt_path, backend="gazebo"))
        assert service.child_registry.launches() == ()
        assert service.arbiter.is_idle()
    finally:
        store.close()


def test_start_persists_exact_context_and_reserves_gpu_and_validation(tmp_path):
    fingerprint, proposal_path, receipt_path, receipt = _write_policy(tmp_path)
    receipt_path.write_text(json.dumps(receipt))
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        admitted = service.start(_start_spec(tmp_path, fingerprint, proposal_path, receipt_path))
        assert admitted.contact_policy_fingerprint == fingerprint
        assert admitted.worker_count == 1
        assert admitted.physical_gpu_uuid == "GPU-physical-a"
        assert len(service.child_registry.launches()) == 1
        assert not service.arbiter.is_idle()
        assert json.loads(store._query_one("SELECT context_json FROM act_campaign_contexts")[0]) == admitted.to_dict()
    finally:
        store.close()


def test_start_refuses_visible_gpu_mapping_drift_before_any_resource(tmp_path):
    fingerprint, proposal_path, receipt_path, receipt = _write_policy(tmp_path)
    receipt_path.write_text(json.dumps(receipt))
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        service.gpu_inventory_probe = lambda: ("GPU-other",)
        with pytest.raises(ValueError, match="GPU_MAPPING_DRIFT"):
            service.start(_start_spec(tmp_path, fingerprint, proposal_path, receipt_path))
        assert service.child_registry.launches() == ()
        assert service.arbiter.is_idle()
        assert store._query_one("SELECT * FROM gpu_workload_leases") is None
    finally:
        store.close()


@pytest.mark.parametrize("name", ("source", "manifest", "runtime_config", "collection_config"))
def test_start_rejects_changed_artifact_bytes_before_any_resource(tmp_path, name):
    fingerprint, proposal_path, receipt_path, receipt = _write_policy(tmp_path)
    receipt_path.write_text(json.dumps(receipt))
    spec = _start_spec(tmp_path, fingerprint, proposal_path, receipt_path)
    (tmp_path / f"{name}.json").write_text("tampered")
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="CAMPAIGN_ARTIFACT_HASH_MISMATCH"):
            service.start(spec)
        assert service.child_registry.launches() == ()
        assert service.arbiter.is_idle()
        assert store._query_one("SELECT * FROM gpu_workload_leases") is None
    finally:
        store.close()


def test_start_registry_race_does_not_commit_parent_or_gpu_lease(tmp_path):
    fingerprint, proposal_path, receipt_path, receipt = _write_policy(tmp_path)
    receipt_path.write_text(json.dumps(receipt))
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        original_validate = service._validate_start
        foreign = launch("w00", 40, "session-0")

        def competing_registration(spec):
            result = original_validate(spec)
            service.child_registry.register(foreign)
            return result

        service._validate_start = competing_registration
        with pytest.raises(ValueError, match="DUPLICATE_CHILD"):
            service.start(_start_spec(tmp_path, fingerprint, proposal_path, receipt_path))
        assert service.child_registry.launches() == (foreign,)
        assert service.arbiter.is_idle()
        assert store._query_one("SELECT * FROM gpu_workload_leases") is None
        assert store._query_one("SELECT * FROM act_campaign_contexts") is None
    finally:
        store.close()


def test_formal_w8_without_exact_qualification_has_no_resources(tmp_path):
    fingerprint, proposal_path, receipt_path, receipt = _write_policy(tmp_path)
    receipt_path.write_text(json.dumps(receipt))
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        base = _start_spec(tmp_path, fingerprint, proposal_path, receipt_path)
        payload = dict(base.payload, worker_count=8, children=[
            launch(f"w{index:02d}", 40 + index, f"session-{index}").__dict__
            for index in range(8)
        ])
        formal = replace(base, kind="act_collection_start", payload=payload)
        with pytest.raises(ValueError, match="W8_QUALIFICATION_REQUIRED"):
            service.start(formal)
        assert service.child_registry.launches() == ()
        assert service.arbiter.is_idle()
        assert store._query_one("SELECT * FROM gpu_workload_leases") is None
    finally:
        store.close()


def test_formal_w8_rejects_a_self_declared_passed_json_without_independent_verifier(tmp_path):
    fingerprint, proposal_path, receipt_path, receipt = _write_policy(tmp_path)
    receipt_path.write_text(json.dumps(receipt))
    base = _start_spec(tmp_path, fingerprint, proposal_path, receipt_path)
    fake_path = tmp_path / "qualification.json"
    fake_path.write_text(json.dumps({
        "status": "PASSED", "worker_count": 8,
        "source_sha256": base.payload["source_sha256"],
        "runtime_config_sha256": base.payload["runtime_config_sha256"],
        "collection_config_sha256": base.payload["collection_config_sha256"],
        "contact_policy_fingerprint": fingerprint,
    }))
    payload = dict(base.payload, worker_count=8, qualification_receipt_path=str(fake_path),
                   children=[launch(f"w{index:02d}", 40 + index, f"session-{index}").__dict__
                             for index in range(8)])
    formal = replace(base, kind="act_collection_start", payload=payload)
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        with pytest.raises(ValueError, match="W8_QUALIFICATION_VERIFIER_UNAVAILABLE"):
            service.start(formal)
        assert service.child_registry.launches() == ()
        assert service.arbiter.is_idle()
        assert store._query_one("SELECT * FROM gpu_workload_leases") is None
    finally:
        store.close()


def test_finish_requires_cleanup_proof_and_releases_exact_owned_resources(tmp_path):
    fingerprint, proposal_path, receipt_path, receipt = _write_policy(tmp_path)
    receipt_path.write_text(json.dumps(receipt))
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        context = service.start(_start_spec(tmp_path, fingerprint, proposal_path, receipt_path))
        with pytest.raises(ValueError, match="ACT_CHILD_CLEANUP_NOT_CONFIRMED"):
            service.finish(context, cleanup_confirmed=False)
        assert service.child_registry.launches()
        assert store._query_one("SELECT * FROM gpu_workload_leases") is not None
        assert not service.arbiter.is_idle()

        with pytest.raises(ValueError, match="CAMPAIGN_CONTEXT_MISMATCH"):
            service.finish(replace(context, physical_gpu_uuid="GPU-foreign"), cleanup_confirmed=True)
        assert service.child_registry.launches()
        assert store._query_one("SELECT * FROM gpu_workload_leases") is not None
        assert not service.arbiter.is_idle()

        projection = service.finish(context, cleanup_confirmed=True)
        assert projection.operation_id == context.operation_id
        assert service.arbiter.is_idle()
        assert store._query_one("SELECT * FROM gpu_workload_leases") is None
        assert service.child_registry.launches() == ()
        assert store._query_one("SELECT * FROM act_campaign_contexts") is not None
        assert service.finish(context, cleanup_confirmed=True) == projection
    finally:
        store.close()


def test_registry_release_many_never_drops_foreign_child_on_mismatch():
    registry = ActChildRegistry()
    first = launch("w00", 40, "session-0")
    second = launch("w01", 41, "session-1")
    registry.register(first)
    registry.register(second)
    with pytest.raises(ValueError, match="CHILD_RELEASE_MISMATCH"):
        registry.release_many((first, replace(second, mujoco_session_id="foreign")))
    assert registry.launches() == (first, second)
    registry.release_many((first, second))
    assert registry.launches() == ()


def test_finish_keeps_gpu_and_children_when_action_terminal_is_unknown(tmp_path):
    from so101_teleop.unified.contracts import MutationError

    fingerprint, proposal_path, receipt_path, receipt = _write_policy(tmp_path)
    receipt_path.write_text(json.dumps(receipt))
    store = IntentStore.open(tmp_path / "state")
    try:
        service = _service(store)
        context = service.start(_start_spec(tmp_path, fingerprint, proposal_path, receipt_path))
        service.arbiter.prepare_child(context.operation_id, "w00")
        with pytest.raises(MutationError, match="UNCONVERGED_CHILD"):
            service.finish(context, cleanup_confirmed=True)
        assert service.child_registry.launches()
        assert store._query_one("SELECT * FROM gpu_workload_leases") is not None
        assert service.arbiter.is_blocked()
    finally:
        store.close()
