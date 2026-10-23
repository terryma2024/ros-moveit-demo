"""Head duplicate instances must not create false multi-cup ambiguity."""


import numpy as np
import pytest

from so101_demo.adapters.act import detector as detector_module
from so101_demo.adapters.act.detector import HeadRgbDetector
from so101_demo.core.detection import DetectionBatch, DetectionCandidate
from so101_demo.act.search import HeadSearchController
from test_act_search import config, evidence
from paths import TEST_ROOT


HIGH_BOX = (152.88339233398438, 201.56985473632812,
            223.02642822265625, 314.5864562988281)
LOW_BOX = (119.40956115722656, 201.95147705078125,
           223.48594665527344, 314.47735595703125)
CENTER_BOX = (300., 200., 340., 280.)


def candidate(instance, mask, *, confidence=.9, box=CENTER_BOX, class_id='plastic_cup'):
    return DetectionCandidate(instance, class_id, confidence, box, mask,
                              1, 'head_camera_frame', 640, 480)


class CapturedDetector:
    """Replace only GPU inference; retain real contracts, tracks and search."""

    def __init__(self, candidates):
        self.batch = DetectionBatch('model', 'a' * 64, 'cuda', 1., 640, 480,
                                    tuple(candidates))

    def detect(self, frame, query):
        assert query.class_id == 'plastic_cup'
        return self.batch


def runtime(candidates):
    return HeadRgbDetector(CapturedDetector(candidates), model_id='model',
                           weights_sha256='a' * 64, tracking_iou=.5,
                           min_bbox_aspect=.5)


def detect(head, stamp=1, attempt='a'):
    return head.detect(np.zeros((480, 640, 3), np.uint8), session_id='s',
                       attempt_id=attempt, source_stamp_ns=stamp,
                       source_frame_id='head_camera_frame')


def mask(*pixels):
    result = np.zeros((480, 640), dtype=bool)
    result[200, list(pixels)] = True
    return result


@pytest.mark.parametrize('reverse', [False, True])
def test_actual_900027_duplicate_masks_keep_high_confidence_instance(reverse):
    with np.load(TEST_ROOT / 'data/head_900027_duplicate_masks.npz') as saved:
        candidates = [candidate('high', saved['high'], confidence=.9388879537582397,
                                box=HIGH_BOX),
                      candidate('low', saved['low'], confidence=.2810225784778595,
                                box=LOW_BOX)]
    if reverse:
        candidates.reverse()
    head = runtime(candidates)
    snapshots = [value.mask.copy() for value in candidates]
    first = detect(head)
    assert first == [dict(xyxy=HIGH_BOX, confidence=.9388879537582397,
                          class_id=0, track_id='head-cup-0')]
    assert detect(head, 2)[0]['track_id'] == 'head-cup-0'
    assert len(head.detector.batch.candidates) == 2
    for value, before in zip(candidates, snapshots):
        np.testing.assert_array_equal(value.mask, before)
        assert not value.mask.flags.writeable


@pytest.mark.parametrize('extra_pixels, expected_count', [(1, 1), (2, 2)])
def test_mask_iou_boundary_is_inclusive(extra_pixels, expected_count):
    # The low mask is not nested (7/8 and 7/9 inside the high mask), so only the
    # IoU rule applies: 7/10 is exactly .7, 7/11 is below it.
    high = mask(*range(9))
    low = mask(*range(2, 9), *range(9, 9 + extra_pixels))
    head = runtime([candidate('high', high, confidence=.9),
                    candidate('low', low, confidence=.8)])
    assert len(detect(head)) == expected_count


def test_overlapping_boxes_disjoint_masks_still_end_search_as_ambiguous():
    head = runtime([candidate('left', mask(300, 301)),
                    candidate('right', mask(302, 303), box=(301., 200., 341., 280.))])
    result = detect(head)
    assert len(result) == 2
    decision = HeadSearchController(config()).tick(*evidence(1., detections=result), 1.)
    assert decision['status'] == 'TARGET_AMBIGUOUS'
    assert decision['bearing_rad'] is None


def test_distinct_cup_classes_do_not_suppress_each_other():
    head = runtime([candidate('plastic', mask(300)),
                    candidate('cup', mask(300), class_id='cup')])
    assert len(detect(head)) == 2


@pytest.mark.parametrize('reverse', [False, True])
def test_equal_confidence_uses_bbox_tie_break_before_tracking(reverse):
    candidates = [candidate('right', mask(300), box=(301., 200., 341., 280.)),
                  candidate('left', mask(300))]
    if reverse:
        candidates.reverse()
    assert detect(runtime(candidates))[0]['xyxy'] == CENTER_BOX
    assert len(detect(runtime(candidates))) == 1


@pytest.mark.parametrize('reverse', [False, True])
def test_equal_confidence_and_bbox_uses_instance_id_tie_break(reverse):
    # aa overlaps both bb/cc above .7; bb/cc overlap each other below .7.
    candidates = [candidate('bb', mask(*range(9), 10)),
                  candidate('cc', mask(*range(1, 10), 11)),
                  candidate('aa', mask(*range(10)))]
    if reverse:
        candidates.reverse()
    assert len(detect(runtime(candidates))) == 1


@pytest.mark.parametrize('excluded', ['class', 'shape'])
def test_ineligible_high_confidence_candidate_cannot_suppress_cup(excluded):
    high = candidate('excluded', mask(300), confidence=.99,
                     class_id='bottle' if excluded == 'class' else 'plastic_cup',
                     box=(200., 200., 400., 250.) if excluded == 'shape' else CENTER_BOX)
    result = detect(runtime([high, candidate('cup', mask(300), confidence=.8)]))
    assert len(result) == 1
    assert result[0]['confidence'] == .8


def test_deduplicated_track_still_requires_three_fresh_frames_and_attempt_reset():
    head = runtime([candidate('high', mask(300)),
                    candidate('low', mask(300), confidence=.8)])
    search = HeadSearchController(config())
    for stamp, time_s in [(1, 1.), (2, 1.1)]:
        decision = search.tick(*evidence(time_s, detections=detect(head, stamp)), time_s)
        assert 'found' not in decision
    decision = search.tick(*evidence(1.2, detections=detect(head, 3)), 1.2)
    assert decision['status'] == 'TARGET_LOCKED'
    with pytest.raises(ValueError, match='DETECTOR_TIMESTAMP_INVALID'):
        detect(head, 3)
    with pytest.raises(ValueError, match='DETECTOR_RESET_REQUIRED'):
        detect(head, 4, 'new')
    head.reset()
    assert detect(head, 1, 'new')[0]['track_id'] == 'head-cup-0'


def captured_900017(stamp=6268000000):
    with np.load(TEST_ROOT / 'data/head_900017_nested_fragment.npz') as saved:
        return [candidate(f'captured-{index}', pixels, confidence=float(box[4]),
                          box=tuple(float(value) for value in box[:4]))
                for index, (pixels, box) in enumerate(zip(
                    saved[f'masks_{stamp}'], saved[f'boxes_{stamp}']))]


@pytest.mark.parametrize('reverse', [False, True])
def test_actual_900017_nested_fragment_keeps_broad_high_confidence_cup(reverse):
    candidates = captured_900017()
    broad, fragment = candidates
    assert [int(value.mask.sum()) for value in candidates] == [2973, 1016]
    assert np.count_nonzero(broad.mask & fragment.mask) == 1013
    if reverse:
        candidates.reverse()
    snapshots = [value.mask.copy() for value in candidates]
    head = runtime(candidates)
    assert detect(head) == [dict(xyxy=broad.bbox_xyxy, confidence=broad.confidence,
                                class_id=0, track_id='head-cup-0')]
    assert detect(head, 2)[0]['track_id'] == 'head-cup-0'
    assert len(head.detector.batch.candidates) == 2
    for value, before in zip(candidates, snapshots):
        np.testing.assert_array_equal(value.mask, before)
        assert not value.mask.flags.writeable


def test_actual_900017_original_three_frame_sequence_only_changes_terminal_count():
    head = runtime([])
    accepted = []
    for stamp in (4168000000, 5268000000, 6268000000):
        head.detector = CapturedDetector(captured_900017(stamp))
        accepted.append(detect(head, stamp))
    assert [len(values) for values in accepted] == [0, 1, 1]
    assert accepted[1][0]['track_id'] == 'head-cup-0'
    # The original viewpoint shift still cannot inherit the earlier track.
    assert accepted[2][0]['track_id'] == 'head-cup-1'


def test_actual_nested_fragment_still_requires_three_fresh_frames_before_lock():
    head = runtime(captured_900017())
    search = HeadSearchController(config(min_confidence=.25))
    for stamp, time_s in ((1, 1.), (2, 1.1)):
        detections = detect(head, stamp)
        assert len(detections) == 1
        decision = search.tick(*evidence(time_s, detections=detections), time_s)
        assert 'found' not in decision
    assert search.tick(*evidence(1.2, detections=detect(head, 3)), 1.2)[
        'status'] == 'TARGET_LOCKED'


BROAD_BOX = (300., 200., 400., 300.)


def nested_pair(child_pixels, child_box, *, child_confidence=.8, child_class='plastic_cup',
                reverse=False):
    """A 100 px parent on row 200 and a child; return the deduplicated result."""
    candidates = [candidate('broad', mask(*range(300, 400)), box=BROAD_BOX, confidence=.9),
                  candidate('child', mask(*child_pixels), box=child_box,
                            confidence=child_confidence, class_id=child_class)]
    if reverse:
        candidates.reverse()
    return detect(runtime(candidates))


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('child_pixels, child_box, expected_count', [
    # Fully nested child: dropped.
    (range(310, 340), (310., 210., 340., 250.), 1),
    # Mask containment: 19/20 = .95 is inclusive, 18/20 is not.
    (range(381, 401), (381., 210., 400., 250.), 1),
    (range(382, 402), (381., 210., 400., 250.), 2),
    # Bbox containment: 19/20 = .95 is inclusive, 18/20 is not.
    (range(381, 400), (381., 210., 401., 250.), 1),
    (range(381, 400), (382., 210., 402., 250.), 2),
    # The child's mask is only 82 percent inside the parent (41/50): both stay.
    (range(359, 409), (359., 210., 400., 250.), 2),
])
def test_containment_thresholds_are_inclusive(child_pixels, child_box, expected_count,
                                              reverse):
    result = nested_pair(child_pixels, child_box, reverse=reverse)
    assert len(result) == expected_count
    if expected_count == 1:
        assert result[0]['xyxy'] == BROAD_BOX


def nested_predicate(child_pixels, child_box):
    parent = candidate('broad', mask(*range(300, 400)), box=BROAD_BOX, confidence=.9)
    child = candidate('child', mask(*child_pixels), box=child_box, confidence=.8)
    return detector_module.is_nested_in(child, parent)


@pytest.mark.parametrize('child_pixels, child_box, expected', [
    # Area ratio: 80/100 = .8 is inclusive, 81/100 is not.
    (range(310, 390), (310., 210., 390., 250.), True),
    (range(310, 391), (310., 210., 391., 250.), False),
    # The same boundaries for mask and bbox containment.
    (range(381, 401), (381., 210., 400., 250.), True),
    (range(382, 402), (381., 210., 400., 250.), False),
    (range(381, 400), (381., 210., 401., 250.), True),
    (range(381, 400), (382., 210., 402., 250.), False),
])
def test_nested_predicate_boundaries_are_inclusive(child_pixels, child_box, expected):
    # The area-ratio cap is not reachable through detect(): a mask that is at
    # least 95 percent inside a larger one with a ratio above .8 always has an
    # IoU above .7 and is removed by the IoU rule, so it is pinned here.
    assert nested_predicate(child_pixels, child_box) is expected


def test_containment_dedup_thresholds_are_the_named_constants():
    assert (detector_module.NESTED_MIN_MASK_CONTAINMENT,
            detector_module.NESTED_MIN_BBOX_CONTAINMENT,
            detector_module.NESTED_MAX_AREA_RATIO) == (.95, .95, .8)


@pytest.mark.parametrize('child_confidence', [.89, .5001, .3, .26])
def test_fully_nested_child_is_dropped_whatever_its_confidence(child_confidence):
    # Neither a high absolute confidence nor a confidence close to the parent's
    # protects a child that lies wholly inside a higher-confidence mask.
    result = nested_pair(range(310, 340), (310., 210., 340., 250.),
                         child_confidence=child_confidence)
    assert [value['xyxy'] for value in result] == [BROAD_BOX]


def test_nested_child_of_another_class_is_not_dropped():
    assert len(nested_pair(range(310, 340), (310., 210., 340., 250.),
                           child_class='cup')) == 2


def test_equal_confidence_nested_child_follows_the_tie_break_order():
    # Candidates are ranked by confidence, then bbox, then instance id, and only
    # a candidate ranked below a kept mask can be dropped as nested in it.
    result = detect(runtime([
        candidate('broad', mask(*range(300, 400)), box=BROAD_BOX, confidence=.9),
        candidate('child', mask(*range(310, 340)), box=(310., 210., 340., 250.),
                  confidence=.9)]))
    assert [value['xyxy'] for value in result] == [BROAD_BOX]


@pytest.mark.parametrize('reverse', [False, True])
def test_front_mask_over_a_comparable_second_cup_is_not_a_containment_duplicate(reverse):
    # A front mask that covers 75 of 90 pixels (83 percent) of a comparably sized
    # second candidate (ratio .9 > .8) is neither nested nor an IoU duplicate
    # (75/115 = .65), so two real cups stay two and the search stays ambiguous.
    second = range(325, 415)
    assert not nested_predicate(second, (325., 210., 415., 290.))
    result = nested_pair(second, (325., 210., 415., 290.), reverse=reverse)
    assert len(result) == 2
    decision = HeadSearchController(config(min_confidence=.25)).tick(
        *evidence(1., detections=result), 1.)
    assert decision['status'] == 'TARGET_AMBIGUOUS'


def test_fully_covered_comparable_candidate_is_removed_by_the_iou_rule_only():
    # Full containment with a ratio above .8 is a mask duplicate (IoU .9), as it
    # was before containment dedup; the containment predicate itself rejects it.
    second = range(310, 400)
    assert not nested_predicate(second, (310., 210., 400., 290.))
    assert len(nested_pair(second, (310., 210., 400., 290.))) == 1


def captured_900027(name):
    with np.load(TEST_ROOT / 'data/head_900027_nested_children.npz') as saved:
        return [candidate(f'{name}-{index}', pixels, confidence=float(box[4]),
                          box=tuple(float(value) for value in box[:4]))
                for index, (pixels, box) in enumerate(zip(
                    saved[f'masks_{name}'], saved[f'boxes_{name}']))]


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('name, count', [('head40', 3), ('rerun2', 3)])
def test_actual_900027_nested_children_keep_the_whole_cup(name, count, reverse):
    candidates = captured_900027(name)
    whole = candidates[0]
    assert len(candidates) == count
    assert whole.confidence == max(value.confidence for value in candidates)
    # Both children lie inside the whole silhouette (IoU alone misses some).
    for child in candidates[1:]:
        assert np.count_nonzero(child.mask & whole.mask) / np.count_nonzero(
            child.mask) >= .99
    if reverse:
        candidates.reverse()
    snapshots = [value.mask.copy() for value in candidates]
    head = runtime(candidates)
    assert detect(head) == [dict(xyxy=whole.bbox_xyxy, confidence=whole.confidence,
                                class_id=0, track_id='head-cup-0')]
    assert detect(head, 2)[0]['track_id'] == 'head-cup-0'
    assert len(head.detector.batch.candidates) == count
    for value, before in zip(candidates, snapshots):
        np.testing.assert_array_equal(value.mask, before)
        assert not value.mask.flags.writeable


def test_actual_900027_nested_children_are_one_target_for_the_search():
    # The whole cup is off-centre in this frame, so the search centres it; the
    # point is that it never ends as TARGET_AMBIGUOUS.
    head = runtime(captured_900027('head40'))
    search = HeadSearchController(config(min_confidence=.25))
    for stamp, time_s in ((1, 1.), (2, 1.1), (3, 1.2)):
        decision = search.tick(*evidence(time_s, detections=detect(head, stamp)), time_s)
        assert decision['status'] != 'TARGET_AMBIGUOUS'
    assert decision['status'] == 'CENTER_CUP'


@pytest.mark.parametrize('reverse', [False, True])
def test_actual_two_separate_cups_stay_two_and_ambiguous(reverse):
    candidates = captured_900027('two_cups')
    assert len(candidates) == 2
    assert np.count_nonzero(candidates[0].mask & candidates[1].mask) == 0
    if reverse:
        candidates.reverse()
    result = detect(runtime(candidates))
    assert sorted(value['xyxy'] for value in result) == sorted(
        value.bbox_xyxy for value in candidates)
    decision = HeadSearchController(config(min_confidence=.25)).tick(
        *evidence(1., detections=result), 1.)
    assert decision['status'] == 'TARGET_AMBIGUOUS'


@pytest.mark.parametrize('shared_pixels', [0, 8, 19])
def test_two_cups_with_low_confidence_smaller_overlapping_mask_remain_ambiguous(
        shared_pixels):
    # Two spatially separate cups may have overlapping boxes and model masks.
    # Even 95% mask containment alone cannot remove a second cup whose box
    # extends outside the first. Both exceed the live search confidence gate.
    broad = candidate('cup-a', mask(*range(300, 340)),
                      box=(280., 180., 320., 280.))
    second_pixels = list(range(340-shared_pixels, 340)) + list(
        range(340, 360-shared_pixels))
    second = candidate('cup-b', mask(*second_pixels), confidence=.3,
                       box=(310., 180., 330., 280.))
    result = detect(runtime([broad, second]))
    assert len(result) == 2
    decision = HeadSearchController(config(min_confidence=.25)).tick(
        *evidence(1., detections=result), 1.)
    assert decision['status'] == 'TARGET_AMBIGUOUS'
    assert decision['bearing_rad'] is None
