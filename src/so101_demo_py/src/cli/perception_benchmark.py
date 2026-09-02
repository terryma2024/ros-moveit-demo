"""Fail-closed command line entry point for the perception benchmark."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import re
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, fields, replace
from functools import partial
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

import numpy as np
import yaml
from PIL import Image
from so101_demo.adapters.perception.detector_factory import DetectorFactoryOptions
from so101_demo.adapters.perception.grounded_sam import GroundedSamDetector
from so101_demo.adapters.perception.grounded_sam_postprocess import GroundedSamThresholds
from so101_demo.adapters.perception.model_bundle import verify_model_bundle
from so101_demo.adapters.perception.model_runtime import ModelSetupError
from so101_demo.adapters.perception.yolo_seg import verify_weights
from so101_demo.perception_benchmark.adapters import (
    CollectionMode,
    GroundedSamRawAdapter,
    VerifiedBenchmarkAssets,
    YoloCalibratedDetector,
    YoloRawAdapter,
    build_calibrated_detector_port,
    build_production_detector_port,
    run_production_detector_port,
)
from so101_demo.perception_benchmark.calibration import (
    CalibrationError,
    calibrate_joint_platform_val,
    unlock_test_seal,
    verify_threshold_lock,
    write_threshold_lock,
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
    PredictionRecord,
    RunKind,
    RuntimeProvenance,
)
from so101_demo.perception_benchmark.dataset import (
    DatasetArchiveVerifier,
    DatasetVerificationError,
    TestSeal,
    load_dataset_inventory,
    load_truth_samples,
    sha256_file,
)
from so101_demo.perception_benchmark.reporting import (
    AggregationInput,
    ColdProcessSample,
    EvidenceEntry,
    EvidenceIndex,
    MetricsAggregator,
    ReportWriter,
    ResourceObservation,
    ResourceTrace,
    RunAggregationEvidence,
    load_evidence_index,
    verify_evidence_index,
)
from so101_demo.perception_benchmark.runner import (
    DetectorBenchmarkRunner,
    RunEvidenceExpectation,
    RunSpec,
    load_verified_run_evidence,
)
from so101_demo.perception_benchmark.timing import ResourceSample

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SCENARIOS = (
    "no_cup",
    "one_cup_distractors",
    "two_cups",
    "cup_near_bottle",
)
_MODELS = ("yolo_seg", "grounded_sam")
_INDEX_SCHEMA = "so101-perception-benchmark/evidence-index/v1"
_INDEX_SEMANTICS = "payload files only; evidence-index.json is excluded to avoid self-reference"
_CONFIG_SHA256 = "2317bca5a5399a0b3b5410aaa3aa8bd31c1f160736120d9bb558fcc0d1c3b2f5"
_ARCHIVE_ID = (
    "datasets/so101-v5-t004-yolo-seg-synthetic/"
    "so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz"
)
_ARCHIVE_SHA256 = "c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1"
_YOLO_WEIGHTS_SHA256 = "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781"
_GROUNDED_MANIFEST_SHA256 = "838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3"
_GROUNDING_DINO_REVISION = "a2bb814dd30d776dcf7e30523b00659f4f141c71"
_SAM_REVISION = "de431c4043854a71d8101e17995dfe596bf101a5"


class BenchmarkError(ValueError):
    """Stable, path-sanitized CLI error."""

    def __init__(self, code: str, detail: str = "benchmark command rejected") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class DryRunSample:
    formal_sample_index: int
    scenario: str
    scenario_index: int
    image_sha256: str


@dataclass(frozen=True, slots=True)
class DryRunPlan:
    samples: tuple[DryRunSample, ...]
    formal: bool = False


def _dry_frame_bytes(scenario_index: int, ordinal: int) -> bytes:
    color = (31 + scenario_index * 47, 41 + ordinal * 73, 97 + scenario_index * 19)
    image = Image.new("RGB", (640, 480), color)
    stream = BytesIO()
    image.save(stream, format="PNG", optimize=False, compress_level=9)
    return stream.getvalue()


def build_dry_run_plan(inventory: object | None = None) -> DryRunPlan:
    """Select exactly two deterministic non-formal images per scenario.

    If an inventory-like object is provided, its scenario counts are checked, but
    its formal sample identities are never copied into this non-formal fixture.
    """

    if inventory is not None:
        counts = getattr(inventory, "scenario_counts", None)
        if counts is None and isinstance(inventory, Mapping):
            counts = inventory.get("scenario_counts")
        if not isinstance(counts, Mapping) or any(
            type(counts.get(scenario)) is not int or counts[scenario] < 2 for scenario in _SCENARIOS
        ):
            raise BenchmarkError("DRY_RUN_INVENTORY_INVALID")
    samples: list[DryRunSample] = []
    for scenario_index, scenario in enumerate(_SCENARIOS):
        for ordinal in range(2):
            payload = _dry_frame_bytes(scenario_index, ordinal)
            samples.append(
                DryRunSample(
                    formal_sample_index=len(samples),
                    scenario=scenario,
                    scenario_index=ordinal,
                    image_sha256=sha256_bytes(payload),
                )
            )
    return DryRunPlan(tuple(samples), formal=False)


def _read_bytes(path: Path, code: str, *, allow_symlink: bool = False) -> bytes:
    target = Path(path)
    try:
        if target.is_symlink():
            if not allow_symlink:
                raise OSError("unsafe file")
            target = target.resolve(strict=True)
        metadata = target.lstat()
        if not target.is_file() or metadata.st_nlink != 1:
            raise OSError("unsafe file")
        payload = target.read_bytes()
        after = target.lstat()
    except OSError as error:
        raise BenchmarkError(code) from error
    if (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise BenchmarkError(code)
    return payload


def _read_json(path: Path, code: str, expected_sha256: str | None = None) -> Mapping[str, Any]:
    payload = _read_bytes(path, code)
    if expected_sha256 is not None and sha256_bytes(payload) != _sha(expected_sha256, code):
        raise BenchmarkError(code)
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BenchmarkError(code) from error
    if not isinstance(value, Mapping):
        raise BenchmarkError(code)
    return value


def _sha(value: object, code: str = "SHA256_INVALID") -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BenchmarkError(code)
    return value


def _config_payload(path: Path) -> bytes:
    payload = _read_bytes(path, "CONFIG_INVALID", allow_symlink=True)
    if sha256_bytes(payload) != _CONFIG_SHA256:
        raise BenchmarkError("CONFIG_SHA256_MISMATCH")
    return payload


def _mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BenchmarkError(code)
    return value


def _load_frozen_config(path: Path) -> Mapping[str, Any]:
    payload = _config_payload(path)
    try:
        document = yaml.safe_load(payload)
    except yaml.YAMLError as error:
        raise BenchmarkError("CONFIG_INVALID") from error
    config = _mapping(document, "CONFIG_INVALID")
    if (
        set(config)
        != {
            "schema_version",
            "dataset",
            "models",
            "runtime",
            "performance",
            "bootstrap",
            "evidence",
            "run_order",
        }
        or config.get("schema_version") != "so101-perception-benchmark/config-v1"
    ):
        raise BenchmarkError("CONFIG_INVALID")
    dataset = _mapping(config.get("dataset"), "CONFIG_INVALID")
    models = _mapping(config.get("models"), "CONFIG_INVALID")
    yolo = _mapping(models.get("yolo_seg"), "CONFIG_INVALID")
    grounded = _mapping(models.get("grounded_sam"), "CONFIG_INVALID")
    yolo_production = _mapping(yolo.get("production"), "CONFIG_INVALID")
    grounded_production = _mapping(grounded.get("production"), "CONFIG_INVALID")
    if (
        dataset.get("archive") != _ARCHIVE_ID
        or dataset.get("archive_sha256") != _ARCHIVE_SHA256
        or dataset.get("image_width") != 640
        or dataset.get("image_height") != 480
        or dataset.get("split_sample_count") != 200
        or yolo.get("model_id") != YOLO_MODEL_ID
        or yolo.get("weights_sha256") != _YOLO_WEIGHTS_SHA256
        or yolo.get("imgsz") != 640
        or yolo_production.get("confidence") != 0.25
        or yolo_production.get("selector_min_confidence") != 0.50
        or _mapping(
            yolo_production.get("nms"),
            "CONFIG_INVALID",
        ).get("source")
        != "resolved_ultralytics_predictor_args"
        or dict(_mapping(yolo.get("low_floor"), "CONFIG_INVALID"))
        != {"confidence": 0.01, "nms_iou": 0.90, "max_det": 300}
        or grounded.get("model_id") != GROUNDED_SAM_MODEL_ID
        or grounded.get("manifest_sha256") != _GROUNDED_MANIFEST_SHA256
        or grounded.get("grounding_dino_revision") != _GROUNDING_DINO_REVISION
        or grounded.get("sam_revision") != _SAM_REVISION
        or grounded.get("prompt") != "plastic cup."
        or dict(grounded_production)
        != {
            "box_threshold": 0.35,
            "text_threshold": 0.25,
            "sam_quality_threshold": 0.75,
            "selector_min_confidence": 0.50,
            "duplicate_iou_threshold": 0.85,
            "minimum_mask_pixels": 64,
            "maximum_mask_area_ratio": 0.50,
            "maximum_candidates": 16,
        }
        or dict(_mapping(grounded.get("low_floor"), "CONFIG_INVALID"))
        != {
            "box_threshold": 0.01,
            "text_threshold": 0.01,
            "sam_quality_threshold": 0.0,
            "selector": "off",
            "maximum_candidates": 300,
        }
        or dict(_mapping(config.get("runtime"), "CONFIG_INVALID"))
        != {
            "dtype": "float32",
            "devices": {"macos": "mps", "linux": "cuda"},
            "allow_cpu_fallback": False,
            "offline": True,
        }
    ):
        raise BenchmarkError("CONFIG_INVALID")
    return config


def _frozen_model(config: Mapping[str, Any], model: str) -> Mapping[str, Any]:
    return _mapping(_mapping(config["models"], "CONFIG_INVALID").get(model), "CONFIG_INVALID")


def _frozen_asset_sha(config: Mapping[str, Any], model: str) -> str:
    values = _frozen_model(config, model)
    key = "weights_sha256" if model == "yolo_seg" else "manifest_sha256"
    return _sha(values.get(key), "CONFIG_INVALID")


def _frozen_model_id(config: Mapping[str, Any], model: str) -> str:
    value = _frozen_model(config, model).get("model_id")
    if not isinstance(value, str) or not value:
        raise BenchmarkError("CONFIG_INVALID")
    return value


def _bind_model_arguments(arguments: argparse.Namespace, config: Mapping[str, Any]) -> None:
    expected = _frozen_asset_sha(config, arguments.model)
    supplied = (
        arguments.weights_sha256 if arguments.model == "yolo_seg" else arguments.manifest_sha256
    )
    asset_path = arguments.weights if arguments.model == "yolo_seg" else arguments.model_root
    if supplied != expected or asset_path is None or not Path(asset_path).is_absolute():
        raise BenchmarkError("FROZEN_PROVENANCE_MISMATCH")


def _bind_archive_arguments(arguments: argparse.Namespace, config: Mapping[str, Any]) -> None:
    dataset = _mapping(config.get("dataset"), "CONFIG_INVALID")
    archive_id = Path(str(dataset.get("archive")))
    archive = Path(arguments.archive)
    if (
        arguments.expected_sha256 != dataset.get("archive_sha256")
        or len(archive.parts) < len(archive_id.parts)
        or archive.parts[-len(archive_id.parts) :] != archive_id.parts
    ):
        raise BenchmarkError("FROZEN_PROVENANCE_MISMATCH")


def _bind_dataset_sha(value: object, config: Mapping[str, Any]) -> None:
    dataset = _mapping(config.get("dataset"), "CONFIG_INVALID")
    if value != dataset.get("archive_sha256"):
        raise BenchmarkError("FROZEN_PROVENANCE_MISMATCH")


def _source_commit(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_COMMIT.fullmatch(value) is None:
        raise BenchmarkError("SOURCE_COMMIT_INVALID")
    return value


def _write_index(root: Path) -> EvidenceIndex:
    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "evidence-index.json":
            continue
        payload = path.read_bytes()
        entries.append(
            EvidenceEntry(
                relative_path=path.relative_to(root).as_posix(),
                size_bytes=len(payload),
                sha256=sha256_bytes(payload),
            )
        )
    index = EvidenceIndex(_INDEX_SCHEMA, _INDEX_SEMANTICS, tuple(entries))
    atomic_write_json(
        root / "evidence-index.json",
        {
            "schema_version": index.schema_version,
            "payload_index_semantics": index.payload_index_semantics,
            "entries": [asdict(entry) for entry in index.entries],
        },
    )
    return verify_evidence_index(root)


def _fixture(path: Path) -> Mapping[str, Any]:
    document = _read_json(path, "DRY_RUN_FIXTURE_INVALID")
    expected = {
        "schema_version",
        "candidate_counts_by_scenario",
        "models",
        "ranking_scores",
        "sam_quality",
    }
    if set(document) != expected or document["schema_version"] != (
        "so101-perception-benchmark/dry-run-fixture-v1"
    ):
        raise BenchmarkError("DRY_RUN_FIXTURE_INVALID")
    counts = document["candidate_counts_by_scenario"]
    if (
        not isinstance(counts, Mapping)
        or set(counts) != set(_SCENARIOS)
        or any(type(counts[item]) is not int or not 0 <= counts[item] <= 2 for item in _SCENARIOS)
        or document["models"] != list(_MODELS)
        or document["ranking_scores"] != [0.91, 0.82]
        or document["sam_quality"] != 0.88
    ):
        raise BenchmarkError("DRY_RUN_FIXTURE_INVALID")
    return document


def _preflight_output_root(path: Path) -> Path:
    root = Path(path)
    if not root.is_absolute():
        raise BenchmarkError("OUTPUT_ROOT_MUST_BE_ABSOLUTE")
    if root.exists() or root.is_symlink():
        raise BenchmarkError("OUTPUT_ROOT_ALREADY_EXISTS")
    parent = root.parent
    if not parent.is_dir():
        raise BenchmarkError("OUTPUT_ROOT_PARENT_INVALID")
    current = parent
    while current != current.parent:
        if current.is_symlink():
            aliases = {
                Path("/tmp"): ("private/tmp", Path("/private/tmp")),
                Path("/var"): ("private/var", Path("/private/var")),
            }
            expected = aliases.get(current)
            try:
                metadata = current.lstat()
                link_text = os.readlink(current)
                resolved = current.resolve(strict=True)
            except OSError as error:
                raise BenchmarkError("OUTPUT_ROOT_PARENT_INVALID") from error
            if (
                expected is None
                or metadata.st_uid != 0
                or link_text != expected[0]
                or resolved != expected[1]
                or not resolved.is_dir()
            ):
                raise BenchmarkError("OUTPUT_ROOT_PARENT_INVALID")
        elif not current.is_dir():
            raise BenchmarkError("OUTPUT_ROOT_PARENT_INVALID")
        current = current.parent
    return root


def _preflight_append_log(path: Path) -> None:
    target = Path(path)
    if not target.is_absolute() or not target.parent.is_dir() or target.parent.is_symlink():
        raise BenchmarkError("ACCESS_LOG_INVALID")
    if target.is_symlink():
        raise BenchmarkError("ACCESS_LOG_INVALID")
    if target.exists():
        try:
            metadata = target.lstat()
        except OSError as error:
            raise BenchmarkError("ACCESS_LOG_INVALID") from error
        if not target.is_file() or metadata.st_nlink != 1:
            raise BenchmarkError("ACCESS_LOG_INVALID")


def _handle_verify_assets(arguments: argparse.Namespace) -> int:
    config = _load_frozen_config(arguments.config)
    _bind_model_arguments(arguments, config)
    if arguments.model == "yolo_seg":
        if arguments.weights is None or arguments.weights_sha256 is None:
            raise BenchmarkError("MODEL_ASSET_ARGUMENTS_INVALID")
        verified = verify_weights(arguments.weights, arguments.weights_sha256)
    else:
        if arguments.model_root is None or arguments.manifest_sha256 is None:
            raise BenchmarkError("MODEL_ASSET_ARGUMENTS_INVALID")
        verified = verify_model_bundle(
            arguments.model_root, arguments.manifest_sha256
        ).manifest_sha256
    print(verified)
    return 0


def _handle_inspect_archive(arguments: argparse.Namespace) -> int:
    config = _load_frozen_config(arguments.config)
    _bind_archive_arguments(arguments, config)
    _preflight_output_root(arguments.sealed_member_inventory)
    result = DatasetArchiveVerifier().verify_archive(
        arguments.archive,
        arguments.expected_sha256,
        arguments.sealed_member_inventory,
    )
    print(result.sealed_test_inventory_sha256)
    return 0


def _handle_prepare_dataset(arguments: argparse.Namespace) -> int:
    config = _load_frozen_config(arguments.config)
    _bind_archive_arguments(arguments, config)
    _preflight_output_root(arguments.output_root)
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        arguments.archive,
        arguments.expected_sha256,
        arguments.output_root,
        "val",
        None,
    )
    print(inventory.inventory_sha256)
    return 0


def _handle_unlock_test(arguments: argparse.Namespace) -> int:
    config = _load_frozen_config(arguments.config)
    _bind_archive_arguments(arguments, config)
    _preflight_output_root(arguments.output_root)
    if (
        not arguments.yolo_threshold_lock.is_file()
        or not arguments.grounded_sam_threshold_lock.is_file()
    ):
        raise BenchmarkError("TEST_SEALED", "two verified threshold locks are required")
    if arguments.yolo_threshold_lock == arguments.grounded_sam_threshold_lock:
        raise BenchmarkError("TEST_SEALED", "two distinct verified threshold locks are required")
    _read_bytes(arguments.yolo_threshold_lock, "THRESHOLD_LOCK_INVALID")
    _read_bytes(arguments.grounded_sam_threshold_lock, "THRESHOLD_LOCK_INVALID")
    _preflight_append_log(arguments.access_log)
    archive = Path(arguments.archive)
    try:
        metadata = archive.lstat()
    except OSError as error:
        raise BenchmarkError("DATASET_ARCHIVE_UNREADABLE") from error
    if archive.is_symlink() or not archive.is_file() or metadata.st_nlink != 1:
        raise BenchmarkError("DATASET_ARCHIVE_UNREADABLE")
    if sha256_file(archive) != arguments.expected_sha256:
        raise BenchmarkError("DATASET_ARCHIVE_SHA256_MISMATCH")
    sealed_sha = sha256_bytes(
        _read_bytes(arguments.sealed_member_inventory, "SEALED_MEMBER_INVENTORY_INVALID")
    )
    with tempfile.TemporaryDirectory(
        prefix=".unlock-preflight-", dir=arguments.output_root.parent
    ) as temporary:
        inspected = DatasetArchiveVerifier().verify_archive(
            arguments.archive,
            arguments.expected_sha256,
            Path(temporary) / "sealed-test-members.json",
        )
    if inspected.sealed_test_member_inventory_sha256 != sealed_sha:
        raise BenchmarkError("TEST_SEAL_ARCHIVE_MISMATCH")
    _preflight_output_root(arguments.output_root)
    seal = unlock_test_seal(
        TestSeal(sealed_sha, arguments.access_log),
        arguments.yolo_threshold_lock,
        arguments.grounded_sam_threshold_lock,
    )
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        arguments.archive,
        arguments.expected_sha256,
        arguments.output_root,
        "test",
        seal,
    )
    print(inventory.inventory_sha256)
    return 0


def _candidate_mask(sample: DryRunSample, candidate_index: int) -> np.ndarray:
    mask = np.zeros((480, 640), dtype=bool)
    x0 = 55 + sample.formal_sample_index * 13 + candidate_index * 190
    y0 = 90 + sample.formal_sample_index * 7
    mask[y0 : y0 + 120, x0 : x0 + 95] = True
    return mask


def _handle_dry_run(arguments: argparse.Namespace) -> int:
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


def _runtime_component(component: object) -> object:
    nested = getattr(component, "model", None)
    return nested if callable(getattr(nested, "parameters", None)) else component


def _validate_characterization_runtime(detector: object, device: str, model: str) -> None:
    if getattr(detector, "runtime_device", None) != device:
        raise BenchmarkError("DEVICE_MISMATCH")
    attributes = ("_model",) if model == "yolo_seg" else ("_grounding_model", "_sam_model")
    for attribute in attributes:
        component = _runtime_component(getattr(detector, attribute, None))
        parameters = getattr(component, "parameters", None)
        if not callable(parameters):
            raise BenchmarkError("RUNTIME_PROVENANCE_UNAVAILABLE")
        try:
            values = tuple(parameters())
        except (RuntimeError, TypeError, ValueError) as error:
            raise BenchmarkError("RUNTIME_PROVENANCE_UNAVAILABLE") from error
        if not values:
            raise BenchmarkError("RUNTIME_PROVENANCE_UNAVAILABLE")
        if {str(item.device).split(":", 1)[0] for item in values} != {device}:
            raise BenchmarkError("DEVICE_MISMATCH")
        if {str(item.dtype).lower().split(".")[-1] for item in values} != {"float32"}:
            raise BenchmarkError("NON_FP32_RUNTIME")


def _characterization_port(arguments: argparse.Namespace, lock: object):
    if (
        getattr(lock, "model", None) != arguments.model
        or getattr(lock, "formal", None) is not True
        or getattr(lock, "deployable", None) is not False
    ):
        raise BenchmarkError("CHARACTERIZATION_LOCK_INVALID")
    selected = lock.selected
    if arguments.model == "yolo_seg":
        detector = YoloCalibratedDetector(
            weights_path=arguments.weights,
            expected_sha256=arguments.weights_sha256,
            requested_device=arguments.device,
            model_id=YOLO_MODEL_ID,
            thresholds=selected,
        )
    else:
        bundle = verify_model_bundle(arguments.model_root, arguments.manifest_sha256)
        detector = GroundedSamDetector(
            bundle=bundle,
            thresholds=GroundedSamThresholds(
                box_threshold=float(selected.box_threshold),
                text_threshold=float(selected.text_threshold),
                duplicate_iou=float(selected.duplicate_iou),
                max_candidates=300,
                sam_quality=float(selected.sam_quality),
                min_mask_pixels=selected.min_mask_pixels,
                max_mask_area_ratio=float(selected.max_mask_area_ratio),
            ),
            requested_device=arguments.device,
            allow_cpu_fallback=False,
        )
    _validate_characterization_runtime(detector, arguments.device, arguments.model)
    return detector


def _production_observer(arguments: argparse.Namespace, run_kind: RunKind):
    if run_kind in {RunKind.TEST_CALIBRATED, RunKind.TEST_CHARACTERIZATION}:
        lock = verify_threshold_lock(arguments.threshold_lock)
        if run_kind is RunKind.TEST_CALIBRATED:
            if not lock.deployable:
                raise BenchmarkError("CALIBRATED_LOCK_NOT_DEPLOYABLE")
            assets = VerifiedBenchmarkAssets(
                model=arguments.model,
                asset_root=(
                    arguments.weights if arguments.model == "yolo_seg" else arguments.model_root
                ),
                weights_sha256=(
                    arguments.weights_sha256 if arguments.model == "yolo_seg" else None
                ),
                manifest_sha256=(
                    arguments.manifest_sha256 if arguments.model == "grounded_sam" else None
                ),
                requested_device=arguments.device,
                allow_cpu_fallback=False,
            )
            detector = build_calibrated_detector_port(arguments.model, lock, assets)
        else:
            detector = _characterization_port(arguments, lock)
        threshold = float(lock.selected.target_confidence_threshold)
    else:
        if arguments.model == "yolo_seg":
            options = DetectorFactoryOptions(
                backend="yolo_seg",
                requested_device=arguments.device,
                allow_cpu_fallback=False,
                yolo_weights_path=arguments.weights,
                yolo_weights_sha256=arguments.weights_sha256,
                yolo_model_id=YOLO_MODEL_ID,
                yolo_imgsz=640,
            )
            threshold = 0.50
        else:
            options = DetectorFactoryOptions(
                backend="grounded_sam",
                requested_device=arguments.device,
                allow_cpu_fallback=False,
                grounded_model_root=arguments.model_root,
                grounded_manifest_sha256=arguments.manifest_sha256,
                grounded_thresholds=GroundedSamThresholds(
                    box_threshold=0.35,
                    text_threshold=0.25,
                    duplicate_iou=0.85,
                    max_candidates=16,
                    sam_quality=0.75,
                    min_mask_pixels=64,
                    max_mask_area_ratio=0.50,
                ),
            )
            threshold = 0.50
        detector = build_production_detector_port(options)
    return partial(run_production_detector_port, detector, selector_threshold=threshold)


def _handle_collect(arguments: argparse.Namespace) -> int:
    run_kind = RunKind(arguments.run_kind)
    if run_kind is RunKind.ORACLE_DIAGNOSTIC and not arguments.allow_oracle_diagnostic:
        raise BenchmarkError("ORACLE_ACK_REQUIRED")
    if arguments.split == "val" and arguments.threshold_lock is not None:
        raise BenchmarkError("VAL_LOCK_FORBIDDEN")
    if arguments.split == "val" and run_kind is not RunKind.VAL_RAW:
        raise BenchmarkError("RUN_KIND_SPLIT_MISMATCH")
    if arguments.split == "test" and run_kind is RunKind.VAL_RAW:
        raise BenchmarkError("RUN_KIND_SPLIT_MISMATCH")
    if (arguments.platform, arguments.device) not in {("macos", "mps"), ("linux", "cuda")}:
        raise BenchmarkError("PLATFORM_DEVICE_MISMATCH")
    if arguments.dtype != "float32":
        raise BenchmarkError("DTYPE_INVALID")
    if arguments.model == "yolo_seg" and (
        arguments.weights is None or arguments.weights_sha256 is None
    ):
        raise BenchmarkError("MODEL_ASSET_ARGUMENTS_INVALID")
    if arguments.model == "grounded_sam" and (
        arguments.model_root is None or arguments.manifest_sha256 is None
    ):
        raise BenchmarkError("MODEL_ASSET_ARGUMENTS_INVALID")
    source_commit = _source_commit(arguments.source_commit)
    config = _load_frozen_config(arguments.config)
    _bind_model_arguments(arguments, config)
    _bind_dataset_sha(arguments.dataset_archive_sha256, config)
    _preflight_output_root(arguments.output_root)
    config_sha = sha256_bytes(_config_payload(arguments.config))
    inventory = _inventory(arguments, config)
    lock_sha = None
    if arguments.split == "test":
        if arguments.threshold_lock is None:
            raise BenchmarkError("TEST_THRESHOLD_LOCK_REQUIRED")
        lock = verify_threshold_lock(arguments.threshold_lock)
        if lock.model != arguments.model or lock.source_commit != source_commit:
            raise BenchmarkError("THRESHOLD_LOCK_MISMATCH")
        lock_sha = lock.lock_sha256
    try:
        arguments.output_root.mkdir(mode=0o700)
    except FileExistsError as error:
        raise BenchmarkError("OUTPUT_ROOT_ALREADY_EXISTS") from error
    except OSError as error:
        raise BenchmarkError("OUTPUT_ROOT_CREATION_FAILED") from error
    adapter = _raw_adapter(arguments, config)
    observer = None
    if run_kind in {
        RunKind.TEST_PRODUCTION,
        RunKind.TEST_CALIBRATED,
        RunKind.TEST_CHARACTERIZATION,
    }:
        observer = _production_observer(arguments, run_kind)
    spec = RunSpec(
        run_id=arguments.run_id,
        run_kind=run_kind,
        platform=arguments.platform,
        model=arguments.model,
        device=arguments.device,
        dtype="float32",
        inventory=inventory,
        config_sha256=config_sha,
        threshold_lock_sha256=lock_sha,
        threshold_lock_path=arguments.threshold_lock,
        source_commit=source_commit,
        output_root=arguments.output_root,
        collection_mode=CollectionMode.LOW_FLOOR,
        production_observer=observer,
        runtime_provenance=_runtime_provenance(arguments),
    )
    manifest = DetectorBenchmarkRunner(adapter, arguments.output_root).run(spec)
    if manifest.status.value != "VALID":
        raise BenchmarkError("RUN_INVALID", manifest.invalid_reason or "run is invalid")
    print(manifest.record_inventory_sha256)
    return 0


def _expectation(path: Path, sha: str) -> RunEvidenceExpectation:
    document = _read_json(path, "RUN_EXPECTATION_INVALID", sha)
    expected = {item.name for item in fields(RunEvidenceExpectation)}
    if set(document) != expected:
        raise BenchmarkError("RUN_EXPECTATION_INVALID")
    try:
        return RunEvidenceExpectation(**document)
    except (TypeError, ValueError) as error:
        raise BenchmarkError("RUN_EXPECTATION_INVALID") from error


def _paths_overlap(first: Path, second: Path) -> bool:
    left = Path(first).resolve(strict=False)
    right = Path(second).resolve(strict=False)
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _preflight_calibration_output(arguments: argparse.Namespace) -> None:
    output = _preflight_output_root(arguments.output_root)
    protected = (
        arguments.dataset_inventory.parent,
        arguments.mac_run_root,
        arguments.linux_run_root,
    )
    if any(_paths_overlap(output, path) for path in protected):
        raise BenchmarkError("CALIBRATION_OUTPUT_OVERLAP")


def _validate_val_run_provenance(
    loaded: object,
    *,
    platform_name: str,
    device: str,
    arguments: argparse.Namespace,
    config: Mapping[str, Any],
) -> None:
    manifest = getattr(loaded, "manifest", None)
    expected = {
        "model": arguments.model,
        "model_id": _frozen_model_id(config, arguments.model),
        "platform": platform_name,
        "device": device,
        "dtype": "float32",
        "run_kind": RunKind.VAL_RAW,
        "source_commit": arguments.source_commit,
        "config_sha256": _CONFIG_SHA256,
        "weights_sha256": _frozen_asset_sha(config, arguments.model),
    }
    if manifest is None or any(
        getattr(manifest, name, None) != value for name, value in expected.items()
    ):
        raise BenchmarkError("RUN_PROVENANCE_MISMATCH")


def _safe_rehome_mask(mask_ref: object, source: Path) -> np.ndarray:
    relative_value = getattr(mask_ref, "relative_path", None)
    if not isinstance(relative_value, str):
        raise BenchmarkError("CALIBRATION_MASK_INVALID")
    relative = PurePosixPath(relative_value)
    if (
        relative.is_absolute()
        or "\\" in relative_value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise BenchmarkError("CALIBRATION_MASK_INVALID")
    root = Path(source).resolve(strict=True)
    target = root.joinpath(*relative.parts)
    try:
        metadata = target.lstat()
        resolved = target.resolve(strict=True)
    except OSError as error:
        raise BenchmarkError("CALIBRATION_MASK_INVALID") from error
    if (
        target.is_symlink()
        or not target.is_file()
        or metadata.st_nlink != 1
        or not resolved.is_relative_to(root)
    ):
        raise BenchmarkError("CALIBRATION_MASK_INVALID")
    return read_mask(mask_ref, root)


def _handle_calibrate(arguments: argparse.Namespace) -> int:
    config = _load_frozen_config(arguments.config)
    _bind_dataset_sha(arguments.dataset_archive_sha256, config)
    _source_commit(arguments.source_commit)
    _preflight_calibration_output(arguments)
    inventory = load_dataset_inventory(
        arguments.dataset_inventory.parent,
        expected_split="val",
        expected_archive_sha256=arguments.dataset_archive_sha256,
        expected_inventory_sha256=arguments.inventory_sha256,
    )
    truths = load_truth_samples(inventory.dataset_root, "val", inventory)
    mac_expectation = _expectation(
        arguments.mac_run_expectation, arguments.mac_run_expectation_sha256
    )
    linux_expectation = _expectation(
        arguments.linux_run_expectation, arguments.linux_run_expectation_sha256
    )
    mac = load_verified_run_evidence(arguments.mac_run_root, inventory, mac_expectation)
    linux = load_verified_run_evidence(arguments.linux_run_root, inventory, linux_expectation)
    if any(
        _paths_overlap(arguments.output_root, path)
        for path in (inventory.dataset_root, mac.evidence_root, linux.evidence_root)
    ):
        raise BenchmarkError("CALIBRATION_OUTPUT_OVERLAP")
    _validate_val_run_provenance(
        mac,
        platform_name="macos",
        device="mps",
        arguments=arguments,
        config=config,
    )
    _validate_val_run_provenance(
        linux,
        platform_name="linux",
        device="cuda",
        arguments=arguments,
        config=config,
    )
    arguments.output_root.mkdir(parents=False, mode=0o700)
    mask_root = arguments.output_root / "calibration-masks"
    mask_root.mkdir()

    def rehome(records: tuple[PredictionRecord, ...], source: Path, platform: str):
        updated = []
        for record in records:
            candidates = []
            for candidate in record.raw_candidates:
                mask = _safe_rehome_mask(candidate.mask, source)
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", candidate.candidate_id) is None:
                    raise BenchmarkError("CALIBRATION_MASK_INVALID")
                relative = (
                    f"{platform}/{record.formal_sample_index:06d}/{candidate.candidate_id}.json"
                )
                destination = mask_root / relative
                if destination.exists() or destination.is_symlink():
                    raise BenchmarkError("CALIBRATION_MASK_OVERWRITE")
                atomic_write_json(destination, encode_mask_rle(mask))
                candidates.append(
                    replace(candidate, mask=replace(candidate.mask, relative_path=relative))
                )
            updated.append(replace(record, raw_candidates=tuple(candidates)))
        return tuple(updated)

    mac_records = rehome(mac.records, mac.evidence_root, "macos")
    linux_records = rehome(linux.records, linux.evidence_root, "linux")
    lock = calibrate_joint_platform_val(
        arguments.model,
        mac_records,
        linux_records,
        truths,
        inventory.inventory_sha256,
        evidence_root=mask_root,
        mac_prediction_inventory_sha256=mac.manifest.record_inventory_sha256,
        linux_prediction_inventory_sha256=linux.manifest.record_inventory_sha256,
        source_commit=mac.manifest.source_commit,
    )
    write_threshold_lock(arguments.output_root / "threshold-lock.json", lock)
    _write_index(arguments.output_root)
    print(lock.lock_sha256)
    return 0


def _resource_sample(document: Mapping[str, Any]) -> ResourceSample:
    if set(document) != {
        "process_rss_bytes",
        "process_cpu_percent",
        "gpu_memory_allocated_bytes",
        "gpu_memory_reserved_bytes",
        "gpu_utilization_percent",
        "gpu_temperature_celsius",
        "gpu_power_watts",
        "unavailable_reasons",
        "tool_versions",
    } or not all(
        isinstance(document[name], Mapping) for name in ("unavailable_reasons", "tool_versions")
    ):
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    return ResourceSample(**document)


def _parse_aggregation_resources(
    document: Mapping[str, Any],
) -> tuple[tuple[ColdProcessSample, ...], ResourceTrace | None]:
    raw_cold = document.get("cold_process_samples", [])
    raw_trace = document.get("resource_trace")
    if not isinstance(raw_cold, list):
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    try:
        cold = tuple(
            ColdProcessSample(**_mapping(item, "AGGREGATION_PLAN_INVALID")) for item in raw_cold
        )
        trace = None
        if raw_trace is not None:
            trace_document = _mapping(raw_trace, "AGGREGATION_PLAN_INVALID")
            if set(trace_document) != {"sampling_frequency_hz", "observations"} or not isinstance(
                trace_document["observations"], list
            ):
                raise BenchmarkError("AGGREGATION_PLAN_INVALID")
            observations = []
            for value in trace_document["observations"]:
                item = _mapping(value, "AGGREGATION_PLAN_INVALID")
                if set(item) != {
                    "phase",
                    "monotonic_ns",
                    "formal_sample_index",
                    "sample",
                }:
                    raise BenchmarkError("AGGREGATION_PLAN_INVALID")
                observations.append(
                    ResourceObservation(
                        phase=item["phase"],
                        monotonic_ns=item["monotonic_ns"],
                        formal_sample_index=item["formal_sample_index"],
                        sample=_resource_sample(
                            _mapping(item["sample"], "AGGREGATION_PLAN_INVALID")
                        ),
                    )
                )
            trace = ResourceTrace(trace_document["sampling_frequency_hz"], tuple(observations))
    except (TypeError, ValueError) as error:
        raise BenchmarkError("AGGREGATION_PLAN_INVALID") from error
    return cold, trace


def _aggregation_evidence(document: Mapping[str, Any], loaded) -> RunAggregationEvidence:
    cold, trace = _parse_aggregation_resources(document)
    return RunAggregationEvidence(
        evidence_root=loaded.evidence_root,
        extended_record_documents=loaded.extended_record_documents,
        cold_process_samples=cold,
        resource_trace=trace,
    )


def _absolute_path_field(document: Mapping[str, Any], name: str) -> Path:
    value = document.get(name)
    if not isinstance(value, str) or not value:
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    path = Path(value)
    if not path.is_absolute():
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    return path


def _validated_aggregation_plan(
    document: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], list[Mapping[str, Any]], str]:
    if (
        set(document)
        != {
            "schema_version",
            "dataset",
            "threshold_locks",
            "runs",
            "source_commit",
        }
        or document.get("schema_version") != "so101-perception-benchmark/aggregation-plan-v1"
    ):
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    dataset = _mapping(document.get("dataset"), "AGGREGATION_PLAN_INVALID")
    locks = _mapping(document.get("threshold_locks"), "AGGREGATION_PLAN_INVALID")
    raw_runs = document.get("runs")
    if set(dataset) != {
        "root",
        "archive_sha256",
        "inventory_sha256",
        "test_access_event_sha256",
        "sealed_member_inventory_sha256",
        "threshold_lock_sha256s",
    } or set(locks) != set(_MODELS):
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    _absolute_path_field(dataset, "root")
    for name in (
        "archive_sha256",
        "inventory_sha256",
        "test_access_event_sha256",
        "sealed_member_inventory_sha256",
    ):
        _sha(dataset.get(name), "AGGREGATION_PLAN_INVALID")
    lock_shas = dataset.get("threshold_lock_sha256s")
    if (
        not isinstance(lock_shas, list)
        or len(lock_shas) != 2
        or any(
            not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in lock_shas
        )
    ):
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    for model in _MODELS:
        anchor = _mapping(locks.get(model), "AGGREGATION_PLAN_INVALID")
        if set(anchor) != {"path", "sha256"}:
            raise BenchmarkError("AGGREGATION_PLAN_INVALID")
        _absolute_path_field(anchor, "path")
        _sha(anchor.get("sha256"), "AGGREGATION_PLAN_INVALID")
    if not isinstance(raw_runs, list) or not raw_runs:
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    runs: list[Mapping[str, Any]] = []
    required = {
        "platform",
        "model",
        "config",
        "run_root",
        "expectation",
        "expectation_sha256",
    }
    optional = {"cold_process_samples", "resource_trace"}
    for value in raw_runs:
        item = _mapping(value, "AGGREGATION_PLAN_INVALID")
        if not required.issubset(item) or not set(item).issubset(required | optional):
            raise BenchmarkError("AGGREGATION_PLAN_INVALID")
        _absolute_path_field(item, "run_root")
        _absolute_path_field(item, "expectation")
        _sha(item.get("expectation_sha256"), "AGGREGATION_PLAN_INVALID")
        if (
            not isinstance(item.get("platform"), str)
            or item["platform"] not in {"macos", "linux"}
            or not isinstance(item.get("model"), str)
            or item["model"] not in set(_MODELS)
            or not isinstance(item.get("config"), str)
            or item["config"]
            not in {
                "TEST_RAW_FROZEN",
                "production",
                "calibrated",
                "characterization",
                "ORACLE_DIAGNOSTIC",
            }
        ):
            raise BenchmarkError("AGGREGATION_PLAN_INVALID")
        _parse_aggregation_resources(item)
        runs.append(item)
    return dataset, locks, runs, _source_commit(document.get("source_commit"))


def _validate_aggregate_run_provenance(
    loaded: object,
    *,
    platform_name: str,
    model: str,
    config_name: str,
    source_commit: str,
    config: Mapping[str, Any],
) -> None:
    kinds = {
        "TEST_RAW_FROZEN": RunKind.TEST_RAW_FROZEN,
        "production": RunKind.TEST_PRODUCTION,
        "calibrated": RunKind.TEST_CALIBRATED,
        "characterization": RunKind.TEST_CHARACTERIZATION,
        "ORACLE_DIAGNOSTIC": RunKind.ORACLE_DIAGNOSTIC,
    }
    expected = {
        "platform": platform_name,
        "model": model,
        "device": "mps" if platform_name == "macos" else "cuda",
        "dtype": "float32",
        "run_kind": kinds[config_name],
        "source_commit": source_commit,
        "config_sha256": _CONFIG_SHA256,
        "model_id": _frozen_model_id(config, model),
        "weights_sha256": _frozen_asset_sha(config, model),
    }
    manifest = getattr(loaded, "manifest", None)
    if manifest is None or any(
        getattr(manifest, name, None) != expected_value for name, expected_value in expected.items()
    ):
        raise BenchmarkError("RUN_PROVENANCE_MISMATCH")


def _handle_aggregate(arguments: argparse.Namespace) -> int:
    config_document = _load_frozen_config(arguments.config)
    _preflight_output_root(arguments.output_root)
    plan = _read_json(
        arguments.aggregation_plan, "AGGREGATION_PLAN_INVALID", arguments.aggregation_plan_sha256
    )
    dataset, locks_document, runs, source_commit = _validated_aggregation_plan(plan)
    _bind_dataset_sha(dataset["archive_sha256"], config_document)
    threshold_locks = {}
    for model in _MODELS:
        lock_anchor = locks_document.get(model)
        if not isinstance(lock_anchor, Mapping) or set(lock_anchor) != {"path", "sha256"}:
            raise BenchmarkError("AGGREGATION_PLAN_INVALID")
        lock_path = _absolute_path_field(lock_anchor, "path")
        expected_lock_sha = _sha(lock_anchor["sha256"], "AGGREGATION_PLAN_INVALID")
        lock = verify_threshold_lock(lock_path)
        if (
            lock.lock_sha256 != expected_lock_sha
            or lock.model != model
            or lock.source_commit != source_commit
        ):
            raise BenchmarkError("THRESHOLD_LOCK_MISMATCH")
        threshold_locks[model] = lock
    inventory = load_dataset_inventory(
        _absolute_path_field(dataset, "root"),
        expected_split="test",
        expected_archive_sha256=dataset["archive_sha256"],
        expected_inventory_sha256=dataset["inventory_sha256"],
        expected_test_access_event_sha256=dataset["test_access_event_sha256"],
        expected_sealed_member_inventory_sha256=dataset["sealed_member_inventory_sha256"],
        expected_threshold_lock_sha256s=tuple(dataset["threshold_lock_sha256s"]),
    )
    truths = load_truth_samples(inventory.dataset_root, "test", inventory)
    raw: dict[str, dict[str, tuple[PredictionRecord, ...]]] = {}
    formal: dict[str, dict[str, dict[str, tuple[PredictionRecord, ...]]]] = {}
    oracle: dict[str, dict[str, tuple[PredictionRecord, ...]]] = {}
    evidence: dict[tuple[str, str, str], RunAggregationEvidence] = {}
    oracle_evidence: dict[tuple[str, str, str], RunAggregationEvidence] = {}
    for item in runs:
        expectation = _expectation(
            _absolute_path_field(item, "expectation"), item["expectation_sha256"]
        )
        loaded = load_verified_run_evidence(
            _absolute_path_field(item, "run_root"), inventory, expectation
        )
        platform, model, config_name = item["platform"], item["model"], item["config"]
        if (
            platform not in {"macos", "linux"}
            or model not in set(_MODELS)
            or config_name
            not in {
                "TEST_RAW_FROZEN",
                "production",
                "calibrated",
                "characterization",
                "ORACLE_DIAGNOSTIC",
            }
        ):
            raise BenchmarkError("AGGREGATION_PLAN_INVALID")
        _validate_aggregate_run_provenance(
            loaded,
            platform_name=platform,
            model=model,
            config_name=config_name,
            source_commit=source_commit,
            config=config_document,
        )
        run_evidence = _aggregation_evidence(item, loaded)
        if config_name == "TEST_RAW_FROZEN":
            raw.setdefault(platform, {})[model] = loaded.records
            evidence[(platform, model, config_name)] = run_evidence
        elif config_name == "ORACLE_DIAGNOSTIC":
            oracle.setdefault(platform, {})[model] = loaded.records
            oracle_evidence[(platform, model, config_name)] = run_evidence
        else:
            formal.setdefault(platform, {}).setdefault(model, {})[config_name] = loaded.records
            evidence[(platform, model, config_name)] = run_evidence
    value = AggregationInput(
        formal=True,
        source_commit=source_commit,
        dataset_archive_sha256=inventory.archive_sha256,
        test_inventory_sha256=inventory.inventory_sha256,
        truth_evidence_root=inventory.dataset_root,
        truth_samples=truths,
        raw_frozen_records=raw,
        formal_records=formal,
        threshold_locks=threshold_locks,
        run_evidence=evidence,
        oracle_records=oracle,
        oracle_evidence=oracle_evidence,
        bootstrap_seed=arguments.bootstrap_seed,
        bootstrap_repetitions=arguments.bootstrap_repetitions,
    )
    summary = MetricsAggregator().aggregate(value)
    ReportWriter().write(summary, arguments.output_root)
    verify_evidence_index(arguments.output_root)
    print(arguments.output_root / "evidence-index.json")
    return 0


def _handle_verify_evidence(arguments: argparse.Namespace) -> int:
    index = load_evidence_index(arguments.output_root)
    if arguments.print_inventory_sha:
        print(sha256_file(arguments.output_root / "evidence-index.json"))
    else:
        print(f"VERIFIED {len(index.entries)}")
    return 0


def _add_dataset_anchors(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset-inventory", type=Path, required=True)
    parser.add_argument("--dataset-archive-sha256", required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--test-access-event-sha256")
    parser.add_argument("--sealed-member-inventory-sha256")
    parser.add_argument("--yolo-lock-sha256")
    parser.add_argument("--grounded-sam-lock-sha256")


def _add_model_assets(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--weights-sha256")
    parser.add_argument("--model-root", type=Path)
    parser.add_argument("--manifest-sha256")


def _add_frozen_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="perception_benchmark")
    commands = parser.add_subparsers(dest="command", required=True)

    verify = commands.add_parser("verify-assets")
    _add_frozen_config(verify)
    verify.add_argument("--model", choices=_MODELS, required=True)
    _add_model_assets(verify)
    verify.set_defaults(handler=_handle_verify_assets)

    inspect = commands.add_parser("inspect-archive")
    _add_frozen_config(inspect)
    inspect.add_argument("--archive", type=Path, required=True)
    inspect.add_argument("--expected-sha256", required=True)
    inspect.add_argument("--sealed-member-inventory", type=Path, required=True)
    inspect.set_defaults(handler=_handle_inspect_archive)

    prepare = commands.add_parser("prepare-dataset")
    _add_frozen_config(prepare)
    prepare.add_argument("--archive", type=Path, required=True)
    prepare.add_argument("--expected-sha256", required=True)
    prepare.add_argument("--split", choices=("val",), required=True)
    prepare.add_argument("--output-root", type=Path, required=True)
    prepare.set_defaults(handler=_handle_prepare_dataset)

    unlock = commands.add_parser("unlock-test")
    _add_frozen_config(unlock)
    unlock.add_argument("--archive", type=Path, required=True)
    unlock.add_argument("--expected-sha256", required=True)
    unlock.add_argument("--sealed-member-inventory", type=Path, required=True)
    unlock.add_argument("--yolo-threshold-lock", type=Path, required=True)
    unlock.add_argument("--grounded-sam-threshold-lock", type=Path, required=True)
    unlock.add_argument("--access-log", type=Path, required=True)
    unlock.add_argument("--output-root", type=Path, required=True)
    unlock.set_defaults(handler=_handle_unlock_test)

    dry = commands.add_parser("dry-run")
    dry.add_argument("--config", type=Path, required=True)
    dry.add_argument("--output-root", type=Path, required=True)
    dry.add_argument("--adapter-fixture", type=Path, required=True)
    dry.set_defaults(handler=_handle_dry_run)

    collect = commands.add_parser("collect")
    collect.add_argument("--run-id", required=True)
    collect.add_argument("--platform", choices=("macos", "linux"), required=True)
    collect.add_argument("--model", choices=_MODELS, required=True)
    collect.add_argument("--device", choices=("mps", "cuda"), required=True)
    collect.add_argument("--dtype", required=True)
    collect.add_argument("--split", choices=("val", "test"), required=True)
    collect.add_argument("--run-kind", choices=tuple(item.value for item in RunKind), required=True)
    _add_dataset_anchors(collect)
    _add_model_assets(collect)
    collect.add_argument("--threshold-lock", type=Path)
    collect.add_argument("--config", type=Path, required=True)
    collect.add_argument("--source-commit", required=True)
    collect.add_argument("--output-root", type=Path, required=True)
    collect.add_argument("--allow-oracle-diagnostic", action="store_true")
    collect.set_defaults(handler=_handle_collect)

    calibrate = commands.add_parser("calibrate")
    _add_frozen_config(calibrate)
    calibrate.add_argument("--model", choices=_MODELS, required=True)
    _add_dataset_anchors(calibrate)
    calibrate.set_defaults(split="val")
    calibrate.add_argument("--mac-run-root", type=Path, required=True)
    calibrate.add_argument("--mac-run-expectation", type=Path, required=True)
    calibrate.add_argument("--mac-run-expectation-sha256", required=True)
    calibrate.add_argument("--linux-run-root", type=Path, required=True)
    calibrate.add_argument("--linux-run-expectation", type=Path, required=True)
    calibrate.add_argument("--linux-run-expectation-sha256", required=True)
    calibrate.add_argument("--source-commit", required=True)
    calibrate.add_argument("--output-root", type=Path, required=True)
    calibrate.set_defaults(handler=_handle_calibrate)

    aggregate = commands.add_parser("aggregate")
    _add_frozen_config(aggregate)
    aggregate.add_argument("--aggregation-plan", type=Path, required=True)
    aggregate.add_argument("--aggregation-plan-sha256", required=True)
    aggregate.add_argument("--bootstrap-seed", type=int, default=20260902)
    aggregate.add_argument("--bootstrap-repetitions", type=int, default=10000)
    aggregate.add_argument("--output-root", type=Path, required=True)
    aggregate.set_defaults(handler=_handle_aggregate)

    verify_evidence = commands.add_parser("verify-evidence")
    verify_evidence.add_argument("--output-root", type=Path, required=True)
    verify_evidence.add_argument("--print-inventory-sha", action="store_true")
    verify_evidence.set_defaults(handler=_handle_verify_evidence)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        return arguments.handler(arguments)
    except BenchmarkError as error:
        print(f"{error.code}: {error.detail}", file=sys.stderr)
        return 2
    except ModelSetupError as error:
        print(f"{error.code}: benchmark command rejected", file=sys.stderr)
        return 2
    except (CalibrationError, DatasetVerificationError, ValueError, OSError) as error:
        code = str(error).split(":", 1)[0]
        if not re.fullmatch(r"[A-Z][A-Z0-9_]+", code):
            code = type(error).__name__.upper()
        print(f"{code}: benchmark command rejected", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
