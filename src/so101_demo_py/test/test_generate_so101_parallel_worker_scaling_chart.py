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
    assert len([row for row in document["levels"] if row["valid_performance_sample"]]) == 5
    assert [row["experiment_id"] for row in document["failed_attempts"]] == [
        "EXP-047-FORMAL-W10",
        "EXP-048-FORMAL-W10-R2",
    ]
    assert expected.count('class="fail"') == 8


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


def test_w10_failure_markers_align_with_w10_ticks() -> None:
    generator = load_generator()
    rendered = generator.render_svg(generator.load_and_validate(DATA_PATH))
    root = ET.fromstring(rendered)
    tick_x = _worker_tick_x(root, 10)
    failure_marker_x = [
        (float(element.get("x1")) + float(element.get("x2"))) / 2
        for element in root.iter(f"{SVG_NAMESPACE}line")
        if element.get("data-role") == "failure-marker"
        and element.get("data-worker") == "10"
    ]

    assert tick_x == [1110.0, 1110.0, 1110.0]
    assert failure_marker_x == [1110.0] * 6


@pytest.mark.parametrize("mutation", ["duplicate_worker", "failed_metric", "complete_failure"])
def test_validation_rejects_ambiguous_or_impossible_data(mutation: str) -> None:
    generator = load_generator()
    document = generator.load_and_validate(DATA_PATH)
    broken = copy.deepcopy(document)
    if mutation == "duplicate_worker":
        broken["levels"][1]["workers"] = 1
    elif mutation == "failed_metric":
        broken["levels"][-1]["execution_s"] = 1.0
    else:
        broken["failed_attempts"][0]["successful_points"] = 20

    with pytest.raises(ValueError):
        generator.render_svg(generator.validate_document(broken))
