"""F1: the candidate entry must compose a real, sealed measurement lifecycle."""

import hashlib
import json
import os
import time
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
V2_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v2.yaml"


def _write(path: Path, data: bytes) -> str:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(0o600)
    return hashlib.sha256(data).hexdigest()


def _fixture_root(tmp_path: Path) -> dict:
    points = tmp_path / "models/points.yaml"
    points_sha = _write(points, b"points: [p1, p2]\n")
    weights = tmp_path / "models/yolo.pt"
    weights_sha = _write(weights, b"yolo-weights")
    grounded = tmp_path / "models/grounded"
    grounded.mkdir(mode=0o700, parents=True, exist_ok=True)
    manifest = grounded / "manifest.json"
    manifest_sha = _write(manifest, b'{"models": ["grounded", "sam"]}\n')
    provenance = tmp_path / "bindings/provenance.json"
    provenance_sha = _write(
        provenance,
        json.dumps({
            "schema_version": 1, "kind": "PRODUCTION_COPIED_BINDING",
            "source_root": "/data/work/so101-worktrees/unbounded-queue-resource-budget",
            "source_commit": "a" * 40, "install_prefix": str(tmp_path / "install"),
            "install_kind": "production_copied",
        }).encode(),
    )
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir(mode=0o700, exist_ok=True)
    return {
        "points_path": str(points), "points_sha256": points_sha,
        "yolo_weights_path": str(weights), "yolo_weights_sha256": weights_sha,
        "grounded_root": str(grounded), "grounded_manifest_sha256": manifest_sha,
        "broker_image_id": "sha256:" + "b" * 64,
        "provenance_binding_path": str(provenance),
        "provenance_binding_sha256": provenance_sha,
        "evidence_root": evidence_root,
    }


def authorization_document(tmp_path: Path, bindings: dict, **changes) -> dict:
    document = {
        "schema_version": 2, "operator_uid": os.getuid(), "dispatch_id": "dispatch-a",
        "task_id": "task-a", "source_commit": "a" * 40,
        "execution_identity_sha256": "b" * 64,
        "worker_count": 2, "catalog_sha256": bindings["points_sha256"], "seed": 7,
        "lifecycle": "FULL_RESTART", "maximum_batches": 1, "batch_deadline_s": 5400.0,
        "expires_at_ns": time.time_ns() + 3_600_000_000_000,
        "batch_root": str(bindings["evidence_root"] / "batches"),
        "owned_scope_sha256": "d" * 64, "safety_policy_sha256": "e" * 64,
        "intent": "CALIBRATION_ONLY", "calibration_sha256": None,
        "runtime_bindings": {
            key: value for key, value in bindings.items() if key != "evidence_root"
        },
    }
    document.update(changes)
    return document


def write_authorization(path: Path, document: dict) -> str:
    return _write(path, json.dumps(document, sort_keys=True).encode())


def load_authorization(tmp_path, bindings):
    from so101_demo.parallel_batch.resource_measurement import MeasurementAuthorization
    path = tmp_path / "private/authorization.json"
    digest = write_authorization(path, authorization_document(tmp_path, bindings))
    return MeasurementAuthorization.load(path, expected_sha256=digest), path, digest


def test_authorization_requires_closed_runtime_bindings(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_measurement import MeasurementAuthorization
    bindings = _fixture_root(tmp_path)
    authorization, _, _ = load_authorization(tmp_path, bindings)
    assert authorization.runtime_bindings.broker_image_id == bindings["broker_image_id"]
    assert authorization.runtime_bindings.points_sha256 == bindings["points_sha256"]

    without = authorization_document(tmp_path, bindings)
    del without["runtime_bindings"]
    path = tmp_path / "private/no-bindings.json"
    digest = write_authorization(path, without)
    with pytest.raises(ContractError) as error:
        MeasurementAuthorization.load(path, expected_sha256=digest)
    assert "runtime_bindings" in str(error.value)

    unknown = authorization_document(tmp_path, bindings)
    unknown["runtime_bindings"]["surprise"] = "x"
    path = tmp_path / "private/unknown-binding.json"
    digest = write_authorization(path, unknown)
    with pytest.raises(ContractError) as error:
        MeasurementAuthorization.load(path, expected_sha256=digest)
    assert "RUNTIME_BINDINGS_UNKNOWN_FIELD" in str(error.value)


def test_candidate_plan_verifies_bytes_identity_and_containment(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_measurement import build_candidate_plan
    bindings = _fixture_root(tmp_path)
    authorization, path, _ = load_authorization(tmp_path, bindings)
    plan = build_candidate_plan(
        authorization=authorization, authorization_path=path, config_path=V2_CONFIG,
        evidence_root=bindings["evidence_root"], batch_id="batch-a")
    assert plan.run_mode == "execute"
    assert plan.schema_version == 2 and plan.batch_kind == "FIRST_PASS"
    assert plan.worker_count == 2
    argv = plan.runner_argv()
    for expected in (str(bindings["points_path"]), str(bindings["yolo_weights_path"]),
                     str(bindings["grounded_root"]), str(V2_CONFIG)):
        assert expected in argv
    assert "--max-points-per-worker" not in argv

    tampered = _fixture_root(tmp_path / "tampered")
    tampered["yolo_weights_path"] = bindings["yolo_weights_path"]
    authorization2, path2, _ = load_authorization(tmp_path / "tampered", tampered)
    Path(bindings["yolo_weights_path"]).write_bytes(b"changed")
    with pytest.raises(ContractError) as error:
        build_candidate_plan(
            authorization=authorization2, authorization_path=path2, config_path=V2_CONFIG,
            evidence_root=tampered["evidence_root"], batch_id="batch-a")
    assert "BINDING_HASH_MISMATCH" in str(error.value)

    # A non-absolute declared binding is refused when the sealed document is parsed.
    from so101_demo.parallel_batch.resource_measurement import MeasurementAuthorization
    relative = _fixture_root(tmp_path / "relative")
    relative_document = authorization_document(tmp_path / "relative", relative)
    relative_document["runtime_bindings"]["points_path"] = "relative/points.yaml"
    relative_path = tmp_path / "relative/private/authorization.json"
    relative_digest = write_authorization(relative_path, relative_document)
    with pytest.raises(ContractError) as error:
        MeasurementAuthorization.load(relative_path, expected_sha256=relative_digest)
    assert "BINDING_PATH" in str(error.value)

    # A missing declared file is a plan-time containment refusal.
    missing = _fixture_root(tmp_path / "missing")
    missing_document = authorization_document(tmp_path / "missing", missing)
    missing["points_path"] = str(tmp_path / "missing/models/absent.yaml")
    missing_document = authorization_document(tmp_path / "missing", missing)
    missing_path = tmp_path / "missing/private/authorization.json"
    missing_digest = write_authorization(missing_path, missing_document)
    missing_authorization = MeasurementAuthorization.load(
        missing_path, expected_sha256=missing_digest)
    with pytest.raises(ContractError) as error:
        build_candidate_plan(
            authorization=missing_authorization, authorization_path=missing_path,
            config_path=V2_CONFIG, evidence_root=missing["evidence_root"],
            batch_id="batch-a")
    assert "BINDING_PATH" in str(error.value)


def test_runner_requires_the_real_session_and_sealed_root(tmp_path):
    """The composition refuses a missing session and cannot seal outside the batch."""

    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_measurement import (
        build_candidate_plan, run_candidate_batch, seal_measurement)

    bindings = _fixture_root(tmp_path)
    authorization, path, _ = load_authorization(tmp_path, bindings)
    plan = build_candidate_plan(
        authorization=authorization, authorization_path=path, config_path=V2_CONFIG,
        evidence_root=bindings["evidence_root"], batch_id="batch-a")

    with pytest.raises(ContractError) as error:
        run_candidate_batch(plan=plan, runner=lambda *_args: {}, session=None)
    assert "CANDIDATE_SESSION" in str(error.value)

    coverage = plan.batch_root / "raw/coverage.json"
    _write(coverage, b"{}")
    with pytest.raises(ContractError) as error:
        seal_measurement(
            authorization=authorization,
            execution_identity_sha256=authorization.execution_identity_sha256,
            raw_files=(coverage,), coverage_events=coverage, result={},
            batch_root=tmp_path / "elsewhere")
    assert "BATCH_ROOT_OUTSIDE_AUTHORIZATION" in str(error.value)

    with pytest.raises(ContractError) as error:
        seal_measurement(
            authorization=authorization, execution_identity_sha256="c" * 64,
            raw_files=(coverage,), coverage_events=coverage, result={})
    assert "RUNTIME_FINGERPRINT_MISMATCH" in str(error.value)
