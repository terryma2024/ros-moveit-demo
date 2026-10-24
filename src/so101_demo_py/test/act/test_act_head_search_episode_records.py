"""The installed producer of the gate's declared `--episode-records`: the measured episode frames.

Phase 4's gate reads one document per declared seed, each carrying the frames measured for that seed with
their per-candidate detections and latencies. The installed phase-3 flight already measures exactly those
frames for the calibration seeds; this producer re-shapes that measured document into the contract the gate
declares - every frame copied verbatim, nothing recomputed - and refuses when a declared seed, a candidate's
measurement or a domain is missing, because the gate would refuse it later and less clearly.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from so101_demo.act.head_search.episode_records import (
    CAL_EPISODE_RECORDS_INCOMPLETE,
    CANDIDATE_IDS,
    RECEIPT_NAME,
    CalibrationEpisodeRecordsRefused,
    record_episode_records,
)
from so101_demo.cli.evaluate_head_search_yolo_candidates import _episode_frames
from so101_demo.perception_benchmark.contracts import canonical_sha256

SEEDS = [700000, 700001]
DOMAINS = ("head", "task")


def _frame(*, seed: int, domain: str, neck_rad: float, scenario: str = "nominal") -> dict:
    return {
        "seed": seed,
        "split": "calibration",
        "domain": domain,
        "camera": "head_camera" if domain == "head" else "task_camera",
        "scene_group_id": f"scene-{seed:09d}",
        "neck_rad": neck_rad,
        "scenario": scenario,
        "match_radius_px": 8.0,
        "truth": [{"instance_id": "plastic_cup", "x": 320.0, "y": 240.0, "visible_px": 9000}],
        "detections": {name: [{"xyxy": [300, 220, 340, 260], "confidence": 0.9, "match_radius_px": 8.0}]
                       for name in CANDIDATE_IDS},
        "latency_ms": {name: 4.0 + index for index, name in enumerate(CANDIDATE_IDS)},
    }


def _measurements(*, seeds=SEEDS, angles=(-0.17559216195018026, -0.047560575342359704, 0.08047101126546086)) -> dict:
    frames = [
        _frame(seed=seed, domain=domain, neck_rad=angle)
        for seed in seeds
        for angle in angles
        for domain in DOMAINS
    ]
    body = {
        "schema_version": 1,
        "kind": "head_search_operating_point_measurement",
        "phase": "perception_operating_point",
        "frame_count": len(frames),
        "frames": frames,
    }
    return {**body, "sha256": canonical_sha256(body)}


def _partitions(*, seeds=SEEDS, split: str = "calibration") -> dict:
    return {
        "schema_version": 1,
        "document": "head-search-scenario-partitions/v1",
        "calibration": list(seeds) if split == "calibration" else [900000],
        "held_out_evaluation": list(seeds) if split == "held_out_evaluation" else [800000],
    }


def _write_json(path: Path, document) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _record(tmp_path: Path, *, measurements=None, partitions=None, **overrides) -> dict:
    measurements_path = _write_json(
        tmp_path / "operating-point-measurements.json",
        _measurements() if measurements is None else measurements,
    )
    partitions_path = _write_json(
        tmp_path / "scenario-partitions.json", _partitions() if partitions is None else partitions
    )
    arguments = {
        "measurements": measurements_path,
        "partitions": partitions_path,
        "output_dir": tmp_path / "episodes" / "calibration",
        "command": "ros2 run so101_demo_py so101_head_search_calibration measure-episode-records",
    }
    arguments.update(overrides)
    return record_episode_records(**arguments)


def _read(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_it_writes_one_document_per_declared_seed_with_the_frames_verbatim(tmp_path: Path) -> None:
    measurements = _measurements()
    result = _record(tmp_path, measurements=measurements)
    output = tmp_path / "episodes" / "calibration"
    assert sorted(path.name for path in output.glob("seed-*.json")) == [
        "seed-700000.json",
        "seed-700001.json",
    ]
    written = _read(output / "seed-700000.json")
    assert written["seed"] == 700000
    assert len(written["frames"]) == 6
    expected = [frame for frame in measurements["frames"] if frame["seed"] == 700000]
    assert written["frames"] == expected
    assert written["frames_sha256"] == canonical_sha256(expected)
    assert written["source"]["sha256"] == hashlib.sha256(
        Path(result["measurements_path"]).read_bytes()
    ).hexdigest()


def test_the_gates_own_loader_reads_the_directory_it_produced(tmp_path: Path) -> None:
    """The installed consumer is the contract: it has to return every measured frame, unmodified."""

    measurements = _measurements()
    result = _record(tmp_path, measurements=measurements)
    frames = _episode_frames(
        _partitions(),
        tmp_path / "episodes" / "calibration",
        "calibration",
        partitions_path=tmp_path / "scenario-partitions.json",
    )
    assert len(frames) == len(measurements["frames"])
    assert frames == measurements["frames"]
    assert result["receipt"]["split"] == "calibration"


def test_the_receipt_records_the_source_digests_and_the_frame_counts(tmp_path: Path) -> None:
    result = _record(tmp_path)
    receipt = _read(result["receipt_path"])
    assert receipt["status"] == "RECORDED"
    assert receipt["kind"] == "head_search_episode_records_receipt"
    assert receipt["seed_count"] == len(SEEDS)
    assert receipt["frame_count"] == len(SEEDS) * 3 * len(DOMAINS)
    assert receipt["domains"] == ["head", "task"]
    assert receipt["candidates"] == list(CANDIDATE_IDS)
    assert receipt["provenance"]["command"].endswith("measure-episode-records")
    for key in ("measurements", "partitions"):
        reference = receipt["provenance"][key]
        assert hashlib.sha256(Path(reference["path"]).read_bytes()).hexdigest() == reference["sha256"]
    assert [entry["seed"] for entry in receipt["seeds"]] == SEEDS
    assert all(entry["frame_count"] == 6 for entry in receipt["seeds"])
    assert len(receipt["frames_sha256"]) == len(SEEDS)
    assert receipt["frames_sha256"]["700000"] == canonical_sha256(
        [frame for frame in _measurements()["frames"] if frame["seed"] == 700000]
    )


def test_it_refuses_a_declared_seed_that_was_never_measured(tmp_path: Path) -> None:
    with pytest.raises(CalibrationEpisodeRecordsRefused) as refusal:
        _record(
            tmp_path,
            measurements=_measurements(seeds=[700000]),
            partitions=_partitions(seeds=[700000, 700001]),
        )
    assert refusal.value.code == CAL_EPISODE_RECORDS_INCOMPLETE
    assert "700001" in refusal.value.detail
    assert not (tmp_path / "episodes" / "calibration").exists()


def test_it_refuses_a_frame_without_a_candidates_measurement(tmp_path: Path) -> None:
    measurements = _measurements()
    del measurements["frames"][0]["detections"]["B"]
    with pytest.raises(CalibrationEpisodeRecordsRefused) as refusal:
        _record(tmp_path, measurements=measurements)
    assert refusal.value.code == CAL_EPISODE_RECORDS_INCOMPLETE
    assert "B" in refusal.value.detail


def test_it_refuses_a_frame_without_a_candidates_latency(tmp_path: Path) -> None:
    measurements = _measurements()
    measurements["frames"][1]["latency_ms"] = {"A": 1.0}
    with pytest.raises(CalibrationEpisodeRecordsRefused) as refusal:
        _record(tmp_path, measurements=measurements)
    assert refusal.value.code == CAL_EPISODE_RECORDS_INCOMPLETE
    assert "latency" in refusal.value.detail


def test_it_refuses_a_frame_of_an_unknown_domain_or_a_missing_domain(tmp_path: Path) -> None:
    measurements = _measurements()
    for frame in measurements["frames"]:
        if frame["domain"] == "task":
            frame["domain"] = "wrist"
    with pytest.raises(CalibrationEpisodeRecordsRefused) as refusal:
        _record(tmp_path, measurements=measurements)
    assert refusal.value.code == CAL_EPISODE_RECORDS_INCOMPLETE
    assert "wrist" in refusal.value.detail

    measurements = _measurements()
    measurements["frames"] = [frame for frame in measurements["frames"] if frame["domain"] != "task"]
    with pytest.raises(CalibrationEpisodeRecordsRefused) as refusal:
        _record(tmp_path, measurements=measurements)
    assert refusal.value.code == CAL_EPISODE_RECORDS_INCOMPLETE
    assert "task" in refusal.value.detail


def test_it_refuses_a_frame_whose_seed_the_partition_does_not_declare(tmp_path: Path) -> None:
    """A frame of the split that claims an undeclared seed means the document and the partitions differ."""

    measurements = _measurements()
    measurements["frames"][0]["seed"] = 700099
    with pytest.raises(CalibrationEpisodeRecordsRefused) as refusal:
        _record(tmp_path, measurements=measurements)
    assert refusal.value.code == CAL_EPISODE_RECORDS_INCOMPLETE
    assert "700099" in refusal.value.detail
    assert "does not declare" in refusal.value.detail


def test_it_refuses_an_existing_output_directory_and_writes_nothing(tmp_path: Path) -> None:
    output = tmp_path / "episodes" / "calibration"
    output.mkdir(parents=True)
    with pytest.raises(CalibrationEpisodeRecordsRefused) as refusal:
        _record(tmp_path, output_dir=output)
    assert refusal.value.code == CAL_EPISODE_RECORDS_INCOMPLETE
    assert "never resumed or overwritten" in refusal.value.detail
    assert sorted(path.name for path in output.iterdir()) == []


def test_it_refuses_a_split_the_partitions_do_not_declare(tmp_path: Path) -> None:
    with pytest.raises(CalibrationEpisodeRecordsRefused) as refusal:
        _record(tmp_path, partitions=_partitions(), split="qualification")
    assert refusal.value.code == CAL_EPISODE_RECORDS_INCOMPLETE
    assert "qualification" in refusal.value.detail


def test_the_receipt_is_not_a_seed_document(tmp_path: Path) -> None:
    result = _record(tmp_path)
    receipt = _read(result["receipt_path"])
    assert receipt["path"] == str(tmp_path / "episodes" / "calibration" / RECEIPT_NAME)
    assert "seed" not in receipt
