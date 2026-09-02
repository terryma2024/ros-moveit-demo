"""Fail-closed dataset archive access and truth loading for formal benchmarks."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
from types import MappingProxyType
from typing import Literal

import PIL
from PIL import Image, ImageDraw
import numpy as np

from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
    canonical_json_bytes,
    encode_mask_rle,
)
from so101_demo.perception_benchmark.contracts import (
    MaskRef,
    SCHEMA_VERSION,
    TruthInstance,
    TruthSample,
)


Split = Literal["val", "test"]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_SAMPLE_COUNT = 200
_EXPECTED_IMAGE_SIZE = (640, 480)
_EXPECTED_SCENARIO_COUNTS = {
    "no_cup": 50,
    "one_cup_distractors": 50,
    "two_cups": 50,
    "cup_near_bottle": 50,
}
_RASTERIZER = {
    "library": "Pillow",
    "version": "12.3.0",
    "coordinate_scale": "dimension_minus_one",
    "rounding": "floor(x+0.5)",
    "boundary": "ImageDraw.polygon fill=1",
}
_KINDS = {"images": ".png", "labels": ".txt", "truth": ".json"}


class DatasetVerificationError(ValueError):
    """A stable fail-closed dataset verification error."""


def _require_sha256(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise DatasetVerificationError(code)
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise DatasetVerificationError("DATASET_ARCHIVE_UNREADABLE") from error
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class DatasetSampleRef:
    formal_sample_index: int
    split: Split
    scenario: str
    image_relpath: str
    label_relpath: str
    truth_relpath: str
    image_sha256: str
    truth_count: int


@dataclass(frozen=True, slots=True)
class ArchiveInventory:
    archive_sha256: str
    sealed_test_member_inventory_sha256: str
    safe_member_count: int
    test_triplet_count: int
    test_scenario_counts: Mapping[str, int] | None

    def __post_init__(self) -> None:
        if self.test_scenario_counts is not None:
            object.__setattr__(
                self,
                "test_scenario_counts",
                MappingProxyType(dict(self.test_scenario_counts)),
            )


@dataclass(frozen=True, slots=True)
class TestAccessGrant:
    event_sha256: str
    sealed_member_inventory_sha256: str
    threshold_lock_sha256s: tuple[str, str]
    granted_at: str


@dataclass(frozen=True, slots=True)
class DatasetInventory:
    schema_version: str
    split: Split
    archive_sha256: str
    inventory_sha256: str
    dataset_root: Path
    sample_count: int
    scenario_counts: Mapping[str, int]
    samples: tuple[DatasetSampleRef, ...]
    test_access_event_sha256: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_root", Path(self.dataset_root))
        object.__setattr__(
            self, "scenario_counts", MappingProxyType(dict(self.scenario_counts))
        )
        object.__setattr__(self, "samples", tuple(self.samples))


@dataclass(frozen=True, slots=True)
class TestSeal:
    sealed_member_inventory_sha256: str
    access_log_path: Path
    access_grant: TestAccessGrant | None = None

    def __post_init__(self) -> None:
        _require_sha256(
            self.sealed_member_inventory_sha256,
            "SEALED_MEMBER_INVENTORY_SHA256_INVALID",
        )
        object.__setattr__(self, "access_log_path", Path(self.access_log_path))

    def unlock(
        self,
        yolo_lock_path: Path,
        grounded_sam_lock_path: Path,
        verify_lock: Callable[[Path], str],
    ) -> "TestSeal":
        if self.access_grant is not None:
            raise DatasetVerificationError("TEST_ACCESS_ALREADY_GRANTED")
        if Path(yolo_lock_path) == Path(grounded_sam_lock_path):
            raise DatasetVerificationError("THRESHOLD_LOCKS_NOT_DISTINCT")
        try:
            lock_shas = (
                _require_sha256(
                    verify_lock(Path(yolo_lock_path)), "THRESHOLD_LOCK_SHA256_INVALID"
                ),
                _require_sha256(
                    verify_lock(Path(grounded_sam_lock_path)),
                    "THRESHOLD_LOCK_SHA256_INVALID",
                ),
            )
        except DatasetVerificationError:
            raise
        except Exception as error:
            raise DatasetVerificationError("THRESHOLD_LOCK_VERIFICATION_FAILED") from error
        if lock_shas[0] == lock_shas[1]:
            raise DatasetVerificationError("THRESHOLD_LOCKS_NOT_DISTINCT")
        grant = append_test_access_event(
            self.access_log_path,
            self.sealed_member_inventory_sha256,
            lock_shas,
        )
        return replace(self, access_grant=grant)


def append_test_access_event(
    access_log_path: Path,
    sealed_member_inventory_sha256: str,
    threshold_lock_sha256s: tuple[str, str],
) -> TestAccessGrant:
    sealed_sha = _require_sha256(
        sealed_member_inventory_sha256,
        "SEALED_MEMBER_INVENTORY_SHA256_INVALID",
    )
    locks = tuple(
        _require_sha256(value, "THRESHOLD_LOCK_SHA256_INVALID")
        for value in threshold_lock_sha256s
    )
    if len(locks) != 2 or locks[0] == locks[1]:
        raise DatasetVerificationError("THRESHOLD_LOCKS_NOT_DISTINCT")
    target = Path(access_log_path)
    if target.is_symlink():
        raise DatasetVerificationError("TEST_ACCESS_LOG_UNSAFE")
    target.parent.mkdir(parents=True, exist_ok=True)
    granted_at = datetime.now(timezone.utc).isoformat()
    event_without_sha = {
        "event_type": "TEST_ACCESS_GRANTED",
        "granted_at": granted_at,
        "sealed_member_inventory_sha256": sealed_sha,
        "threshold_lock_sha256s": list(locks),
    }
    event_sha = hashlib.sha256(canonical_json_bytes(event_without_sha)).hexdigest()
    event = {**event_without_sha, "event_sha256": event_sha}
    try:
        with target.open("ab") as stream:
            stream.write(canonical_json_bytes(event))
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise DatasetVerificationError("TEST_ACCESS_LOG_WRITE_FAILED") from error
    return TestAccessGrant(event_sha, sealed_sha, locks, granted_at)


@dataclass(frozen=True, slots=True)
class _ArchiveMember:
    archive_path: str
    relative_path: str
    kind: str
    split: Split
    stem: str
    size: int
    sha256: str


def _safe_member_path(name: str) -> bool:
    if not name or "\\" in name:
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and all(
        part not in {"", ".", ".."} for part in path.parts
    )


def _classify_member(name: str) -> tuple[str, Split, str, str] | None:
    parts = PurePosixPath(name).parts
    if len(parts) < 3:
        return None
    kind, split, filename = parts[-3:]
    if kind not in _KINDS or split not in {"val", "test"}:
        return None
    suffix = _KINDS[kind]
    if not filename.endswith(suffix) or filename == suffix:
        return None
    stem = filename[: -len(suffix)]
    return kind, split, stem, "/".join((kind, split, filename))


def _inspect_archive(
    archive: Path, expected_sha256: str
) -> tuple[list[tarfile.TarInfo], list[_ArchiveMember]]:
    expected = _require_sha256(expected_sha256, "DATASET_ARCHIVE_SHA256_INVALID")
    if sha256_file(archive) != expected:
        raise DatasetVerificationError("DATASET_ARCHIVE_HASH_MISMATCH")
    members: list[tarfile.TarInfo] = []
    classified: list[_ArchiveMember] = []
    seen_paths: set[str] = set()
    try:
        with tarfile.open(archive, "r:gz") as stream:
            for member in stream.getmembers():
                if (
                    not _safe_member_path(member.name)
                    or member.issym()
                    or member.islnk()
                    or not (member.isfile() or member.isdir())
                    or member.name in seen_paths
                ):
                    raise DatasetVerificationError("ARCHIVE_PATH_UNSAFE")
                seen_paths.add(member.name)
                members.append(member)
                classification = _classify_member(member.name)
                if classification is None or not member.isfile():
                    continue
                kind, split, stem, relative_path = classification
                extracted = stream.extractfile(member)
                if extracted is None:
                    raise DatasetVerificationError("ARCHIVE_MEMBER_UNREADABLE")
                digest = hashlib.sha256()
                for chunk in iter(lambda: extracted.read(1024 * 1024), b""):
                    digest.update(chunk)
                classified.append(
                    _ArchiveMember(
                        member.name,
                        relative_path,
                        kind,
                        split,
                        stem,
                        member.size,
                        digest.hexdigest(),
                    )
                )
    except DatasetVerificationError:
        raise
    except (OSError, tarfile.TarError) as error:
        raise DatasetVerificationError("DATASET_ARCHIVE_INVALID") from error
    return members, classified


def _require_triplets(
    members: list[_ArchiveMember], split: Split, expected_count: int
) -> dict[str, dict[str, _ArchiveMember]]:
    triplets: dict[str, dict[str, _ArchiveMember]] = {}
    for member in members:
        if member.split != split:
            continue
        by_kind = triplets.setdefault(member.stem, {})
        if member.kind in by_kind:
            code = "TEST_MEMBER_COUNT_INVALID" if split == "test" else "SPLIT_MEMBER_COUNT_INVALID"
            raise DatasetVerificationError(code)
        by_kind[member.kind] = member
    valid = (
        len(triplets) == expected_count
        and all(set(by_kind) == set(_KINDS) for by_kind in triplets.values())
    )
    if not valid:
        code = "TEST_MEMBER_COUNT_INVALID" if split == "test" else "SPLIT_MEMBER_COUNT_INVALID"
        raise DatasetVerificationError(code)
    return triplets


class DatasetArchiveVerifier:
    def verify_archive(
        self,
        archive: Path,
        expected_sha256: str,
        sealed_test_inventory_path: Path,
    ) -> ArchiveInventory:
        sealed_path = Path(sealed_test_inventory_path)
        if sealed_path.exists() or sealed_path.is_symlink():
            raise DatasetVerificationError("OUTPUT_ROOT_ALREADY_EXISTS")
        members, classified = _inspect_archive(Path(archive), expected_sha256)
        _require_triplets(classified, "test", _EXPECTED_SAMPLE_COUNT)
        test_members = sorted(
            (member for member in classified if member.split == "test"),
            key=lambda item: item.relative_path,
        )
        sealed_document = {
            "schema_version": SCHEMA_VERSION,
            "split": "test",
            "members": [
                {
                    "path": member.archive_path,
                    "sha256": member.sha256,
                    "size": member.size,
                }
                for member in test_members
            ],
        }
        sealed_sha = atomic_write_json(sealed_path, sealed_document)
        return ArchiveInventory(
            expected_sha256,
            sealed_sha,
            len(members),
            _EXPECTED_SAMPLE_COUNT,
            None,
        )

    def verify_and_extract_split(
        self,
        archive: Path,
        expected_sha256: str,
        output_root: Path,
        split: Split,
        test_seal: TestSeal | None,
    ) -> DatasetInventory:
        root = Path(output_root)
        if root.exists() or root.is_symlink():
            raise DatasetVerificationError("OUTPUT_ROOT_ALREADY_EXISTS")
        if split not in {"val", "test"}:
            raise DatasetVerificationError("SPLIT_INVALID")
        grant = None if test_seal is None else test_seal.access_grant
        if split == "test" and grant is None:
            raise DatasetVerificationError("TEST_SEALED")
        _require_rasterizer_version()
        _, classified = _inspect_archive(Path(archive), expected_sha256)
        triplets = _require_triplets(classified, split, _EXPECTED_SAMPLE_COUNT)
        root.mkdir(parents=True, mode=0o700)
        selected = {
            member.archive_path: member
            for by_kind in triplets.values()
            for member in by_kind.values()
        }
        try:
            with tarfile.open(archive, "r:gz") as stream:
                for tar_member in stream.getmembers():
                    selected_member = selected.get(tar_member.name)
                    if selected_member is None:
                        continue
                    source = stream.extractfile(tar_member)
                    if source is None:
                        raise DatasetVerificationError("ARCHIVE_MEMBER_UNREADABLE")
                    target = root / selected_member.relative_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as destination:
                        shutil.copyfileobj(source, destination, length=1024 * 1024)
                        destination.flush()
                        os.fsync(destination.fileno())
                    target.chmod(0o444)
        except DatasetVerificationError:
            raise
        except (OSError, tarfile.TarError) as error:
            raise DatasetVerificationError("SPLIT_EXTRACTION_FAILED") from error
        return self._build_semantic_inventory(
            root,
            split,
            expected_sha256,
            grant,
        )

    def _build_semantic_inventory(
        self,
        root: Path,
        split: Split,
        archive_sha256: str,
        access_grant: TestAccessGrant | None,
    ) -> DatasetInventory:
        records: list[DatasetSampleRef] = []
        image_shas: set[str] = set()
        scenarios: Counter[str] = Counter()
        images = {path.stem: path for path in (root / "images" / split).glob("*.png")}
        labels = {path.stem: path for path in (root / "labels" / split).glob("*.txt")}
        truths = {path.stem: path for path in (root / "truth" / split).glob("*.json")}
        if (
            not (set(images) == set(labels) == set(truths))
            or len(images) != _EXPECTED_SAMPLE_COUNT
        ):
            raise DatasetVerificationError("SPLIT_MEMBER_COUNT_INVALID")
        for stem in sorted(images):
            image_path = images[stem]
            try:
                with Image.open(image_path) as image:
                    size = image.size
                    image.verify()
            except Exception as error:
                raise DatasetVerificationError("IMAGE_DECODE_FAILED") from error
            if size != _EXPECTED_IMAGE_SIZE:
                raise DatasetVerificationError("IMAGE_DIMENSIONS_INVALID")
            image_sha = sha256_file(image_path)
            if image_sha in image_shas:
                raise DatasetVerificationError("DUPLICATE_IMAGE_SHA256")
            image_shas.add(image_sha)
            truth = _read_truth(truths[stem], split)
            label_polygons = _read_label_polygons(labels[stem])
            truth_polygons = _truth_polygons(truth)
            if label_polygons != truth_polygons:
                raise DatasetVerificationError("LABEL_TRUTH_POLYGON_MISMATCH")
            scenario = truth["scenario"]
            scenarios[scenario] += 1
            records.append(
                DatasetSampleRef(
                    formal_sample_index=0,
                    split=split,
                    scenario=scenario,
                    image_relpath=image_path.relative_to(root).as_posix(),
                    label_relpath=labels[stem].relative_to(root).as_posix(),
                    truth_relpath=truths[stem].relative_to(root).as_posix(),
                    image_sha256=image_sha,
                    truth_count=len(truth_polygons),
                )
            )
        if dict(scenarios) != _EXPECTED_SCENARIO_COUNTS:
            raise DatasetVerificationError("SCENARIO_COUNTS_INVALID")
        ordered = tuple(
            replace(record, formal_sample_index=index)
            for index, record in enumerate(
                sorted(records, key=lambda item: item.image_sha256)
            )
        )
        test_access = None
        if split == "test":
            if access_grant is None:
                raise DatasetVerificationError("TEST_SEALED")
            test_access = {
                "event_sha256": access_grant.event_sha256,
                "sealed_member_inventory_sha256": access_grant.sealed_member_inventory_sha256,
                "threshold_lock_sha256s": list(access_grant.threshold_lock_sha256s),
                "granted_at": access_grant.granted_at,
            }
        document = {
            "schema_version": SCHEMA_VERSION,
            "split": split,
            "archive_sha256": archive_sha256,
            "sample_count": len(ordered),
            "scenario_counts": dict(sorted(scenarios.items())),
            "rasterizer": _RASTERIZER,
            "test_access": test_access,
            "samples": [
                {
                    "formal_sample_index": sample.formal_sample_index,
                    "split": sample.split,
                    "scenario": sample.scenario,
                    "image_relpath": sample.image_relpath,
                    "label_relpath": sample.label_relpath,
                    "truth_relpath": sample.truth_relpath,
                    "image_sha256": sample.image_sha256,
                    "truth_count": sample.truth_count,
                }
                for sample in ordered
            ],
        }
        inventory_path = root / "inventory.json"
        inventory_sha = atomic_write_json(inventory_path, document)
        inventory_path.chmod(0o444)
        sha_path = root / "inventory.sha256"
        try:
            with sha_path.open("x", encoding="ascii") as stream:
                stream.write(f"{inventory_sha}  inventory.json\n")
                stream.flush()
                os.fsync(stream.fileno())
            sha_path.chmod(0o444)
        except OSError as error:
            raise DatasetVerificationError("INVENTORY_WRITE_FAILED") from error
        return DatasetInventory(
            SCHEMA_VERSION,
            split,
            archive_sha256,
            inventory_sha,
            root,
            len(ordered),
            dict(scenarios),
            ordered,
            None if access_grant is None else access_grant.event_sha256,
        )


def _require_rasterizer_version() -> None:
    if PIL.__version__ != _RASTERIZER["version"]:
        raise DatasetVerificationError("RASTERIZER_VERSION_MISMATCH")


def _round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def rasterize_polygon(
    polygon_xy: tuple[tuple[float, float], ...], width: int, height: int
) -> np.ndarray:
    _require_rasterizer_version()
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, int)
        or not isinstance(height, int)
        or width <= 0
        or height <= 0
        or len(polygon_xy) < 3
    ):
        raise DatasetVerificationError("POLYGON_RASTERIZATION_INPUT_INVALID")
    pixels: list[tuple[int, int]] = []
    for point in polygon_xy:
        if len(point) != 2:
            raise DatasetVerificationError("POLYGON_RASTERIZATION_INPUT_INVALID")
        x, y = point
        if not (math.isfinite(x) and math.isfinite(y) and 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise DatasetVerificationError("POLYGON_RASTERIZATION_INPUT_INVALID")
        pixels.append(
            (
                min(width - 1, max(0, _round_half_up(x * (width - 1)))),
                min(height - 1, max(0, _round_half_up(y * (height - 1)))),
            )
        )
    image = Image.new("1", (width, height), 0)
    ImageDraw.Draw(image).polygon(pixels, fill=1)
    return np.asarray(image, dtype=bool)


def _read_truth(path: Path, split: Split) -> dict[str, object]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            document = json.load(stream, parse_float=Decimal)
    except (OSError, json.JSONDecodeError, InvalidOperation) as error:
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID") from error
    if not isinstance(document, dict):
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
    scenario = document.get("scenario")
    instances = document.get("instances")
    visible_count = document.get("visible_instance_count")
    if (
        document.get("split") != split
        or scenario not in _EXPECTED_SCENARIO_COUNTS
        or not isinstance(instances, list)
        or isinstance(visible_count, bool)
        or not isinstance(visible_count, int)
        or visible_count != len(instances)
    ):
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
    expected_count = {
        "no_cup": 0,
        "one_cup_distractors": 1,
        "two_cups": 2,
        "cup_near_bottle": 1,
    }[scenario]
    if len(instances) != expected_count:
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
    _truth_polygons(document)
    return document


def _truth_polygons(
    truth: Mapping[str, object],
) -> tuple[tuple[tuple[Decimal, Decimal], ...], ...]:
    instances = truth.get("instances")
    if not isinstance(instances, list):
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
    result: list[tuple[tuple[Decimal, Decimal], ...]] = []
    for instance in instances:
        if not isinstance(instance, dict):
            raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
        raw_polygon = instance.get("polygon_xy")
        if not isinstance(raw_polygon, list) or len(raw_polygon) < 3:
            raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
        polygon: list[tuple[Decimal, Decimal]] = []
        for point in raw_polygon:
            if not isinstance(point, list) or len(point) != 2:
                raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
            try:
                x, y = (Decimal(str(point[0])), Decimal(str(point[1])))
            except InvalidOperation as error:
                raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID") from error
            if not (x.is_finite() and y.is_finite() and 0 <= x <= 1 and 0 <= y <= 1):
                raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
            polygon.append((x, y))
        result.append(tuple(polygon))
    return tuple(result)


def _read_label_polygons(
    path: Path,
) -> tuple[tuple[tuple[Decimal, Decimal], ...], ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise DatasetVerificationError("LABEL_DOCUMENT_INVALID") from error
    polygons: list[tuple[tuple[Decimal, Decimal], ...]] = []
    for line in lines:
        fields = line.split()
        if len(fields) < 7 or len(fields) % 2 != 1 or fields[0] != "0":
            raise DatasetVerificationError("LABEL_DOCUMENT_INVALID")
        try:
            values = tuple(Decimal(value) for value in fields[1:])
        except InvalidOperation as error:
            raise DatasetVerificationError("LABEL_DOCUMENT_INVALID") from error
        if any(not value.is_finite() or not 0 <= value <= 1 for value in values):
            raise DatasetVerificationError("LABEL_DOCUMENT_INVALID")
        polygons.append(tuple(zip(values[::2], values[1::2], strict=True)))
    return tuple(polygons)


def load_truth_samples(
    dataset_root: Path,
    split: Split,
    inventory: DatasetInventory,
) -> tuple[TruthSample, ...]:
    _require_rasterizer_version()
    root = Path(dataset_root)
    if (
        split not in {"val", "test"}
        or inventory.split != split
        or root.resolve() != inventory.dataset_root.resolve()
    ):
        raise DatasetVerificationError("TRUTH_INVENTORY_MISMATCH")
    if split == "test":
        _require_sha256(inventory.test_access_event_sha256, "TEST_SEALED")
    elif inventory.test_access_event_sha256 is not None:
        raise DatasetVerificationError("TRUTH_INVENTORY_MISMATCH")
    samples: list[TruthSample] = []
    for sample_ref in inventory.samples:
        truth = _read_truth(root / sample_ref.truth_relpath, split)
        polygons = _truth_polygons(truth)
        raw_instances = truth["instances"]
        assert isinstance(raw_instances, list)
        instances: list[TruthInstance] = []
        stem = Path(sample_ref.truth_relpath).stem
        for instance_index, (raw_instance, decimal_polygon) in enumerate(
            zip(raw_instances, polygons, strict=True)
        ):
            assert isinstance(raw_instance, dict)
            mask = rasterize_polygon(
                tuple((float(x), float(y)) for x, y in decimal_polygon),
                _EXPECTED_IMAGE_SIZE[0],
                _EXPECTED_IMAGE_SIZE[1],
            )
            relative_path = (
                Path("truth_masks")
                / split
                / f"{stem}-{instance_index:02d}.json"
            )
            mask_path = root / relative_path
            if mask_path.exists() or mask_path.is_symlink():
                raise DatasetVerificationError("TRUTH_MASK_ALREADY_EXISTS")
            atomic_write_json(mask_path, encode_mask_rle(mask))
            mask_path.chmod(0o444)
            decoded_sha = hashlib.sha256(
                mask.astype(np.uint8, copy=False).tobytes(order="C")
            ).hexdigest()
            body_name = raw_instance.get("body_name")
            if not isinstance(body_name, str) or not body_name.startswith("plastic_cup"):
                raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
            instances.append(
                TruthInstance(
                    instance_id=f"{body_name}-{instance_index}",
                    label="plastic_cup",
                    mask=MaskRef(
                        relative_path=relative_path.as_posix(),
                        sha256=decoded_sha,
                        pixel_count=int(mask.sum()),
                        image_width=_EXPECTED_IMAGE_SIZE[0],
                        image_height=_EXPECTED_IMAGE_SIZE[1],
                    ),
                )
            )
        samples.append(
            TruthSample(
                formal_sample_index=sample_ref.formal_sample_index,
                split=split,
                scenario=sample_ref.scenario,
                image_relpath=sample_ref.image_relpath,
                image_sha256=sample_ref.image_sha256,
                image_width=_EXPECTED_IMAGE_SIZE[0],
                image_height=_EXPECTED_IMAGE_SIZE[1],
                instances=tuple(instances),
            )
        )
    return tuple(samples)
