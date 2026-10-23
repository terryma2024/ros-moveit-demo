"""The work queue of a parallel rollout: one unit is one attempt of one (point, trial).

A trial is a label only: the rollout has no episode seeds, so two trials of one point differ in nothing but the free-running timing.
An INVALID attempt (an infrastructure fault) is queued again as the same (point, trial) with the next attempt number, up to
`--max-invalid-retries` more attempts; it is counted apart from the policy's results, exactly as the native command does.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re

from so101_demo.act.rollout_shared import select_scenes

#: a unit id is the scene id of the task (and the episode's attempt id): the instance's identifier rule
_UNIT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
FINAL_VERDICTS = ("DONE", "FAILED", "NO_MOTION")


@dataclass(frozen=True)
class Unit:
    point_id: str
    group: str
    trial: int
    attempt_number: int = 1

    @property
    def unit_id(self) -> str:
        return f"{self.point_id}-t{self.trial}-a{self.attempt_number}"

    @property
    def key(self) -> tuple:
        """What stays the same across the attempts of one unit of work."""
        return (self.point_id, self.trial)

    def retry(self) -> "Unit":
        return replace(self, attempt_number=self.attempt_number + 1)


def checked(unit: Unit) -> Unit:
    if (type(unit.trial) is not int or unit.trial < 1 or type(unit.attempt_number) is not int or unit.attempt_number < 1
            or _UNIT_ID.fullmatch(unit.unit_id) is None):
        raise ValueError("ROLLOUT_UNIT_ID_INVALID: " + str(unit.unit_id))
    return unit


def build_units(scenes_document: dict, *, group: str, scene_ids, trials: int, limit=None, max_invalid_retries: int = 0) -> list:
    """The first attempt of every (point, trial), trial by trial (all points of trial 1, then trial 2, ...).

    Every attempt a retry can produce is checked here too, so a scene id too long for the identifier rule is refused before
    anything starts."""
    if type(trials) is not int or trials < 1:
        raise ValueError("ROLLOUT_TRIALS_INVALID")
    scenes = select_scenes(scenes_document, group, scene_ids, limit)
    units = []
    for trial in range(1, trials + 1):
        for scene in scenes:
            unit = checked(Unit(point_id=scene["scene_id"], group=group, trial=trial))
            checked(replace(unit, attempt_number=max_invalid_retries + 1))
            units.append(unit)
    return units
