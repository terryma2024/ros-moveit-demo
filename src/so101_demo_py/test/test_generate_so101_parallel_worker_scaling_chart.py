from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest


REPOSITORY_ROOT = Path(__file__).parents[3]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/generate_so101_parallel_worker_scaling_chart.py"
DATA_PATH = REPOSITORY_ROOT / "docs/guides/data/so101-parallel-worker-scaling.json"
SVG_PATH = REPOSITORY_ROOT / "docs/guides/assets/so101-parallel-worker-scaling.svg"
SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"


def load_generator():
    spec = importlib.util.spec_from_file_location("parallel_worker_chart", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_maintained_data_and_svg_are_valid_and_current() -> None:
    generator = load_generator()
    document = generator.load_and_validate(DATA_PATH)
    expected = generator.render_svg(document)

    assert SVG_PATH.read_text(encoding="utf-8") == expected
    assert generator.main(["--data", str(DATA_PATH), "--output", str(SVG_PATH), "--check"]) == 0
    root = ET.fromstring(expected)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert [row["workers"] for row in document["levels"]] == [1, 2, 4, 6, 8, 10]
    assert len([row for row in document["levels"] if row["valid_performance_sample"]]) == 6
    w10 = document["levels"][-1]
    assert w10 == {
        "workers": 10,
        "experiment_id": "EXP-049-W10-SUCCESS-RECOVERY",
        "status": "PASSED",
        "successful_points": 20,
        "valid_performance_sample": True,
        "execution_s": 215.4021017551422,
        "throughput_points_per_min": 5.570976282135338,
        "speedup_vs_w1": 7.3932118091306736,
        "parallel_efficiency": 0.7393211809130673,
        "peak_memory_b": 10148159488,
    }
    assert [row["experiment_id"] for row in document["failed_attempts"]] == [
        "EXP-047-FORMAL-W10",
        "EXP-048-FORMAL-W10-R2",
    ]
    assert document["conclusion"]["fastest_valid_level"] == 10
    assert document["conclusion"]["recommended_default_workers"] == 8
    assert document["conclusion"]["w10_valid_performance_samples"] == 1
    assert document["conclusion"]["w10_failed_runtime_attempts"] == 2
    assert 'data-role="failure-marker"' not in expected
    assert "EXP-049" in expected
    assert "EXP-047-FORMAL-W10 / EXP-048-FORMAL-W10-R2" in expected


def _worker_tick_x(root: ET.Element, worker: int) -> list[float]:
    return [
        float(element.get("x"))
        for element in root.iter(f"{SVG_NAMESPACE}text")
        if element.get("data-role") == "worker-tick"
        and element.get("data-worker") == str(worker)
    ]


def test_w8_series_points_and_labels_align_with_w8_ticks() -> None:
    generator = load_generator()
    rendered = generator.render_svg(generator.load_and_validate(DATA_PATH))
    root = ET.fromstring(rendered)
    tick_x = _worker_tick_x(root, 8)
    point_x = [
        float(element.get("cx"))
        for element in root.iter(f"{SVG_NAMESPACE}circle")
        if element.get("data-worker") == "8"
    ]
    label_x = [
        float(element.get("x"))
        for element in root.iter(f"{SVG_NAMESPACE}text")
        if element.get("data-role") == "value-label"
        and element.get("data-worker") == "8"
    ]
    series_x = []
    for element in root.iter(f"{SVG_NAMESPACE}polyline"):
        if element.get("class") not in {"valid", "ideal"}:
            continue
        points = element.get("points").split()
        series_x.append(float(points[4].split(",")[0]))

    assert tick_x == [883.8, 883.8, 883.8]
    assert point_x == tick_x
    assert label_x == tick_x
    assert series_x == [883.8, 883.8, 883.8, 883.8]


def test_w10_series_points_and_labels_align_with_w10_ticks() -> None:
    generator = load_generator()
    rendered = generator.render_svg(generator.load_and_validate(DATA_PATH))
    root = ET.fromstring(rendered)
    tick_x = _worker_tick_x(root, 10)
    point_x = [
        float(element.get("cx"))
        for element in root.iter(f"{SVG_NAMESPACE}circle")
        if element.get("data-worker") == "10"
    ]
    label_x = [
        float(element.get("x"))
        for element in root.iter(f"{SVG_NAMESPACE}text")
        if element.get("data-role") == "value-label"
        and element.get("data-worker") == "10"
    ]
    series_x = []
    for element in root.iter(f"{SVG_NAMESPACE}polyline"):
        if element.get("class") not in {"valid", "ideal"}:
            continue
        points = element.get("points").split()
        series_x.append(float(points[-1].split(",")[0]))

    assert tick_x == [1110.0, 1110.0, 1110.0]
    assert point_x == tick_x
    assert label_x == tick_x
    assert series_x == [1110.0, 1110.0, 1110.0, 1110.0]


def test_w10_footer_uses_maintained_experiment_ids() -> None:
    generator = load_generator()
    document = copy.deepcopy(generator.load_and_validate(DATA_PATH))
    document["levels"][-1]["experiment_id"] = "EXP-W10-SUCCESS-FIXTURE"
    document["failed_attempts"][0]["experiment_id"] = "EXP-W10-FAIL-A"
    document["failed_attempts"][1]["experiment_id"] = "EXP-W10-FAIL-B"

    rendered = generator.render_svg(document)

    assert "EXP-W10-SUCCESS-FIXTURE" in rendered
    assert "EXP-W10-FAIL-A / EXP-W10-FAIL-B" in rendered
    assert "EXP-049" not in rendered
    assert "EXP-047" not in rendered
    assert "EXP-048" not in rendered


@pytest.mark.parametrize("mutation", ["duplicate_worker", "failed_metric", "complete_failure"])
def test_validation_rejects_ambiguous_or_impossible_data(mutation: str) -> None:
    generator = load_generator()
    document = generator.load_and_validate(DATA_PATH)
    broken = copy.deepcopy(document)
    if mutation == "duplicate_worker":
        broken["levels"][1]["workers"] = 1
    elif mutation == "failed_metric":
        broken["levels"][-1]["status"] = "FAILED"
        broken["levels"][-1]["valid_performance_sample"] = False
    else:
        broken["failed_attempts"][0]["successful_points"] = 20

    with pytest.raises(ValueError):
        generator.render_svg(generator.validate_document(broken))
