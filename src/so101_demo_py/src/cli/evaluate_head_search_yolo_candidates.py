"""Evaluate the three frozen Head Search candidates and decide which one to calibrate.

This is the gate the plan runs before the formal calibration: it reads the three sealed candidate
identities, the frozen head and task test splits, and the held-out episode partition, measures both
measurement families, applies the margins and writes `model-comparison.json` together with
`model-selection-verdict.json`. It never retunes anything: every identity it reads is checked against the
digest it was sealed with, and an identity that drifted is refused rather than repaired.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
from so101_demo.perception_benchmark.contracts import canonical_sha256
from so101_demo.perception_benchmark.head_search_models import (
    CANDIDATE_IDS,
    CandidateEvaluation,
    EvaluationError,
    choose_candidate,
    load_frozen_candidate,
    paired_scene_delta_bootstrap,
    require_selection_supported,
    verify_split_manifest,
    write_comparison,
)

STATIC_METRIC_KEYS = ("mask_map50_95", "recall", "f1")


def _path(value: str) -> Path:
    return Path(value).expanduser()


def _episode_frames(
    partitions: Mapping[str, object],
    records: Path | None,
    split: str,
    *,
    partitions_path: Path,
) -> list[Mapping[str, object]]:
    """The held-out frames of the declared partition, or a named refusal when they do not exist yet."""

    seeds = partitions.get(split)
    if not isinstance(seeds, (list, tuple)) or not seeds:
        raise EvaluationError(
            f"EVALUATION_PARTITION_MISSING: the partitions declare no {split} seeds"
        )
    # the declared sibling is resolved first: the pinned invocation passes no episode records, so the
    # default must be reachable rather than shadowed by the refusal below
    if records is None:
        default = Path(partitions_path).resolve().parent / "held-out-episodes"
        records = default if default.is_dir() else None
    if records is None:
        raise EvaluationError(
            "EVALUATION_EPISODES_UNAVAILABLE: the held-out episodes are recorded by the calibration run, "
            "so this gate needs --episode-records or a held-out-episodes directory beside the partitions "
            "file (frames with their scene_group_id and measurements)"
        )
    frames: list[Mapping[str, object]] = []
    wanted = {int(seed) for seed in seeds}
    for path in sorted(Path(records).glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, Mapping) or int(document.get("seed", -1)) not in wanted:
            continue
        frames.extend(document.get("frames") or [])
    if not frames:
        raise EvaluationError(
            f"EVALUATION_EPISODES_INCOMPLETE: no frame of the {split} partition was recorded"
        )
    recorded = {int(frame.get("seed", -1)) for frame in frames}
    missing_seeds = sorted(wanted - recorded)
    if missing_seeds:
        raise EvaluationError(
            f"EVALUATION_EPISODES_INCOMPLETE: the {split} partition declares seeds {missing_seeds} that "
            "were never recorded"
        )
    for frame in frames:
        detections = frame.get("detections")
        if not isinstance(detections, Mapping):
            raise EvaluationError(
                "EVALUATION_EPISODES_INCOMPLETE: a frame records no per-candidate detections"
            )
        absent = sorted(name for name in CANDIDATE_IDS if name not in detections)
        if absent:
            raise EvaluationError(
                f"EVALUATION_EPISODES_INCOMPLETE: a frame has no measurement for candidates {absent}; "
                "an absent measurement is not an empty detection list"
            )
        latency = frame.get("latency_ms")
        if not isinstance(latency, Mapping) or any(name not in latency for name in CANDIDATE_IDS):
            raise EvaluationError(
                "EVALUATION_LATENCY_UNMEASURED: a frame records no per-candidate latency, so the "
                "budget cannot be measured"
            )
    return frames


def _unsupported_declarations(
    operating_point: Mapping[str, object], document: Mapping[str, object]
) -> list[str]:
    """The sealed conditions this measurement path cannot apply, from both declaration sources."""

    unsupported: list[str] = []
    for source_name, source in (
        ("the operating point", dict(operating_point)),
        (
            "the candidate document",
            {
                key: document.get(key)
                for key in ("tracker", "postprocess", "runtime", "min_area_px2", "min_bbox_aspect")
            },
        ),
    ):
        for key in ("min_bbox_aspect", "postprocess", "runtime", "min_area_px2"):
            value = source.get(key)
            if value in (None, {}, 0):
                continue
            unsupported.append(f"{source_name}:{key}")
        tracker = source.get("tracker")
        if tracker in (None, {}, 0):
            continue
        # the one tracker form this path applies is the IoU NMS threshold; anything else is refused
        if (
            isinstance(tracker, Mapping)
            and set(tracker) == {"iou"}
            and isinstance(tracker["iou"], (int, float))
        ):
            continue
        unsupported.append(f"{source_name}:tracker")
    return unsupported


def _dataset_sums(dataset_root: Path) -> Mapping[str, str] | None:
    """The dataset's published sums, looked up beside its root, or None when it publishes none."""

    from so101_demo.perception_benchmark.head_search_models import load_dataset_sums

    for candidate in (dataset_root / "SHA256SUMS", dataset_root.parent / "SHA256SUMS"):
        if candidate.is_file():
            return load_dataset_sums(candidate)
    return None


def _resolve_tracking_iou(
    operating_point: Mapping[str, object], document: Mapping[str, object]
) -> float:
    """The IoU threshold the validator must use, resolved from both declaration sources.

    An accepted tracker declaration that the measurement then ignores would let a frozen condition look
    sealed while a different value is measured, so the value is either applied or the gate refuses.
    """

    declarations = []
    for source_name, source in (
        ("the operating point", operating_point),
        ("the candidate document", document),
    ):
        tracker = source.get("tracker")
        if isinstance(tracker, Mapping) and set(tracker) == {"iou"}:
            declarations.append((source_name, float(tracker["iou"])))
        scalar = source.get("tracking_iou")
        if isinstance(scalar, (int, float)) and not isinstance(scalar, bool):
            declarations.append((source_name, float(scalar)))
    if not declarations:
        return 0.5
    values = {value for _, value in declarations}
    if len(values) > 1:
        raise EvaluationError(
            "EVALUATION_OPERATING_POINT_CONFLICT: the sealed identity declares different tracking IoU "
            f"thresholds ({sorted(values)}), so the measurement cannot honour both"
        )
    return values.pop()


def _measure_static(
    weights: Path,
    dataset_root: Path,
    samples: Sequence[Mapping],
    operating_point: Mapping[str, object],
    device: str,
    scratch: Path,
    document: Mapping[str, object] | None = None,
) -> dict[str, float]:
    """Measure one candidate on one frozen split with Ultralytics' own segmentation validation."""

    try:
        from ultralytics import YOLO
    except ImportError as error:  # pragma: no cover - the measurement environment provides it
        raise EvaluationError(
            "EVALUATION_MEASUREMENT_UNAVAILABLE: ultralytics is not importable in this interpreter"
        ) from error
    if device != "cuda":
        raise EvaluationError("EVALUATION_DEVICE_INVALID: candidates are measured on cuda only")
    list_path = scratch / "val.txt"
    list_path.write_text(
        "".join(f"{(dataset_root / str(sample['image'])).resolve()}\n" for sample in samples),
        encoding="utf-8",
    )
    data_path = scratch / "val.yaml"
    data_path.write_text(
        "path: "
        + str(dataset_root)
        + "\ntrain: "
        + str(list_path)
        + "\nval: "
        + str(list_path)
        + "\nnames:\n  0: plastic_cup\n",
        encoding="utf-8",
    )
    model = YOLO(str(weights))
    results = model.val(
        data=str(data_path),
        split="val",
        device=device,
        conf=float(operating_point.get("min_confidence", 0.25)),
        iou=_resolve_tracking_iou(operating_point, document or {}),
        verbose=False,
    )
    metrics = getattr(results, "results_dict", None)
    if not isinstance(metrics, Mapping):
        raise EvaluationError(
            "EVALUATION_MEASUREMENT_UNAVAILABLE: the validator returned no metrics"
        )
    measured = {
        "mask_map50_95": float(metrics.get("metrics/mAP50-95(M)", float("nan"))),
    }
    precision = metrics.get("metrics/precision(M)")
    recall = metrics.get("metrics/recall(M)")
    if precision is None or recall is None:
        raise EvaluationError(
            "EVALUATION_MEASUREMENT_UNAVAILABLE: the validator reported no mask precision and recall, "
            "so F1 cannot be derived"
        )
    measured["recall"] = float(recall)
    # Ultralytics exposes precision and recall, not F1; the gate derives it rather than trusting a
    # missing key, which used to become NaN and quietly leave F1 out of the decision
    measured["f1"] = (
        2 * float(precision) * float(recall) / (float(precision) + float(recall))
        if (float(precision) + float(recall)) > 0
        else 0.0
    )
    unsupported = _unsupported_declarations(operating_point, document or {})
    if unsupported:
        raise EvaluationError(
            "EVALUATION_OPERATING_POINT_UNSUPPORTED: the sealed identity declares "
            + ", ".join(sorted(unsupported))
            + ", which this measurement path does not apply"
        )
    return measured


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evaluate_head_search_yolo_candidates",
        description="Compare the frozen Head Search candidates and record the selection",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--candidate", action="append", required=True, type=_path)
    compare.add_argument("--head-dataset", required=True, type=_path)
    compare.add_argument("--head-split", default="test")
    compare.add_argument("--task-dataset", required=True, type=_path)
    compare.add_argument("--task-split", default="test")
    compare.add_argument("--episode-partitions", required=True, type=_path)
    compare.add_argument("--episode-split", default="held_out_evaluation")
    compare.add_argument("--episode-records", type=_path)
    compare.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    # the pinned invocation passes only candidates, manifests, partitions, repetitions, device and
    # output, so every other location is derived from an artifact that was itself verified
    compare.add_argument("--weights-dir", type=_path)
    compare.add_argument("--head-dataset-root", type=_path)
    compare.add_argument("--task-dataset-root", type=_path)
    compare.add_argument("--device", default="cuda")
    compare.add_argument("--output", required=True, type=_path)
    parsed = parser.parse_args(arguments)

    try:
        frozen = [load_frozen_candidate(path) for path in parsed.candidate]
        if sorted(candidate.candidate_id for candidate in frozen) != sorted(CANDIDATE_IDS):
            raise EvaluationError(
                f"EVALUATION_CANDIDATE_SET_INVALID: expected {CANDIDATE_IDS}, got "
                f"{sorted(candidate.candidate_id for candidate in frozen)}"
            )
        weights = sorted({candidate.weight_sha256 for candidate in frozen})
        if len(weights) != len(frozen):
            raise EvaluationError(
                "EVALUATION_CANDIDATE_SET_INVALID: two candidates share one frozen weight"
            )
        head_manifest = json.loads(parsed.head_dataset.read_text(encoding="utf-8"))
        task_manifest = json.loads(parsed.task_dataset.read_text(encoding="utf-8"))
        weights_dir = parsed.weights_dir or Path(parsed.candidate[0]).resolve().parent
        weight_paths: dict[str, Path] = {}
        for candidate in frozen:
            weight_path = (weights_dir / f"{candidate.candidate_id}.pt").resolve()
            if not weight_path.is_file():
                raise EvaluationError(
                    f"EVALUATION_WEIGHTS_MISSING: no weight file for candidate "
                    f"{candidate.candidate_id} in {weights_dir}"
                )
            if hashlib.sha256(weight_path.read_bytes()).hexdigest() != candidate.weight_sha256:
                raise EvaluationError(
                    "EVALUATION_FROZEN_IDENTITY_DRIFT: the weight file is not the sealed one for "
                    f"candidate {candidate.candidate_id}"
                )
            weight_paths[candidate.candidate_id] = weight_path
        head_root = parsed.head_dataset_root or parsed.head_dataset.resolve().parent
        task_root = parsed.task_dataset_root or parsed.task_dataset.resolve().parent
        head_sums = _dataset_sums(Path(head_root))
        task_sums = _dataset_sums(Path(task_root))
        head_samples = verify_split_manifest(
            head_manifest, parsed.head_split, dataset_root=head_root, domain="head", sums=head_sums
        )
        task_samples = verify_split_manifest(
            task_manifest, parsed.task_split, dataset_root=task_root, domain="task", sums=task_sums
        )
        partitions = json.loads(parsed.episode_partitions.read_text(encoding="utf-8"))
        frames = _episode_frames(
            partitions,
            parsed.episode_records,
            parsed.episode_split,
            partitions_path=parsed.episode_partitions,
        )

        scratch = Path(parsed.output)
        scratch.mkdir(parents=True, exist_ok=True)
        evaluations = []
        head_scene_cells: dict[str, dict[str, dict[str, float]]] = {}
        for candidate in frozen:
            weight_path = weight_paths[candidate.candidate_id]
            static = {}
            head_scene_cells[candidate.candidate_id] = {}
            for domain, samples, root in (
                ("head", head_samples, head_root),
                ("task", task_samples, task_root),
            ):
                operating_point = (candidate.document["operating_points"] or {})[domain]
                domain_scratch = scratch / f"measure-{candidate.candidate_id}-{domain}"
                domain_scratch.mkdir(parents=True, exist_ok=True)
                if domain == "head":
                    per_scene = _measure_static_per_scene(
                        weight_path,
                        Path(root),
                        samples,
                        operating_point,
                        parsed.device,
                        domain_scratch / "by-scene",
                        document=candidate.document,
                    )
                    head_scene_cells[candidate.candidate_id] = per_scene
                    measured = {
                        key: float(np.mean([cell[key] for cell in per_scene.values()]))
                        for key in STATIC_METRIC_KEYS
                    }
                else:
                    measured = _measure_static(
                        weight_path,
                        Path(root),
                        samples,
                        operating_point,
                        parsed.device,
                        domain_scratch,
                        document=candidate.document,
                    )
                for key in STATIC_METRIC_KEYS:
                    if key not in measured:
                        raise EvaluationError(
                            f"EVALUATION_METRIC_MISSING: the {candidate.candidate_id} {domain} cell has "
                            f"no {key}"
                        )
                static[domain] = {key: float(measured[key]) for key in STATIC_METRIC_KEYS}
            episodes = {
                domain: _episode_cells(frames, candidate.candidate_id, domain, parsed.episode_split)
                for domain in ("head", "task")
            }
            evaluations.append(
                CandidateEvaluation(
                    candidate_id=candidate.candidate_id,
                    weight_sha256=candidate.weight_sha256,
                    static_image_metrics=static,
                    held_out_episode_metrics=episodes,
                    latency_ms_per_frame=_measured_latency_p95(
                        frames, candidate.candidate_id, parsed.episode_split
                    ),
                    no_cup_false_candidates=_measured_false_candidates(
                        frames, candidate.candidate_id, parsed.episode_split
                    ),
                )
            )
        try:
            verdict = choose_candidate(*evaluations)
        except Exception as error:  # the selection rules refuse instead of choosing
            # HS-275: write the refusal as an artefact for ANY selection refusal, not only the
            # retention guard - the F1-margin refusal left no comparison behind, so its measured
            # numbers existed only inside the message.
            if "EVALUATION_" not in str(error):
                raise
            # HS-251/252/255: record the refusal as a decision with evidence, then re-raise so the
            # exit status still reports failure. Nothing is promoted; the margin is untouched.
            from so101_demo.perception_benchmark.head_search_models import TASK_RETENTION_MARGIN

            target = Path(parsed.output)
            target.mkdir(parents=True, exist_ok=True)
            comparison = {
                "kind": "head-search-model-comparison",
                "episode_split": parsed.episode_split,
                "candidates": {
                    item.candidate_id: {
                        "static_image_metrics": dict(item.static_image_metrics),
                        "held_out_episode_metrics": dict(item.held_out_episode_metrics),
                        "latency_ms_per_frame": item.latency_ms_per_frame,
                        "no_cup_false_candidates": item.no_cup_false_candidates,
                    }
                    for item in evaluations
                },
                "retention": {"margin": TASK_RETENTION_MARGIN, "refusal": str(error)},
                "refusal": str(error),
            }
            (target / "model-comparison.json").write_text(
                json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            verdict_document = {
                "kind": "head-search-model-selection-verdict",
                "selection": None,
                "retained_model": "C",
                "reason": ("no supportable selection: " + str(error)),
                "retention": {"margin": TASK_RETENTION_MARGIN, "refusal": str(error)},
                "promoted": False,
            }
            (target / "model-selection-verdict.json").write_text(
                json.dumps(verdict_document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            raise
        # the paired scene-level delta: each challenger against the retained model, per episode domain
        scenes: dict[str, object] = {}
        static_intervals: dict[str, tuple[float, float]] = {}
        scenes_by_id = sorted(set().union(*(set(cells) for cells in head_scene_cells.values())))
        if scenes_by_id and all(
            len(cells) == len(scenes_by_id) for cells in head_scene_cells.values()
        ):
            valued_static = [
                {
                    "scene_group_id": scene,
                    **{
                        f"value_{name}": float(head_scene_cells[name][scene]["mask_map50_95"])
                        for name in CANDIDATE_IDS
                    },
                }
                for scene in scenes_by_id
            ]
            scenes["static_head"] = {}
            for challenger in ("A", "B"):
                delta = paired_scene_delta_bootstrap(
                    valued_static,
                    left_key=f"value_{challenger}",
                    right_key="value_C",
                    repetitions=parsed.bootstrap_repetitions,
                    seed=20260930,
                )
                static_intervals[challenger] = delta.interval
                scenes["static_head"][f"{challenger}_minus_C"] = {
                    "independent_unit": delta.independent_unit,
                    "unit_count": delta.unit_count,
                    "mean": delta.mean,
                    "interval": list(delta.interval),
                    "repetitions": delta.repetitions,
                }
            require_selection_supported(verdict, static_intervals)
        for domain in ("head", "task"):
            domain_frames = [
                frame
                for frame in frames
                if isinstance(frame, Mapping)
                and frame.get("domain") == domain
                and frame.get("split") == parsed.episode_split
            ]
            valued = [
                {
                    "scene_group_id": frame.get("scene_group_id"),
                    **{f"value_{name}": _matched_fraction(frame, name) for name in CANDIDATE_IDS},
                }
                for frame in domain_frames
            ]
            if not valued:
                continue
            scenes[domain] = {}
            for challenger in ("A", "B"):
                delta = paired_scene_delta_bootstrap(
                    valued,
                    left_key=f"value_{challenger}",
                    right_key="value_C",
                    repetitions=parsed.bootstrap_repetitions,
                    seed=20260930,
                )
                scenes[domain][f"{challenger}_minus_C"] = {
                    "independent_unit": delta.independent_unit,
                    "unit_count": delta.unit_count,
                    "mean": delta.mean,
                    "interval": list(delta.interval),
                    "repetitions": delta.repetitions,
                }
        paths = write_comparison(
            parsed.output,
            candidates=evaluations,
            verdict=verdict,
            bootstrap_repetitions=parsed.bootstrap_repetitions,
            scenes=scenes,
        )
    except (EvaluationError, OSError, ValueError) as error:
        print(json.dumps({"failure": str(error), "status": "ERROR"}, sort_keys=True))
        return 2

    print(
        json.dumps(
            {
                "status": "OK",
                "selected": verdict.candidate_id,
                "comparison": str(paths.comparison),
                "verdict": str(paths.verdict),
                "comparison_sha256": canonical_sha256(
                    json.loads(paths.comparison.read_text(encoding="utf-8"))
                ),
            },
            sort_keys=True,
        )
    )
    return 0


def _measure_static_per_scene(
    weights: Path,
    dataset_root: Path,
    samples: Sequence[Mapping],
    operating_point: Mapping[str, object],
    device: str,
    scratch: Path,
    *,
    document: Mapping[str, object] | None = None,
) -> dict[str, dict[str, float]]:
    """Measure the deciding head cells one scene at a time, so their interval can be bootstrapped.

    Ultralytics validation reports one aggregate per call, so a per-scene value means one call per scene
    group. This runs only for the head domain, the domain the selection is decided on; the task domain
    keeps its single whole-split measurement.
    """

    by_scene: dict[str, list[Mapping]] = {}
    for sample in samples:
        scene = str(sample.get("scene_group_id") or sample.get("seed"))
        by_scene.setdefault(scene, []).append(sample)
    cells: dict[str, dict[str, float]] = {}
    # Memoisation (HS-264): a per-scene value depends only on the weights file, the operating point
    # and that scene's images, and each call costs one whole Ultralytics validation. Re-running with
    # an unchanged head point must therefore not pay ~200 val calls again. The key covers all three
    # inputs, so a changed weight, point or image can never reuse a stale cell.
    import hashlib as _hashlib

    cache_dir = scratch.parent / "scene-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = _hashlib.sha256()
    with Path(weights).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    weight_sha = digest.hexdigest()
    point_key = json.dumps(operating_point, sort_keys=True, default=str)
    for index, scene in enumerate(sorted(by_scene)):
        images = "|".join(sorted(str(item.get("image_sha256")) for item in by_scene[scene]))
        key = _hashlib.sha256(
            "\n".join((weight_sha, point_key, scene, images)).encode("utf-8")
        ).hexdigest()[:32]
        cached = cache_dir / f"{key}.json"
        if cached.is_file():
            cells[scene] = json.loads(cached.read_text(encoding="utf-8"))
            continue
        scene_scratch = scratch / f"scene-{index:04d}"
        scene_scratch.mkdir(parents=True, exist_ok=True)
        value = _measure_static(
            weights,
            dataset_root,
            by_scene[scene],
            operating_point,
            device,
            scene_scratch,
            document=document,
        )
        cached.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        cells[scene] = value
    return cells


def _measured_latency_p95(
    frames: Sequence[Mapping[str, object]], candidate_id: str, split: str
) -> float:
    """The candidate's measured per-frame latency p95 on the partition, never a document field."""

    values = []
    for frame in frames:
        if frame.get("split") != split:
            continue
        raw = (frame.get("latency_ms") or {}).get(candidate_id)
        # every input timing is validated, not only the quantile that is finally reported
        if (
            isinstance(raw, bool)
            or not isinstance(raw, (int, float))
            or not math.isfinite(float(raw))
        ):
            raise EvaluationError(
                f"EVALUATION_LATENCY_UNMEASURED: candidate {candidate_id} has a non-finite or "
                "non-numeric latency on a recorded frame"
            )
        if float(raw) < 0.0:
            raise EvaluationError(
                f"EVALUATION_LATENCY_UNMEASURED: candidate {candidate_id} has a negative latency on a "
                "recorded frame"
            )
        values.append(float(raw))
    if not values:
        raise EvaluationError(
            f"EVALUATION_LATENCY_UNMEASURED: no measured latency for candidate {candidate_id}"
        )
    values.sort()
    index = min(len(values) - 1, int(round(0.95 * (len(values) - 1))))
    return values[index]


def _measured_false_candidates(
    frames: Sequence[Mapping[str, object]], candidate_id: str, split: str
) -> int:
    """Count detections on frames that hold no object, from the records rather than a declaration."""

    total = 0
    for frame in frames:
        if frame.get("split") != split:
            continue
        if frame.get("truth"):
            continue
        if frame.get("scenario") not in (None, "no_cup"):
            continue
        total += len((frame.get("detections") or {}).get(candidate_id) or [])
    return total


def _matched_fraction(frame: Mapping[str, object], candidate_id: str) -> float:
    """The fraction of a frame's true objects one candidate matched, for the paired bootstrap."""

    truths = frame.get("truth") or []
    if not truths:
        return 0.0
    detections = (frame.get("detections") or {}).get(candidate_id) or []
    matched: set[int] = set()
    for detection in detections:
        best, best_distance = None, None
        for index, truth in enumerate(truths):
            if index in matched:
                continue
            distance = float(
                ((detection["x"] - truth["x"]) ** 2 + (detection["y"] - truth["y"]) ** 2) ** 0.5
            )
            if best_distance is None or distance < best_distance:
                best, best_distance = index, distance
        if best is not None and float(best_distance) <= float(frame.get("match_radius_px", 8.0)):
            matched.add(best)
    return len(matched) / len(truths)


def _episode_cells(
    frames: Sequence[Mapping[str, object]], candidate_id: str, domain: str, split: str
) -> dict[str, float]:
    """Recall, F1 and bbox-centre p95 of one candidate on one held-out episode domain."""

    domain_frames = [
        frame
        for frame in frames
        if isinstance(frame, Mapping)
        and frame.get("domain") == domain
        and frame.get("split") == split
    ]
    if not domain_frames:
        raise EvaluationError(
            f"EVALUATION_EPISODES_INCOMPLETE: no {domain} {split} frame was recorded"
        )
    true_positive = false_positive = false_negative = 0
    offsets: list[float] = []
    for frame in domain_frames:
        detections = (frame.get("detections") or {}).get(candidate_id) or []
        truths = frame.get("truth") or []
        matched = set()
        for detection in detections:
            best, best_distance = None, None
            for index, truth in enumerate(truths):
                if index in matched:
                    continue
                distance = float(
                    ((detection["x"] - truth["x"]) ** 2 + (detection["y"] - truth["y"]) ** 2) ** 0.5
                )
                if best_distance is None or distance < best_distance:
                    best, best_distance = index, distance
            if best is not None and float(best_distance) <= float(
                frame.get("match_radius_px", 8.0)
            ):
                matched.add(best)
                offsets.append(float(best_distance))
                true_positive += 1
            else:
                false_positive += 1
        false_negative += len(truths) - len(matched)
    precision = (
        true_positive / (true_positive + false_positive) if true_positive or false_positive else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative) if true_positive or false_negative else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    if offsets:
        offsets.sort()
        index = min(len(offsets) - 1, int(round(0.95 * (len(offsets) - 1))))
        p95 = offsets[index]
    else:
        p95 = 0.0
    if not offsets and any((frame.get("truth") or []) for frame in domain_frames):
        p95 = float("inf")  # no evidence is not a perfect result
    return {"recall": recall, "f1": f1, "bbox_center_p95_px": p95}


if __name__ == "__main__":
    raise SystemExit(main())
