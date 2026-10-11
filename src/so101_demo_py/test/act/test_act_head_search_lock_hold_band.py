"""A lock run starts in the strict deadband and survives detector jitter inside a wider hold band."""
import math

import pytest

from so101_demo.act.search import HeadSearchController
from test_act_search import BOX, evidence
from test_act_head_search_centering_damping import controller

DEADBAND = 5.
HOLD_MARGIN = 3.


def observe(search, stamp, error, *, rows=(200., 280.), track='cup1'):
    detection = dict(BOX, xyxy=(300.+error, rows[0], 340.+error, rows[1]), track_id=track)
    return search.tick(*evidence(stamp, q=search.target, detections=(detection,)), stamp)


def test_hold_margin_is_the_pinned_named_constant():
    from so101_demo.act.lock_band import LOCK_HOLD_MARGIN_PX
    assert LOCK_HOLD_MARGIN_PX == HOLD_MARGIN


@pytest.mark.parametrize('legacy', [False, True])
def test_strict_start_then_hold_band_frame_then_strict_frame_locks(legacy):
    search = controller(legacy=legacy)
    counts = []
    for stamp, error in ((1., -4.7), (1.1, -6.3)):
        assert 'found' not in observe(search, stamp, error)
        counts.append(search.lock_count)
    result = observe(search, 1.2, -4.8)
    assert counts == [1, 2]
    assert result['status'] == 'TARGET_LOCKED' and result['found'] is True
    assert search.lock_count == 3


@pytest.mark.parametrize('sign', [-1, 1])
def test_hold_band_is_symmetric(sign):
    search = controller()
    observe(search, 1., sign*4.7)
    observe(search, 1.1, -sign*6.3)
    assert observe(search, 1.2, sign*4.8)['status'] == 'TARGET_LOCKED'


def test_a_run_cannot_start_inside_the_hold_band_only():
    search = controller()
    yaw = search.target
    for stamp, error in ((1., 5.5), (1.1, 6.5), (1.2, 5.5)):
        before = search.target
        result = observe(search, stamp, error)
        assert 'found' not in result and search.lock_count == 0
        assert search.target != before
    assert yaw != search.target


def test_a_frame_beyond_the_hold_band_resets_and_issues_the_correction():
    search = controller()
    observe(search, 1., -4.7)
    assert search.lock_count == 1
    yaw = search.target
    result = observe(search, 1.1, -8.5)
    assert search.lock_count == 0 and 'found' not in result
    assert search.target - yaw == pytest.approx(math.atan(8.5/400))
    assert search.fine_count == 1


def test_band_edges_are_inclusive_and_pinned():
    search = controller()
    # the strict edge starts a run, the hold edge continues it
    observe(search, 1., DEADBAND)
    observe(search, 1.1, DEADBAND+HOLD_MARGIN)
    assert search.lock_count == 2
    assert observe(search, 1.2, -(DEADBAND+HOLD_MARGIN))['status'] == 'TARGET_LOCKED'
    # just outside the strict edge cannot start; just outside the hold edge resets
    search = controller()
    observe(search, 1., DEADBAND+.01)
    assert search.lock_count == 0
    search = controller()
    observe(search, 1., DEADBAND)
    observe(search, 1.1, DEADBAND+HOLD_MARGIN+.01)
    assert search.lock_count == 0


def test_a_hold_band_frame_issues_no_motion():
    search = controller()
    observe(search, 1., -4.7)
    yaw, count, angle = search.target, search.fine_count, search.fine_angle
    result = observe(search, 1.1, -6.3)
    assert result['stop'] is False and result['neck_target_rad'] == yaw
    assert (search.target, search.fine_count, search.fine_angle) == (yaw, count, angle)
    assert search.lock_count == 2


def test_vertical_bounds_still_reset_inside_the_hold_band():
    search = controller()
    observe(search, 1., -4.7)
    yaw = search.target
    result = observe(search, 1.1, -6.3, rows=(420., 480.))
    assert search.lock_count == 0 and 'found' not in result
    assert search.target != yaw


def test_a_detection_gap_still_drops_the_run():
    search = controller()
    observe(search, 1., -4.7)
    search.tick(*evidence(1.1, q=search.target), 1.1)
    assert search.lock_count == 0
    observe(search, 1.2, -6.3)
    assert search.lock_count == 0
