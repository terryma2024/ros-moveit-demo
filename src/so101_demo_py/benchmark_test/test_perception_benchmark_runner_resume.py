"""Resuming a run, terminal manifests, checkpoints and input drift."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from perception_benchmark_runner_support import (
    SHA_A,
    SHA_B,
    SHA_C,
    SOURCE_COMMIT,
    SyntheticAdapter,
    _formal_yolo_lock,
    _locked_inventory,
    _record,
    _spec,
    _synthetic_inventory,
)
import pytest

from so101_demo.perception_benchmark.adapters import (
    CollectionMode,
    RawDetectionResult,
    ResourceSamplingError,
)
from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
)
from so101_demo.perception_benchmark.contracts import (
    RunKind,
    RunStatus,
)
from so101_demo.perception_benchmark.runner.contracts import (
    RunCheckpoint,
    RunIntegrityError,
)
from so101_demo.perception_benchmark.runner.detector_runner import DetectorBenchmarkRunner
from so101_demo.perception_benchmark.runner.resume import verify_resume


def _checkpoint(root: Path) -> RunCheckpoint:
    document = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
    document["records_dir"] = Path(document["records_dir"])
    document["run_kind"] = RunKind(document["run_kind"])
    document["collection_mode"] = CollectionMode(document["collection_mode"])
    return RunCheckpoint(**document)


@pytest.mark.parametrize(
    "mutation",
    (
        "gap",
        "duplicate",
        "record-tamper",
        "record-content-tamper",
        "mask-tamper",
        "checkpoint-sha",
        "config",
        "source",
        "model",
        "device",
        "dtype",
        "run-kind",
        "lock",
        "run-id",
        "platform",
        "model-id",
        "weights",
        "collection-mode",
        "runtime-name",
        "runtime-version",
        "runtime-environment",
        "thermal-limit",
        "record-count",
        "record-inventory",
        "inventory",
    ),
)
def test_resume_rejects_any_noncontiguous_tampered_or_changed_identity(
    tmp_path: Path, mutation: str
) -> None:
    """Catch resume selecting a next filename instead of proving one exact prefix."""

    inventory = _synthetic_inventory(tmp_path, 4)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(inventory, output_root)
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(spec)
    checkpoint = _checkpoint(output_root)

    if mutation == "gap":
        (output_root / "records" / "000001.json").rename(
            output_root / "records" / "000005.json"
        )
    elif mutation == "duplicate":
        document = _record(output_root, 1)
        document["formal_sample_index"] = 0
        atomic_write_json(output_root / "records" / "000001.json", document)
    elif mutation == "record-tamper":
        path = output_root / "records" / "000002.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "record-content-tamper":
        path = output_root / "records" / "000001.json"
        document = _record(output_root, 1)
        document["timing_breakdown"]["dino_or_yolo_ms"] = 2.0
        document["timing_breakdown"]["total_ms"] = 2.0
        atomic_write_json(path, document)
    elif mutation == "mask-tamper":
        mask_path = output_root / _record(output_root, 2)["raw_candidates"][0]["mask"]["relative_path"]
        mask_path.write_bytes(mask_path.read_bytes() + b" ")
    elif mutation == "checkpoint-sha":
        checkpoint = replace(checkpoint, last_record_sha256=SHA_A)
    elif mutation == "config":
        checkpoint = replace(checkpoint, config_sha=SHA_B)
    elif mutation == "source":
        checkpoint = replace(checkpoint, source_commit="cafebabe" * 5)
    elif mutation == "model":
        checkpoint = replace(checkpoint, model="grounded_sam")
    elif mutation == "device":
        checkpoint = replace(checkpoint, device="cuda")
    elif mutation == "dtype":
        checkpoint = replace(checkpoint, dtype="float16")
    elif mutation == "run-kind":
        checkpoint = replace(checkpoint, run_kind=RunKind.TEST_RAW_FROZEN)
    elif mutation == "lock":
        checkpoint = replace(checkpoint, threshold_lock_sha256=SHA_B)
    elif mutation == "run-id":
        checkpoint = replace(checkpoint, run_id="other-run")
    elif mutation == "platform":
        checkpoint = replace(checkpoint, platform="linux")
    elif mutation == "model-id":
        checkpoint = replace(checkpoint, model_id="other-yolo")
    elif mutation == "weights":
        checkpoint = replace(checkpoint, weights_sha256=SHA_C)
    elif mutation == "collection-mode":
        checkpoint = replace(checkpoint, collection_mode=None)
    elif mutation == "runtime-name":
        checkpoint = replace(checkpoint, runtime_name="other-runtime")
    elif mutation == "runtime-version":
        checkpoint = replace(checkpoint, runtime_version="fixture-2")
    elif mutation == "runtime-environment":
        checkpoint = replace(checkpoint, runtime_environment={"fixture": "changed"})
    elif mutation == "thermal-limit":
        checkpoint = replace(checkpoint, max_gpu_temperature_celsius=90.0)
    elif mutation == "record-count":
        checkpoint = replace(checkpoint, record_count=3)
    elif mutation == "record-inventory":
        checkpoint = replace(checkpoint, record_inventory_sha256=SHA_C)
    else:
        checkpoint = replace(checkpoint, inventory_sha256=SHA_C)

    with pytest.raises(RunIntegrityError):
        verify_resume(
            checkpoint,
            inventory,
            config_sha=SHA_A,
            source_commit=SOURCE_COMMIT,
        )


def test_exact_valid_prefix_resumes_without_reprocessing_or_overwriting(
    tmp_path: Path,
) -> None:
    """Catch a complete verified prefix being re-run or its artifacts overwritten."""

    inventory = _synthetic_inventory(tmp_path, 4)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(inventory, output_root)
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(spec)
    before = {
        path.name: path.read_bytes() for path in (output_root / "records").iterdir()
    }
    manifest_before = (output_root / "manifest.json").read_bytes()
    resumed_adapter = SyntheticAdapter(output_root)

    manifest = DetectorBenchmarkRunner(resumed_adapter, output_root).run(spec)

    assert manifest.status is RunStatus.VALID
    assert manifest.record_count == 4
    assert resumed_adapter.calls == []
    assert {
        path.name: path.read_bytes() for path in (output_root / "records").iterdir()
    } == before
    assert (output_root / "manifest.json").read_bytes() == manifest_before


@pytest.mark.parametrize(
    "mutation",
    (
        "delete-mask",
        "delete-record",
        "delete-checkpoint",
        "tamper-tail",
        "change-spec",
        "input-drift",
    ),
)
def test_terminal_valid_rejects_evidence_or_spec_drift_without_rewrite_or_model_call(
    tmp_path: Path, mutation: str
) -> None:
    """Catch terminal VALID bypassing read-only verification on later invocations."""

    inventory = _synthetic_inventory(tmp_path, 2)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(inventory, output_root)
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(spec)
    manifest_path = output_root / "manifest.json"
    manifest_before = manifest_path.read_bytes()
    rerun_spec = spec

    if mutation == "delete-mask":
        mask_path = output_root / _record(output_root, 1)["raw_candidates"][0][
            "mask"
        ]["relative_path"]
        mask_path.unlink()
    elif mutation == "delete-record":
        (output_root / "records/000001.json").unlink()
    elif mutation == "delete-checkpoint":
        (output_root / "checkpoint.json").unlink()
    elif mutation == "tamper-tail":
        record_path = output_root / "records/000001.json"
        document = _record(output_root, 1)
        document["timing_breakdown"]["dino_or_yolo_ms"] = 2.0
        document["timing_breakdown"]["total_ms"] = 2.0
        atomic_write_json(record_path, document)
    elif mutation == "change-spec":
        rerun_spec = replace(spec, config_sha256=SHA_C)
    else:
        image_path = inventory.dataset_root / inventory.samples[1].image_relpath
        image_path.write_bytes(image_path.read_bytes() + b"drift")

    adapter = SyntheticAdapter(output_root)
    with pytest.raises(RunIntegrityError):
        DetectorBenchmarkRunner(adapter, output_root).run(rerun_spec)

    assert adapter.calls == []
    assert manifest_path.read_bytes() == manifest_before


def test_terminal_valid_requires_current_verified_lock_path_without_manifest_rewrite(
    tmp_path: Path,
) -> None:
    """Catch a locked terminal run accepting a missing or substituted lock path."""

    lock = _formal_yolo_lock()
    inventory, lock_path, _ = _locked_inventory(tmp_path / "locked", lock)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(
        inventory,
        output_root,
        run_id="terminal-locked",
        run_kind=RunKind.TEST_RAW_FROZEN,
        threshold_lock_sha256=lock.lock_sha256,
        threshold_lock_path=lock_path,
    )
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(spec)
    manifest_path = output_root / "manifest.json"
    manifest_before = manifest_path.read_bytes()
    changed = replace(spec, threshold_lock_path=tmp_path / "missing-lock.json")
    adapter = SyntheticAdapter(output_root)

    with pytest.raises(RunIntegrityError):
        DetectorBenchmarkRunner(adapter, output_root).run(changed)

    assert adapter.calls == []
    assert manifest_path.read_bytes() == manifest_before


def test_terminal_schema_failure_does_not_rewrite_decodable_terminal_manifest(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(inventory, output_root)
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(spec)
    manifest_path = output_root / "manifest.json"
    document = json.loads(manifest_path.read_bytes())
    document["ended_at"] = None
    atomic_write_json(manifest_path, document)
    terminal_bytes = manifest_path.read_bytes()
    adapter = SyntheticAdapter(output_root)

    with pytest.raises(RunIntegrityError, match="MANIFEST_SCHEMA_INVALID"):
        DetectorBenchmarkRunner(adapter, output_root).run(spec)

    assert adapter.calls == []
    assert manifest_path.read_bytes() == terminal_bytes


@pytest.mark.parametrize("terminal_status", (RunStatus.VALID, RunStatus.INVALID))
@pytest.mark.parametrize("schema_mutation", ("extra-field", "missing-field"))
def test_raw_terminal_manifest_schema_drift_is_read_only_before_strict_loading(
    tmp_path: Path,
    terminal_status: RunStatus,
    schema_mutation: str,
) -> None:
    """Catch strict manifest construction running before raw terminal detection."""

    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(inventory, output_root)
    if terminal_status is RunStatus.INVALID:
        spec = replace(spec, platform="linux", device="mps")
    first = DetectorBenchmarkRunner(
        SyntheticAdapter(output_root), output_root
    ).run(spec)
    assert first.status is terminal_status
    manifest_path = output_root / "manifest.json"
    document = json.loads(manifest_path.read_bytes())
    if schema_mutation == "extra-field":
        document["unexpected_terminal_field"] = "must-not-be-rewritten"
    else:
        del document["runtime_version"]
    atomic_write_json(manifest_path, document)
    terminal_bytes = manifest_path.read_bytes()
    adapter = SyntheticAdapter(output_root)

    with pytest.raises(RunIntegrityError, match="MANIFEST_SCHEMA_INVALID"):
        DetectorBenchmarkRunner(adapter, output_root).run(spec)

    assert adapter.calls == []
    assert manifest_path.read_bytes() == terminal_bytes


def test_terminal_invalid_remains_byte_immutable_and_never_resumes(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(inventory, output_root, platform="linux", device="mps")
    first_adapter = SyntheticAdapter(output_root)
    first = DetectorBenchmarkRunner(first_adapter, output_root).run(spec)
    assert first.status is RunStatus.INVALID
    manifest_path = output_root / "manifest.json"
    manifest_before = manifest_path.read_bytes()
    second_adapter = SyntheticAdapter(output_root)

    second = DetectorBenchmarkRunner(second_adapter, output_root).run(spec)

    assert second.status is RunStatus.INVALID
    assert second_adapter.calls == []
    assert manifest_path.read_bytes() == manifest_before


def test_checkpoint_crash_never_advances_past_durable_record_and_resume_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Catch checkpoint publication before record durability or silent crash repair."""

    inventory = _synthetic_inventory(tmp_path, 5)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root)
    runner = DetectorBenchmarkRunner(adapter, output_root)
    real_write = runner._write_checkpoint

    def crash_at_two(checkpoint: RunCheckpoint) -> None:
        if checkpoint.last_formal_sample_index == 2:
            raise OSError("checkpoint device failed")
        real_write(checkpoint)

    monkeypatch.setattr(runner, "_write_checkpoint", crash_at_two)
    manifest = runner.run(_spec(inventory, output_root))

    assert manifest.status is RunStatus.INVALID
    assert sorted(path.name for path in (output_root / "records").iterdir()) == [
        "000000.json",
        "000001.json",
        "000002.json",
    ]
    assert _checkpoint(output_root).last_formal_sample_index == 1
    resumed = SyntheticAdapter(output_root)
    resumed_manifest = DetectorBenchmarkRunner(resumed, output_root).run(
        _spec(inventory, output_root)
    )
    assert resumed_manifest.status is RunStatus.INVALID
    assert resumed.calls == []


@pytest.mark.parametrize(
    ("adapter_kwargs", "thermal_limit", "reason", "retained"),
    (
        ({"failures": {2: ResourceSamplingError("sensor failed")}}, None, "RESOURCE_EVIDENCE_FAILED", 2),
        ({"empty_resources_at": 2}, None, "RESOURCE_STREAM_EMPTY", 2),
        ({"temperatures": {2: 91.0}}, 80.0, "THERMAL_LIMIT_EXCEEDED", 2),
    ),
)
def test_resource_or_thermal_failure_invalidates_whole_run_and_stops(
    tmp_path: Path,
    adapter_kwargs: dict[str, object],
    thermal_limit: float | None,
    reason: str,
    retained: int,
) -> None:
    """Catch invalid hardware evidence being counted as an ordinary image error."""

    inventory = _synthetic_inventory(tmp_path, 5)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root, **adapter_kwargs)
    spec = _spec(
        inventory,
        output_root,
        max_gpu_temperature_celsius=thermal_limit,
    )

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(spec)

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == reason
    assert manifest.record_count == retained
    assert adapter.calls == list(range(retained + 1))
    assert sorted((output_root / "records").glob("*.json")) == [
        output_root / "records" / f"{index:06d}.json"
        for index in range(retained)
    ]
    resumed = SyntheticAdapter(output_root)
    resumed_manifest = DetectorBenchmarkRunner(resumed, output_root).run(spec)
    assert resumed_manifest.status is RunStatus.INVALID
    assert resumed.calls == []


def test_resume_detects_current_input_drift_and_inventory_document_tamper(
    tmp_path: Path,
) -> None:
    """Catch resume trusting stale record metadata over current immutable inputs."""

    inventory = _synthetic_inventory(tmp_path, 3)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    checkpoint = _checkpoint(output_root)

    image_path = inventory.dataset_root / inventory.samples[2].image_relpath
    image_path.write_bytes(image_path.read_bytes() + b"drift")
    with pytest.raises(RunIntegrityError, match="INPUT_IMAGE_SHA256_CHANGED"):
        verify_resume(checkpoint, inventory, SHA_A, SOURCE_COMMIT)

    image_path.write_bytes(image_path.read_bytes()[:-5])
    inventory_path = inventory.dataset_root / "inventory.json"
    inventory_path.write_bytes(inventory_path.read_bytes() + b" ")
    with pytest.raises(RunIntegrityError, match="INVENTORY_CANONICAL_INVALID"):
        verify_resume(checkpoint, inventory, SHA_A, SOURCE_COMMIT)


def test_adapter_mask_is_verified_before_record_or_checkpoint_publication(
    tmp_path: Path,
) -> None:
    """Catch a stale MaskRef being committed before its lossless mask is verified."""

    class MissingMaskAdapter(SyntheticAdapter):
        def collect(self, frame: object, mode: CollectionMode) -> RawDetectionResult:
            result = super().collect(frame, mode)
            mask_path = self.evidence_root / result.raw_candidates[0].mask.relative_path
            mask_path.unlink()
            return result

    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = MissingMaskAdapter(output_root)

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(inventory, output_root)
    )

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == "RECORD_MASK_PATH_INVALID"
    assert list((output_root / "records").iterdir()) == []
    assert not (output_root / "checkpoint.json").exists()


def test_preexisting_record_or_symlink_output_is_never_overwritten(
    tmp_path: Path,
) -> None:
    """Catch runner writes escaping or replacing evidence it does not own."""

    inventory = _synthetic_inventory(tmp_path, 1)
    occupied = tmp_path / "occupied"
    (occupied / "records").mkdir(parents=True)
    original = b"user-owned\n"
    (occupied / "records" / "000000.json").write_bytes(original)
    adapter = SyntheticAdapter(occupied)
    manifest = DetectorBenchmarkRunner(adapter, occupied).run(
        _spec(inventory, occupied)
    )
    assert manifest.status is RunStatus.INVALID
    assert adapter.calls == []
    assert (occupied / "records" / "000000.json").read_bytes() == original

    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    linked_adapter = SyntheticAdapter(outside)
    linked_manifest = DetectorBenchmarkRunner(linked_adapter, linked).run(
        _spec(inventory, linked)
    )
    assert linked_manifest.status is RunStatus.INVALID
    assert linked_adapter.calls == []
    assert list(outside.iterdir()) == []
