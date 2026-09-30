"""Low-frequency regression tests for the Head Search A/B/C evaluation gate.

The gate this file exercises decides which frozen candidate the calibration binds. Its statistics are
scene-level, not frame-level: one deployment sees one scene at a time, so resampling frames from the same
scene would pretend there is more independent evidence than there is.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from so101_demo.perception_benchmark.head_search_models import (
    CANDIDATE_IDS,
    CandidateEvaluation,
    EvaluationError,
    choose_candidate,
    paired_scene_bootstrap,
)


def _frames(*, scene: str, values: list[float]) -> list[dict]:
    return [
        {"scene_group_id": scene, "value": value, "no_cup_false_candidates": 0} for value in values
    ]


FRAMES_FROM_TWO_SCENES = _frames(scene="scene-a", values=[0.4, 0.6]) + _frames(
    scene="scene-b", values=[0.5, 0.7]
)


def test_bootstrap_resamples_scene_groups_not_frames() -> None:
    result = paired_scene_bootstrap(FRAMES_FROM_TWO_SCENES, repetitions=10_000, seed=17)

    assert result.independent_unit == "scene_group_id"
    assert result.unit_count == 2
    assert result.repetitions == 10_000
    assert result.interval[0] <= result.mean <= result.interval[1]


def test_bootstrap_defaults_to_the_frozen_repetition_count() -> None:
    result = paired_scene_bootstrap(FRAMES_FROM_TWO_SCENES, seed=17)

    assert result.repetitions == 10_000


def test_bootstrap_refuses_a_frame_without_a_scene() -> None:
    with pytest.raises(EvaluationError, match="EVALUATION_SCENE_REQUIRED"):
        paired_scene_bootstrap([{"value": 0.5}], repetitions=10, seed=17)


def _evaluation(
    candidate_id: str,
    *,
    head_ap: float,
    task_ap: float,
    head_recall: float = 0.9,
    task_recall: float = 0.9,
    head_f1: float = 0.9,
    task_f1: float = 0.9,
    bbox_p95_px: float = 1.0,
    no_cup_false_candidates: int = 0,
    latency_ms_per_frame: float = 5.0,
    weight_sha256: str | None = None,
) -> CandidateEvaluation:
    return CandidateEvaluation(
        candidate_id=candidate_id,
        weight_sha256=weight_sha256 or hashlib.sha256(candidate_id.encode()).hexdigest(),
        static_image_metrics={
            "head": {"mask_map50_95": head_ap, "recall": head_recall, "f1": head_f1},
            "task": {"mask_map50_95": task_ap, "recall": task_recall, "f1": task_f1},
        },
        held_out_episode_metrics={
            "head": {"recall": head_recall, "f1": head_f1, "bbox_center_p95_px": bbox_p95_px},
            "task": {"recall": task_recall, "f1": task_f1, "bbox_center_p95_px": bbox_p95_px},
        },
        latency_ms_per_frame=latency_ms_per_frame,
        no_cup_false_candidates=no_cup_false_candidates,
    )


A_EQUIVALENT = _evaluation("A", head_ap=0.10, task_ap=0.50)
B_EQUIVALENT = _evaluation("B", head_ap=0.505, task_ap=0.495)
C_EQUIVALENT_RETAINED = _evaluation("C", head_ap=0.507, task_ap=0.508)


def test_all_equivalent_candidates_prefer_retained_mixed_model() -> None:
    verdict = choose_candidate(A_EQUIVALENT, B_EQUIVALENT, C_EQUIVALENT_RETAINED)

    assert verdict.candidate_id == "C"


def test_a_candidate_must_win_by_a_margin_to_replace_the_retained_model() -> None:
    # B is ahead of C on the head cell but by less than the 0.01 AP margin: no replacement
    thin = _evaluation("B", head_ap=0.512, task_ap=0.508)
    assert choose_candidate(A_EQUIVALENT, thin, C_EQUIVALENT_RETAINED).candidate_id == "C"
    clear = _evaluation("B", head_ap=0.53, task_ap=0.508)
    assert choose_candidate(A_EQUIVALENT, clear, C_EQUIVALENT_RETAINED).candidate_id == "B"


def test_the_task_domain_must_be_retained_within_its_margin() -> None:
    # C keeps its head cell but loses more than the retention margin on the task domain
    degraded = _evaluation("C", head_ap=0.52, task_ap=0.45)
    with pytest.raises(EvaluationError, match="EVALUATION_TASK_RETENTION_LOST"):
        choose_candidate(A_EQUIVALENT, B_EQUIVALENT, degraded)


def test_an_unsafe_candidate_is_never_selected() -> None:
    unsafe = _evaluation("B", head_ap=0.9, task_ap=0.9, no_cup_false_candidates=1)
    with pytest.raises(EvaluationError, match="EVALUATION_FALSE_CANDIDATE"):
        choose_candidate(A_EQUIVALENT, unsafe, C_EQUIVALENT_RETAINED)
    slow = _evaluation("B", head_ap=0.9, task_ap=0.9, latency_ms_per_frame=500.0)
    with pytest.raises(EvaluationError, match="EVALUATION_LATENCY_BUDGET"):
        choose_candidate(A_EQUIVALENT, slow, C_EQUIVALENT_RETAINED)
    loose = _evaluation("B", head_ap=0.9, task_ap=0.9, bbox_p95_px=9.0)
    with pytest.raises(EvaluationError, match="EVALUATION_BBOX_MARGIN"):
        choose_candidate(A_EQUIVALENT, loose, C_EQUIVALENT_RETAINED)


def test_the_candidate_set_must_hold_the_three_frozen_identities() -> None:
    assert CANDIDATE_IDS == ("A", "B", "C")
    with pytest.raises(EvaluationError, match="EVALUATION_CANDIDATE_SET_INVALID"):
        choose_candidate(A_EQUIVALENT, B_EQUIVALENT)
    duplicate = _evaluation("B", head_ap=0.1, task_ap=0.1)
    with pytest.raises(EvaluationError, match="EVALUATION_CANDIDATE_SET_INVALID"):
        choose_candidate(A_EQUIVALENT, B_EQUIVALENT, duplicate)


def test_comparison_report_keeps_static_and_episode_metrics_separate(tmp_path: Path) -> None:
    from so101_demo.perception_benchmark.head_search_models import write_comparison

    verdict = choose_candidate(A_EQUIVALENT, B_EQUIVALENT, C_EQUIVALENT_RETAINED)
    paths = write_comparison(
        tmp_path,
        candidates=(A_EQUIVALENT, B_EQUIVALENT, C_EQUIVALENT_RETAINED),
        verdict=verdict,
        bootstrap_repetitions=10_000,
    )

    comparison = json.loads(paths.comparison.read_text(encoding="utf-8"))
    selection = json.loads(paths.verdict.read_text(encoding="utf-8"))
    assert set(comparison["candidates"]) == {"A", "B", "C"}
    for entry in comparison["candidates"].values():
        assert set(entry["static_image_metrics"]) == {"head", "task"}
        assert set(entry["held_out_episode_metrics"]) == {"head", "task"}, (
            "the two measurement families must never be merged"
        )
        assert "bbox_center_p95_px" not in entry["static_image_metrics"]["head"]
    assert selection["selected"] == "C"
    assert selection["bootstrap_repetitions"] == 10_000
    assert selection["independent_unit"] == "scene_group_id"


def test_a_candidate_whose_weight_changed_is_refused(tmp_path: Path) -> None:
    from so101_demo.perception_benchmark.head_search_models import load_frozen_candidate

    document = {
        "candidate_id": "C",
        "weight_sha256": "a" * 64,
        "operating_points": {"head": {}, "task": {}},
        "tracker": {"iou": 0.3},
        "postprocess": {},
        "runtime": {},
    }
    path = tmp_path / "frozen-c.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    loaded = load_frozen_candidate(path)
    assert loaded.candidate_id == "C" and loaded.weight_sha256 == "a" * 64
    document["weight_sha256"] = "b" * 64
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(EvaluationError, match="EVALUATION_FROZEN_IDENTITY_DRIFT"):
        load_frozen_candidate(path, expected_sha256="a" * 64)
