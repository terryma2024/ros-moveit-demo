"""Rollout scenes: pure sampling with an injected reachability verdict, and the separation rules of the design."""

import json
import math
from pathlib import Path

import pytest

from so101_demo.act import rollout_scenes as rs

TRIANGLE = ((0.02, -0.28), (-0.08, -0.28), (0.02, -0.36))      # the three approved anchors (default, left, forward)
PLACE = (-0.0803, -0.2468)
POINTS_YAML = """schema_version: 1
points:
  - {id: task_start, label: Task start, cup_position_world_m: [0.02, -0.28, 0.165]}
  - {id: cup_test_forward_5cm, label: Forward 5 cm, cup_position_world_m: [0.02, -0.33, 0.165]}
  - {id: cup_test_left_5cm, label: Left 5 cm, cup_position_world_m: [-0.03, -0.28, 0.165]}
  - {id: cup_test_right_5cm, label: Right 5 cm, cup_position_world_m: [0.07, -0.28, 0.165]}
"""
ANCHORS_YAML = """schema_version: 1
anchors:
  default: {cup_start_m: [0.02, -0.28, 0.165], neck_start_rad: 0.1}
  left: {cup_start_m: [-0.08, -0.28, 0.165], neck_start_rad: 0.0}
  forward: {cup_start_m: [0.02, -0.36, 0.165], neck_start_rad: 0.0}
"""


def _always(_xy):
    return True


def _taken():
    # a coarse lattice of "training" points inside the triangle, 0.02 m apart
    points = []
    for ix in range(-4, 2):
        for iy in range(-17, -13):
            x, y = round(ix * 0.02, 6), round(iy * 0.02, 6)
            if rs.in_triangle((x, y), TRIANGLE):
                points.append((x, y))
    return points


def _sample(group, seed, count, *, reachable=_always, rollout_xy=(), taken=None, **kwargs):
    return rs.sample_group(group=group, seed=seed, count=count, region={"kind": "triangle", "vertices": TRIANGLE},
                           place_xy=PLACE, reachable=reachable, taken_xy=_taken() if taken is None else taken,
                           rollout_xy=rollout_xy, reset_z_m=0.165, **kwargs)


def test_standard_points_come_from_the_task_point_file_in_order(tmp_path):
    path = tmp_path / "points.yaml"
    path.write_text(POINTS_YAML)
    scenes = rs.load_standard_points(path, triangle=TRIANGLE, taken_xy=[(0.02, -0.285)])
    assert [scene["point_id"] for scene in scenes] == [
        "task_start", "cup_test_forward_5cm", "cup_test_left_5cm", "cup_test_right_5cm"]
    assert {scene["group"] for scene in scenes} == {"rollout_standard"}
    assert scenes[0]["scene_id"] == "rollout-standard-task_start"
    assert scenes[0]["cup_position_world_m"] == [0.02, -0.28, 0.165] and scenes[0]["xy"] == [0.02, -0.28]
    # three points lie on the boundary of the anchor triangle, the right point is outside it
    assert [scene["inside_triangle"] for scene in scenes] == [True, True, True, False]
    assert scenes[0]["nearest_training_m"] == pytest.approx(0.005)
    assert all(scene["seed"] is None for scene in scenes)


def test_standard_points_refuse_a_malformed_file(tmp_path):
    path = tmp_path / "points.yaml"
    path.write_text("schema_version: 1\npoints: []\n")
    with pytest.raises(ValueError, match="ROLLOUT_STANDARD_POINTS_INVALID"):
        rs.load_standard_points(path)
    path.write_text(POINTS_YAML.replace("[0.02, -0.28, 0.165]", "[0.02, -0.28]"))
    with pytest.raises(ValueError, match="ROLLOUT_STANDARD_POINTS_INVALID"):
        rs.load_standard_points(path)


def test_anchor_triangle_reads_the_three_approved_anchor_positions(tmp_path):
    path = tmp_path / "anchors.yaml"
    path.write_text(ANCHORS_YAML)
    assert rs.anchor_triangle(path) == ((0.02, -0.28), (-0.08, -0.28), (0.02, -0.36))


def test_group_sampling_obeys_every_separation_rule():
    taken = _taken()
    scenes = _sample("rollout_validation", 576010, 12, taken=taken)
    assert len(scenes) == 12
    xy = [tuple(scene["xy"]) for scene in scenes]
    for point in xy:
        assert rs.in_triangle(point, TRIANGLE)
        assert math.dist(point, PLACE) >= rs.PLACE_EXCLUSION_M
        assert min(math.dist(point, other) for other in taken) >= rs.MIN_GAP_TO_TAKEN_M - 1e-12
    pairs = [math.dist(a, b) for index, a in enumerate(xy) for b in xy[index + 1:]]
    assert min(pairs) >= rs.MIN_GAP_WITHIN_M - 1e-12
    for scene in scenes:
        assert scene["group"] == "rollout_validation" and scene["seed"] == 576010
        assert scene["cup_position_world_m"] == [*scene["xy"], 0.165]
        assert scene["nearest_training_m"] == pytest.approx(
            min(math.dist(scene["xy"], other) for other in taken), abs=1e-6)
        assert scene["reachability"] is True


def test_sampling_is_deterministic_and_writes_plain_decimals():
    first = _sample("rollout_test", 576011, 6)
    assert first == _sample("rollout_test", 576011, 6)
    assert first != _sample("rollout_test", 576012, 6)
    text = json.dumps(first)
    assert "e-" not in text and all(len(repr(value).split(".")[-1]) <= 6 for scene in first for value in scene["xy"])


def test_test_group_is_separated_from_validation_and_standard_points():
    standard = [(0.02, -0.28), (0.02, -0.33)]
    validation = _sample("rollout_validation", 576010, 8, rollout_xy=standard)
    test = _sample("rollout_test", 576011, 8, rollout_xy=standard + [tuple(s["xy"]) for s in validation])
    others = standard + [tuple(s["xy"]) for s in validation]
    for scene in test:
        assert min(math.dist(scene["xy"], other) for other in others) >= rs.MIN_GAP_WITHIN_M - 1e-12
    assert not {scene["scene_id"] for scene in test} & {scene["scene_id"] for scene in validation}


def test_a_point_the_reachability_verdict_refuses_is_never_kept():
    seen = []

    def reachable(xy):
        seen.append(xy)
        return xy[0] < -0.02               # only the left part of the triangle

    scenes = _sample("rollout_validation", 576010, 5, reachable=reachable)
    assert all(scene["xy"][0] < -0.02 for scene in scenes)
    assert len(seen) > len(scenes)         # refused draws were asked about and dropped


def test_a_five_pose_verdict_must_pass_every_pose():
    poses = ("pregrasp", "grasp", "lift", "place", "retreat")
    verdicts = iter(({pose: pose != "place" for pose in poses}, {pose: True for pose in poses}) * 50)
    scenes = _sample("rollout_validation", 576010, 3, reachable=lambda _xy: next(verdicts))
    assert len(scenes) == 3
    assert all(scene["reachability"] == {pose: True for pose in poses} for scene in scenes)
    with pytest.raises(ValueError, match="ROLLOUT_REACHABILITY_VERDICT_INVALID"):
        _sample("rollout_validation", 576010, 1, reachable=lambda _xy: {})
    with pytest.raises(ValueError, match="ROLLOUT_REACHABILITY_VERDICT_INVALID"):
        _sample("rollout_validation", 576010, 1, reachable=lambda _xy: "yes")


def test_an_exhausted_generator_fails_closed():
    with pytest.raises(ValueError, match="ROLLOUT_GENERATOR_EXHAUSTED"):
        _sample("rollout_validation", 576010, 3, reachable=lambda _xy: False, max_draws=200)


def test_extrapolation_group_lies_outside_the_triangle():
    scenes = rs.sample_group(group="rollout_extrapolation", seed=576012, count=5,
                             region={"kind": "box", "x": (0.03, 0.07), "y": (-0.36, -0.28),
                                     "exclude_triangle": TRIANGLE},
                             place_xy=PLACE, reachable=_always, taken_xy=_taken(), rollout_xy=(), reset_z_m=0.165)
    assert len(scenes) == 5
    for scene in scenes:
        assert not rs.in_triangle(scene["xy"], TRIANGLE) and 0.03 <= scene["xy"][0] <= 0.07
        assert scene["inside_triangle"] is False


def test_unknown_group_region_or_count_is_refused():
    with pytest.raises(ValueError, match="ROLLOUT_GROUP_INVALID"):
        _sample("rollout_standard", 1, 1)                     # the standard group is loaded, never sampled
    with pytest.raises(ValueError, match="ROLLOUT_SAMPLING_PARAMETERS_INVALID"):
        _sample("rollout_validation", 1, 0)
    with pytest.raises(ValueError, match="ROLLOUT_SAMPLING_PARAMETERS_INVALID"):
        rs.sample_group(group="rollout_validation", seed=1, count=1, region={"kind": "disc"}, place_xy=PLACE,
                        reachable=_always, taken_xy=[], rollout_xy=(), reset_z_m=0.165)


def test_scene_document_pins_the_groups_and_verifies_clean(tmp_path):
    points = tmp_path / "points.yaml"
    points.write_text(POINTS_YAML)
    standard = rs.load_standard_points(points, triangle=TRIANGLE, taken_xy=_taken())
    validation = _sample("rollout_validation", rs.SEEDS["rollout_validation"], 6,
                         rollout_xy=[tuple(s["xy"]) for s in standard])
    test = _sample("rollout_test", rs.SEEDS["rollout_test"], 6,
                   rollout_xy=[tuple(s["xy"]) for s in standard + validation])
    document = rs.build_scene_document(
        {"rollout_standard": standard, "rollout_validation": validation, "rollout_test": test},
        parameters={"place_xy": list(PLACE), "triangle": [list(v) for v in TRIANGLE]})
    assert document["kind"] == "ACT_ROLLOUT_SCENES" and list(document["groups"]) == [
        "rollout_standard", "rollout_validation", "rollout_test"]
    rs.verify_scene_document(document, taken_xy=_taken(), place_xy=PLACE)
    assert rs.verify_scene_document(json.loads(json.dumps(document)), taken_xy=_taken(), place_xy=PLACE) is None


def test_scene_document_verification_catches_each_rule_violation():
    validation = _sample("rollout_validation", 576010, 4)
    document = rs.build_scene_document({"rollout_validation": validation}, parameters={})

    def damaged(edit):
        copy = json.loads(json.dumps(document))
        edit(copy["groups"]["rollout_validation"])
        return copy

    with pytest.raises(ValueError, match="ROLLOUT_SCENES_HASH_INVALID"):
        rs.verify_scene_document(damaged(lambda g: g[0].update(seed=1)), taken_xy=_taken(), place_xy=PLACE)

    def rebuilt(edit):
        copy = json.loads(json.dumps(document["groups"]))
        edit(copy["rollout_validation"])
        return rs.build_scene_document(copy, parameters={})

    def move(scene, xy):
        scene.update(xy=xy, cup_position_world_m=[*xy, 0.165])

    near_place = rebuilt(lambda g: move(g[0], [PLACE[0] + 0.01, PLACE[1]]))
    with pytest.raises(ValueError, match="ROLLOUT_SCENE_PLACE_EXCLUSION"):
        rs.verify_scene_document(near_place, taken_xy=[], place_xy=PLACE)
    duplicate = rebuilt(lambda g: move(g[1], [g[0]["xy"][0] + 0.001, g[0]["xy"][1]]))
    with pytest.raises(ValueError, match="ROLLOUT_SCENE_GAP_WITHIN"):
        rs.verify_scene_document(duplicate, taken_xy=[], place_xy=PLACE)
    on_training = rebuilt(lambda g: move(g[0], [0.0, -0.3]))
    with pytest.raises(ValueError, match="ROLLOUT_SCENE_GAP_TO_TAKEN"):
        rs.verify_scene_document(on_training, taken_xy=[(0.0, -0.3001)], place_xy=PLACE)
