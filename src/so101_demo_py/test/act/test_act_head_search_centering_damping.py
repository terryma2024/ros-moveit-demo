"""Nonconverging bbox reversals must not perpetuate full-angle oscillation."""
from copy import deepcopy
import math

import pytest

from so101_demo.act.search import HeadSearchController
from test_act_search import BOX, evidence
from test_act_head_stopped_search_policy import bounded_config, simulation


def controller(*, legacy=False, **changes):
    values = bounded_config(center_deadband_px=5., max_fine_corrections=4)
    values.update(changes)
    return HeadSearchController(values, simulation_policy=None if legacy else simulation())


def observe(search, stamp, error, *, track='cup1'):
    detection = dict(BOX, xyxy=(300.+error, 200., 340.+error, 280.), track_id=track)
    return search.tick(*evidence(stamp, q=search.target, detections=(detection,)), stamp)


@pytest.mark.parametrize('direction', [-1, 1])
def test_nonconverging_reversal_reduces_overshoot_and_can_lock(direction):
    search = controller()
    observe(search, 1., direction*6.5)
    yaw = search.target
    result = observe(search, 1.1, -direction*6.4)
    # These fixtures have an undistorted 400 px focal length and a horizontal optical axis.
    assert result['neck_target_rad']-yaw == pytest.approx(direction*math.atan(6.4/400)/2)
    assert search.fine_angle == pytest.approx(math.atan(6.5/400)+math.atan(6.4/400)/2)
    for stamp in (1.2, 1.3):
        assert 'found' not in observe(search, stamp, direction*2.)
    assert observe(search, 1.4, direction*2.)['status'] == 'TARGET_LOCKED'


def test_large_improvement_keeps_full_correction_despite_reversal():
    search = controller()
    observe(search, 1., -72.)
    yaw = search.target
    observe(search, 1.1, 6.5)
    assert search.target-yaw == pytest.approx(-math.atan(6.5/400))


@pytest.mark.parametrize('boundary', ['track_change', 'missing_detection', 'reset'])
def test_damping_does_not_leak_to_a_new_target(boundary):
    search = controller()
    observe(search, 1., 6.5)
    observe(search, 1.1, -6.4)
    if boundary == 'missing_detection':
        search.tick(*evidence(1.2, q=search.target), 1.2)
    elif boundary == 'reset':
        search.reset(search.config)
    yaw = search.target
    observe(search, 1.3, 6.5, track='cup2' if boundary == 'track_change' else 'cup1')
    assert search.target-yaw == pytest.approx(-math.atan(6.5/400))


def test_reduced_gain_persists_through_same_side_observation_and_copy():
    search = controller()
    observe(search, 1., 6.5)
    observe(search, 1.1, -6.4)
    search = deepcopy(search)
    yaw = search.target
    observe(search, 1.2, -6.)
    assert search.target-yaw == pytest.approx(math.atan(6./400)/2)


def test_damping_never_bypasses_the_fine_count_budget():
    search = controller(max_fine_corrections=2)
    observe(search, 1., 6.5)
    observe(search, 1.1, -6.4)
    assert observe(search, 1.2, 6.5)['status'] == 'TARGET_NOT_CENTERED'


def test_damping_never_bypasses_the_cumulative_motion_budget():
    search = controller(max_fine_total_rad=.02)
    observe(search, 1., 6.5)
    assert observe(search, 1.1, -6.4)['status'] == 'TARGET_NOT_CENTERED'


def test_legacy_calibration_keeps_original_full_angle_behavior():
    search = controller(legacy=True)
    observe(search, 1., 6.5)
    yaw = search.target
    observe(search, 1.1, -6.4)
    assert search.target-yaw == pytest.approx(math.atan(6.4/400))
