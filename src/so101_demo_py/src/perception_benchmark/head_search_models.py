"""Frozen-candidate evaluation for Head Search: scene-level statistics and the A/B/C verdict.

Three candidates are compared once, on data they never trained or tuned on: the pinned task-camera
baseline A, the head-only candidate B and the mixed candidate C. The gate has three duties. It must
resample whole camera scenes rather than frames, because one deployment sees one scene at a time and
frames from a scene are not independent evidence. It must keep the static-image measurements and the
held-out detector/tracker episode measurements in separate sections, because they answer different
questions. And it must prefer the retained mixed model unless a challenger wins the head domain by a
declared margin without giving up the task domain.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import numpy as np
from so101_demo.perception_benchmark.contracts import canonical_sha256

#: the frozen candidate set, in the order the plan names them
CANDIDATE_IDS = ("A", "B", "C")
#: a challenger must beat the retained model by this much on the head cell (AP, F1 and recall)
MASK_MAP_MARGIN = 0.01
F1_MARGIN = 0.01
RECALL_MARGIN = 0.01
#: a challenger may not lose more than this on bbox-centre p95
BBOX_P95_MARGIN_PX = 2.0
#: the mixed model must keep the task domain within this much of the best task cell
TASK_RETENTION_MARGIN = 0.01
#: the detector must keep up with the control loop the design freezes
LATENCY_BUDGET_MS_PER_FRAME = 20.0
#: the plan's frozen bootstrap size
DEFAULT_REPETITIONS = 10_000
INDEPENDENT_UNIT = "scene_group_id"


class EvaluationError(ValueError):
    """An evaluation the gate must refuse, named so a caller can refuse by name."""


@dataclass(frozen=True, slots=True)
class SceneBootstrapResult:
    """One scene-level bootstrap over a paired measurement."""

    independent_unit: str
    unit_count: int
    repetitions: int
    seed: int
    mean: float
    interval: tuple[float, float]


def _frame_value(frame: Mapping[str, object]) -> float:
    value = frame.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationError("EVALUATION_VALUE_REQUIRED: every frame needs a finite value")
    number = float(value)
    if not math.isfinite(number):
        raise EvaluationError("EVALUATION_VALUE_REQUIRED: every frame needs a finite value")
    return number


def paired_scene_bootstrap(
    frames: Sequence[Mapping[str, object]],
    metric: Callable[[Sequence[Mapping[str, object]]], float] | None = None,
    *,
    repetitions: int = DEFAULT_REPETITIONS,
    seed: int = 20260930,
) -> SceneBootstrapResult:
    """Resample whole scenes and report the interval of the (paired) statistic.

    `frames` is one flat sequence whose records carry their `scene_group_id`; the resampling unit is the
    scene, and every frame of a drawn scene is drawn with it, so the interval reflects the number of
    independent scenes rather than the number of images.
    """

    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions <= 0:
        raise EvaluationError("EVALUATION_REPETITIONS_INVALID: repetitions must be positive")
    items = tuple(frames)
    if not items:
        raise EvaluationError("EVALUATION_FRAMES_REQUIRED: the bootstrap needs frames")
    scenes: dict[str, list[Mapping[str, object]]] = {}
    for frame in items:
        scene = frame.get(INDEPENDENT_UNIT)
        if not isinstance(scene, str) or not scene:
            raise EvaluationError(
                f"EVALUATION_SCENE_REQUIRED: every frame needs a {INDEPENDENT_UNIT}"
            )
        scenes.setdefault(scene, []).append(frame)
    statistic = metric or (lambda drawn: float(np.mean([_frame_value(frame) for frame in drawn])))
    names = sorted(scenes)
    generator = np.random.default_rng(seed)
    values = np.empty(repetitions, dtype=np.float64)
    for repetition in range(repetitions):
        drawn_scenes = [
            names[index] for index in generator.integers(0, len(names), size=len(names))
        ]
        drawn: list[Mapping[str, object]] = []
        for name in drawn_scenes:
            drawn.extend(scenes[name])
        value = float(statistic(drawn))
        if not math.isfinite(value):
            raise EvaluationError("EVALUATION_STATISTIC_INVALID: the statistic must be finite")
        values[repetition] = value
    return SceneBootstrapResult(
        independent_unit=INDEPENDENT_UNIT,
        unit_count=len(names),
        repetitions=repetitions,
        seed=seed,
        mean=float(np.mean(values)),
        interval=(float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))),
    )


def paired_scene_delta_bootstrap(
    frames: Sequence[Mapping[str, object]],
    *,
    left_key: str,
    right_key: str,
    repetitions: int = DEFAULT_REPETITIONS,
    seed: int = 20260930,
) -> SceneBootstrapResult:
    """The paired scene-level interval of `left - right`, which is what a comparison actually asks.

    The two candidates are measured on the *same* frames, so every resample draws whole scenes once and
    differences the two candidates inside them. Pairing removes the scene-to-scene variation that would
    otherwise dominate the interval and hide a real difference.
    """

    items = tuple(frames)
    if not items:
        raise EvaluationError("EVALUATION_FRAMES_REQUIRED: the bootstrap needs frames")

    def delta(drawn: Sequence[Mapping[str, object]]) -> float:
        left = right = 0.0
        for frame in drawn:
            try:
                left += float(frame[left_key])
                right += float(frame[right_key])
            except (KeyError, TypeError, ValueError) as error:
                raise EvaluationError(
                    f"EVALUATION_VALUE_REQUIRED: every frame needs finite {left_key} and {right_key}"
                ) from error
        if not drawn:
            raise EvaluationError("EVALUATION_FRAMES_REQUIRED: a resample drew no frames")
        return (left - right) / len(drawn)

    return paired_scene_bootstrap(items, delta, repetitions=repetitions, seed=seed)


def load_dataset_sums(sums_path: Path | str) -> dict[str, str]:
    """Read a published `SHA256SUMS` file into a path-to-digest map."""

    sums: dict[str, str] = {}
    for line in Path(sums_path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2 or len(parts[0]) != 64:
            continue
        digest, name = parts
        sums[name[2:] if name.startswith("./") else name] = digest
    if not sums:
        raise EvaluationError(f"EVALUATION_SEAL_UNVERIFIED: {sums_path} holds no digests")
    return sums


def verify_split_manifest(
    manifest: Mapping[str, object],
    split: str,
    *,
    dataset_root: Path | str,
    domain: str,
    require_digests: bool = False,
    sums: Mapping[str, str] | None = None,
) -> list[Mapping[str, object]]:
    """Verify one split of a sealed dataset manifest before anything is measured on it.

    Declared counts are not evidence. The selected samples must be canonical relative paths that exist
    inside the dataset root they claim, their seeds and scene groups must not appear in another split, and
    any per-file digest a sample carries must match the bytes on disk.
    """

    if not isinstance(manifest, Mapping):
        raise EvaluationError(
            f"EVALUATION_MANIFEST_INVALID: the {domain} manifest is not a mapping"
        )
    for key in ("camera_name", "split_counts", "samples", "sample_count"):
        if key not in manifest:
            raise EvaluationError(
                f"EVALUATION_MANIFEST_INVALID: the {domain} manifest has no {key}"
            )
    if "dataset_contract" not in manifest and "schema_version" not in manifest:
        # the head dataset carries its contract marker, the pinned task dataset carries a schema version
        raise EvaluationError(
            f"EVALUATION_MANIFEST_INVALID: the {domain} manifest declares neither a dataset contract nor "
            "a schema version"
        )
    counts = manifest["split_counts"]
    if not isinstance(counts, Mapping) or split not in counts:
        raise EvaluationError(
            f"EVALUATION_SPLIT_MISSING: the {domain} manifest has no {split} split"
        )
    root = Path(dataset_root).resolve()
    if not root.is_dir():
        raise EvaluationError(f"EVALUATION_MANIFEST_INVALID: {root} is not a dataset root")
    samples: list[Mapping[str, object]] = []
    seeds: dict[object, str] = {}
    groups: dict[object, str] = {}
    for sample in manifest["samples"] or []:
        if not isinstance(sample, Mapping):
            raise EvaluationError(
                f"EVALUATION_MANIFEST_INVALID: the {domain} manifest has a non-mapping sample"
            )
        sample_split = sample.get("split")
        for key, seen, label, required in (
            ("seed", seeds, "seed", True),
            # the pinned task dataset identifies its episodes by seed; scene groups are checked where the
            # manifest carries them, and a seed is required everywhere
            ("scene_group_id", groups, "scene group", False),
        ):
            value = sample.get(key)
            if value is None:
                if required:
                    raise EvaluationError(
                        f"EVALUATION_MANIFEST_INVALID: the {domain} manifest has a sample without a "
                        f"{label}"
                    )
                continue
            previous = seen.get(value)
            if previous is not None and previous != sample_split:
                raise EvaluationError(
                    f"EVALUATION_SPLIT_LEAK: the {domain} manifest puts the same {label} {value!r} in "
                    f"both {previous} and {sample_split}"
                )
            seen[value] = str(sample_split)
        if sample_split != split:
            continue
        for key in ("image", "label", "truth"):
            relative = sample.get(key)
            if not isinstance(relative, str) or not relative:
                raise EvaluationError(
                    f"EVALUATION_MANIFEST_INVALID: a {domain} {split} sample has no {key}"
                )
            candidate = PurePosixPath(relative)
            if (
                candidate.is_absolute()
                or "\\" in relative
                or candidate.as_posix() != relative
                or any(part in {"", ".", ".."} for part in candidate.parts)
            ):
                raise EvaluationError(
                    f"EVALUATION_MANIFEST_INVALID: {relative!r} is not a canonical relative path"
                )
            path = root / relative
            if not path.is_file():
                raise EvaluationError(
                    f"EVALUATION_MANIFEST_INVALID: {relative!r} is not on disk under {root}"
                )
            if not path.resolve().is_relative_to(root):
                raise EvaluationError(
                    f"EVALUATION_MANIFEST_INVALID: {relative!r} resolves outside the dataset root"
                )
            digest = sample.get(f"{key}_sha256")
            if digest is None:
                # a manifest that carries no per-file digest is still sealed if the dataset publishes
                # sums for its files; without either, the gate cannot claim the file is the sealed one
                published = None if sums is None else sums.get(f"dataset/{relative}")
                if published is None:
                    raise EvaluationError(
                        f"EVALUATION_SEAL_UNVERIFIED: {relative!r} carries no digest and no published "
                        "sums cover it, so its seal cannot be verified"
                    )
                digest = published
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != digest:
                raise EvaluationError(
                    f"EVALUATION_MANIFEST_INVALID: {relative!r} does not match its recorded digest"
                )
        samples.append(sample)
    if len(samples) != int(counts[split]):
        raise EvaluationError(
            f"EVALUATION_SPLIT_INCOMPLETE: the {domain} manifest lists {len(samples)} {split} samples "
            f"but declares {counts[split]}"
        )
    return samples


@dataclass(frozen=True, slots=True)
class FrozenCandidate:
    """One candidate identity exactly as it was sealed before test access."""

    candidate_id: str
    weight_sha256: str
    document: Mapping[str, object]

    @property
    def sha256(self) -> str:
        return canonical_sha256(dict(self.document))


def load_frozen_candidate(
    path: Path | str, *, expected_sha256: str | None = None
) -> FrozenCandidate:
    """Read a frozen candidate document, refusing a weight that is not the sealed one."""

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise EvaluationError("EVALUATION_FROZEN_IDENTITY_INVALID: the document must be a mapping")
    # a candidate that is not promotable - a smoke plan, for instance - never enters model selection
    if "promotable" in document and document["promotable"] is not True:
        raise EvaluationError(
            "EVALUATION_CANDIDATE_NOT_PROMOTABLE: this candidate records promotable "
            f"{document['promotable']!r}, so it cannot be selected"
        )
    for key in (
        "candidate_id",
        "weight_sha256",
        "operating_points",
        "tracker",
        "postprocess",
        "runtime",
    ):
        if key not in document:
            raise EvaluationError(f"EVALUATION_FROZEN_IDENTITY_INVALID: the document lacks {key}")
    candidate_id = str(document["candidate_id"])
    if candidate_id not in CANDIDATE_IDS:
        raise EvaluationError(
            f"EVALUATION_FROZEN_IDENTITY_INVALID: {candidate_id!r} is not one of {CANDIDATE_IDS}"
        )
    digest = str(document["weight_sha256"])
    if len(digest) != 64:
        raise EvaluationError(
            "EVALUATION_FROZEN_IDENTITY_INVALID: the weight digest must be sha256"
        )
    if expected_sha256 is not None and digest != expected_sha256:
        raise EvaluationError(
            "EVALUATION_FROZEN_IDENTITY_DRIFT: the weight is not the one this evaluation froze"
        )
    for domain in ("head", "task"):
        if domain not in (document["operating_points"] or {}):
            raise EvaluationError(
                f"EVALUATION_FROZEN_IDENTITY_INVALID: no {domain} operating point is sealed"
            )
    return FrozenCandidate(candidate_id=candidate_id, weight_sha256=digest, document=document)


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    """One candidate's measured performance, kept in its two separate measurement families."""

    candidate_id: str
    weight_sha256: str
    static_image_metrics: Mapping[str, Mapping[str, float]]
    held_out_episode_metrics: Mapping[str, Mapping[str, float]]
    latency_ms_per_frame: float
    no_cup_false_candidates: int


@dataclass(frozen=True, slots=True)
class SelectionVerdict:
    """The gate's decision and the reason for it."""

    candidate_id: str
    head_mask_map: Mapping[str, float]
    task_mask_map: Mapping[str, float]
    reason: str


def _cell(metrics: Mapping[str, Mapping[str, float]], domain: str, key: str) -> float:
    try:
        value = float(metrics[domain][key])
    except (KeyError, TypeError) as error:
        raise EvaluationError(
            f"EVALUATION_METRIC_MISSING: the {domain} cell has no {key}"
        ) from error
    if not math.isfinite(value):
        raise EvaluationError(f"EVALUATION_METRIC_MISSING: the {domain} {key} is not finite")
    return value


def _check_safety(candidate: CandidateEvaluation, retained: CandidateEvaluation) -> None:
    if candidate.no_cup_false_candidates:
        raise EvaluationError(
            f"EVALUATION_FALSE_CANDIDATE: {candidate.candidate_id} reports "
            f"{candidate.no_cup_false_candidates} false candidates on empty scenes"
        )
    if not math.isfinite(float(candidate.latency_ms_per_frame)) or (
        float(candidate.latency_ms_per_frame) > LATENCY_BUDGET_MS_PER_FRAME
    ):
        raise EvaluationError(
            f"EVALUATION_LATENCY_BUDGET: {candidate.candidate_id} needs "
            f"{candidate.latency_ms_per_frame} ms per frame"
        )
    for domain in ("head", "task"):
        candidate_p95 = _cell(candidate.held_out_episode_metrics, domain, "bbox_center_p95_px")
        retained_p95 = _cell(retained.held_out_episode_metrics, domain, "bbox_center_p95_px")
        if candidate_p95 - retained_p95 > BBOX_P95_MARGIN_PX:
            raise EvaluationError(
                f"EVALUATION_BBOX_MARGIN: {candidate.candidate_id} is {candidate_p95 - retained_p95:.2f} "
                f"px worse than the retained model on the {domain} domain"
            )


def _family_cell(candidate: CandidateEvaluation, family: str, domain: str, key: str) -> float:
    metrics = (
        candidate.static_image_metrics
        if family == "static_image"
        else candidate.held_out_episode_metrics
    )
    return _cell(metrics, domain, key)


def _head_cells(candidate: CandidateEvaluation, family: str, key: str) -> float:
    metrics = (
        candidate.static_image_metrics
        if family == "static_image"
        else candidate.held_out_episode_metrics
    )
    return _cell(metrics, "head", key)


def _task_cells(candidate: CandidateEvaluation, family: str, key: str) -> float:
    metrics = (
        candidate.static_image_metrics
        if family == "static_image"
        else candidate.held_out_episode_metrics
    )
    return _cell(metrics, "task", key)


def choose_candidate(*candidates: CandidateEvaluation) -> SelectionVerdict:
    """Apply the frozen margins and prefer the retained mixed model unless a challenger clearly wins.

    A challenger replaces the retained model only when it wins the head domain in **both** measurement
    families by the declared margins - the static-image cells and the held-out detector/tracker episodes -
    and only when the retained model keeps the task domain in both. A candidate that wins one family and
    loses the other is not a decision the frozen evidence can support, so the retained model stays.
    """

    by_id: dict[str, CandidateEvaluation] = {}
    for candidate in candidates:
        if candidate.candidate_id in by_id:
            raise EvaluationError(
                f"EVALUATION_CANDIDATE_SET_INVALID: {candidate.candidate_id} appears twice"
            )
        by_id[candidate.candidate_id] = candidate
    if set(by_id) != set(CANDIDATE_IDS):
        raise EvaluationError(
            f"EVALUATION_CANDIDATE_SET_INVALID: the gate needs exactly {CANDIDATE_IDS}, got "
            f"{sorted(by_id)}"
        )
    retained = by_id["C"]
    for candidate in candidates:
        _check_safety(candidate, retained)

    head_mask_map = {
        name: _head_cells(candidate, "static_image", "mask_map50_95")
        for name, candidate in by_id.items()
    }
    task_mask_map = {
        name: _task_cells(candidate, "static_image", "mask_map50_95")
        for name, candidate in by_id.items()
    }
    best_task_static = max(task_mask_map.values())
    if best_task_static - task_mask_map["C"] > TASK_RETENTION_MARGIN:
        raise EvaluationError(
            "EVALUATION_TASK_RETENTION_LOST: the mixed model gives up "
            f"{best_task_static - task_mask_map['C']:.3f} mask mAP on the task domain"
        )
    best_task_episode = max(
        _task_cells(candidate, "held_out_episode", "recall") for candidate in by_id.values()
    )
    if (
        best_task_episode - _task_cells(retained, "held_out_episode", "recall")
        > TASK_RETENTION_MARGIN
    ):
        raise EvaluationError(
            "EVALUATION_TASK_RETENTION_LOST: the mixed model gives up task-domain recall on the "
            "held-out episodes"
        )

    static_winner = "C"
    for name in ("A", "B"):
        if head_mask_map[name] - head_mask_map[static_winner] > MASK_MAP_MARGIN:
            static_winner = name
    retained_recall = _head_cells(retained, "held_out_episode", "recall")
    retained_f1 = _head_cells(retained, "held_out_episode", "f1")
    qualifying = [
        name
        for name in ("A", "B")
        if _head_cells(by_id[name], "held_out_episode", "recall") - retained_recall > RECALL_MARGIN
        and retained_f1 - _head_cells(by_id[name], "held_out_episode", "f1") <= F1_MARGIN
    ]
    # the best qualifying challenger, never simply the last one inspected
    episode_winner = (
        max(qualifying, key=lambda name: _head_cells(by_id[name], "held_out_episode", "recall"))
        if qualifying
        else "C"
    )
    if static_winner != episode_winner:
        static_winner = episode_winner = "C"
    winner = static_winner
    # a selection nobody can defend is refused rather than recorded: if another candidate is better than
    # the winner on a measured cell by more than the margin, the frozen evidence does not support a choice
    for name, candidate in by_id.items():
        if name == winner:
            continue
        for family in ("static_image", "held_out_episode"):
            for key, margin, code in (
                ("f1", F1_MARGIN, "EVALUATION_F1_MARGIN"),
                ("recall", RECALL_MARGIN, "EVALUATION_RECALL_MARGIN"),
            ):
                for domain in ("head", "task"):
                    rival = _family_cell(candidate, family, domain, key)
                    chosen = _family_cell(by_id[winner], family, domain, key)
                    if rival - chosen > margin:
                        raise EvaluationError(
                            f"{code}: {name} beats {winner} on the {family} {domain} {key} by "
                            f"{rival - chosen:.3f}, so neither can be selected without retuning"
                        )
    for name, candidate in by_id.items():
        if name == winner:
            continue
        for domain in ("head", "task"):
            rival = _cell(candidate.static_image_metrics, domain, "f1")
            chosen = _cell(by_id[winner].static_image_metrics, domain, "f1")
            if rival - chosen > F1_MARGIN:
                raise EvaluationError(
                    f"EVALUATION_F1_MARGIN: {name} beats {winner} on the static-image {domain} F1 by "
                    f"{rival - chosen:.3f}, so neither can be selected without retuning"
                )
            rival_recall = _cell(candidate.static_image_metrics, domain, "recall")
            chosen_recall = _cell(by_id[winner].static_image_metrics, domain, "recall")
            if rival_recall - chosen_recall > RECALL_MARGIN:
                raise EvaluationError(
                    f"EVALUATION_RECALL_MARGIN: {name} beats {winner} on the static-image {domain} "
                    "recall by more than the margin, so neither can be selected without retuning"
                )
    reason = (
        f"{winner} holds the best head cells in both measurement families within the margins and keeps "
        f"the task domain within {TASK_RETENTION_MARGIN}"
    )
    return SelectionVerdict(
        candidate_id=winner,
        head_mask_map=head_mask_map,
        task_mask_map=task_mask_map,
        reason=reason,
    )


#: the candidate the plan retains unless a challenger is demonstrably better
RETAINED_CANDIDATE = "C"


def require_selection_supported(
    verdict: SelectionVerdict, intervals: Mapping[str, tuple[float, float]]
) -> None:
    """A challenger may only replace the retained model on evidence, not on a point estimate.

    `intervals` maps a challenger's id to the paired scene-level interval of its advantage over the
    retained model on the deciding head cell. A challenger whose interval does not exclude zero has not
    shown an advantage the frozen data supports, and the gate refuses rather than recording a choice the
    evidence cannot carry.
    """

    if verdict.candidate_id == RETAINED_CANDIDATE:
        return
    interval = intervals.get(verdict.candidate_id)
    if interval is None:
        raise EvaluationError(
            f"EVALUATION_SELECTION_UNSUPPORTED: {verdict.candidate_id} was selected without a paired "
            "scene-level interval for its advantage over the retained model"
        )
    if not (float(interval[0]) > 0.0):
        raise EvaluationError(
            f"EVALUATION_SELECTION_UNSUPPORTED: {verdict.candidate_id}'s advantage over the retained "
            f"model is not supported by its paired scene interval {tuple(interval)}"
        )


@dataclass(frozen=True, slots=True)
class ComparisonPaths:
    comparison: Path
    verdict: Path


def write_comparison(
    root: Path | str,
    *,
    candidates: Sequence[CandidateEvaluation],
    verdict: SelectionVerdict,
    bootstrap_repetitions: int,
    scenes: Mapping[str, object] | None = None,
) -> ComparisonPaths:
    """Write the two reports, keeping the measurement families and the decision apart."""

    root = Path(root)
    comparison = root / "model-comparison.json"
    selection = root / "model-selection-verdict.json"
    if comparison.exists() or selection.exists():
        raise EvaluationError(
            f"EVALUATION_ROOT_EXISTS: {root} already holds a comparison; the gate never overwrites one"
        )
    root.mkdir(parents=True, exist_ok=True)
    comparison.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "bootstrap_repetitions": bootstrap_repetitions,
                "independent_unit": INDEPENDENT_UNIT,
                "scenes": dict(scenes or {}),
                "candidates": {
                    candidate.candidate_id: {
                        "weight_sha256": candidate.weight_sha256,
                        "static_image_metrics": {
                            domain: dict(cells)
                            for domain, cells in candidate.static_image_metrics.items()
                        },
                        "held_out_episode_metrics": {
                            domain: dict(cells)
                            for domain, cells in candidate.held_out_episode_metrics.items()
                        },
                        "latency_ms_per_frame": candidate.latency_ms_per_frame,
                        "no_cup_false_candidates": candidate.no_cup_false_candidates,
                    }
                    for candidate in candidates
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    selection.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "selected": verdict.candidate_id,
                "reason": verdict.reason,
                "head_mask_map50_95": dict(verdict.head_mask_map),
                "task_mask_map50_95": dict(verdict.task_mask_map),
                "bootstrap_repetitions": bootstrap_repetitions,
                "independent_unit": INDEPENDENT_UNIT,
                "margins": {
                    "mask_map50_95": MASK_MAP_MARGIN,
                    "f1": F1_MARGIN,
                    "recall": RECALL_MARGIN,
                    "bbox_center_p95_px": BBOX_P95_MARGIN_PX,
                    "task_retention": TASK_RETENTION_MARGIN,
                    "latency_ms_per_frame": LATENCY_BUDGET_MS_PER_FRAME,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return ComparisonPaths(comparison=comparison, verdict=selection)
