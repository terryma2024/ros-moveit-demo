"""Polygon shrink, Poisson-disk spacing and determinism, spatial splits and the rollout-point rules of the scene sampler."""

import math

import pytest

from so101_demo.act import scene_boundary as sb
from so101_demo.act import scene_sampling as ss

CENTRE = sb.DEFAULT_CENTRE_XY
RADII = {"E": 0.10, "NE": 0.09, "N": 0.08, "NW": 0.09, "W": 0.10, "SW": 0.09, "S": 0.09, "SE": 0.09}
BOUNDARY = {name: sb.point_on_ray(CENTRE, name, radius) for name, radius in RADII.items()}
ROLLOUT = {"task_start": (0.02, -0.28), "forward_5cm": (0.02, -0.33), "left_5cm": (-0.03, -0.28), "right_5cm": (0.07, -0.28)}


def _everywhere(x, y):
    return True


def _sample(**options):
    options.setdefault("reachable", _everywhere)
    return ss.sample_scenes(BOUNDARY, ROLLOUT, **options)


def test_shrinking_a_square_moves_every_edge_inward():
    square = [(0.0, 0.0), (0.2, 0.0), (0.2, 0.2), (0.0, 0.2)]
    assert ss.shrink_polygon(square, 0.01) == [(0.01, 0.01), (0.19, 0.01), (0.19, 0.19), (0.01, 0.19)]
    assert ss.shrink_polygon(list(reversed(square)), 0.01) == [(0.01, 0.01), (0.19, 0.01), (0.19, 0.19), (0.01, 0.19)]


def test_shrinking_a_polygon_that_collapses_is_refused():
    with pytest.raises(ss.RegionInvalidError):
        ss.shrink_polygon([(0.0, 0.0), (0.02, 0.0), (0.02, 0.02), (0.0, 0.02)], 0.011)


def test_a_self_crossing_boundary_is_refused():
    bowtie = {**BOUNDARY, "N": BOUNDARY["S"], "S": BOUNDARY["N"]}
    with pytest.raises(ss.RegionInvalidError):
        ss.boundary_polygon(bowtie)
    with pytest.raises(ss.RegionInvalidError):
        ss.boundary_polygon({"E": (0, 0)})


def test_region_membership_keeps_the_inward_margin_and_the_hard_limits():
    region = ss.Region(ss.boundary_polygon(BOUNDARY), 0.01)
    assert region.contains(CENTRE)
    assert not region.contains((CENTRE[0] + 0.095, CENTRE[1]))  # inside the polygon but within 1 cm of the edge
    assert not region.contains((CENTRE[0] + 0.2, CENTRE[1]))
    place = sb.PLACE_TARGET_XY
    assert not region.contains((place[0], place[1] - 0.05))  # inside the polygon, inside the place exclusion


def test_the_sample_has_the_target_count_spacing_and_stays_in_the_region():
    sample = _sample()
    region = ss.Region(sample.polygon, 0.01)
    assert len(sample.points) == 103 and len(set(sample.points)) == 103
    assert sample.spacing_m >= ss.MIN_SPACING_FLOOR_M
    nearest = min(math.dist(a, b) for i, a in enumerate(sample.points) for b in sample.points[:i])
    assert nearest >= sample.spacing_m - 1e-9
    assert all(region.contains(p) for p in sample.points)
    assert all(sb.hard_limit_violation(*p) is None for p in sample.points)
    assert sample.shrunk_polygon != sample.polygon


def test_the_sample_is_a_pure_function_of_the_seed():
    first, again, other = _sample(seed=11), _sample(seed=11), _sample(seed=12)
    assert (first.points, first.splits, first.spacing_m) == (again.points, again.splits, again.spacing_m)
    assert first.points != other.points


def test_the_reachability_verdict_filters_the_scenes():
    sample = _sample(reachable=lambda x, y: x < CENTRE[0] + 0.03)
    assert all(p[0] < CENTRE[0] + 0.03 for p in sample.points)
    assert len(sample.points) == 103


def test_a_region_that_cannot_hold_the_count_at_the_floor_spacing_fails_by_name():
    tiny = {name: sb.point_on_ray(CENTRE, name, 0.03) for name in sb.RAY_NAMES}
    with pytest.raises(ss.SamplingCapacityError, match="SAMPLING_CAPACITY"):
        ss.sample_scenes(tiny, {}, reachable=_everywhere, count=103, split_counts={"train": 83, "validation": 10, "offline_test": 10})


def test_the_spacing_never_falls_below_the_floor():
    region = ss.Region(ss.boundary_polygon(BOUNDARY), 0.01)
    points, spacing = ss.poisson_disk(region, 400, 5)
    assert spacing >= ss.MIN_SPACING_FLOOR_M
    assert min(math.dist(a, b) for i, a in enumerate(points) for b in points[:i]) >= spacing - 1e-9


def test_splits_have_the_requested_counts_and_cover_the_region():
    sample = _sample()
    assert {s: sample.splits.count(s) for s in ("train", "validation", "offline_test")} == {
        "train": 83, "validation": 10, "offline_test": 10}
    middle = (sum(p[0] for p in sample.points) / 103, sum(p[1] for p in sample.points) / 103)
    for name in ("validation", "offline_test"):
        held = [p for p, s in zip(sample.points, sample.splits) if s == name]
        quadrants = {(p[0] >= middle[0], p[1] >= middle[1]) for p in held}
        assert len(quadrants) == 4, name
        spread = max(math.dist(a, b) for a in held for b in held)
        assert spread > 0.12  # the held-out points span the region, they are not one cluster
    held_all = [p for p, s in zip(sample.points, sample.splits) if s != "train"]
    assert min(math.dist(a, b) for i, a in enumerate(held_all) for b in held_all[:i]) > ss.MIN_SPACING_FLOOR_M


def test_split_counts_that_do_not_add_up_are_refused():
    with pytest.raises(ss.SplitStratificationError):
        ss.stratified_splits([(0.0, 0.0), (1.0, 1.0), (2.0, 0.0)], {"train": 1, "validation": 1, "offline_test": 2}, 1)


def test_rollout_points_keep_clear_of_every_scene_and_their_distances_are_reported():
    sample = _sample()
    for name, p in ROLLOUT.items():
        nearest = min(math.dist(p, q) for q in sample.points)
        assert nearest >= ss.ROLLOUT_CLEARANCE_M
        assert sample.rollout_nearest_scene_m[name] == pytest.approx(nearest, abs=1e-6)
        assert sample.rollout_nearest_training_m[name] >= sample.rollout_nearest_scene_m[name]


def test_a_rollout_point_outside_the_region_raises_a_named_error():
    near = {name: sb.point_on_ray(CENTRE, name, 0.03) for name in sb.RAY_NAMES}
    with pytest.raises(ss.RolloutPointOutsideRegionError, match="ROLLOUT_POINT_OUTSIDE_REGION: right_5cm"):
        ss.sample_scenes(near, {"right_5cm": ROLLOUT["right_5cm"]}, reachable=_everywhere)


def test_a_rollout_point_inside_the_place_exclusion_is_outside_the_region():
    with pytest.raises(ss.RolloutPointOutsideRegionError):
        _sample_with_rollout({"on_target": (-0.08, -0.25)})


def _sample_with_rollout(rollout):
    return ss.sample_scenes(BOUNDARY, rollout, reachable=_everywhere)
