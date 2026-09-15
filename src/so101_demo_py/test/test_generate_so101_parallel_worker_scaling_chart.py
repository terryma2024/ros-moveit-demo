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


def test_valid_w8_point_uses_full_w1_through_w10_axis_domain() -> None:
    generator = load_generator()
    rendered = generator.render_svg(generator.load_and_validate(DATA_PATH))
    root = ET.fromstring(rendered)
    valid_dots = [
        element
        for element in root.iter("{http://www.w3.org/2000/svg}circle")
        if element.get("class") == "dot"
    ]

    assert valid_dots[4].get("cx") == "883.8"


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
