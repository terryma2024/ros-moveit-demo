"""The collect subcommand and the characterization port."""

from __future__ import annotations

import argparse
from functools import partial

from so101_demo.adapters.perception.detector_factory import DetectorFactoryOptions
from so101_demo.adapters.perception.grounded_sam import GroundedSamDetector
from so101_demo.adapters.perception.grounded_sam_postprocess import GroundedSamThresholds
from so101_demo.adapters.perception.model_bundle import verify_model_bundle
from so101_demo.cli.benchmark.common import (
    BenchmarkError,
    _bind_dataset_sha,
    _bind_model_arguments,
    _config_payload,
    _frozen_model,
    _load_frozen_config,
    _mapping,
    _preflight_output_root,
    _source_commit,
)
from so101_demo.cli.benchmark.dry_run import _inventory, _raw_adapter, _runtime_provenance
from so101_demo.perception_benchmark.adapters import (
    CollectionMode,
    VerifiedBenchmarkAssets,
    YoloCalibratedDetector,
    build_calibrated_detector_port,
    build_production_detector_port,
    run_production_detector_port,
)
from so101_demo.perception_benchmark.calibration.lock_io import verify_threshold_lock
from so101_demo.perception_benchmark.codec import (
    sha256_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    YOLO_MODEL_ID,
    RunKind,
)
from so101_demo.perception_benchmark.runner.contracts import RunSpec
from so101_demo.perception_benchmark.runner.detector_runner import DetectorBenchmarkRunner


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
        production_candidate_mask_iou_threshold=float(
            _mapping(
                _frozen_model(config, "grounded_sam").get("production"),
                "CONFIG_INVALID",
            )["candidate_mapping_mask_iou_threshold"]
        ),
    )
    manifest = DetectorBenchmarkRunner(adapter, arguments.output_root).run(spec)
    if manifest.status.value != "VALID":
        raise BenchmarkError("RUN_INVALID", manifest.invalid_reason or "run is invalid")
    print(manifest.record_inventory_sha256)
    return 0
