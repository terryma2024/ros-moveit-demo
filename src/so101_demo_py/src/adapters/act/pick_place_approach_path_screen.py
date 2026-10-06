"""Inspect an APPROACH goal pair against the execution layer's saved path state.

This read-only check creates no motion permit and never dispatches a controller.
"""

from __future__ import annotations

import copy

from so101_demo.act.contracts import finite, validate_action_prefix
from so101_demo.act.execution import bounded_positions
from .pick_place_approach_goals import APPROACH_GOAL_KEYS, build_approach_goals

_GOAL_KEYS = APPROACH_GOAL_KEYS


class PickPlaceApproachPathScreen:
    def __init__(self, *, search_port, sources, broker, path_checker, cancelled):
        if (not callable(getattr(search_port, "validated_search_observation", None))
                or not callable(getattr(sources, "capture", None))
                or not callable(getattr(path_checker, "check_path", None))
                or not callable(getattr(cancelled, "is_set", None))
                or getattr(path_checker, "model_sha256", None) is None
                or getattr(getattr(sources, "contact_pairs", None), "model_sha256", None)
                != path_checker.model_sha256):
            raise ValueError("PICK_PLACE_APPROACH_SCREEN_CONFIG_INVALID")
        self.search_port, self.sources, self.broker = search_port, sources, broker
        self.path_checker, self.cancelled = path_checker, cancelled

    @staticmethod
    def _goals(goals, prefix):
        checked = validate_action_prefix(prefix)
        try:
            if (not isinstance(goals, (tuple, list)) or len(goals) != 2
                    or any(type(goal) is not dict or set(goal) != _GOAL_KEYS for goal in goals)):
                raise ValueError("goal fields")
            start = finite(goals[0]["header_stamp_s"], nonnegative=True)
            held = bounded_positions(tuple(goals[0]["positions"][0])
                                     + tuple(goals[1]["positions"][0]))
            expected = build_approach_goals(checked, held, header_stamp_s=start)
            for goal, wanted in zip(goals, expected, strict=True):
                normalized = dict(goal)
                normalized["joint_names"] = tuple(goal["joint_names"])
                normalized["header_stamp_s"] = finite(goal["header_stamp_s"], nonnegative=True)
                normalized["time_from_start_s"] = tuple(
                    finite(item, nonnegative=True) for item in goal["time_from_start_s"])
                normalized["positions"] = tuple(tuple(finite(item) for item in row)
                                                for row in goal["positions"])
                if (type(goal["sequence"]) is not int or normalized != wanted):
                    raise ValueError("goal does not match prefix")
            return start, held
        except (KeyError, TypeError, ValueError, IndexError, OverflowError) as error:
            raise ValueError("PICK_PLACE_APPROACH_GOALS_INVALID") from error

    def inspect(self, goals, prefix, *, snapshot=None):
        start, held = self._goals(goals, prefix)
        if self.cancelled.is_set():
            raise ValueError("PICK_PLACE_APPROACH_CANCELLED")
        if type(snapshot) is not dict:
            raise ValueError("PICK_PLACE_APPROACH_SNAPSHOT_REQUIRED")
        state = copy.deepcopy(snapshot)
        try:
            if (state["model_sha256"] != self.path_checker.model_sha256
                    or state["phase"] != "APPROACH" or state["holding_state"] != "EMPTY"
                    or state["cup_in_gripper_transform"] is not None
                    or finite(state["controller_start_time_s"]) != start
                    or bounded_positions(state["controller_start_positions"]) != held):
                raise ValueError("path scope or start state")
            safe = self.path_checker.check_path(validate_action_prefix(prefix), state)
            details = copy.deepcopy(self.path_checker.last_check)
            if (type(safe) is not bool or type(details) is not dict
                    or details.get("safe") is not safe or not safe):
                raise ValueError("independent path check refused")
        except (KeyError, TypeError, ValueError, IndexError, OverflowError) as error:
            raise ValueError("PICK_PLACE_APPROACH_PATH_UNSAFE") from error
        if self.cancelled.is_set():
            raise ValueError("PICK_PLACE_APPROACH_CANCELLED")
        return details
