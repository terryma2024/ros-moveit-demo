"""act_scene_sample: the final scene list and its report, in the existing scene-list format."""

import hashlib
import json
import math

import pytest

from so101_demo.act import parallel_collection_contracts, scene_boundary as sb
from so101_demo.act.scene_list_format import KIND, plain_decimal_json, read_scene_rows
from so101_demo.cli import act_scene_sample as cli

RADII = {"E": 0.10, "NE": 0.09, "N": 0.08, "NW": 0.09, "W": 0.10, "SW": 0.09, "S": 0.09, "SE": 0.09}
POINTS = """schema_version: 1
points:
  - {id: task_start, label: a, cup_position_world_m: [0.02, -0.28, 0.165]}
  - {id: cup_test_forward_5cm, label: b, cup_position_world_m: [0.02, -0.33, 0.165]}
  - {id: cup_test_left_5cm, label: c, cup_position_world_m: [-0.03, -0.28, 0.165]}
  - {id: cup_test_right_5cm, label: d, cup_position_world_m: [0.07, -0.28, 0.165]}
"""


def planner(document_filter=lambda x, y: True):
    def call(document):
        return {
            p["id"]: ("REACHABLE", None) if document_filter(*p["cup_position_world_m"][:2]) else ("UNREACHABLE", "X")
            for p in document["points"]
        }

    return call


def inputs(tmp_path, radii=None):
    boundary_points = {n: list(sb.point_on_ray(sb.DEFAULT_CENTRE_XY, n, r)) for n, r in (radii or RADII).items()}
    (tmp_path / "state.json").write_text(json.dumps({"boundary_points": boundary_points}))
    (tmp_path / "points.yaml").write_text(POINTS)
    return ["--state", str(tmp_path / "state.json"), "--rollout-points", str(tmp_path / "points.yaml"),
            "--scenes-output", str(tmp_path / "scenes.json"), "--report-output", str(tmp_path / "report.json"),
            "--call-dir", str(tmp_path / "calls")]


def test_without_a_planner_command_the_cli_refuses_and_writes_nothing(tmp_path):
    with pytest.raises(ValueError, match="SCENE_SAMPLE_REACHABILITY_PROBE_NOT_AVAILABLE"):
        cli.main(inputs(tmp_path))
    assert not (tmp_path / "scenes.json").exists()


def test_the_scene_list_has_the_existing_format_and_the_report_the_required_fields(tmp_path):
    assert cli.main(inputs(tmp_path), reach_call=planner()) == 0
    text = (tmp_path / "scenes.json").read_text()
    document = json.loads(text)
    assert document["kind"] == KIND and document["schema_version"] == 1 and document["cup_z_m"] == 0.165
    assert document["split_quota"] == {"train": 83, "validation": 10, "offline_test": 10}
    rows = document["scenarios"]
    assert len(rows) == 103 and [r["scene_id"] for r in rows][:2] == ["frm-000", "frm-001"]
    assert [r["split"] for r in rows] == ["train"] * 83 + ["validation"] * 10 + ["offline_test"] * 10
    assert len({r["seed"] for r in rows}) == 103 and all(set(r) == {"scene_id", "seed", "split", "cup_position_world_m"} for r in rows)
    literals = []
    json.loads(text, parse_float=lambda literal: literals.append(literal) or float(literal))
    assert literals and not [literal for literal in literals if "e" in literal.lower()]  # plain decimals, no exponents (paths in strings do not count)
    assert read_scene_rows(tmp_path / "scenes.json") == rows
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["scene_count"] == 103 and report["split_counts"] == {"train": 83, "validation": 10, "offline_test": 10}
    assert report["min_spacing_m"] >= 0.004 and report["nearest_pair_m"] >= report["min_spacing_m"] - 1e-9
    assert len(report["region_polygon"]) == 8 and len(report["shrunk_region_polygon"]) == 8
    assert set(report["rollout_nearest_training_m"]) == {"task_start", "cup_test_forward_5cm", "cup_test_left_5cm", "cup_test_right_5cm"}
    assert min(report["rollout_nearest_training_m"].values()) >= 0.004


def test_the_list_round_trips_through_the_campaign_scene_reader(tmp_path):
    cli.main(inputs(tmp_path), reach_call=planner())
    path = tmp_path / "scenes.json"
    reference = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    ids = parallel_collection_contracts.scene_ids(reference, count=103)
    assert len(ids) == len(set(ids)) == 103
    rows = json.loads(path.read_text())["scenarios"]
    points = [r["cup_position_world_m"][:2] for r in rows]
    assert min(math.dist(a, b) for i, a in enumerate(points) for b in points[:i]) >= 0.004
    assert all(sb.hard_limit_violation(*p) is None for p in points)


def test_scenes_that_fail_the_five_pose_filter_are_not_used(tmp_path):
    cli.main([*inputs(tmp_path), "--count", "40", "--split-counts", "30", "5", "5"], reach_call=planner(lambda x, y: x < 0.105))
    rows = json.loads((tmp_path / "scenes.json").read_text())["scenarios"]
    assert all(r["cup_position_world_m"][0] + 0.01 < 0.105 + 1e-9 for r in rows)
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["positions_rejected_by_reachability"] > 0


def test_a_boundary_that_leaves_a_rollout_point_outside_stops_the_cli_before_writing(tmp_path):
    arguments = inputs(tmp_path, {name: 0.03 for name in sb.RAY_NAMES})
    with pytest.raises(Exception, match="ROLLOUT_POINT_OUTSIDE_REGION"):
        cli.main(arguments, reach_call=planner())
    assert not (tmp_path / "scenes.json").exists() and not (tmp_path / "report.json").exists()


def test_an_unfinished_boundary_state_is_refused(tmp_path):
    arguments = inputs(tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({"brackets": {}}))
    with pytest.raises(ValueError, match="SCENE_SAMPLE_BOUNDARY_NOT_FINISHED"):
        cli.main(arguments, reach_call=planner())


def test_plain_decimals_replace_exponent_numbers():
    assert plain_decimal_json({"a": 1e-05, "b": [-2.5e-07, 0.5]}) == '{"a": 0.000010, "b": [-0.000000, 0.5]}'
