"""F2: the installed factory, CLI and allocator compose the SAME budget provider."""

import hashlib
import json
import os
from pathlib import Path

import pytest

SHA = "a" * 64


def _write(path: Path, document) -> str:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = json.dumps(document, sort_keys=True).encode()
    path.write_bytes(payload)
    path.chmod(0o600)
    return hashlib.sha256(payload).hexdigest()


def _dims(value):
    return {"ram_bytes": value, "gpu_bytes": value, "cpu_core_equivalent": value}


def _stage():
    return {"demand": _dims(1.0), "uncertainty": _dims(0.1), "background": _dims(1.0),
            "tool_overhead": _dims(0.1), "available_headroom": _dims(1.0)}


def fingerprint():
    """The current runtime fingerprint; its sha256 is the exact-N execution identity."""

    from so101_demo.parallel_batch.resource_budget import ResourceBudgetProvider  # noqa: F401
    from so101_demo.parallel_batch.resource_identity import (
        RuntimeFingerprint, normalization_sha256)
    return RuntimeFingerprint(
        2, {"gpu_uuid": "GPU-1", "fixture": "synthetic"},
        normalization_sha256(), "c" * 64, "d" * 64, "e" * 64)


def synthetic_authority(tmp_path: Path, worker_count: int = 4, identity: str | None = None):
    """Task-owned synthetic P/Q/M/D authority confined to this fixture."""

    identity = identity or fingerprint().sha256
    qualification = {
        "schema_version": 2, "execution_identity_sha256": identity,
        "worker_count": worker_count, "coverage_policy_sha256": "b" * 64,
        "sealed_manifest_sha256s": ["d" * 64], "normal_valid_runs": 5,
        "normal_required_runs": 5, "coverage_complete": True, "cleanup_verified": True,
        "independent_physics_verified": True, "resource_contract_verified": True,
    }
    qualification_path = tmp_path / "authority/qualification.json"
    qualification_sha = _write(qualification_path, qualification)
    profile = {
        "schema_version": 2, "execution_identity_sha256": identity,
        "coverage_policy_sha256": "b" * 64,
        "entries": {
            str(worker_count): {
                "worker_count": worker_count, "status": "APPROVED",
                "qualification_sha256": qualification_sha,
                "raw_manifest_sha256s": ["d" * 64],
                "coverage": {cell: ["observed"] for cell in (
                    "COLD_START", "STEADY_YOLO", "STEADY_GROUNDED_SAM", "STEADY_MIXED",
                    "MOTION_RELEASE", "BROKER_RELOAD_WITH_N_RESIDENT",
                    "WORKER_RECOVERY_WITH_N_RESIDENT", "FINALIZATION_CLEANUP")},
                "stages": {name: _stage() for name in
                           ("startup", "steady", "recovery", "finalization")},
                "review_reference": "astra:synthetic-fixture",
            }
        },
    }
    profile_path = tmp_path / "sealed/profile.json"
    profile_sha = _write(profile_path, profile)
    promotion_path = tmp_path / "authority/promotion.json"
    promotion_sha = _write(promotion_path, {
        "schema_version": 2, "kind": "PROMOTION", "profile_sha256": profile_sha,
        "exact_worker_count": worker_count, "operator_approval_uid": os.getuid(),
        "reviews": ["sol:synthetic", "astra:synthetic"],
    })
    receipt_path = tmp_path / "authority/deployment.json"
    _write(receipt_path, {
        "schema_version": 2, "kind": "DEPLOYMENT_RECEIPT", "profile_sha256": profile_sha,
        "promotion_sha256": promotion_sha, "location_binding": {"prefix": str(tmp_path)},
    })
    return {
        "profile_path": str(profile_path), "profile_sha256": profile_sha,
        "promotion_path": str(promotion_path),
        "deployment_receipt_path": str(receipt_path),
        "qualification_paths": {str(worker_count): str(qualification_path)},
        "execution_identity_sha256": identity,
        "worker_count": worker_count,
        "profile_sha": profile_sha,
        "qualification_sha": qualification_sha,
    }


def _environment(authority, tmp_path):
    return {
        "SO101_VALIDATION_BUDGET_PROFILE": authority["profile_path"],
        "SO101_VALIDATION_BUDGET_PROFILE_SHA256": authority["profile_sha256"],
        "SO101_VALIDATION_PROMOTION_RECORD": authority["promotion_path"],
        "SO101_VALIDATION_DEPLOYMENT_RECEIPT": authority["deployment_receipt_path"],
        "SO101_VALIDATION_QUALIFICATION_PATHS": json.dumps(
            authority["qualification_paths"], sort_keys=True),
        "SO101_VALIDATION_EXECUTION_IDENTITY": authority["execution_identity_sha256"],
        "SO101_VALIDATION_EVIDENCE_ROOT": str(tmp_path / "evidence"),
    }


def _live(admitted=True):
    from so101_demo.parallel_batch.resource_budget import LiveResourceObservation
    dims = {"ram_bytes": 1000.0, "gpu_bytes": 1000.0, "cpu_core_equivalent": 10.0}
    return LiveResourceObservation(
        monotonic_s=1.0, capacity=dims,
        observed={"ram_bytes": 100.0, "gpu_bytes": 100.0, "cpu_core_equivalent": 0.1},
        background={"ram_bytes": 10.0, "gpu_bytes": 10.0, "cpu_core_equivalent": 0.1},
        tool_overhead={"ram_bytes": 1.0, "gpu_bytes": 1.0, "cpu_core_equivalent": 0.01},
        remaining={"ram_bytes": 10.0, "gpu_bytes": 10.0, "cpu_core_equivalent": 0.1},
        error={"ram_bytes": 1.0, "gpu_bytes": 1.0, "cpu_core_equivalent": 0.01},
        attribution_complete=admitted, swap_delta=0, psi_full_delta=0.0, throttled=False)


def test_installed_production_composes_the_shared_gate(tmp_path):
    from so101_demo.parallel_batch.resource_budget import (
        FixedAdmissionRequest, compose_production_admission)
    from so101_demo.parallel_batch.resource_identity import RuntimeFingerprint

    current = fingerprint()
    authority = synthetic_authority(tmp_path, 4, current.sha256)
    environment = _environment(authority, tmp_path)
    gate = compose_production_admission(
        environment=environment, live_observation=_live(), current=current)
    assert gate is not None
    admitted = gate.admit(FixedAdmissionRequest(
        worker_count=4, batch_id="batch-a", epoch=1,
        execution_identity_sha256=authority["execution_identity_sha256"],
        request_kind="FIXED_PRODUCTION"))
    assert admitted.admitted is True, admitted.reason_codes
    assert admitted.profile_sha256 == authority["profile_sha"]

    unqualified = gate.admit(FixedAdmissionRequest(
        worker_count=3, batch_id="batch-a", epoch=1,
        execution_identity_sha256=authority["execution_identity_sha256"],
        request_kind="FIXED_PRODUCTION"))
    assert unqualified.admitted is False
    assert "EXACT_N_UNQUALIFIED" in unqualified.reason_codes


def test_three_consumers_agree_through_the_composed_gate(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import _prepare_live_headroom
    from so101_demo.parallel_batch.resource_budget import (
        compose_production_admission, FixedAdmissionRequest)
    from so101_demo.parallel_batch.resource_identity import RuntimeFingerprint
    from so101_teleop.expert_validation.production import _HostResourceProbe
    from so101_demo.parallel_batch.contracts import (
        FixedExecutionConfigV2, load_parallel_runtime_config_v2)
    import so101_demo

    current = fingerprint()
    authority = synthetic_authority(tmp_path, 4, current.sha256)
    environment = _environment(authority, tmp_path)
    gate = compose_production_admission(
        environment=environment, live_observation=_live(), current=current)

    # 1. Web probe through the installed factory.
    admitted, reasons, _ = _HostResourceProbe(resource_gate=gate).probe(
        None, FixedExecutionConfigV2(2, "PARALLEL", 4))
    assert admitted, reasons
    refused, refused_reasons, _ = _HostResourceProbe(resource_gate=gate).probe(
        None, FixedExecutionConfigV2(2, "PARALLEL", 5))
    assert refused is False and "EXACT_N_UNQUALIFIED" in refused_reasons

    # 2. CLI prepare path.
    class Options:
        live_headroom_evidence = None
        live_headroom_acceptance = None
        live_headroom_current_provenance_root = None
        batch_id = "batch-a"

    config = load_parallel_runtime_config_v2(
        Path(so101_demo.__file__).resolve().parents[1]
        / "config/mujoco/parallel_batch_v2.yaml")
    admitted_headroom, _, _, _ = _prepare_live_headroom(
        Options(), config, 4, resource_gate=gate)

    # 3. Allocator path.
    from so101_demo.parallel_batch.resources import (
        ResourceAllocationError, WorkerResourceAllocator)

    allocator = WorkerResourceAllocator(
        config, tmp_path / "evidence/alloc", probe=None, base_environment={},
        claim_root=tmp_path / "claims", resource_gate=gate)
    try:
        headroom = allocator._live_headroom(4)
        assert headroom["profile_sha256"] == authority["profile_sha"]
        with pytest.raises(ResourceAllocationError) as error:
            allocator._live_headroom(5)
        assert "EXACT_N_UNQUALIFIED" in str(error.value)
    finally:
        allocator.close()
    del admitted_headroom


def test_missing_or_tampered_authority_refuses_without_downgrade(tmp_path):
    from so101_demo.parallel_batch.resource_budget import compose_production_admission
    from so101_demo.parallel_batch.resource_identity import RuntimeFingerprint

    assert compose_production_admission(environment={}) is None

    current = fingerprint()
    authority = synthetic_authority(tmp_path, 4, current.sha256)
    environment = _environment(authority, tmp_path)
    Path(authority["profile_path"]).write_bytes(b'{"tampered": true}')
    with pytest.raises(Exception) as error:
        compose_production_admission(
            environment=environment, live_observation=_live(), current=current)
    assert "HASH_MISMATCH" in str(error.value)

    # Current-resource drift refuses the requested N instead of downgrading to another.
    authority = synthetic_authority(tmp_path / "drift", 4, current.sha256)
    environment = _environment(authority, tmp_path / "drift")
    gate = compose_production_admission(
        environment=environment, live_observation=_live(admitted=False), current=current)
    from so101_demo.parallel_batch.resource_budget import FixedAdmissionRequest
    decision = gate.admit(FixedAdmissionRequest(
        worker_count=4, batch_id="batch-a", epoch=1,
        execution_identity_sha256=authority["execution_identity_sha256"],
        request_kind="FIXED_PRODUCTION"))
    assert decision.admitted is False
    assert decision.worker_count == 4
    assert "BACKGROUND_ENVELOPE_EXCEEDED" in decision.reason_codes


class _FakeExecutionPort:
    """Typed bounded execution boundary: no workload is started offline."""

    def __init__(self):
        self.launches = []

    def start(self, *args, **kwargs):  # pragma: no cover - never reached offline
        self.launches.append((args, kwargs))
        raise AssertionError("offline test must not launch a workload")


def test_installed_factory_service_derives_capabilities_from_the_gate(tmp_path):
    """The actual installed factory composes the gate and reports provider decisions."""

    import so101_demo
    from so101_teleop.expert_validation.production import create_production_service
    from so101_demo.parallel_batch.resource_budget import compose_production_admission

    current = fingerprint()
    authority = synthetic_authority(tmp_path, 4, current.sha256)
    environment = _environment(authority, tmp_path)
    environment["SO101_VALIDATION_PARALLEL_CONFIG"] = str(
        Path(so101_demo.__file__).resolve().parents[1]
        / "config/mujoco/parallel_batch_v2.yaml")

    def admission_factory(env):
        return compose_production_admission(
            environment=env, live_observation=_live(), current=current)

    service = create_production_service(
        tmp_path / "evidence/service", environment=environment,
        execution_port=_FakeExecutionPort(), admission_factory=admission_factory)
    try:
        capabilities = service.capabilities()
        by_count = {
            entry["worker_count"]: entry
            for entry in capabilities["worker_count_availability"]
        }
        assert by_count[4]["selectable"] is True, by_count[4]
        assert by_count[4]["status"] == "APPROVED"
        assert by_count[4]["profile_sha256"] == authority["profile_sha"]
        assert by_count[4]["qualification_sha256"] == authority["qualification_sha"]
        for count in (2, 3, 5, 6, 7, 8):
            assert by_count[count]["selectable"] is False, count
            assert "EXACT_N_UNQUALIFIED" in by_count[count]["reason_codes"], count
        # No downgrade: the qualified count stays the only selectable one.
        assert [c for c, entry in by_count.items() if entry["selectable"]] == [4]
    finally:
        service.store.close()


def test_installed_factory_without_authority_reports_unmeasured(tmp_path):
    import so101_demo
    from so101_teleop.expert_validation.production import create_production_service

    environment = {
        "SO101_VALIDATION_PARALLEL_CONFIG": str(
            Path(so101_demo.__file__).resolve().parents[1]
            / "config/mujoco/parallel_batch_v2.yaml"),
    }
    service = create_production_service(
        tmp_path / "evidence/no-authority", environment=environment,
        execution_port=_FakeExecutionPort())
    try:
        capabilities = service.capabilities()
        for entry in capabilities["worker_count_availability"]:
            assert entry["selectable"] is False
            assert entry["status"] == "NOT_MEASURED"
            assert "BUDGET_PROFILE_UNAVAILABLE" in entry["reason_codes"]
    finally:
        service.store.close()
