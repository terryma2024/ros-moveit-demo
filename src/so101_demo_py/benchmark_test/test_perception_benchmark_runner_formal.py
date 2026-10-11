"""Formal threshold locks, masks, prior manifests and the running manifest."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

from perception_benchmark_runner_support import (
    SHA_A,
    SHA_B,
    SHA_C,
    SyntheticAdapter,
    _formal_yolo_lock,
    _locked_inventory,
    _record,
    _record_inventory_digest,
    _runtime_provenance,
    _spec,
    _synthetic_inventory,
)
import pytest

from so101_demo.perception_benchmark.adapters import (
    ResourceSamplingError,
)
from so101_demo.perception_benchmark.calibration.lock_io import write_threshold_lock
from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
)
from so101_demo.perception_benchmark.contracts import (
    RunKind,
    RunStatus,
    RuntimeProvenance,
)
from so101_demo.perception_benchmark.runner.detector_runner import DetectorBenchmarkRunner


@pytest.mark.parametrize(
    "variant", ("bare", "wrong-model", "fixture", "posthoc", "unregistered")
)
def test_formal_test_requires_verified_pre_access_model_lock_without_log_mutation(
    tmp_path: Path, variant: str
) -> None:
    """Catch a hex digest, fixture/post-hoc lock, or unregistered lock opening test."""

    formal = _formal_yolo_lock(
        formal=variant != "fixture",
        model="grounded_sam" if variant == "wrong-model" else "yolo_seg",
    )
    inventory, lock_path, access_log = _locked_inventory(
        tmp_path,
        formal,
        write_lock_before_access=variant != "posthoc",
    )
    selected_lock = formal
    if variant == "unregistered":
        selected_lock = replace(formal, lock_sha256="0" * 64).with_recomputed_sha256()
        write_threshold_lock(lock_path, selected_lock)
    before = access_log.read_bytes()
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root)
    spec = _spec(
        inventory,
        output_root,
        run_id=f"locked-{variant}",
        run_kind=RunKind.TEST_RAW_FROZEN,
        threshold_lock_sha256=(
            formal.lock_sha256 if variant == "bare" else selected_lock.lock_sha256
        ),
        threshold_lock_path=None if variant == "bare" else lock_path,
    )

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(spec)

    assert manifest.status is RunStatus.INVALID
    assert adapter.calls == []
    assert access_log.read_bytes() == before


def test_verified_registered_lock_runs_without_touching_access_log(
    tmp_path: Path,
) -> None:
    lock = _formal_yolo_lock()
    inventory, lock_path, access_log = _locked_inventory(tmp_path, lock)
    before = access_log.read_bytes()
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root)

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            inventory,
            output_root,
            run_id="locked-valid",
            run_kind=RunKind.TEST_RAW_FROZEN,
            threshold_lock_sha256=lock.lock_sha256,
            threshold_lock_path=lock_path,
        )
    )

    assert manifest.status is RunStatus.VALID
    assert adapter.calls == [0]
    assert access_log.read_bytes() == before


@pytest.mark.parametrize(
    ("platform", "device"), (("macos", "cuda"), ("linux", "mps"))
)
def test_platform_device_pair_is_fail_closed_before_model_call(
    tmp_path: Path, platform: str, device: str
) -> None:
    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root)
    adapter.runtime_device = device  # type: ignore[assignment]

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            inventory,
            output_root,
            platform=platform,
            device=device,
            runtime_provenance=_runtime_provenance(device=device),
        )
    )

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == "PLATFORM_DEVICE_MISMATCH"
    assert adapter.calls == []


def test_adapter_asset_digest_must_match_supplied_runtime_provenance(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root)
    adapter._weights_sha256 = SHA_C

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(inventory, output_root)
    )

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == "RUNTIME_WEIGHTS_PROVENANCE_MISMATCH"
    assert adapter.calls == []


def test_resource_failure_is_typed_not_message_classified(tmp_path: Path) -> None:
    inventory = _synthetic_inventory(tmp_path, 2)
    typed_root = tmp_path / "typed"
    typed_root.mkdir()
    typed = SyntheticAdapter(
        typed_root, failures={0: ResourceSamplingError("telemetry failed")}
    )
    typed_manifest = DetectorBenchmarkRunner(typed, typed_root).run(
        _spec(inventory, typed_root)
    )
    assert typed_manifest.status is RunStatus.INVALID
    assert typed_manifest.invalid_reason == "RESOURCE_EVIDENCE_FAILED"

    ordinary_root = tmp_path / "ordinary"
    ordinary_root.mkdir()
    ordinary = SyntheticAdapter(
        ordinary_root, failures={0: RuntimeError("resource sampler failed")}
    )
    ordinary_manifest = DetectorBenchmarkRunner(ordinary, ordinary_root).run(
        _spec(inventory, ordinary_root)
    )
    assert ordinary_manifest.status is RunStatus.VALID
    assert ordinary_manifest.record_count == 2
    assert ordinary_manifest.error_count == 1


def test_record_masks_are_republished_to_exact_canonical_layout(tmp_path: Path) -> None:
    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root)

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(inventory, output_root)
    )

    assert manifest.status is RunStatus.VALID
    mask = _record(output_root, 0)["raw_candidates"][0]["mask"]
    assert mask["relative_path"] == "masks/000000/yolo-000.rle.json"
    assert (output_root / mask["relative_path"]).is_file()
    assert (output_root / "adapter-masks/000000/yolo-000.rle.json").is_file()


@pytest.mark.parametrize("occupied", ("file", "symlink"))
def test_canonical_mask_target_is_never_overwritten_or_followed(
    tmp_path: Path, occupied: str
) -> None:
    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    if occupied == "file":
        target = output_root / "masks/000000/yolo-000.rle.json"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"user-owned\n")
    else:
        (output_root / "masks").symlink_to(outside, target_is_directory=True)
    adapter = SyntheticAdapter(output_root)

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(inventory, output_root)
    )

    assert manifest.status is RunStatus.INVALID
    records_dir = output_root / "records"
    assert not records_dir.exists() or list(records_dir.iterdir()) == []
    if occupied == "file":
        assert target.read_bytes() == b"user-owned\n"
    else:
        assert list(outside.iterdir()) == []


def test_prior_manifest_detects_last_record_and_checkpoint_rewrite(
    tmp_path: Path,
) -> None:
    """Catch coordinated tail/checkpoint tamper being laundered by a new manifest."""

    inventory = _synthetic_inventory(tmp_path, 2)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(inventory, output_root)
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(spec)
    manifest_path = output_root / "manifest.json"
    prior = json.loads(manifest_path.read_text())
    running = dict(prior)
    running["status"] = "RUNNING"
    running["ended_at"] = None
    running["invalid_reason"] = None
    atomic_write_json(manifest_path, running)

    record_path = output_root / "records/000001.json"
    record = json.loads(record_path.read_text())
    record["timing_breakdown"]["dino_or_yolo_ms"] = 2.0
    record["timing_breakdown"]["total_ms"] = 2.0
    atomic_write_json(record_path, record)
    changed_record_sha = hashlib.sha256(record_path.read_bytes()).hexdigest()
    checkpoint_path = output_root / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text())
    checkpoint["last_record_sha256"] = changed_record_sha
    if "record_inventory_sha256" in checkpoint:
        checkpoint["record_inventory_sha256"] = _record_inventory_digest(output_root)
    atomic_write_json(checkpoint_path, checkpoint)

    resumed = SyntheticAdapter(output_root)
    invalid = DetectorBenchmarkRunner(resumed, output_root).run(spec)

    assert invalid.status is RunStatus.INVALID
    assert invalid.started_at == prior["started_at"]
    assert invalid.record_count == prior["record_count"]
    assert invalid.record_inventory_sha256 == prior["record_inventory_sha256"]
    assert resumed.calls == []


def test_invalid_resume_preserves_original_manifest_identity_and_counts(
    tmp_path: Path,
) -> None:
    """Catch a changed resume spec rewriting the prior run's frozen metadata."""

    inventory = _synthetic_inventory(tmp_path, 2)
    output_root = tmp_path / "run"
    output_root.mkdir()
    original_spec = _spec(inventory, output_root)
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        original_spec
    )
    manifest_path = output_root / "manifest.json"
    prior = json.loads(manifest_path.read_text())
    prior["status"] = "RUNNING"
    prior["ended_at"] = None
    atomic_write_json(manifest_path, prior)
    changed_provenance = RuntimeProvenance(
        runtime_device="mps",
        runtime_name="synthetic-runtime",
        runtime_version="fixture-1",
        weights_sha256=SHA_B,
        environment={"fixture": "changed", "torch": "2.8.0"},
    )
    adapter = SyntheticAdapter(output_root)

    invalid = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            inventory,
            output_root,
            config_sha256=SHA_C,
            runtime_provenance=changed_provenance,
        )
    )

    assert invalid.status is RunStatus.INVALID
    assert invalid.started_at == prior["started_at"]
    assert invalid.config_sha256 == SHA_A
    assert invalid.runtime_environment == {"fixture": "runner", "torch": "2.8.0"}
    assert invalid.record_count == prior["record_count"]
    assert invalid.record_inventory_sha256 == prior["record_inventory_sha256"]
    assert adapter.calls == []


def test_running_manifest_tracks_safe_checkpoint_before_process_interrupt(
    tmp_path: Path,
) -> None:
    """Catch RUNNING metadata remaining at fabricated zero counts after a safe commit."""

    inventory = _synthetic_inventory(tmp_path, 3)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root, failures={1: KeyboardInterrupt()})

    with pytest.raises(KeyboardInterrupt):
        DetectorBenchmarkRunner(adapter, output_root).run(
            _spec(inventory, output_root)
        )

    running = json.loads((output_root / "manifest.json").read_text())
    first_sha = hashlib.sha256(
        (output_root / "records/000000.json").read_bytes()
    ).hexdigest()
    assert running["status"] == "RUNNING"
    assert running["record_count"] == 1
    assert running["error_count"] == 0
    assert running["record_chain_head_sha256"] == first_sha
    assert running["record_inventory_sha256"] == _record_inventory_digest(output_root)
    assert running["ended_at"] is None
