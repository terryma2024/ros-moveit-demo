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




OFFLINE_INSTALL = Path(
    "/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main"
    "/unbounded-queue-resource-budget/offline-install")
OFFLINE_SHARE = OFFLINE_INSTALL / "so101_demo_py/share/so101_demo_py/config/mujoco"
OFFLINE_LIB = OFFLINE_INSTALL / "so101_demo_py/lib/so101_demo_py"
OFFLINE_BINDING = Path(
    "/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main"
    "/unbounded-queue-resource-budget/bindings/offline-provenance.json")


def installed_environment(**overrides):
    """The installed layout environment, pointed at copied (non-symlink) artifacts."""

    environment = {
        "SO101_VALIDATION_POINTS": str(
            OFFLINE_SHARE / "moveit_expert_validation_points_v1.yaml"),
        "SO101_VALIDATION_PARALLEL_CONFIG": str(OFFLINE_SHARE / "parallel_batch_v2.yaml"),
        "SO101_VALIDATION_ADAPTIVE_CONFIG": str(
            OFFLINE_SHARE / "parallel_adaptive_workers_v1.yaml"),
        "SO101_VALIDATION_COORDINATOR_EXECUTABLE": str(OFFLINE_LIB / "so101_parallel_batch"),
        "SO101_VALIDATION_CLEANUP_EXECUTABLE": str(
            OFFLINE_LIB / "so101_parallel_batch_cleanup"),
        "SO101_VALIDATION_ADAPTIVE_WRAPPER": str(OFFLINE_LIB / "run_so101_adaptive_batch.zsh"),
        "SO101_VALIDATION_PROVENANCE_BINDING": str(OFFLINE_BINDING),
        "SO101_VALIDATION_YOLO_WEIGHTS":
            "/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/"
            "optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt",
        "SO101_VALIDATION_GROUNDED_ROOT": "/data/work/so101-models/grounded-sam-v2-scipy-lock",
        "SO101_VALIDATION_BROKER_IMAGE":
            "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1",
    }
    environment.update(overrides)
    return environment


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


def _installed_child_environment(extra: dict) -> dict:
    """PYTHONPATH where both product modules resolve from the copied offline prefix."""

    import sys
    demo = OFFLINE_INSTALL / "so101_demo_py/lib/python3.12/site-packages"
    teleop = OFFLINE_INSTALL / "so101_teleop/lib/python3.12/site-packages"
    support = OFFLINE_INSTALL / "so101_mujoco_support/lib/python3.12/site-packages"
    underlay = [
        "/data/work/ws_mujoco_ros2_control_fork/install/lib/python3.12/site-packages",
        "/data/work/ws_moveit/install/mujoco_ros2_control_msgs/lib/python3.12/site-packages",
        "/opt/ros/jazzy/lib/python3.12/site-packages",
    ]
    test_site = str(Path(sys.executable).resolve().parent.parent / "lib/python3.12/site-packages")
    environment = dict(os.environ)
    environment.update(extra)
    environment["SO101_DISABLE_KIMI_EDITABLE_FINDER"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    environment["SO101_E2E_EVIDENCE_ROOT"] = extra.get(
        "SO101_VALIDATION_EVIDENCE_ROOT", str(Path(extra["SO101_VALIDATION_POINTS"]).parent))
    environment["PYTHONPATH"] = ":".join(
        [str(demo), str(teleop), str(support), *underlay, test_site])
    environment["TMPDIR"] = extra["_TMPDIR"]
    environment["TMP"] = extra["_TMPDIR"]
    environment["TEMP"] = extra["_TMPDIR"]
    return environment


_CHILD_PROGRAM = r"""
import hashlib, json, os, sys, tempfile
from pathlib import Path

EVIDENCE = Path(os.environ["SO101_VALIDATION_EVIDENCE_ROOT"])
AUTHORITY = Path(os.environ["TEST_AUTHORITY_DIR"])
LIVE_DOCUMENT = json.loads(Path(os.environ["TEST_LIVE_OBSERVATION"]).read_text())
CURRENT_DOCUMENT = json.loads(Path(os.environ["TEST_FINGERPRINT"]).read_text())

from so101_demo.parallel_batch.resource_budget import (
    LiveResourceObservation, compose_production_admission)
from so101_demo.parallel_batch.resource_identity import RuntimeFingerprint
from so101_teleop.expert_validation.production import create_production_service


class Port:
    def start(self, *args, **kwargs):  # pragma: no cover - never launched
        raise AssertionError("offline child must not launch a workload")


current = RuntimeFingerprint(
    schema_version=CURRENT_DOCUMENT["schema_version"], facts=CURRENT_DOCUMENT["facts"],
    normalization_sha256=CURRENT_DOCUMENT["normalization_sha256"],
    semantic_config_sha256=CURRENT_DOCUMENT["semantic_config_sha256"],
    execution_inventory_sha256=CURRENT_DOCUMENT["execution_inventory_sha256"],
    installed_inventory_sha256=CURRENT_DOCUMENT["installed_inventory_sha256"])
live = LiveResourceObservation(**{
    **LIVE_DOCUMENT,
    "capacity": LIVE_DOCUMENT["capacity"], "observed": LIVE_DOCUMENT["observed"],
    "background": LIVE_DOCUMENT["background"],
    "tool_overhead": LIVE_DOCUMENT["tool_overhead"],
    "remaining": LIVE_DOCUMENT["remaining"], "error": LIVE_DOCUMENT["error"]})

environment = dict(os.environ)
environment.update(json.loads(Path(os.environ["TEST_AUTHORITY_ENV"]).read_text()))


def admission_factory(env):
    return compose_production_admission(
        environment=env, live_observation=live, current=current)


service = create_production_service(
    EVIDENCE / "service", environment=environment, execution_port=Port(),
    admission_factory=admission_factory)
try:
    capabilities = service.capabilities()
finally:
    service.store.close()
print(json.dumps({"capabilities": capabilities, "tempdir": tempfile.gettempdir()}))
"""


def test_installed_factory_child_reports_provider_derived_capabilities(tmp_path):
    """The actual installed factory, imported from the copied prefix, derives N4."""

    import json as _json
    import subprocess
    import sys

    current = fingerprint()
    authority = synthetic_authority(tmp_path, 4, current.sha256)
    evidence = tmp_path / "evidence"
    evidence.mkdir(mode=0o700, parents=True)
    environment = installed_environment(**_environment(authority, tmp_path))
    environment["SO101_VALIDATION_EVIDENCE_ROOT"] = str(evidence)
    scratch = tmp_path / "tmp"
    scratch.mkdir(mode=0o700, exist_ok=True)

    authority_env = tmp_path / "authority-env.json"
    authority_env.write_text(_json.dumps(environment, sort_keys=True))
    live_path = tmp_path / "live.json"
    live = _live()
    live_path.write_text(_json.dumps({
        "monotonic_s": live.monotonic_s,
        "capacity": dict(live.capacity), "observed": dict(live.observed),
        "background": dict(live.background), "tool_overhead": dict(live.tool_overhead),
        "remaining": dict(live.remaining), "error": dict(live.error),
        "attribution_complete": live.attribution_complete,
        "swap_delta": live.swap_delta, "psi_full_delta": live.psi_full_delta,
        "throttled": live.throttled,
    }, sort_keys=True))
    fingerprint_path = tmp_path / "fingerprint.json"
    fingerprint_path.write_text(_json.dumps(current.as_document(), sort_keys=True))

    child = _installed_child_environment({
        **environment,
        "_TMPDIR": str(scratch),
        "TEST_AUTHORITY_DIR": str(tmp_path / "authority"),
        "TEST_AUTHORITY_ENV": str(authority_env),
        "TEST_LIVE_OBSERVATION": str(live_path),
        "TEST_FINGERPRINT": str(fingerprint_path),
    })
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD_PROGRAM], capture_output=True, text=True,
        env=child, cwd=str(tmp_path))
    assert completed.returncode == 0, completed.stderr[-2000:]
    document = _json.loads(completed.stdout.strip().splitlines()[-1])
    assert document["tempdir"].startswith(str(scratch))
    by_count = {
        entry["worker_count"]: entry
        for entry in document["capabilities"]["worker_count_availability"]
    }
    assert by_count[4]["selectable"] is True, by_count[4]
    assert by_count[4]["profile_sha256"] == authority["profile_sha"]
    assert by_count[4]["qualification_sha256"] == authority["qualification_sha"]
    assert [count for count, entry in by_count.items() if entry["selectable"]] == [4]
    for count in (2, 3, 5, 6, 7, 8):
        assert "EXACT_N_UNQUALIFIED" in by_count[count]["reason_codes"], count
