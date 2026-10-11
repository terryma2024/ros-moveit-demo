"""The frozen benchmark constants, the dry-run plans, frozen configuration binding and output preflight."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from io import BytesIO
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from PIL import Image
import yaml

from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
    sha256_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    YOLO_MODEL_ID,
)
from so101_demo.perception_benchmark.reporting.records import EvidenceEntry, EvidenceIndex
from so101_demo.perception_benchmark.reporting.writer import verify_evidence_index

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


_CONFIG_SHA256 = "9917a897672298b75a5a13166b25a10e019045bd6c990e42e481ead5288375b2"


_ARCHIVE_ID = (
    "datasets/so101-v5-t005-grounded-sam-postfix/so101-v5-t005-grounded-sam-postfix-r4.tar.gz"
)


_ARCHIVE_SHA256 = "8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832"


_YOLO_WEIGHTS_SHA256 = "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781"


_GROUNDED_MANIFEST_SHA256 = "b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05"


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


@dataclass(frozen=True, slots=True)
class ActualDryRunSample:
    dry_sample_index: int
    source_val_formal_sample_index: int
    scenario: str
    image_relpath: str
    image_sha256: str


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


def build_actual_dry_run_plan(inventory: object) -> tuple[ActualDryRunSample, ...]:
    """Bind a non-formal smoke run to two immutable val images per scenario."""

    if getattr(inventory, "split", None) != "val":
        raise BenchmarkError("DRY_RUN_INVENTORY_INVALID")
    counts = getattr(inventory, "scenario_counts", None)
    samples = getattr(inventory, "samples", None)
    if (
        not isinstance(counts, Mapping)
        or any(
            type(counts.get(scenario)) is not int or counts[scenario] < 2 for scenario in _SCENARIOS
        )
        or not isinstance(samples, tuple)
    ):
        raise BenchmarkError("DRY_RUN_INVENTORY_INVALID")
    selected: list[ActualDryRunSample] = []
    for scenario in _SCENARIOS:
        candidates = sorted(
            (sample for sample in samples if getattr(sample, "scenario", None) == scenario),
            key=lambda sample: (
                getattr(sample, "image_sha256", ""),
                getattr(sample, "formal_sample_index", -1),
            ),
        )
        if len(candidates) < 2:
            raise BenchmarkError("DRY_RUN_INVENTORY_INVALID")
        for sample in candidates[:2]:
            formal_index = getattr(sample, "formal_sample_index", None)
            image_relpath = getattr(sample, "image_relpath", None)
            image_sha256 = getattr(sample, "image_sha256", None)
            if (
                isinstance(formal_index, bool)
                or not isinstance(formal_index, int)
                or formal_index < 0
                or not isinstance(image_relpath, str)
                or not image_relpath
            ):
                raise BenchmarkError("DRY_RUN_INVENTORY_INVALID")
            selected.append(
                ActualDryRunSample(
                    dry_sample_index=len(selected),
                    source_val_formal_sample_index=formal_index,
                    scenario=scenario,
                    image_relpath=image_relpath,
                    image_sha256=_sha(image_sha256, "DRY_RUN_INVENTORY_INVALID"),
                )
            )
    if len({sample.image_sha256 for sample in selected}) != 8:
        raise BenchmarkError("DRY_RUN_INVENTORY_INVALID")
    return tuple(selected)


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
            "candidate_mapping_mask_iou_threshold": 0.98,
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
