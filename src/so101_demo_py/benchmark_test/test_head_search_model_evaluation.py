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
    # winning only the static-image family is not a decision the frozen evidence supports
    static_only = _evaluation("B", head_ap=0.53, task_ap=0.508)
    assert choose_candidate(A_EQUIVALENT, static_only, C_EQUIVALENT_RETAINED).candidate_id == "C"
    # winning the head domain in both families replaces the retained model
    clear = _evaluation("B", head_ap=0.53, task_ap=0.508, head_recall=0.95, head_f1=0.95)
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


def _write_candidate(root: Path, candidate_id: str, weight_sha: str = "a" * 64) -> Path:
    path = root / f"frozen-{candidate_id.lower()}.json"
    path.write_text(
        json.dumps(
            {
                "candidate_id": candidate_id,
                "weight_sha256": weight_sha,
                "operating_points": {
                    "head": {"min_confidence": 0.4},
                    "task": {"min_confidence": 0.4},
                },
                "tracker": {"iou": 0.3},
                "postprocess": {"min_area_px2": 64},
                "runtime": {"device": "cuda"},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_compare_cli_refuses_an_incomplete_candidate_set(tmp_path: Path) -> None:
    from so101_demo.cli.evaluate_head_search_yolo_candidates import main

    candidates = [
        str(_write_candidate(tmp_path, "A", "a" * 64)),
        str(_write_candidate(tmp_path, "B", "b" * 64)),
    ]
    arguments = ["compare"]
    for path in candidates:
        arguments += ["--candidate", path]
    arguments += [
        "--head-dataset",
        str(tmp_path / "head.json"),
        "--task-dataset",
        str(tmp_path / "task.json"),
        "--episode-partitions",
        str(tmp_path / "partitions.json"),
        "--weights-dir",
        str(tmp_path),
        "--head-dataset-root",
        str(tmp_path),
        "--task-dataset-root",
        str(tmp_path),
        "--output",
        str(tmp_path / "out"),
    ]
    assert main(arguments) == 2


def test_compare_cli_refuses_a_drifted_weight_file(tmp_path: Path) -> None:
    from so101_demo.cli.evaluate_head_search_yolo_candidates import main

    for candidate_id, digest in (("A", "a" * 64), ("B", "b" * 64), ("C", "c" * 64)):
        _write_candidate(tmp_path, candidate_id, digest)
        (tmp_path / f"{candidate_id}.pt").write_bytes(f"weights-{candidate_id}".encode())
    root = tmp_path / "dataset"
    digests = {}
    for name, relative in (
        ("image", "images/test/1.png"),
        ("label", "labels/test/1.txt"),
        ("truth", "truth/test/1.json"),
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"payload")
        digests[f"{name}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    sample = {
        "seed": 1,
        "split": "test",
        "scene_group_id": "scene-1",
        "image": "images/test/1.png",
        "label": "labels/test/1.txt",
        "truth": "truth/test/1.json",
        **digests,
    }
    sealed = json.dumps(
        {
            "dataset_contract": "so101-head-search-yolo-seg-v1",
            "camera_name": "head_camera",
            "sample_count": 1,
            "split_counts": {"test": 1},
            "samples": [sample],
        }
    )
    (tmp_path / "head.json").write_text(sealed, encoding="utf-8")
    (tmp_path / "task.json").write_text(sealed, encoding="utf-8")
    (tmp_path / "partitions.json").write_text(
        json.dumps({"held_out_evaluation": [1]}), encoding="utf-8"
    )
    arguments = [
        "compare",
        "--candidate",
        str(tmp_path / "frozen-a.json"),
        "--candidate",
        str(tmp_path / "frozen-b.json"),
        "--candidate",
        str(tmp_path / "frozen-c.json"),
        "--head-dataset",
        str(tmp_path / "head.json"),
        "--task-dataset",
        str(tmp_path / "task.json"),
        "--episode-partitions",
        str(tmp_path / "partitions.json"),
        "--weights-dir",
        str(tmp_path),
        "--head-dataset-root",
        str(root),
        "--task-dataset-root",
        str(root),
        "--output",
        str(tmp_path / "out"),
    ]
    # the weight files do not hash to the sealed digests: the gate refuses that specific reason
    import contextlib
    import io

    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        assert main(arguments) == 2
    assert "EVALUATION_FROZEN_IDENTITY_DRIFT" in captured.getvalue(), captured.getvalue()


def test_paired_delta_bootstrap_differences_the_two_candidates_inside_each_scene() -> None:
    from so101_demo.perception_benchmark.head_search_models import paired_scene_delta_bootstrap

    frames = [
        {"scene_group_id": "scene-a", "left": 0.60, "right": 0.40},
        {"scene_group_id": "scene-a", "left": 0.62, "right": 0.42},
        {"scene_group_id": "scene-b", "left": 0.50, "right": 0.30},
        {"scene_group_id": "scene-b", "left": 0.48, "right": 0.28},
    ]
    result = paired_scene_delta_bootstrap(
        frames, left_key="left", right_key="right", repetitions=2_000
    )

    assert result.independent_unit == "scene_group_id" and result.unit_count == 2
    assert result.interval[0] > 0.0, "a systematic difference must survive scene resampling"
    assert result.mean == pytest.approx(0.20, abs=0.01)


def test_paired_delta_bootstrap_keeps_a_scene_level_effect_visible() -> None:
    """Scene-level pairing must not be defeated by within-scene variation."""

    from so101_demo.perception_benchmark.head_search_models import paired_scene_delta_bootstrap

    frames = []
    for scene, base in (("scene-a", 0.0), ("scene-b", 0.4), ("scene-c", 0.8)):
        for offset in (0.0, 0.05, -0.05):
            frames.append(
                {"scene_group_id": scene, "left": base + offset + 0.10, "right": base + offset}
            )
    result = paired_scene_delta_bootstrap(
        frames, left_key="left", right_key="right", repetitions=2_000
    )

    assert result.mean == pytest.approx(0.10, abs=1e-9)
    assert result.interval[0] >= 0.09


def test_split_manifest_verification_refuses_a_path_that_leaves_the_dataset(
    tmp_path: Path,
) -> None:
    from so101_demo.perception_benchmark.head_search_models import verify_split_manifest

    outside = tmp_path / "outside.png"
    outside.write_bytes(b"not a real image")
    root = tmp_path / "dataset"
    root.mkdir()
    manifest = {
        "dataset_contract": "so101-head-search-yolo-seg-v1",
        "camera_name": "head_camera",
        "sample_count": 1,
        "split_counts": {"test": 1},
        "samples": [
            {
                "seed": 1,
                "split": "test",
                "scene_group_id": "scene-1",
                "image": "../../outside.png",
                "label": "labels/test/1.txt",
                "truth": "truth/test/1.json",
            }
        ],
    }
    with pytest.raises(EvaluationError, match="EVALUATION_MANIFEST_INVALID"):
        verify_split_manifest(manifest, "test", dataset_root=root, domain="head")


def test_split_manifest_verification_refuses_a_digest_that_does_not_match(tmp_path: Path) -> None:
    from so101_demo.perception_benchmark.head_search_models import verify_split_manifest

    root = tmp_path / "dataset"
    for relative in ("images/test/1.png", "labels/test/1.txt", "truth/test/1.json"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"payload")
    base = {
        "seed": 1,
        "split": "test",
        "scene_group_id": "scene-1",
        "image": "images/test/1.png",
        "label": "labels/test/1.txt",
        "truth": "truth/test/1.json",
    }
    digests = {
        f"{name}_sha256": hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for name, relative in (
            ("image", "images/test/1.png"),
            ("label", "labels/test/1.txt"),
            ("truth", "truth/test/1.json"),
        )
    }
    manifest = {
        "dataset_contract": "so101-head-search-yolo-seg-v1",
        "camera_name": "head_camera",
        "sample_count": 1,
        "split_counts": {"test": 1},
        "samples": [{**base, **digests, "image_sha256": "0" * 64}],
    }
    with pytest.raises(EvaluationError, match="EVALUATION_MANIFEST_INVALID"):
        verify_split_manifest(manifest, "test", dataset_root=root, domain="head")
    manifest["samples"] = [{**base, **digests}]
    assert len(verify_split_manifest(manifest, "test", dataset_root=root, domain="head")) == 1
    # a manifest with no per-file digests is sealed only by published sums, and refused without them
    undigested = {**base}
    with pytest.raises(EvaluationError, match="EVALUATION_SEAL_UNVERIFIED"):
        verify_split_manifest(
            {**manifest, "samples": [undigested]}, "test", dataset_root=root, domain="head"
        )
    sums = {f"dataset/{base[key]}": digests[f"{key}_sha256"] for key in ("image", "label", "truth")}
    assert (
        len(
            verify_split_manifest(
                {**manifest, "samples": [undigested]},
                "test",
                dataset_root=root,
                domain="head",
                sums=sums,
            )
        )
        == 1
    )


def test_compare_cli_accepts_the_pinned_invocation_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Finding 1: the plan's own invocation must not die inside argparse."""

    from so101_demo.cli.evaluate_head_search_yolo_candidates import main

    for candidate_id, digest in (("A", "a" * 64), ("B", "b" * 64), ("C", "c" * 64)):
        _write_candidate(tmp_path, candidate_id, digest)
    root = tmp_path / "dataset"
    for relative in ("images/test/1.png", "labels/test/1.txt", "truth/test/1.json"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"payload")
    manifest = {
        "dataset_contract": "so101-head-search-yolo-seg-v1",
        "camera_name": "head_camera",
        "sample_count": 1,
        "split_counts": {"test": 1},
        "samples": [
            {
                "seed": 1,
                "split": "test",
                "scene_group_id": "scene-1",
                "image": "images/test/1.png",
                "label": "labels/test/1.txt",
                "truth": "truth/test/1.json",
            }
        ],
    }
    (root / "dataset-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "partitions.json").write_text(
        json.dumps({"held_out_evaluation": [1]}), encoding="utf-8"
    )
    # exactly the plan's argument shape: no --weights-dir, no dataset roots, no episode records
    arguments = [
        "compare",
        "--candidate",
        str(tmp_path / "frozen-a.json"),
        "--candidate",
        str(tmp_path / "frozen-b.json"),
        "--candidate",
        str(tmp_path / "frozen-c.json"),
        "--head-dataset",
        str(root / "dataset-manifest.json"),
        "--head-split",
        "test",
        "--task-dataset",
        str(root / "dataset-manifest.json"),
        "--task-split",
        "test",
        "--episode-partitions",
        str(tmp_path / "partitions.json"),
        "--episode-split",
        "held_out_evaluation",
        "--bootstrap-repetitions",
        "10000",
        "--device",
        "cuda",
        "--output",
        str(tmp_path / "out"),
    ]
    assert main(arguments) == 2, "a refusal is fine, an argparse exit is not"
    printed = capsys.readouterr().out
    assert "EVALUATION_" in printed, printed
    assert "usage:" not in printed.lower()


def test_a_candidate_with_better_measured_f1_blocks_an_undefendable_selection() -> None:
    """The reviewer's exact counterexample: C wins AP by 0.005 but loses F1 by 0.8."""

    weak_f1 = _evaluation("C", head_ap=0.80, task_ap=0.80, head_f1=0.10, task_f1=0.10)
    strong_f1 = _evaluation("B", head_ap=0.795, task_ap=0.80, head_f1=0.90, task_f1=0.90)
    with pytest.raises(EvaluationError, match="EVALUATION_F1_MARGIN"):
        choose_candidate(A_EQUIVALENT, strong_f1, weak_f1)


def test_a_challenger_needs_a_scene_interval_that_excludes_zero() -> None:
    from so101_demo.perception_benchmark.head_search_models import require_selection_supported

    clear = _evaluation("B", head_ap=0.53, task_ap=0.508, head_recall=0.95, head_f1=0.95)
    verdict = choose_candidate(A_EQUIVALENT, clear, C_EQUIVALENT_RETAINED)
    assert verdict.candidate_id == "B"
    require_selection_supported(verdict, {"B": (0.01, 0.09)})  # supported
    with pytest.raises(EvaluationError, match="EVALUATION_SELECTION_UNSUPPORTED"):
        require_selection_supported(verdict, {"B": (-0.02, 0.05)})  # straddles zero
    with pytest.raises(EvaluationError, match="EVALUATION_SELECTION_UNSUPPORTED"):
        require_selection_supported(verdict, {})  # no interval at all
    retained = choose_candidate(A_EQUIVALENT, B_EQUIVALENT, C_EQUIVALENT_RETAINED)
    assert retained.candidate_id == "C"
    require_selection_supported(retained, {})  # keeping the retained model needs no interval


def test_a_challenger_that_wins_the_episodes_blocks_a_retained_selection() -> None:
    """The re-review's counterexample: B beats C on episode recall and F1 by 0.09 while C is retained."""

    static_best = _evaluation("A", head_ap=0.70, task_ap=0.50)
    episode_best = _evaluation("B", head_ap=0.60, task_ap=0.50, head_recall=0.99, head_f1=0.99)
    retained = _evaluation("C", head_ap=0.50, task_ap=0.50, head_recall=0.90, head_f1=0.90)
    with pytest.raises(EvaluationError, match="EVALUATION_(F1|RECALL)_MARGIN"):
        choose_candidate(static_best, episode_best, retained)


def test_the_episode_winner_is_the_best_challenger_not_the_last_one() -> None:
    strong = _evaluation("A", head_ap=0.60, task_ap=0.50, head_recall=0.99, head_f1=0.99)
    weaker = _evaluation("B", head_ap=0.55, task_ap=0.50, head_recall=0.95, head_f1=0.99)
    retained = _evaluation("C", head_ap=0.50, task_ap=0.50, head_recall=0.90, head_f1=0.90)
    verdict = choose_candidate(strong, weaker, retained)
    assert verdict.candidate_id == "A", (
        "the strongest qualifying challenger wins, not the last seen"
    )


def test_the_top_level_identity_cannot_hide_behind_a_neutral_operating_point() -> None:
    """The third reviewer's P1: an empty per-domain value must not mask a top-level declaration."""

    from so101_demo.cli.evaluate_head_search_yolo_candidates import _unsupported_declarations

    hidden = _unsupported_declarations(
        {"tracker": {}}, {"tracker": {"type": "unsupported-tracker"}}
    )
    assert hidden, "an unsupported top-level tracker must not be masked by an empty local mapping"
    assert _unsupported_declarations({"tracker": {"iou": 0.3}}, {}) == []
    assert _unsupported_declarations({}, {"runtime": {"device": "mps"}})
    assert _unsupported_declarations({}, {"min_area_px2": 64})


def test_a_supported_tracker_declaration_is_applied_or_refused() -> None:
    """The fourth review's finding: an accepted declaration must not be ignored by the measurement."""

    from so101_demo.cli.evaluate_head_search_yolo_candidates import _resolve_tracking_iou

    assert _resolve_tracking_iou({"tracker": {"iou": 0.3}}, {}) == 0.3
    assert _resolve_tracking_iou({}, {"tracker": {"iou": 0.42}}) == 0.42
    assert _resolve_tracking_iou({}, {}) == 0.5
    assert _resolve_tracking_iou({"tracking_iou": 0.25}, {"tracker": {"iou": 0.25}}) == 0.25
    with pytest.raises(EvaluationError, match="EVALUATION_OPERATING_POINT_CONFLICT"):
        _resolve_tracking_iou({"tracker": {"iou": 0.3}}, {"tracker": {"iou": 0.7}})


def test_a_non_promotable_candidate_is_refused(tmp_path: Path) -> None:
    """A smoke candidate records promotable false and must not enter model selection."""

    from so101_demo.perception_benchmark.head_search_models import load_frozen_candidate

    document = {
        "candidate_id": "C",
        "weight_sha256": "a" * 64,
        "operating_points": {"head": {}, "task": {}},
        "tracker": {"iou": 0.3},
        "postprocess": {},
        "runtime": {},
        "promotable": False,
    }
    path = tmp_path / "frozen-smoke.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(EvaluationError, match="EVALUATION_CANDIDATE_NOT_PROMOTABLE"):
        load_frozen_candidate(path)

    document["promotable"] = True
    path.write_text(json.dumps(document), encoding="utf-8")
    assert load_frozen_candidate(path).candidate_id == "C", "a promotable candidate still loads"
