"""The public run loader and its verification rounds."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from perception_benchmark_runner_support import (
    SHA_A,
    SHA_B,
    SHA_C,
    SOURCE_COMMIT,
    SyntheticAdapter,
    _formal_yolo_lock,
    _locked_inventory,
    _record,
    _record_inventory_digest,
    _spec,
    _synthetic_inventory,
)
import pytest

from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    YOLO_MODEL_ID,
    RunKind,
    RunStatus,
    RuntimeProvenance,
)
from so101_demo.perception_benchmark.dataset import truth as dataset_module_truth
from so101_demo.perception_benchmark.runner.contracts import (
    RunEvidenceExpectation,
    RunIntegrityError,
)
from so101_demo.perception_benchmark.runner.detector_runner import DetectorBenchmarkRunner
from so101_demo.perception_benchmark.runner.resume import load_verified_run_evidence
from so101_demo.perception_benchmark.runner.storage import LoadedRunEvidence


def _evidence_expectation(**overrides: object) -> RunEvidenceExpectation:
    values: dict[str, object] = {
        "run_id": "fixture-val-raw",
        "run_kind": RunKind.VAL_RAW,
        "platform": "macos",
        "model": "yolo_seg",
        "device": "mps",
        "dtype": "float32",
        "source_commit": SOURCE_COMMIT,
        "config_sha256": SHA_A,
        "threshold_lock_sha256": None,
        "model_id": YOLO_MODEL_ID,
        "weights_sha256": SHA_B,
        "runtime_name": "synthetic-runtime",
        "runtime_version": "fixture-1",
        "runtime_environment": {"fixture": "runner", "torch": "2.8.0"},
        "max_gpu_temperature_celsius": None,
    }
    values.update(overrides)
    return RunEvidenceExpectation(**values)  # type: ignore[arg-type]


def test_public_run_loader_returns_immutable_full_verified_evidence(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    expected_manifest = DetectorBenchmarkRunner(
        SyntheticAdapter(output_root), output_root
    ).run(_spec(inventory, output_root))

    loaded = load_verified_run_evidence(
        output_root, inventory, _evidence_expectation()
    )

    assert isinstance(loaded, LoadedRunEvidence)
    assert loaded.evidence_root == output_root.resolve(strict=True)
    assert loaded.manifest == expected_manifest
    assert len(loaded.records) == 200
    assert len(loaded.extended_record_documents) == 200
    assert loaded.records[199].formal_sample_index == 199
    with pytest.raises(TypeError):
        loaded.extended_record_documents[0]["platform"] = "linux"  # type: ignore[index]
    with pytest.raises(TypeError):
        loaded.manifest.runtime_environment["fixture"] = "changed"  # type: ignore[index]


def test_public_run_loader_accepts_verified_terminal_tree_relocation(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    producer_root = tmp_path / "producer" / "run"
    producer_root.mkdir(parents=True)
    expected_manifest = DetectorBenchmarkRunner(
        SyntheticAdapter(producer_root), producer_root
    ).run(_spec(inventory, producer_root))
    relocated_root = tmp_path / "durable" / "renamed-run"
    shutil.copytree(producer_root, relocated_root)

    checkpoint = json.loads((relocated_root / "checkpoint.json").read_bytes())
    assert checkpoint["records_dir"] == str(producer_root / "records")

    loaded = load_verified_run_evidence(
        relocated_root, inventory, _evidence_expectation()
    )

    assert loaded.evidence_root == relocated_root.resolve(strict=True)
    assert loaded.manifest == expected_manifest
    assert len(loaded.records) == 200

    checkpoint["records_dir"] = str(tmp_path / "not-records")
    atomic_write_json(relocated_root / "checkpoint.json", checkpoint)
    with pytest.raises(RunIntegrityError, match="RESUME_RECORDS_DIRECTORY_CHANGED"):
        load_verified_run_evidence(
            relocated_root, inventory, _evidence_expectation()
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("run_kind", RunKind.TEST_RAW_FROZEN),
        ("platform", "linux"),
        ("model", "grounded_sam"),
        ("device", "cuda"),
        ("source_commit", "cafebabe" * 5),
        ("config_sha256", SHA_C),
        ("threshold_lock_sha256", SHA_C),
        ("model_id", GROUNDED_SAM_MODEL_ID),
        ("weights_sha256", SHA_C),
        ("runtime_name", "other-runtime"),
        ("runtime_version", "other-version"),
        ("runtime_environment", {"fixture": "changed"}),
        ("max_gpu_temperature_celsius", 80.0),
    ),
)
def test_public_run_loader_rejects_external_expectation_mismatch(
    tmp_path: Path, field: str, value: object
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    expectation = replace(_evidence_expectation(), **{field: value})

    with pytest.raises(RunIntegrityError):
        load_verified_run_evidence(output_root, inventory, expectation)


def test_public_run_expectation_rejects_non_fp32_dtype() -> None:
    with pytest.raises(ValueError, match="dtype must be float32"):
        replace(_evidence_expectation(), dtype="float16")


def _rewrite_terminal_anchors(root: Path) -> None:
    record_path = root / "records/000199.json"
    record_sha = hashlib.sha256(record_path.read_bytes()).hexdigest()
    checkpoint_path = root / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_bytes())
    checkpoint["last_record_sha256"] = record_sha
    checkpoint["record_inventory_sha256"] = _record_inventory_digest(root)
    atomic_write_json(checkpoint_path, checkpoint)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["record_chain_head_sha256"] = record_sha
    manifest["record_inventory_sha256"] = checkpoint["record_inventory_sha256"]
    atomic_write_json(manifest_path, manifest)


@pytest.mark.parametrize(
    "mutation",
    (
        "running-manifest",
        "partial-records",
        "extra-record",
        "tail-tamper",
        "extra-document-field",
        "resource-mismatch",
        "mask-tamper",
        "image-tamper",
    ),
)
def test_public_run_loader_rejects_partial_tampered_or_extended_schema_drift(
    tmp_path: Path, mutation: str
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    manifest_path = output_root / "manifest.json"
    terminal_before = manifest_path.read_bytes()
    if mutation == "running-manifest":
        manifest = json.loads(terminal_before)
        manifest["status"] = "RUNNING"
        manifest["ended_at"] = None
        atomic_write_json(manifest_path, manifest)
        terminal_before = manifest_path.read_bytes()
    elif mutation == "partial-records":
        (output_root / "records/000199.json").unlink()
    elif mutation == "extra-record":
        (output_root / "records/000200.json").write_bytes(b"{}\n")
    elif mutation == "tail-tamper":
        record_path = output_root / "records/000199.json"
        record_path.write_bytes(record_path.read_bytes() + b" ")
    elif mutation in {"extra-document-field", "resource-mismatch"}:
        record_path = output_root / "records/000199.json"
        document = json.loads(record_path.read_bytes())
        if mutation == "extra-document-field":
            document["unexpected"] = "forbidden"
        else:
            document["resource_samples"][0]["process_cpu_percent"] = -1.0
        atomic_write_json(record_path, document)
        _rewrite_terminal_anchors(output_root)
        terminal_before = manifest_path.read_bytes()
    elif mutation == "mask-tamper":
        record = _record(output_root, 199)
        mask = output_root / record["raw_candidates"][0]["mask"]["relative_path"]
        mask.write_bytes(mask.read_bytes() + b" ")
    else:
        image = inventory.dataset_root / inventory.samples[199].image_relpath
        image.write_bytes(image.read_bytes() + b"drift")

    with pytest.raises(RunIntegrityError):
        load_verified_run_evidence(
            output_root, inventory, _evidence_expectation()
        )

    assert manifest_path.read_bytes() == terminal_before


def test_public_run_loader_requires_exact_full_inventory_denominator(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 8)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )

    with pytest.raises(RunIntegrityError, match="TERMINAL_RUN_DENOMINATOR_INCOMPLETE"):
        load_verified_run_evidence(
            output_root, inventory, _evidence_expectation()
        )


def test_public_run_loader_verifies_registered_test_lock_chain(
    tmp_path: Path,
) -> None:
    lock = _formal_yolo_lock()
    inventory, lock_path, access_log = _locked_inventory(
        tmp_path / "locked", lock, count=200
    )
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(
        inventory,
        output_root,
        run_id="public-locked",
        run_kind=RunKind.TEST_RAW_FROZEN,
        threshold_lock_sha256=lock.lock_sha256,
        threshold_lock_path=lock_path,
    )
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(spec)
    expectation = _evidence_expectation(
        run_id="public-locked",
        run_kind=RunKind.TEST_RAW_FROZEN,
        threshold_lock_sha256=lock.lock_sha256,
    )
    assert len(
        load_verified_run_evidence(output_root, inventory, expectation).records
    ) == 200

    access_log.write_bytes(access_log.read_bytes() + b"{}\n")
    with pytest.raises(RunIntegrityError, match="INVENTORY_ACCESS_CHAIN_INVALID"):
        load_verified_run_evidence(output_root, inventory, expectation)


def test_runner_honors_relocated_access_log_bound_into_inventory_capability(
    tmp_path: Path,
) -> None:
    lock = _formal_yolo_lock()
    inventory, lock_path, producer_access_log = _locked_inventory(
        tmp_path / "producer", lock, count=200
    )
    relocated_root = tmp_path / "relocated-dataset"
    shutil.copytree(inventory.dataset_root, relocated_root)
    relocated_access_log = tmp_path / "relocated-test-access.jsonl"
    shutil.copy2(producer_access_log, relocated_access_log)
    producer_access_log.rename(tmp_path / "producer-access-log-moved.jsonl")
    relocated_inventory = replace(
        inventory,
        dataset_root=relocated_root,
        access_log_path=relocated_access_log,
    )
    dataset_module_truth._issue_inventory(relocated_inventory)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(
        relocated_inventory,
        output_root,
        run_id="relocated-locked",
        run_kind=RunKind.TEST_RAW_FROZEN,
        threshold_lock_sha256=lock.lock_sha256,
        threshold_lock_path=lock_path,
    )

    manifest = DetectorBenchmarkRunner(
        SyntheticAdapter(output_root), output_root
    ).run(spec)

    assert manifest.status is RunStatus.VALID
    assert manifest.record_count == 200


def test_round1_public_run_loader_rejects_another_valid_run_id(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root, run_id="other-valid-run")
    )

    with pytest.raises(RunIntegrityError, match="RUN_EVIDENCE_EXPECTATION_MISMATCH"):
        load_verified_run_evidence(output_root, inventory, _evidence_expectation())


def test_round1_public_run_loader_rejects_runtime_wildcard_for_self_consistent_drift(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    drifted = RuntimeProvenance(
        runtime_device="mps",
        runtime_name="drifted-runtime",
        runtime_version="drifted-2",
        weights_sha256=SHA_B,
        environment={"fixture": "drifted", "torch": "2.9.0"},
    )
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root, runtime_provenance=drifted)
    )

    with pytest.raises((ValueError, RunIntegrityError)):
        wildcard = replace(
            _evidence_expectation(),
            runtime_name=None,
            runtime_version=None,
            runtime_environment=None,
        )
        load_verified_run_evidence(output_root, inventory, wildcard)


@pytest.mark.parametrize(
    ("field", "value"),
    (("started_at", False), ("ended_at", True)),
)
def test_round1_public_run_loader_rejects_non_string_manifest_timestamps(
    tmp_path: Path, field: str, value: object
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    manifest_path = output_root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest[field] = value
    atomic_write_json(manifest_path, manifest)

    with pytest.raises(RunIntegrityError, match="MANIFEST_SCHEMA_INVALID"):
        load_verified_run_evidence(output_root, inventory, _evidence_expectation())


def test_round1_public_run_loader_rejects_boolean_checkpoint_count(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    checkpoint_path = output_root / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_bytes())
    checkpoint["error_count"] = False
    atomic_write_json(checkpoint_path, checkpoint)

    with pytest.raises(RunIntegrityError, match="CHECKPOINT_SCHEMA_INVALID"):
        load_verified_run_evidence(output_root, inventory, _evidence_expectation())


@pytest.mark.parametrize(
    ("filename", "error_code"),
    (
        ("manifest.json", "MANIFEST_SCHEMA_INVALID"),
        ("checkpoint.json", "CHECKPOINT_SCHEMA_INVALID"),
    ),
)
def test_round1_public_run_loader_rejects_normalizable_environment_type_drift(
    tmp_path: Path, filename: str, error_code: str
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    document_path = output_root / filename
    document = json.loads(document_path.read_bytes())
    document["runtime_environment"] = [
        ["fixture", "runner"],
        ["torch", "2.8.0"],
    ]
    atomic_write_json(document_path, document)

    with pytest.raises(RunIntegrityError, match=error_code):
        load_verified_run_evidence(output_root, inventory, _evidence_expectation())


def test_round1_public_run_loader_rejects_hardlinked_terminal_file(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    os.link(output_root / "manifest.json", tmp_path / "external-manifest.json")

    with pytest.raises(RunIntegrityError, match="RUN_EVIDENCE_FILE_UNSAFE"):
        load_verified_run_evidence(output_root, inventory, _evidence_expectation())


@pytest.mark.parametrize(
    "alias_base",
    (Path("/tmp"), Path(tempfile.gettempdir())),
    ids=("tmp-alias", "default-var-alias"),
)
def test_round2_public_run_loader_accepts_macos_system_ancestor_aliases(
    alias_base: Path,
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="so101-public-run-", dir=alias_base
    ) as temporary:
        workspace = Path(temporary)
        inventory = _synthetic_inventory(workspace, 200)
        output_root = workspace / "run"
        output_root.mkdir()
        DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
            _spec(inventory, output_root)
        )

        loaded = load_verified_run_evidence(
            output_root, inventory, _evidence_expectation()
        )

        assert loaded.evidence_root == output_root.resolve(strict=True)
        assert len(loaded.records) == 200


def test_round2_public_run_loader_rejects_final_root_symlink(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    linked_root = tmp_path / "linked-run"
    linked_root.symlink_to(output_root, target_is_directory=True)

    with pytest.raises(RunIntegrityError, match="RUN_EVIDENCE_ROOT_INVALID"):
        load_verified_run_evidence(
            linked_root, inventory, _evidence_expectation()
        )


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    (
        ("runtime-environment", "RECORD_SCHEMA_INVALID"),
        ("tool-versions", "RECORD_RESOURCE_INVALID"),
        ("unavailable-reasons", "RECORD_RESOURCE_INVALID"),
    ),
)
def test_round2_public_run_loader_rejects_normalizable_nested_record_mappings(
    tmp_path: Path, mutation: str, error_code: str
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    record_path = output_root / "records/000199.json"
    document = json.loads(record_path.read_bytes())
    if mutation == "runtime-environment":
        document["runtime_provenance"]["environment"] = [
            ["fixture", "runner"],
            ["torch", "2.8.0"],
        ]
    elif mutation == "tool-versions":
        document["resource_samples"][0]["tool_versions"] = [["fixture", "1"]]
    else:
        reasons = document["resource_samples"][0]["unavailable_reasons"]
        document["resource_samples"][0]["unavailable_reasons"] = list(
            reasons.items()
        )
    atomic_write_json(record_path, document)
    _rewrite_terminal_anchors(output_root)

    with pytest.raises(RunIntegrityError, match=error_code):
        load_verified_run_evidence(
            output_root, inventory, _evidence_expectation()
        )
