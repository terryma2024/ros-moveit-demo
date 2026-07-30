import math

import pytest

from so101_teleop.geometry import apply_rotation_step, apply_translation_step
from so101_teleop.models import Pose6D, StepFrame


BASE = Pose6D(
    frame_id="world",
    tcp_frame="so101_tcp",
    x_m=0.2,
    y_m=-0.1,
    z_m=0.3,
    roll_rad=0.0,
    pitch_rad=0.0,
    yaw_rad=0.0,
)


def test_world_y_step_is_exactly_one_millimetre():
    """Changing world-frame translation math must not turn a 1 mm step into another distance."""
    actual = apply_translation_step(BASE, "y", 0.001, StepFrame.WORLD)

    assert actual.y_m == pytest.approx(BASE.y_m + 0.001, abs=1e-12)
    assert actual.x_m == BASE.x_m


def test_tool_x_step_uses_current_tcp_orientation():
    """Replacing tool composition with world axes would move this yawed TCP along X."""
    yaw90 = BASE.copy(update={"yaw_rad": math.pi / 2})
    actual = apply_translation_step(yaw90, "x", 0.001, StepFrame.TOOL)

    assert actual.y_m == pytest.approx(yaw90.y_m + 0.001, abs=1e-12)
    assert actual.x_m == pytest.approx(yaw90.x_m, abs=1e-12)


def test_tool_rotation_composes_after_current_orientation():
    """Swapping tool and world multiplication changes the yaw of this non-commuting rotation."""
    pitched = BASE.copy(update={"pitch_rad": math.pi / 2})
    actual = apply_rotation_step(pitched, "x", math.pi / 2, StepFrame.TOOL)

    assert actual.roll_rad == pytest.approx(math.pi / 2, abs=1e-12)
    assert actual.pitch_rad == pytest.approx(math.pi / 2, abs=1e-12)
    assert actual.yaw_rad == pytest.approx(0.0, abs=1e-12)
