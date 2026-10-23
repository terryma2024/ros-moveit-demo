"""Adaptive Head prefix timing preserves measured-state polynomial limits."""

import math

import pytest

from so101_demo.adapters.act.head_trajectory_guard import HeadTrajectoryGuard, quintic_extrema
from so101_demo.adapters.act import head_trajectory_guard


def test_resting_aligned_prefix_uses_fifty_milliseconds():
    assert HeadTrajectoryGuard._prefix_offset_ns(0., 0.) == 50_000_000


@pytest.mark.parametrize('mismatch,velocity', [(.002, 0.), (-.002, 0.),
    (0., .04), (0., -.04), (.002, -.04), (-.002, .04)])
def test_prefix_extends_until_measured_quintic_remains_within_current_limits(mismatch, velocity):
    offset = HeadTrajectoryGuard._prefix_offset_ns(mismatch, velocity)
    assert 50_000_000 < offset <= 600_000_000
    remaining = offset * 1e-9 - .014
    extrema = quintic_extrema(mismatch, velocity, 0., 0., 0., 0., remaining)
    assert max(abs(v) for v in extrema['velocity']) <= head_trajectory_guard._MAX_VELOCITY
    assert max(abs(a) for a in extrema['acceleration']) <= head_trajectory_guard._MAX_ACCELERATION


@pytest.mark.parametrize('mismatch,velocity', [(math.nan, 0.), (0., math.inf),
    (.00201, 0.), (0., .042)])
def test_prefix_refuses_invalid_or_out_of_bound_measured_anchors(mismatch, velocity):
    with pytest.raises((ValueError, PermissionError)):
        HeadTrajectoryGuard._prefix_offset_ns(mismatch, velocity)
