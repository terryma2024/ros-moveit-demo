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

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

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


def choose_candidate(*candidates: CandidateEvaluation) -> SelectionVerdict:
    """Apply the frozen margins and prefer the retained mixed model unless a challenger clearly wins."""

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

    head_cells = {
        name: _cell(candidate.static_image_metrics, "head", "mask_map50_95")
        for name, candidate in by_id.items()
    }
    task_cells = {
        name: _cell(candidate.static_image_metrics, "task", "mask_map50_95")
        for name, candidate in by_id.items()
    }
    best_task = max(task_cells.values())
    if best_task - task_cells["C"] > TASK_RETENTION_MARGIN:
        raise EvaluationError(
            "EVALUATION_TASK_RETENTION_LOST: the mixed model gives up "
            f"{best_task - task_cells['C']:.3f} mask mAP on the task domain"
        )
    winner = "C"
    for name in ("A", "B"):
        if head_cells[name] - head_cells[winner] > MASK_MAP_MARGIN:
            winner = name
    for name, candidate in by_id.items():
        if name == winner:
            continue
        for domain in ("head", "task"):
            if (
                _cell(candidate.static_image_metrics, domain, "recall")
                - _cell(by_id[winner].static_image_metrics, domain, "recall")
                > RECALL_MARGIN
            ):
                raise EvaluationError(
                    f"EVALUATION_RECALL_MARGIN: {name} beats {winner} on {domain} recall by more than "
                    "the margin, so neither can be selected without retuning"
                )
    reason = (
        f"{winner} holds the best head cell within the margins and keeps the task domain within "
        f"{TASK_RETENTION_MARGIN}"
    )
    return SelectionVerdict(
        candidate_id=winner, head_mask_map=head_cells, task_mask_map=task_cells, reason=reason
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
