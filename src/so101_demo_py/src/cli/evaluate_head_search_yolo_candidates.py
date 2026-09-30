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
from collections.abc import Mapping, Sequence
from pathlib import Path

from so101_demo.perception_benchmark.contracts import canonical_sha256
from so101_demo.perception_benchmark.head_search_models import (
    CANDIDATE_IDS,
    CandidateEvaluation,
    EvaluationError,
    choose_candidate,
    load_frozen_candidate,
    paired_scene_bootstrap,
    write_comparison,
)

STATIC_METRIC_KEYS = ("mask_map50_95", "recall", "f1")


def _path(value: str) -> Path:
    return Path(value).expanduser()


def _split_samples(manifest: Mapping[str, object], split: str, *, domain: str) -> list[Mapping]:
    raw = manifest.get("split_counts")
    if not isinstance(raw, Mapping) or split not in raw:
        raise EvaluationError(
            f"EVALUATION_SPLIT_MISSING: the {domain} manifest has no {split} split"
        )
    samples = [
        sample
        for sample in manifest.get("samples") or []
        if isinstance(sample, Mapping) and sample.get("split") == split
    ]
    if len(samples) != int(raw[split]):
        raise EvaluationError(
            f"EVALUATION_SPLIT_INCOMPLETE: the {domain} manifest lists {len(samples)} {split} samples "
            f"but declares {raw[split]}"
        )
    return samples


def _episode_frames(
    partitions: Mapping[str, object], records: Path | None, split: str
) -> list[Mapping[str, object]]:
    """The held-out frames of the declared partition, or a named refusal when they do not exist yet."""

    seeds = partitions.get(split)
    if not isinstance(seeds, (list, tuple)) or not seeds:
        raise EvaluationError(
            f"EVALUATION_PARTITION_MISSING: the partitions declare no {split} seeds"
        )
    if records is None:
        raise EvaluationError(
            "EVALUATION_EPISODES_UNAVAILABLE: the held-out episodes are recorded by the calibration run, "
            "so this gate needs --episode-records (frames with their scene_group_id and measurements)"
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
    return frames


def _measure_static(
    weights: Path,
    dataset_root: Path,
    samples: Sequence[Mapping],
    operating_point: Mapping[str, object],
    device: str,
    scratch: Path,
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
        iou=float(operating_point.get("tracking_iou", 0.5)),
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
    for key in ("recall", "f1"):
        value = metrics.get(f"metrics/{key}(M)")
        if value is None:
            value = metrics.get(f"metrics/{key}(B)")
        measured[key] = float(value if value is not None else float("nan"))
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
    compare.add_argument("--weights-dir", required=True, type=_path)
    compare.add_argument("--head-dataset-root", required=True, type=_path)
    compare.add_argument("--task-dataset-root", required=True, type=_path)
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
        head_samples = _split_samples(head_manifest, parsed.head_split, domain="head")
        task_samples = _split_samples(task_manifest, parsed.task_split, domain="task")
        partitions = json.loads(parsed.episode_partitions.read_text(encoding="utf-8"))
        frames = _episode_frames(partitions, parsed.episode_records, parsed.episode_split)

        scratch = Path(parsed.output)
        scratch.mkdir(parents=True, exist_ok=True)
        evaluations = []
        for candidate in frozen:
            weight_path = (parsed.weights_dir / f"{candidate.candidate_id}.pt").resolve()
            if not weight_path.is_file():
                raise EvaluationError(
                    f"EVALUATION_WEIGHTS_MISSING: no weight file for candidate "
                    f"{candidate.candidate_id} in {parsed.weights_dir}"
                )
            if hashlib.sha256(weight_path.read_bytes()).hexdigest() != candidate.weight_sha256:
                raise EvaluationError(
                    "EVALUATION_FROZEN_IDENTITY_DRIFT: the weight file is not the sealed one for "
                    f"candidate {candidate.candidate_id}"
                )
            static = {}
            for domain, samples, root in (
                ("head", head_samples, parsed.head_dataset_root),
                ("task", task_samples, parsed.task_dataset_root),
            ):
                operating_point = (candidate.document["operating_points"] or {})[domain]
                domain_scratch = scratch / f"measure-{candidate.candidate_id}-{domain}"
                domain_scratch.mkdir(parents=True, exist_ok=True)
                measured = _measure_static(
                    weight_path,
                    Path(root),
                    samples,
                    operating_point,
                    parsed.device,
                    domain_scratch,
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
                    latency_ms_per_frame=float(
                        candidate.document.get("latency_ms_per_frame", float("nan"))
                    ),
                    no_cup_false_candidates=int(
                        candidate.document.get("no_cup_false_candidates", 0)
                    ),
                )
            )
        verdict = choose_candidate(*evaluations)
        bootstrap = paired_scene_bootstrap(
            frames, repetitions=parsed.bootstrap_repetitions, seed=20260930
        )
        paths = write_comparison(
            parsed.output,
            candidates=evaluations,
            verdict=verdict,
            bootstrap_repetitions=parsed.bootstrap_repetitions,
            scenes={
                "independent_unit": bootstrap.independent_unit,
                "unit_count": bootstrap.unit_count,
                "mean": bootstrap.mean,
                "interval": list(bootstrap.interval),
            },
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
    return {"recall": recall, "f1": f1, "bbox_center_p95_px": p95}


if __name__ == "__main__":
    raise SystemExit(main())
