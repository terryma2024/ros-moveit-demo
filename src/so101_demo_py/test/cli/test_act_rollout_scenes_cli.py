"""The scene-list command writes once, only with an injected reachability probe, and the file verifies."""

import json

import pytest

from so101_demo.act import rollout_scenes as rs
from so101_demo.cli import act_rollout_scenes

POINTS = """schema_version: 1
points:
  - {id: task_start, label: a, cup_position_world_m: [0.02, -0.28, 0.165]}
  - {id: cup_test_right_5cm, label: b, cup_position_world_m: [0.07, -0.28, 0.165]}
"""
ANCHORS = """schema_version: 1
anchors:
  default: {cup_start_m: [0.02, -0.28, 0.165], neck_start_rad: 0.1}
  left: {cup_start_m: [-0.08, -0.28, 0.165], neck_start_rad: 0.0}
  forward: {cup_start_m: [0.02, -0.36, 0.165], neck_start_rad: 0.0}
"""


def _inputs(tmp_path):
    (tmp_path / "points.yaml").write_text(POINTS)
    (tmp_path / "anchors.yaml").write_text(ANCHORS)
    (tmp_path / "taken.json").write_text(json.dumps({"scenarios": [{"xy": [0.0, -0.3]}, {"xy": [-0.04, -0.32]}]}))
    return ["--points", str(tmp_path / "points.yaml"), "--anchors", str(tmp_path / "anchors.yaml"),
            "--taken-scenes", str(tmp_path / "taken.json"), "--place-xy", "-0.0803", "-0.2468",
            "--validation-count", "4", "--test-count", "4", "--extrapolation-count", "2",
            "--output", str(tmp_path / "scenes.json")]


def test_without_a_probe_the_command_refuses_and_writes_nothing(tmp_path):
    with pytest.raises(ValueError, match="ROLLOUT_REACHABILITY_PROBE_NOT_AVAILABLE"):
        act_rollout_scenes.main(_inputs(tmp_path))
    assert not (tmp_path / "scenes.json").exists()


def test_with_a_probe_the_list_is_written_once_and_verifies(tmp_path, capsys):
    arguments = _inputs(tmp_path)
    assert act_rollout_scenes.main(arguments, reachable_factory=lambda: (lambda _xy: True)) == 0
    document = json.loads((tmp_path / "scenes.json").read_text())
    assert [len(document["groups"][name]) for name in rs.GROUPS] == [2, 4, 4, 2]
    assert document["groups"]["rollout_validation"][0]["seed"] == 576010
    assert document["groups"]["rollout_test"][0]["seed"] == 576011
    rs.verify_scene_document(document, taken_xy=[(0.0, -0.3), (-0.04, -0.32)], place_xy=(-0.0803, -0.2468))
    assert json.loads(capsys.readouterr().out)["manifest_sha256"] == document["manifest_sha256"]
    with pytest.raises(ValueError, match="ROLLOUT_SCENES_OUTPUT_EXISTS"):
        act_rollout_scenes.main(arguments, reachable_factory=lambda: (lambda _xy: True))
