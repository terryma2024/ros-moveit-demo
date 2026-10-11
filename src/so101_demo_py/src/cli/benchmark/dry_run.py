"""The fixture and actual dry-run subcommands."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import importlib.metadata
from io import BytesIO
from pathlib import Path, PurePosixPath
import platform
from typing import Any, Mapping

import numpy as np
from PIL import Image

from so101_demo.cli.benchmark.assets import _candidate_mask
from so101_demo.cli.benchmark.common import (
    _MODELS,
    _SCENARIOS,
    ActualDryRunSample,
    BenchmarkError,
    _bind_dataset_sha,
    _bind_model_arguments,
    _config_payload,
    _dry_frame_bytes,
    _fixture,
    _frozen_model,
    _load_frozen_config,
    _mapping,
    _preflight_output_root,
    _read_bytes,
    _sha,
    _source_commit,
    _write_index,
    build_actual_dry_run_plan,
    build_dry_run_plan,
)
from so101_demo.core.detection import DetectionFrame
from so101_demo.perception_benchmark.adapters import (
    CollectionMode,
    GroundedSamRawAdapter,
    YoloRawAdapter,
)
from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
    encode_mask_rle,
    read_mask,
    sha256_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    YOLO_MODEL_ID,
    RunKind,
    RuntimeProvenance,
)
from so101_demo.perception_benchmark.dataset.contracts import sha256_file
from so101_demo.perception_benchmark.dataset.loading import load_dataset_inventory


def _handle_fixture_dry_run(arguments: argparse.Namespace) -> int:
    config_payload = _config_payload(arguments.config)
    fixture = _fixture(arguments.adapter_fixture)
    output = arguments.output_root
    _preflight_output_root(output)
    try:
        output.mkdir(parents=False, mode=0o700)
    except FileExistsError as error:
        raise BenchmarkError("OUTPUT_ROOT_ALREADY_EXISTS") from error
    except OSError as error:
        raise BenchmarkError("OUTPUT_ROOT_CREATION_FAILED") from error
    plan = build_dry_run_plan()
    records_per_model: Counter[str] = Counter()
    samples_document: list[dict[str, object]] = []
    for sample in plan.samples:
        scenario_position = _SCENARIOS.index(sample.scenario)
        frame_payload = _dry_frame_bytes(scenario_position, sample.scenario_index)
        frame_relative = f"frames/{sample.formal_sample_index:06d}.png"
        frame_path = output / frame_relative
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        frame_path.write_bytes(frame_payload)
        samples_document.append(
            {
                "formal_sample_index": sample.formal_sample_index,
                "scenario": sample.scenario,
                "image_sha256": sample.image_sha256,
                "image_relpath": frame_relative,
            }
        )
        count = fixture["candidate_counts_by_scenario"][sample.scenario]
        for model in fixture["models"]:
            candidates = []
            for candidate_index in range(count):
                mask = _candidate_mask(sample, candidate_index)
                candidate_id = f"{model}-{candidate_index:03d}"
                mask_relative = (
                    f"masks/{model}/{sample.formal_sample_index:06d}/{candidate_id}.rle.json"
                )
                atomic_write_json(output / mask_relative, encode_mask_rle(mask))
                score = fixture["ranking_scores"][candidate_index]
                candidates.append(
                    {
                        "candidate_id": candidate_id,
                        "label": "plastic_cup",
                        "bbox_xyxy": [
                            int(np.flatnonzero(mask.any(axis=0))[0]),
                            int(np.flatnonzero(mask.any(axis=1))[0]),
                            int(np.flatnonzero(mask.any(axis=0))[-1] + 1),
                            int(np.flatnonzero(mask.any(axis=1))[-1] + 1),
                        ],
                        "mask_relative_path": mask_relative,
                        "ranking_score": score,
                        "ranking_score_source": (
                            "class_confidence" if model == "yolo_seg" else "grounding_box_score"
                        ),
                        "sam_quality": None if model == "yolo_seg" else fixture["sam_quality"],
                    }
                )
            record = {
                "schema_version": "so101-perception-benchmark/dry-run-record-v1",
                "run_kind": "NON_FORMAL_DRY_RUN",
                "formal": False,
                "formal_sample_index": sample.formal_sample_index,
                "scenario": sample.scenario,
                "image_sha256": sample.image_sha256,
                "model": model,
                "model_id": YOLO_MODEL_ID if model == "yolo_seg" else GROUNDED_SAM_MODEL_ID,
                "runtime_device": "fixture",
                "candidates": candidates,
            }
            atomic_write_json(
                output / "records" / f"{sample.formal_sample_index:06d}-{model}.json",
                record,
            )
            records_per_model[model] += 1
    atomic_write_json(
        output / "manifest.json",
        {
            "schema_version": "so101-perception-benchmark/dry-run-manifest-v1",
            "run_kind": "NON_FORMAL_DRY_RUN",
            "formal": False,
            "sample_count": len(plan.samples),
            "model_record_count": sum(records_per_model.values()),
            "records_per_model": dict(sorted(records_per_model.items())),
            "config_sha256": sha256_bytes(config_payload),
            "fixture_sha256": sha256_file(arguments.adapter_fixture),
            "samples": samples_document,
        },
    )
    _write_index(output)
    print(output / "evidence-index.json")
    return 0


def _load_actual_dry_frame(inventory: object, sample: ActualDryRunSample) -> DetectionFrame:
    root_value = getattr(inventory, "dataset_root", None)
    if not isinstance(root_value, Path):
        raise BenchmarkError("DRY_RUN_INVENTORY_INVALID")
    try:
        root = root_value.resolve(strict=True)
    except OSError as error:
        raise BenchmarkError("DRY_RUN_IMAGE_INVALID") from error
    relative = PurePosixPath(sample.image_relpath)
    if (
        relative.is_absolute()
        or "\\" in sample.image_relpath
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise BenchmarkError("DRY_RUN_IMAGE_INVALID")
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise BenchmarkError("DRY_RUN_IMAGE_INVALID")
    path = root.joinpath(*relative.parts)
    try:
        if not path.resolve(strict=True).is_relative_to(root):
            raise BenchmarkError("DRY_RUN_IMAGE_INVALID")
    except OSError as error:
        raise BenchmarkError("DRY_RUN_IMAGE_INVALID") from error
    payload = _read_bytes(path, "DRY_RUN_IMAGE_INVALID")
    if sha256_bytes(payload) != sample.image_sha256:
        raise BenchmarkError("DRY_RUN_IMAGE_SHA256_CHANGED")
    try:
        with Image.open(BytesIO(payload)) as image:
            rgb8 = np.asarray(image.convert("RGB"), dtype=np.uint8)
    except (OSError, ValueError) as error:
        raise BenchmarkError("DRY_RUN_IMAGE_INVALID") from error
    return DetectionFrame(
        rgb8=rgb8,
        source_stamp_ns=sample.source_val_formal_sample_index + 1,
        source_frame_id=sample.image_relpath,
    )


def _runtime_document(value: RuntimeProvenance) -> dict[str, object]:
    return {
        "runtime_device": value.runtime_device,
        "runtime_name": value.runtime_name,
        "runtime_version": value.runtime_version,
        "weights_sha256": value.weights_sha256,
        "environment": dict(value.environment),
    }


def _candidate_document(value: object) -> dict[str, object]:
    mask = getattr(value, "mask", None)
    return {
        "candidate_id": getattr(value, "candidate_id"),
        "label": getattr(value, "label"),
        "bbox_xyxy": list(getattr(value, "bbox_xyxy")),
        "mask": {
            "relative_path": getattr(mask, "relative_path"),
            "sha256": getattr(mask, "sha256"),
            "pixel_count": getattr(mask, "pixel_count"),
            "image_width": getattr(mask, "image_width"),
            "image_height": getattr(mask, "image_height"),
        },
        "ranking_score": getattr(value, "ranking_score"),
        "ranking_score_source": getattr(value, "ranking_score_source"),
        "class_confidence": getattr(value, "class_confidence"),
        "grounding_box_score": getattr(value, "grounding_box_score"),
        "grounding_text_score": getattr(value, "grounding_text_score"),
        "sam_quality": getattr(value, "sam_quality"),
    }


def _timing_document(value: object) -> dict[str, object]:
    return {
        name: getattr(value, name)
        for name in (
            "preprocess_ms",
            "dino_or_yolo_ms",
            "sam_ms",
            "postprocess_ms",
            "selector_ms",
            "total_ms",
        )
    }


def _resource_document(value: object) -> dict[str, object]:
    result = {
        name: getattr(value, name)
        for name in (
            "process_rss_bytes",
            "process_cpu_percent",
            "gpu_memory_allocated_bytes",
            "gpu_memory_reserved_bytes",
            "gpu_utilization_percent",
            "gpu_temperature_celsius",
            "gpu_power_watts",
        )
    }
    result["unavailable_reasons"] = dict(getattr(value, "unavailable_reasons"))
    result["tool_versions"] = dict(getattr(value, "tool_versions"))
    return result


def _actual_model_arguments(
    arguments: argparse.Namespace, model: str, output: Path
) -> argparse.Namespace:
    values = vars(arguments).copy()
    values.update(model=model, output_root=output)
    return argparse.Namespace(**values)


def _validate_actual_result(result: object, *, model: str, device: str, output: Path) -> None:
    expected_id = YOLO_MODEL_ID if model == "yolo_seg" else GROUNDED_SAM_MODEL_ID
    if (
        getattr(result, "model_id", None) != expected_id
        or getattr(result, "runtime_device", None) != device
        or getattr(result, "dtype", None) != "float32"
        or getattr(result, "collection_mode", None) is not CollectionMode.LOW_FLOOR
        or getattr(result, "fallback_used", None) is not False
    ):
        raise BenchmarkError("DRY_RUN_RUNTIME_PROVENANCE_INVALID")
    for candidate in getattr(result, "raw_candidates", ()):
        try:
            read_mask(candidate.mask, output)
        except (OSError, ValueError) as error:
            raise BenchmarkError("DRY_RUN_MASK_INVALID") from error


def _handle_actual_dry_run(arguments: argparse.Namespace) -> int:
    if (arguments.platform, arguments.device) not in {("macos", "mps"), ("linux", "cuda")}:
        raise BenchmarkError("PLATFORM_DEVICE_MISMATCH")
    if arguments.dtype != "float32":
        raise BenchmarkError("DTYPE_INVALID")
    source_commit = _source_commit(arguments.source_commit)
    config = _load_frozen_config(arguments.config)
    model_arguments = {
        model: _actual_model_arguments(arguments, model, arguments.output_root) for model in _MODELS
    }
    for values in model_arguments.values():
        _bind_model_arguments(values, config)
    inventory = _inventory(arguments, config)
    plan = build_actual_dry_run_plan(inventory)
    output = _preflight_output_root(arguments.output_root)
    try:
        output.mkdir(parents=False, mode=0o700)
    except FileExistsError as error:
        raise BenchmarkError("OUTPUT_ROOT_ALREADY_EXISTS") from error
    except OSError as error:
        raise BenchmarkError("OUTPUT_ROOT_CREATION_FAILED") from error

    records_per_model: Counter[str] = Counter()
    model_documents: dict[str, object] = {}
    for model in _MODELS:
        values = model_arguments[model]
        adapter = _raw_adapter(values, config)
        provenance = _runtime_provenance(values)
        if provenance.runtime_device != arguments.device:
            raise BenchmarkError("DRY_RUN_RUNTIME_PROVENANCE_INVALID")
        for sample in plan:
            frame = _load_actual_dry_frame(inventory, sample)
            result = adapter.collect(frame, CollectionMode.LOW_FLOOR)
            _validate_actual_result(
                result,
                model=model,
                device=arguments.device,
                output=output,
            )
            atomic_write_json(
                output / "records" / f"{sample.dry_sample_index:06d}-{model}.json",
                {
                    "schema_version": "so101-perception-benchmark/actual-dry-run-record-v1",
                    "run_kind": RunKind.NON_FORMAL_DRY_RUN.value,
                    "formal": False,
                    "dry_sample_index": sample.dry_sample_index,
                    "source_val_formal_sample_index": sample.source_val_formal_sample_index,
                    "split": "val",
                    "scenario": sample.scenario,
                    "image_relpath": sample.image_relpath,
                    "image_sha256": sample.image_sha256,
                    "model": model,
                    "model_id": result.model_id,
                    "runtime_provenance": _runtime_document(provenance),
                    "dtype": result.dtype,
                    "collection_mode": result.collection_mode.value,
                    "fallback_used": result.fallback_used,
                    "phase_timings": _timing_document(result.phase_timings),
                    "resource_samples": [
                        _resource_document(item) for item in result.resource_samples
                    ],
                    "irreversible_limits": dict(result.irreversible_limits),
                    "raw_count": len(result.raw_candidates),
                    "raw_candidates": [
                        _candidate_document(candidate) for candidate in result.raw_candidates
                    ],
                },
            )
            records_per_model[model] += 1
        model_documents[model] = _runtime_document(provenance)

    samples_document = [asdict(sample) for sample in plan]
    report = {
        "schema_version": "so101-perception-benchmark/actual-dry-run-report-v1",
        "run_kind": RunKind.NON_FORMAL_DRY_RUN.value,
        "formal": False,
        "platform": arguments.platform,
        "device": arguments.device,
        "dtype": arguments.dtype,
        "fallback_used": False,
        "sample_count": len(plan),
        "model_record_count": sum(records_per_model.values()),
        "records_per_model": dict(sorted(records_per_model.items())),
        "missing_sample_count": 0,
    }
    atomic_write_json(output / "report.json", report)
    (output / "report.md").write_text(
        "# NON_FORMAL_DRY_RUN\n\n"
        f"- Platform: `{arguments.platform}`\n"
        f"- Device: `{arguments.device}`\n"
        "- Dtype: `float32`\n"
        "- CPU fallback: `false`\n"
        "- Samples: `8` (two per scenario)\n"
        "- Model records: `16`\n"
        "- Missing samples: `0`\n",
        encoding="utf-8",
    )
    atomic_write_json(
        output / "manifest.json",
        {
            "schema_version": "so101-perception-benchmark/actual-dry-run-manifest-v1",
            "execution_mode": "actual",
            "run_kind": RunKind.NON_FORMAL_DRY_RUN.value,
            "formal": False,
            "platform": arguments.platform,
            "device": arguments.device,
            "dtype": arguments.dtype,
            "fallback_used": False,
            "source_commit": source_commit,
            "dataset_archive_sha256": inventory.archive_sha256,
            "inventory_sha256": inventory.inventory_sha256,
            "config_sha256": sha256_bytes(_config_payload(arguments.config)),
            "sample_count": len(plan),
            "model_record_count": sum(records_per_model.values()),
            "records_per_model": dict(sorted(records_per_model.items())),
            "models": model_documents,
            "samples": samples_document,
        },
    )
    _write_index(output)
    print(output / "evidence-index.json")
    return 0


def _handle_dry_run(arguments: argparse.Namespace) -> int:
    actual_names = (
        "platform",
        "device",
        "dtype",
        "dataset_inventory",
        "dataset_archive_sha256",
        "inventory_sha256",
        "weights",
        "weights_sha256",
        "model_root",
        "manifest_sha256",
        "source_commit",
    )
    actual_values = tuple(getattr(arguments, name, None) for name in actual_names)
    if arguments.adapter_fixture is not None:
        if any(value is not None for value in actual_values):
            raise BenchmarkError("DRY_RUN_MODE_MIXED")
        return _handle_fixture_dry_run(arguments)
    if any(value is None for value in actual_values):
        raise BenchmarkError("DRY_RUN_ACTUAL_ARGUMENTS_REQUIRED")
    return _handle_actual_dry_run(arguments)


def _inventory(arguments: argparse.Namespace, config: Mapping[str, Any]):
    _bind_dataset_sha(arguments.dataset_archive_sha256, config)
    kwargs: dict[str, object] = {
        "expected_split": arguments.split,
        "expected_archive_sha256": arguments.dataset_archive_sha256,
        "expected_inventory_sha256": arguments.inventory_sha256,
    }
    if arguments.split == "test":
        kwargs.update(
            {
                "expected_test_access_event_sha256": arguments.test_access_event_sha256,
                "expected_sealed_member_inventory_sha256": arguments.sealed_member_inventory_sha256,
                "expected_threshold_lock_sha256s": (
                    arguments.yolo_lock_sha256,
                    arguments.grounded_sam_lock_sha256,
                ),
                "expected_access_log_path": arguments.test_access_log,
            }
        )
    return load_dataset_inventory(arguments.dataset_inventory.parent, **kwargs)


class _FrozenRawAdapter:
    def __init__(self, delegate: object, model: str, model_config: Mapping[str, Any]) -> None:
        self._delegate = delegate
        self._model = model
        self._low_floor = dict(_mapping(model_config.get("low_floor"), "CONFIG_INVALID"))
        self.model_id = getattr(delegate, "model_id", None)
        self.runtime_device = getattr(delegate, "runtime_device", None)
        if model == "yolo_seg":
            self._weights_sha256 = getattr(delegate, "_weights_sha256", None)
        else:
            self._manifest_sha256 = getattr(delegate, "_manifest_sha256", None)

    def collect(self, frame: object, mode: object):
        result = self._delegate.collect(frame, mode)
        limits = dict(result.irreversible_limits)
        if self._model == "yolo_seg":
            expected = {
                "nms_iou": self._low_floor["nms_iou"],
                "max_det": self._low_floor["max_det"],
            }
            if limits != expected:
                raise BenchmarkError("LOW_FLOOR_CONFIG_MISMATCH")
        else:
            expected = {
                "box_threshold": self._low_floor["box_threshold"],
                "text_threshold": self._low_floor["text_threshold"],
                "sam_quality_floor": self._low_floor["sam_quality_threshold"],
                "min_mask_pixels": 64,
                "max_mask_area_ratio": 0.50,
            }
            if limits != expected or len(result.raw_candidates) > int(
                self._low_floor["maximum_candidates"]
            ):
                raise BenchmarkError("LOW_FLOOR_CONFIG_MISMATCH")
        return result


def _raw_adapter(arguments: argparse.Namespace, config: Mapping[str, Any]):
    if arguments.model == "yolo_seg":
        delegate = YoloRawAdapter.from_weights(
            weights_path=arguments.weights,
            expected_sha256=arguments.weights_sha256,
            requested_device=arguments.device,
            model_id=YOLO_MODEL_ID,
            evidence_root=arguments.output_root,
        )
    else:
        delegate = GroundedSamRawAdapter.from_bundle(
            arguments.model_root,
            expected_manifest_sha256=arguments.manifest_sha256,
            requested_device=arguments.device,
            evidence_root=arguments.output_root,
        )
    return _FrozenRawAdapter(delegate, arguments.model, _frozen_model(config, arguments.model))


def _model_asset_sha(arguments: argparse.Namespace) -> str:
    return arguments.weights_sha256 if arguments.model == "yolo_seg" else arguments.manifest_sha256


def _installed_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError as error:
        raise BenchmarkError("RUNTIME_PROVENANCE_UNAVAILABLE") from error


def _runtime_provenance(arguments: argparse.Namespace) -> RuntimeProvenance:
    runtime_distribution = "ultralytics" if arguments.model == "yolo_seg" else "transformers"
    return RuntimeProvenance(
        runtime_device=arguments.device,
        runtime_name=runtime_distribution,
        runtime_version=_installed_version(runtime_distribution),
        weights_sha256=_sha(_model_asset_sha(arguments), "MODEL_ASSET_SHA256_INVALID"),
        environment={
            "numpy": _installed_version("numpy"),
            "pillow": _installed_version("Pillow"),
            "python": platform.python_version(),
            "torch": _installed_version("torch"),
        },
    )
