"""The goals builder is judged by the path screen's own validator, not by this file's opinion."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from so101_demo.act.joints import ARM_JOINTS  # noqa: E402
from so101_demo.adapters.act.pick_place_approach_goals import (  # noqa: E402
    APPROACH_GOAL_KEYS, build_approach_goals,
)
from so101_demo.adapters.act.pick_place_approach_path_screen import _GOAL_KEYS  # noqa: E402

HELD = (0.0, -0.3, 0.2, 0.0, 0.0, 0.0)


def _prefix():
    return {"session_id": "session-1", "attempt_id": "attempt-1", "sequence": 0,
            "observation_time_s": 1.3, "target_times_s": (1.4,),
            "positions": ((0.1, -0.2, 0.15, 0.0, 0.0, 0.1),)}


def test_the_builder_mirrors_the_screens_goal_key_set_exactly():
    assert APPROACH_GOAL_KEYS == _GOAL_KEYS


def test_the_screen_accepts_the_goals_this_builder_produces():
    """The judge is the screen's own `_goals`, which is where the field-by-field contract lives."""

    from so101_demo.adapters.act.pick_place_approach_path_screen import PickPlaceApproachPathScreen

    prefix = _prefix()
    goals = build_approach_goals(prefix, HELD, header_stamp_s=1.35)

    start, held = PickPlaceApproachPathScreen._goals(goals, prefix)
    assert start == 1.35
    assert tuple(held) == HELD
    assert [tuple(goal["joint_names"]) for goal in goals] == [ARM_JOINTS[:5], ARM_JOINTS[5:]]


def test_a_header_stamp_outside_the_prefixs_window_is_refused_by_name():
    """The stamp is not a free choice: the screen requires it inside the prefix's own window."""

    prefix = _prefix()
    for bad in (1.3, 1.4, 1.2):
        with pytest.raises(ValueError, match="APPROACH_HEADER_STAMP_INVALID"):
            build_approach_goals(prefix, HELD, header_stamp_s=bad)
