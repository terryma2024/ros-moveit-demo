from __future__ import annotations

import csv
import importlib.util
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from so101_demo.core.task_points import parse_task_point_list


REPOSITORY_ROOT = Path(__file__).parents[3]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/generate_so101_moveit_expert_position_top_view.py"
EXPECTED_GENERATED_XY_M = [
    (-0.096188, -0.202721),
    (-0.142433, -0.229357),
    (0.052012, -0.188697),
    (-0.011136, -0.190250),
    (0.089108, -0.163392),
    (0.168214, -0.229738),
    (-0.151600, -0.286314),
    (-0.116185, -0.253172),
    (-0.005403, -0.251512),
    (0.168300, -0.266687),
    (0.184999, -0.336486),
    (-0.169743, -0.394454),
    (-0.115527, -0.402872),
    (0.007123, -0.396726),
    (0.159754, -0.385135),
    (0.095218, -0.375025),
]


def load_generator():
    spec = importlib.util.spec_from_file_location("position_top_view", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generation_uses_canonical_geometry_and_is_deterministic() -> None:
    generator = load_generator()
    geometry = generator.load_geometry(REPOSITORY_ROOT)
    anchors = generator.load_anchors(REPOSITORY_ROOT)

    points = generator.generate_positions(anchors, geometry, seed=20260911)
    minimum_separation_m = generator.validate(points, geometry)

    assert geometry.table_bounds == (-0.25, 0.25, -0.50, 0.10)
    assert geometry.base_bounds == (-0.09, 0.09, -0.09, 0.09)
    assert geometry.target_center == (-0.08, -0.25)
    assert geometry.target_bounds == (-0.09, -0.07, -0.26, -0.24)
    assert geometry.cup_radius_m == 0.04
    assert geometry.target_tolerance_radius_m == 0.01
    assert [(point.x_m, point.y_m, point.z_m) for point in points[:4]] == [
        (0.02, -0.28, 0.165),
        (0.02, -0.33, 0.165),
        (-0.03, -0.28, 0.165),
        (0.07, -0.28, 0.165),
    ]
    assert [(point.x_m, point.y_m) for point in points[4:]] == EXPECTED_GENERATED_XY_M
    assert math.isclose(minimum_separation_m, 0.035441666566345335, abs_tol=1e-12)


def test_cli_outputs_match_task_point_schema(tmp_path: Path) -> None:
    generator = load_generator()

    assert generator.main(
        [
            "--repo-root",
            str(REPOSITORY_ROOT),
            "--output-dir",
            str(tmp_path),
        ]
    ) == 0

    yaml_path = tmp_path / "so101-position-manifest.yaml"
    csv_path = tmp_path / "so101-position-manifest.csv"
    svg_path = tmp_path / "so101-position-top-view.svg"
    payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    parsed = parse_task_point_list(
        payload,
        (-0.30, -0.50, 0.10, 0.35, 0.20, 0.50),
    )
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))

    assert len(parsed.points) == len(rows) == 20
    assert [point.id for point in parsed.points[:4]] == [
        "task_start",
        "cup_test_forward_5cm",
        "cup_test_left_5cm",
        "cup_test_right_5cm",
    ]
    assert [(point.id, tuple(point.cup_position_world_m)) for point in parsed.points] == [
        (
            row["name"],
            (float(row["x_m"]), float(row["y_m"]), float(row["z_m"])),
        )
        for row in rows
    ]
    svg = svg_path.read_text(encoding="utf-8")
    assert "20 个杯子初始位置" in svg
    assert "机械臂底座" in svg
    assert "移动目标 T" in svg
    assert "P01" in svg and "P20" in svg
    assert 'data-role="p01-cup-footprint"' in svg
    assert 'data-role="target-center-tolerance"' in svg
    assert 'r="52.0"' in svg
    assert 'r="13.0"' in svg

    root = ET.fromstring(svg)
    position_points = [
        element
        for element in root.iter("{http://www.w3.org/2000/svg}circle")
        if element.get("data-role") == "position-point"
    ]
    assert len(position_points) == 20
    assert {point.get("r") for point in position_points} == {"10.0"}
    assert {point.get("data-status") for point in position_points} == {"pending"}
    assert {
        (point.get("fill"), point.get("stroke")) for point in position_points
    } == {("#e3f2fd", "#1976d2")}


def test_cli_marks_failed_points_from_an_external_manifest_and_results(
    tmp_path: Path,
) -> None:
    generator = load_generator()
    geometry = generator.load_geometry(REPOSITORY_ROOT)
    anchors = generator.load_anchors(REPOSITORY_ROOT)
    points = generator.generate_positions(anchors, geometry, seed=20260911)

    points_path = tmp_path / "frozen-points.yaml"
    points_payload = {
        "schema_version": 1,
        "points": [
            {
                "id": f"case_{index:02d}",
                "label": f"Case {index:02d}",
                "cup_position_world_m": [point.x_m, point.y_m, point.z_m],
            }
            for index, point in enumerate(points, start=1)
        ],
    }
    points_path.write_text(
        yaml.safe_dump(points_payload, sort_keys=False),
        encoding="utf-8",
    )

    failure_stages = {
        9: "perception",
        18: "planning_ik_move_above_object",
        19: "planning_ik_lift",
        20: "declared_planning_move_above_object",
    }
    results_path = tmp_path / "per-scene.tsv"
    with results_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("order", "id", "success", "first_failure_stage"),
            delimiter="\t",
        )
        writer.writeheader()
        for index in range(1, 21):
            writer.writerow(
                {
                    "order": index,
                    "id": f"case_{index:02d}",
                    "success": str(index not in failure_stages),
                    "first_failure_stage": failure_stages.get(index, ""),
                }
            )

    output_dir = tmp_path / "annotated"
    assert generator.main(
        [
            "--repo-root",
            str(REPOSITORY_ROOT),
            "--output-dir",
            str(output_dir),
            "--points-yaml",
            str(points_path),
            "--results-tsv",
            str(results_path),
        ]
    ) == 0

    svg = (output_dir / "so101-position-top-view.svg").read_text(encoding="utf-8")
    root = ET.fromstring(svg)
    position_points = [
        element
        for element in root.iter("{http://www.w3.org/2000/svg}circle")
        if element.get("data-role") == "position-point"
    ]
    assert len(position_points) == 20
    assert {point.get("r") for point in position_points} == {"10.0"}

    points_by_status = {
        status: [
            point
            for point in position_points
            if point.get("data-status") == status
        ]
        for status in ("success", "pending", "failure")
    }
    assert len(points_by_status["success"]) == 16
    assert len(points_by_status["pending"]) == 0
    assert len(points_by_status["failure"]) == 4
    assert {
        (point.get("fill"), point.get("stroke"))
        for point in points_by_status["success"]
    } == {("#e8f5e9", "#2e7d32")}
    assert {
        (point.get("fill"), point.get("stroke"))
        for point in points_by_status["failure"]
    } == {("#fde8e8", "#d32f2f")}
    assert {
        point.get("data-point-id") for point in points_by_status["failure"]
    } == {"P09", "P18", "P19", "P20"}
    for stage in failure_stages.values():
        assert stage in svg
