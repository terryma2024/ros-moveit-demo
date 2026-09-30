"""Closed identities for Head Search data, episodes, and candidates.

Tasks 2-4 consume exactly these three documents. The split seal fixes which `scene_group_id` belongs
to which image split, so one MuJoCo world state cannot leak across camera domains or into val/test.
The episode validator keeps the calibration, held-out evaluation and 40-scenario qualification seed
lists mutually disjoint. The candidate identity binds one weight file to both camera-domain
operating points, the postprocess version, the tracker and the runtime, and that whole tuple is what
the frozen-model evaluation gate compares. Head Search never uses Grounded-SAM, so no key here names
one.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from so101_demo.perception_benchmark.contracts import OperatingPoint, canonical_sha256

IMAGE_SPLITS = ("train", "val", "test")
HEAD_SEARCH_CANDIDATE_IDS = ("A", "B", "C")
EPISODE_PARTITION_NAMES = ("calibration", "held_out", "qualification")
CANDIDATE_IDENTITY_KEYS = (
    "candidate_id",
    "weights_sha256",
    "head_operating_point",
    "task_operating_point",
    "postprocess_sha256",
    "tracker_sha256",
    "runtime_sha256",
)
SPLIT_SEAL_KEYS = ("camera_name", "dataset_sha256", "counts", "scene_groups")

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _require_digest(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA256 digest")
    return value


def _require_nonempty(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_mapping(name: str, value: object) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def validate_scene_group_partition(
    *, head: Mapping[str, str], task: Mapping[str, str]
) -> Mapping[str, str]:
    """Merge two camera-domain `scene_group_id` partitions, refusing any cross-domain leak.

    A MuJoCo world state that lands in `train` for one camera and `test` for the other would make
    the frozen-model comparison report its own training data as a held-out result, so the merged
    split must be identical wherever a group appears in both domains.
    """

    merged: dict[str, str] = {}
    for domain, partition in (("head", head), ("task", task)):
        for scene_group_id, split in _require_mapping(f"{domain} partition", partition).items():
            scene_group_id = _require_nonempty("scene_group_id", scene_group_id)
            if split not in IMAGE_SPLITS:
                raise ValueError(
                    f"SCENE_GROUP_SPLIT_INVALID: {scene_group_id} names unknown split {split!r}"
                )
            previous = merged.get(scene_group_id)
            if previous is not None and previous != split:
                raise ValueError(
                    f"SCENE_GROUP_SPLIT_LEAK: {scene_group_id} is {previous} in one camera domain "
                    f"and {split} in the {domain} camera domain"
                )
            merged[scene_group_id] = split
    return MappingProxyType(merged)


@dataclass(frozen=True, slots=True)
class HeadSearchSplitSeal:
    """The frozen image-split identity of one sealed YOLO-Seg dataset."""

    camera_name: str
    dataset_sha256: str
    counts: Mapping[str, int]
    scene_groups: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "camera_name", _require_nonempty("camera_name", self.camera_name))
        object.__setattr__(
            self, "dataset_sha256", _require_digest("dataset_sha256", self.dataset_sha256)
        )
        raw_counts = _require_mapping("counts", self.counts)
        counts: dict[str, int] = {}
        for split in IMAGE_SPLITS:
            value = raw_counts.get(split)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(
                    "SPLIT_COUNTS_INVALID: counts must hold exactly train, val, test as positive "
                    "image counts"
                )
            counts[split] = value
        if set(raw_counts) != set(IMAGE_SPLITS):
            raise ValueError(
                "SPLIT_COUNTS_INVALID: counts must hold exactly train, val, test as positive image "
                "counts"
            )
        raw_groups = _require_mapping("scene_groups", self.scene_groups)
        if set(raw_groups) != set(IMAGE_SPLITS):
            raise ValueError(
                "SCENE_GROUP_PARTITION_INVALID: scene_groups must hold exactly train, val, test"
            )
        groups: dict[str, tuple[str, ...]] = {}
        seen: dict[str, str] = {}
        for split in IMAGE_SPLITS:
            members = raw_groups[split]
            if isinstance(members, (str, bytes)) or not isinstance(members, Iterable):
                raise ValueError(
                    f"SCENE_GROUP_PARTITION_INVALID: {split} must list its scene_group_ids"
                )
            values = tuple(_require_nonempty("scene_group_id", item) for item in members)
            for scene_group_id in values:
                previous = seen.get(scene_group_id)
                if previous is not None and previous != split:
                    raise ValueError(
                        f"SCENE_GROUP_SPLIT_LEAK: {scene_group_id} is in {previous} and {split}"
                    )
                if previous is not None:
                    raise ValueError(
                        f"SCENE_GROUP_DUPLICATE: {scene_group_id} is listed twice in {split}"
                    )
                seen[scene_group_id] = split
            groups[split] = values
        object.__setattr__(self, "counts", MappingProxyType(counts))
        object.__setattr__(self, "scene_groups", MappingProxyType(groups))

    def to_document(self) -> dict[str, object]:
        return {
            "camera_name": self.camera_name,
            "dataset_sha256": self.dataset_sha256,
            "counts": {split: self.counts[split] for split in IMAGE_SPLITS},
            "scene_groups": {split: tuple(self.scene_groups[split]) for split in IMAGE_SPLITS},
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_document())

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> HeadSearchSplitSeal:
        if not isinstance(document, Mapping) or set(document) != set(SPLIT_SEAL_KEYS):
            raise ValueError(
                "SPLIT_SEAL_FIELDS_INVALID: document must hold exactly the split-seal keys"
            )
        return cls(
            camera_name=document["camera_name"],  # type: ignore[arg-type]
            dataset_sha256=document["dataset_sha256"],  # type: ignore[arg-type]
            counts=document["counts"],  # type: ignore[arg-type]
            scene_groups=document["scene_groups"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class CandidateIdentity:
    """One frozen A/B/C candidate: weights plus both operating points, tracker and runtime."""

    candidate_id: str
    weights_sha256: str
    head_operating_point: OperatingPoint
    task_operating_point: OperatingPoint
    postprocess_sha256: str
    tracker_sha256: str
    runtime_sha256: str

    def __post_init__(self) -> None:
        if self.candidate_id not in HEAD_SEARCH_CANDIDATE_IDS:
            raise ValueError("candidate_id must be one of A, B, C")
        for name in ("weights_sha256", "postprocess_sha256", "tracker_sha256", "runtime_sha256"):
            object.__setattr__(self, name, _require_digest(name, getattr(self, name)))
        for name in ("head_operating_point", "task_operating_point"):
            if not isinstance(getattr(self, name), OperatingPoint):
                raise ValueError(f"{name} must be an OperatingPoint")

    def to_document(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "weights_sha256": self.weights_sha256,
            "head_operating_point": self.head_operating_point.to_document(),
            "task_operating_point": self.task_operating_point.to_document(),
            "postprocess_sha256": self.postprocess_sha256,
            "tracker_sha256": self.tracker_sha256,
            "runtime_sha256": self.runtime_sha256,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_document())

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> CandidateIdentity:
        if not isinstance(document, Mapping) or set(document) != set(CANDIDATE_IDENTITY_KEYS):
            raise ValueError(
                "CANDIDATE_IDENTITY_FIELDS_INVALID: document must hold exactly the candidate-identity "
                "keys"
            )
        return cls(
            candidate_id=document["candidate_id"],  # type: ignore[arg-type]
            weights_sha256=document["weights_sha256"],  # type: ignore[arg-type]
            head_operating_point=OperatingPoint.from_document(
                document["head_operating_point"]  # type: ignore[arg-type]
            ),
            task_operating_point=OperatingPoint.from_document(
                document["task_operating_point"]  # type: ignore[arg-type]
            ),
            postprocess_sha256=document["postprocess_sha256"],  # type: ignore[arg-type]
            tracker_sha256=document["tracker_sha256"],  # type: ignore[arg-type]
            runtime_sha256=document["runtime_sha256"],  # type: ignore[arg-type]
        )


def validate_episode_seed_partitions(
    *, calibration: Iterable[int], held_out: Iterable[int], qualification: Iterable[int]
) -> Mapping[str, tuple[int, ...]]:
    """Return the three frozen episode seed lists, refusing any overlap or repeat."""

    partitions: dict[str, Iterable[int]] = {
        "calibration": calibration,
        "held_out": held_out,
        "qualification": qualification,
    }
    result: dict[str, tuple[int, ...]] = {}
    seen: dict[int, str] = {}
    for name in EPISODE_PARTITION_NAMES:
        seeds = partitions[name]
        if isinstance(seeds, (str, bytes)) or not isinstance(seeds, Iterable):
            raise ValueError(f"EPISODE_SEED_INVALID: {name} must be an iterable of integer seeds")
        values: list[int] = []
        for seed in seeds:
            if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
                raise ValueError(
                    f"EPISODE_SEED_INVALID: {name} seed {seed!r} must be a nonnegative integer"
                )
            if seed in values:
                raise ValueError(f"EPISODE_SEED_DUPLICATE: {name} repeats seed {seed}")
            if seed in seen:
                raise ValueError(
                    f"EPISODE_PARTITION_OVERLAP: seed {seed} is in {seen[seed]} and {name}"
                )
            values.append(seed)
            seen[seed] = name
        result[name] = tuple(values)
    return MappingProxyType(result)
