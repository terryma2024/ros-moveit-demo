"""Head duplicate instances must not create false multi-cup ambiguity."""

from pathlib import Path

import numpy as np
import pytest

from so101_demo.adapters.act.detector import HeadRgbDetector
from so101_demo.core.detection import DetectionBatch, DetectionCandidate
from so101_demo.act.search import HeadSearchController
from test_act_search import config, evidence


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
    with np.load(Path(__file__).parent / 'data/head_900027_duplicate_masks.npz') as saved:
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


@pytest.mark.parametrize('shared_pixels, expected_count', [(7, 1), (6, 2)])
def test_mask_overlap_boundary_is_inclusive(shared_pixels, expected_count):
    head = runtime([candidate('high', mask(*range(10)), confidence=.9),
                    candidate('low', mask(*range(shared_pixels)), confidence=.8)])
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
    with np.load(Path(__file__).parent / 'data/head_900017_nested_fragment.npz') as saved:
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


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('damage', [None, 'mask_containment', 'mask_area',
                                   'bbox_containment', 'bbox_area',
                                   'confidence_absolute', 'confidence_relative',
                                   'confidence_equal', 'class'])
def test_nested_fragment_guards_and_inclusive_boundaries(damage, reverse):
    # Exactly 19/20 mask and bbox containment, 20/40 mask area, 200/400 bbox
    # area, and .5/1 confidence exercise all inclusive boundaries together.
    broad_mask = mask(*range(300, 340))
    fragment_mask = mask(*range(321, 341))
    broad_box = (300., 200., 320., 220.)
    fragment_box = (310.5, 200., 320.5, 220.)
    broad_confidence, fragment_confidence = 1., .5
    fragment_class = 'plastic_cup'
    if damage == 'mask_containment':
        fragment_mask = mask(*range(322, 342))  # 18/20 inside.
    elif damage == 'mask_area':
        fragment_mask = mask(*range(318, 339))  # 21/40, despite full containment.
    elif damage == 'bbox_containment':
        fragment_box = (310.51, 200., 320.51, 220.)
    elif damage == 'bbox_area':
        fragment_box = (310.4, 200., 320.41, 220.)
    elif damage == 'confidence_absolute':
        fragment_confidence = .5001
    elif damage == 'confidence_relative':
        broad_confidence = .999
    elif damage == 'confidence_equal':
        broad_confidence = .5
    elif damage == 'class':
        fragment_class = 'cup'
    candidates = [candidate('broad', broad_mask, box=broad_box,
                            confidence=broad_confidence),
                  candidate('fragment', fragment_mask, box=fragment_box,
                            confidence=fragment_confidence, class_id=fragment_class)]
    if reverse:
        candidates.reverse()
    result = detect(runtime(candidates))
    assert len(result) == (1 if damage is None else 2)
    if damage is None:
        assert result[0]['xyxy'] == broad_box


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
