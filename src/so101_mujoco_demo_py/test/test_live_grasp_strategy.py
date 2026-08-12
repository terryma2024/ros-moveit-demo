import pytest

from so101_mujoco_demo_py.live_phases.grasp_strategy import (
    FIVE_WIN_SEATING_PRELOAD_Q6_RAD,
    seating_preload_target,
)


def test_contact_detection_does_not_replace_frozen_seating_preload() -> None:
    assert FIVE_WIN_SEATING_PRELOAD_Q6_RAD == pytest.approx(
        -0.04850794875050089,
        abs=1e-15,
    )
    assert seating_preload_target(-0.04746121642596459) == pytest.approx(
        FIVE_WIN_SEATING_PRELOAD_Q6_RAD,
        abs=1e-15,
    )


def test_seating_preload_never_reopens_an_already_more_closed_gripper() -> None:
    already_more_closed_q6 = FIVE_WIN_SEATING_PRELOAD_Q6_RAD - 0.0002

    assert seating_preload_target(already_more_closed_q6) == already_more_closed_q6


def test_seating_preload_rejects_non_finite_joint_evidence() -> None:
    with pytest.raises(ValueError, match="finite"):
        seating_preload_target(float("nan"))
