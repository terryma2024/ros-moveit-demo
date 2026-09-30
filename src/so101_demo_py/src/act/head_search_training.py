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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
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
            if not isinstance(members, (list, tuple)):
                raise ValueError(
                    f"SCENE_GROUP_PARTITION_INVALID: {split} must be a list or tuple of "
                    "scene_group_ids; a mapping, string, set or generator would lose or hide members"
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
        for split in IMAGE_SPLITS:
            if not 1 <= len(groups[split]) <= counts[split]:
                raise ValueError(
                    f"SCENE_GROUP_COUNT_INVALID: {split} lists {len(groups[split])} scene groups "
                    f"for {counts[split]} declared images"
                )
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


# ----------------------------------------------------------------------------------------------------------------------
# Candidate training plans: B learns from the head camera domain alone, C from the union of both camera domains with a
# frozen 1:1 batch composition, and both inherit candidate A's frozen hyperparameters.
# ----------------------------------------------------------------------------------------------------------------------

TRAINING_CONTRACT_KEYS = (
    "task",
    "model",
    "class_names",
    "classes",
    "imgsz",
    "epochs",
    "batch",
    "workers",
    "seed",
    "deterministic",
    "device",
    "allow_cpu_fallback",
    "amp",
    "optimizer",
    "patience",
    "plots",
    "shuffle",
    "checkpoint_score",
    "validation_domains",
    "dataset_domains",
    "promotable",
    "domain_train",
    "domain_val",
)
#: everything that must be identical between B and C, in the order it is hashed
HYPERPARAMETER_KEYS = (
    "task",
    "imgsz",
    "batch",
    "workers",
    "seed",
    "deterministic",
    "amp",
    "optimizer",
    "patience",
    "shuffle",
)
CHECKPOINT_SCORE = "0.5*head_val_mask_map50_95+0.5*task_val_mask_map50_95"
_CANDIDATE_IDS = ("A", "B", "C")


def _positive_count(name: str, value: object) -> int:
    if type(value) is not int or value <= 0:
        raise CandidatePlanError(f"CANDIDATE_CONTRACT_INVALID: {name} must be a positive integer")
    return value


class CandidatePlanError(ValueError):
    """A candidate plan the toolchain must refuse, named so a caller can refuse by name."""


@dataclass(frozen=True, slots=True)
class TrainingContract:
    """The frozen training inputs one or more candidates inherit."""

    device: str
    allow_cpu_fallback: bool
    checkpoint_score: str
    validation_domains: tuple[str, ...]
    dataset_domains: tuple[str, ...]
    batch_size: int
    epochs: int
    promotable: bool
    hyperparameters: Mapping[str, object]
    recipe: Mapping[str, object]
    domain_train: int
    domain_val: int

    def to_document(self) -> dict[str, object]:
        return {
            "recipe": dict(self.recipe),
            "domain_train": self.domain_train,
            "domain_val": self.domain_val,
            "device": self.device,
            "allow_cpu_fallback": self.allow_cpu_fallback,
            "checkpoint_score": self.checkpoint_score,
            "validation_domains": list(self.validation_domains),
            "dataset_domains": list(self.dataset_domains),
            "batch": self.batch_size,
            "epochs": self.epochs,
            "promotable": self.promotable,
            "hyperparameters": dict(self.hyperparameters),
        }


def load_training_contract(path: Path | str) -> TrainingContract:
    """Read one tracked candidate-training contract, refusing anything the device policy forbids."""

    contract_path = Path(path)
    if contract_path.is_symlink() or not contract_path.is_file():
        raise CandidatePlanError(
            f"CANDIDATE_CONTRACT_INVALID: contract must be a regular file: {contract_path}"
        )
    try:
        import yaml
    except ImportError as error:  # pragma: no cover - PyYAML is a package dependency
        raise CandidatePlanError("CANDIDATE_CONTRACT_INVALID: PyYAML is required") from error
    document = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise CandidatePlanError("CANDIDATE_CONTRACT_INVALID: contract must be a mapping")
    missing = set(TRAINING_CONTRACT_KEYS) - set(document)
    if missing:
        raise CandidatePlanError(
            "CANDIDATE_CONTRACT_INVALID: contract is missing " + ", ".join(sorted(missing))
        )
    unknown = set(document) - set(TRAINING_CONTRACT_KEYS)
    if unknown:
        raise CandidatePlanError(
            "CANDIDATE_CONTRACT_INVALID: contract carries unknown keys "
            + ", ".join(sorted(unknown))
        )
    device = str(document["device"])
    fallback = document["allow_cpu_fallback"]
    if device != "cuda":
        raise CandidatePlanError(
            f"CANDIDATE_DEVICE_INVALID: Head Search trains on cuda only, not {device!r}"
        )
    if type(fallback) is not bool or fallback:
        raise CandidatePlanError(
            "CANDIDATE_CPU_FALLBACK_FORBIDDEN: Head Search never falls back to the CPU"
        )
    score = str(document["checkpoint_score"])
    if score != CHECKPOINT_SCORE:
        raise CandidatePlanError(
            "CANDIDATE_CHECKPOINT_SCORE_INVALID: B and C share the two-domain score "
            f"{CHECKPOINT_SCORE!r}"
        )
    domains = tuple(str(value) for value in document["validation_domains"])
    if domains != ("head", "task"):
        raise CandidatePlanError(
            "CANDIDATE_VALIDATION_DOMAINS_INVALID: both camera domains must be scored"
        )
    batch = document["batch"]
    if type(batch) is not int or batch <= 0 or batch % 2 != 0:
        raise CandidatePlanError(
            "CANDIDATE_BATCH_INVALID: an even batch is required for a 1:1 domain composition"
        )
    epochs = document["epochs"]
    if type(epochs) is not int or epochs <= 0:
        raise CandidatePlanError("CANDIDATE_EPOCHS_INVALID: epochs must be a positive integer")
    if type(document["promotable"]) is not bool:
        raise CandidatePlanError("CANDIDATE_PROMOTABLE_INVALID: promotable must be boolean")
    return TrainingContract(
        device=device,
        allow_cpu_fallback=False,
        checkpoint_score=score,
        validation_domains=domains,
        dataset_domains=tuple(str(value) for value in document["dataset_domains"]),
        batch_size=batch,
        epochs=epochs,
        promotable=bool(document["promotable"]),
        hyperparameters=MappingProxyType({key: document[key] for key in HYPERPARAMETER_KEYS}),
        recipe=MappingProxyType(dict(document)),
        domain_train=_positive_count("domain_train", document.get("domain_train")),
        domain_val=_positive_count("domain_val", document.get("domain_val")),
    )


@dataclass(frozen=True, slots=True)
class CandidateBatch:
    """One training batch's frozen composition."""

    head_count: int
    task_count: int


@dataclass(frozen=True, slots=True)
class CandidatePlan:
    candidate_id: str
    train_count: int
    val_count: int
    domain_counts: Mapping[str, int]
    validation_counts: Mapping[str, int]
    batches: tuple[CandidateBatch, ...]
    batch_size: int
    epochs: int
    device: str
    allow_cpu_fallback: bool
    checkpoint_score: str
    validation_domains: tuple[str, ...]
    dataset_digests: Mapping[str, str]
    hyperparameters: Mapping[str, object]
    promotable: bool
    base_model_sha256: str
    recipe: Mapping[str, object]
    task_subset: tuple[int, ...]
    head_train_seeds: tuple[int, ...]
    head_val_seeds: tuple[int, ...]
    task_val_seeds: tuple[int, ...]

    def to_document(self) -> dict[str, object]:
        return {
            "base_model_sha256": self.base_model_sha256,
            "recipe": dict(self.recipe),
            "task_subset": list(self.task_subset),
            "head_train_seeds": list(self.head_train_seeds),
            "head_val_seeds": list(self.head_val_seeds),
            "task_val_seeds": list(self.task_val_seeds),
            "candidate_id": self.candidate_id,
            "train_count": self.train_count,
            "val_count": self.val_count,
            "domain_counts": dict(self.domain_counts),
            "validation_counts": dict(self.validation_counts),
            "batches": [
                {"head_count": batch.head_count, "task_count": batch.task_count}
                for batch in self.batches
            ],
            "batch_size": self.batch_size,
            "epochs": self.epochs,
            "device": self.device,
            "allow_cpu_fallback": self.allow_cpu_fallback,
            "checkpoint_score": self.checkpoint_score,
            "validation_domains": list(self.validation_domains),
            "dataset_digests": dict(self.dataset_digests),
            "hyperparameters": dict(self.hyperparameters),
            "promotable": self.promotable,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_document())


def _manifest_splits(
    name: str, manifest: Mapping[str, object]
) -> dict[str, list[Mapping[str, object]]]:
    """Read a sealed dataset manifest, refusing anything that is not one."""

    if not isinstance(manifest, Mapping):
        raise CandidatePlanError(f"CANDIDATE_MANIFEST_INVALID: {name} must be a manifest mapping")
    # ``dataset_contract`` and ``promotable`` are produced by this work's generator, but the
    # pinned external A dataset (Task 12 Step 1, revision b55430fb...) predates them and the plan
    # consumes it as-is. They are therefore optional here; a manifest without ``promotable`` is
    # treated as non-promotable, which is the safe reading and keeps HS-052's refusal intact.
    required = {"camera_name", "split_counts", "samples"}
    missing = required - set(manifest)
    if missing:
        raise CandidatePlanError(
            f"CANDIDATE_MANIFEST_INVALID: {name} is missing " + ", ".join(sorted(missing))
        )
    samples = manifest["samples"]
    if not isinstance(samples, (list, tuple)) or not samples:
        raise CandidatePlanError(f"CANDIDATE_MANIFEST_INVALID: {name} declares no samples")
    raw_counts = manifest["split_counts"]
    if not isinstance(raw_counts, Mapping):
        raise CandidatePlanError(f"CANDIDATE_MANIFEST_INVALID: {name} declares no split_counts")
    by_split: dict[str, list[Mapping[str, object]]] = {"train": [], "val": []}
    for split in ("train", "val"):
        declared = raw_counts.get(split)
        if type(declared) is not int or declared <= 0:
            raise CandidatePlanError(
                f"CANDIDATE_MANIFEST_INVALID: {name} needs a positive {split} count"
            )
    seeds: dict[object, str] = {}
    groups: dict[object, str] = {}
    for sample in samples:
        if not isinstance(sample, Mapping):
            raise CandidatePlanError(f"CANDIDATE_MANIFEST_INVALID: {name} has a non-mapping sample")
        split = sample.get("split")
        if split not in by_split:
            continue
        # ``scene_group_id`` is emitted by this work's generator; the pinned external A dataset
        # (revision b55430fb...) identifies scenes by ``scenario`` instead. Falling back keeps the
        # split-leak check meaningful for both shapes rather than skipping it for one of them.
        for key, seen, label in (
            ("seed", seeds, "seed"),
            ("scene_group_id", groups, "scene group"),
        ):
            value = sample.get(key)
            if value is None and key == "scene_group_id":
                value = sample.get("scenario")
            if value is None:
                raise CandidatePlanError(
                    f"CANDIDATE_MANIFEST_INVALID: {name} has a {split} sample without a {label}"
                )
            previous = seen.get(value)
            if previous is not None and previous != split:
                raise CandidatePlanError(
                    f"CANDIDATE_SPLIT_LEAK: {name} puts the same {label} {value!r} in both {previous} "
                    f"and {split}"
                )
            seen[value] = split
        by_split[split].append(sample)
    for split in ("train", "val"):
        if len(by_split[split]) != int(raw_counts[split]):
            raise CandidatePlanError(
                f"CANDIDATE_MANIFEST_INVALID: {name} declares {raw_counts[split]} {split} samples but "
                f"lists {len(by_split[split])}"
            )
    return by_split


def _ordered_seeds(samples: Sequence[Mapping[str, object]]) -> tuple[int, ...]:
    return tuple(sorted(int(sample["seed"]) for sample in samples))


def build_candidate_plan(
    candidate_id: str,
    *,
    head: Mapping[str, object],
    task: Mapping[str, object],
    contract: TrainingContract | Path | str,
    base_model_sha256: str,
) -> CandidatePlan:
    """Freeze one candidate's data union, batch composition and every effective input."""

    if candidate_id not in _CANDIDATE_IDS:
        raise CandidatePlanError(
            f"CANDIDATE_ID_INVALID: {candidate_id!r} is not one of {_CANDIDATE_IDS}"
        )
    if candidate_id == "A":
        raise CandidatePlanError(
            "CANDIDATE_ID_INVALID: candidate A is the pinned task-camera baseline and is not rebuilt here"
        )
    if not isinstance(base_model_sha256, str) or len(base_model_sha256) != 64:
        raise CandidatePlanError(
            "CANDIDATE_BASE_MODEL_INVALID: the frozen base weights need their sha256 digest"
        )
    trained = (
        contract if isinstance(contract, TrainingContract) else load_training_contract(contract)
    )
    head_splits = _manifest_splits("head manifest", head)
    task_splits = _manifest_splits("task manifest", task)
    head_digest = canonical_sha256(head)
    task_digest = canonical_sha256(task)
    if head.get("promotable") is False and trained.promotable:
        raise CandidatePlanError(
            "CANDIDATE_HEAD_NOT_SEALED: this is a smoke head dataset, so it can only train a "
            "non-promotable smoke plan"
        )
    if head_digest == task_digest:
        raise CandidatePlanError(
            "CANDIDATE_DOMAINS_ALIASED: the head and task domains are the same dataset"
        )
    for name, manifest in (("head", head), ("task", task)):
        camera = str(manifest.get("camera_name", ""))
        if not camera:
            raise CandidatePlanError(f"CANDIDATE_MANIFEST_INVALID: {name} manifest names no camera")
    if str(head.get("camera_name")) == str(task.get("camera_name")):
        raise CandidatePlanError(
            "CANDIDATE_DOMAINS_ALIASED: both candidates must come from different camera domains"
        )
    head_train = _ordered_seeds(head_splits["train"])
    task_train = _ordered_seeds(task_splits["train"])
    head_val = _ordered_seeds(head_splits["val"])
    task_val = _ordered_seeds(task_splits["val"])
    if len(head_train) < trained.domain_train or len(head_val) < trained.domain_val:
        raise CandidatePlanError(
            "CANDIDATE_DOMAIN_SHORT: the head domain is smaller than the contract's frozen targets"
        )
    if len(task_train) < trained.domain_train or len(task_val) < trained.domain_val:
        raise CandidatePlanError(
            "CANDIDATE_DOMAIN_SHORT: the task domain is smaller than the contract's frozen targets"
        )
    task_train_subset = task_train[: trained.domain_train]
    task_val_subset = task_val[: trained.domain_val]
    validation_counts = {"head": trained.domain_val, "task": trained.domain_val}
    if candidate_id == "C":
        domain_counts = {"head": trained.domain_train, "task": trained.domain_train}
        train_count = 2 * trained.domain_train
        val_count = 2 * trained.domain_val
        half = trained.batch_size // 2
        batches = [
            CandidateBatch(
                head_count=min(half, trained.domain_train - offset),
                task_count=min(half, trained.domain_train - offset),
            )
            for offset in range(0, trained.domain_train, half)
        ]
        task_subset = task_train_subset
    else:
        domain_counts = {"head": trained.domain_train}
        train_count = trained.domain_val * 0 + trained.domain_train
        # B trains on the head domain alone but is still scored on both validation domains, so its
        # validation union holds both cells and `val_count` counts them
        val_count = 2 * trained.domain_val
        batches = [
            CandidateBatch(
                head_count=min(trained.batch_size, trained.domain_train - offset), task_count=0
            )
            for offset in range(0, trained.domain_train, trained.batch_size)
        ]
        task_subset = ()
    promotable = bool(trained.promotable and head.get("promotable") is not False)
    return CandidatePlan(
        candidate_id=candidate_id,
        train_count=train_count,
        val_count=val_count,
        domain_counts=MappingProxyType(domain_counts),
        validation_counts=MappingProxyType(validation_counts),
        batches=tuple(batches),
        batch_size=trained.batch_size,
        epochs=trained.epochs,
        device=trained.device,
        allow_cpu_fallback=trained.allow_cpu_fallback,
        checkpoint_score=trained.checkpoint_score,
        validation_domains=trained.validation_domains,
        dataset_digests=MappingProxyType({"head": head_digest, "task": task_digest}),
        hyperparameters=trained.hyperparameters,
        promotable=promotable,
        base_model_sha256=base_model_sha256,
        recipe=trained.recipe,
        task_subset=task_subset,
        head_train_seeds=head_train[: trained.domain_train],
        head_val_seeds=head_val[: trained.domain_val],
        task_val_seeds=task_val_subset,
    )
