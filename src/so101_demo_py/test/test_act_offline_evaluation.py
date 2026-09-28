"""Task 12A: padded frames must not enter a joint metric, and bad rows must not vanish."""

import pytest

from so101_demo.act.offline_evaluation import masked_joint_mae, masked_joint_rmse


def test_padding_is_excluded_from_joint_metrics():
    predicted = [[1., 2., 3., 4., 5., 6.], [100., 100., 100., 100., 100., 100.]]
    target = [[0., 0., 0., 0., 0., 0.], [0., 0., 0., 0., 0., 0.]]
    assert masked_joint_mae(predicted, target, [True, False]) == [1., 2., 3., 4., 5., 6.]


def test_a_mask_that_keeps_nothing_is_refused_rather_than_reported_as_zero_error():
    with pytest.raises(ValueError, match="NO_VALID_TARGETS"):
        masked_joint_mae([[1.] * 6], [[0.] * 6], [False])
    with pytest.raises(ValueError, match="NO_VALID_TARGETS"):
        masked_joint_rmse([], [], [])


def test_shapes_values_and_mask_types_are_closed(tmp_path):
    for predicted, target, valid in (
            ([[1.] * 6], [[0.] * 6, [0.] * 6], [True]),          # length mismatch
            ([[1.] * 5], [[0.] * 5], [True]),                     # not six joints
            ([[1.] * 6], [[0.] * 6], [1]),                        # the mask is not a bool
            ([[float("nan")] * 6], [[0.] * 6], [True]),           # a non-finite prediction
            ([[True] * 6], [[0.] * 6], [True]),                   # a bool is not a joint angle
            ([[1.] * 6], [[float("inf")] * 6], [True]),           # nor is a non-finite target
    ):
        shape_fault = (len(predicted) != len(target) or len(predicted[0]) != 6
                       or type(valid[0]) is not bool)
        expected = "MASK_SHAPE_INVALID" if shape_fault else "(PREDICTED|TARGET)_INVALID"
        with pytest.raises(ValueError, match=expected):
            masked_joint_mae(predicted, target, valid)


def test_rmse_matches_the_same_masked_frames():
    predicted = [[3., 0., 0., 0., 0., 0.], [100.] * 6]
    target = [[0.] * 6, [0.] * 6]
    assert masked_joint_rmse(predicted, target, [True, False]) == [3., 0., 0., 0., 0., 0.]
    # the two metrics agree on a single frame, and the mask alone decides the denominator
    assert masked_joint_mae([[1.] * 6, [9.] * 6], [[0.] * 6, [0.] * 6], [True, True]) == [5.] * 6
