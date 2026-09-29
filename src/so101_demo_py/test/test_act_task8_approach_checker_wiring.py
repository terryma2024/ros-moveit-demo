"""P1-5 (rereview 5): the APPROACH checker a full case needs must actually build, from the admitted document.

CP-1814 found that it could not: `MujocoPathChecker` requires `allowed_pairs_by_phase` (`physics.py:34`, keyword-only,
no default) while `pick_place_child_port`'s checker call omitted it, so supplying the admitted route motion raised
`TypeError` - and a full case could never be driven. CP-1815 found the repair is correct by constructing the checker
in-process, and recorded that the `spawn` handshake can only be exercised from an importable module. This file is that
module: it builds the REAL checker from the REAL route document and asserts the handshake the production builder then
compares against `route_motion["model_sha256"]`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # noqa: E402

from so101_demo.adapters.act.pick_place_child_port import checker_pairs_by_phase  # noqa: E402


def _route_motion() -> dict:
    from test_act_task6_route_diagnostic import manifest as route_manifest

    from so101_demo.adapters.act.calibration_motion import route_motion_configuration

    return route_motion_configuration(route_manifest())


def test_the_pairs_come_from_the_admitted_document_and_are_never_invented():
    motion = _route_motion()
    pairs = checker_pairs_by_phase(motion)
    assert isinstance(pairs, dict) and pairs, "the checker is gated on a per-phase mapping"
    assert set(pairs) == {"APPROACH"}, (
        "a document with no per-phase mapping is read as a single-phase APPROACH gate, the shape "
        "`calibration_motion.py:174-184` uses")
    # the route diagnostic admits NO contact at all, and that is what the mapping must say
    assert pairs["APPROACH"] == frozenset()
    # and a document that carries its own per-phase mapping is used verbatim - nothing is merged or guessed
    carried = {"APPROACH": [["a", "b"]], "CLOSE": [["c", "d"]]}
    assert checker_pairs_by_phase({"allowed_pairs_by_phase": carried}) == {
        "APPROACH": frozenset({("a", "b")}), "CLOSE": frozenset({("c", "d")})}


def test_the_real_checker_starts_and_greets_with_the_admitted_hash():
    """The spawn handshake, from an importable module - the assertion CP-1815 could not make from a probe."""

    from so101_demo.adapters.act.physics import MujocoPathProcess

    motion = _route_motion()
    checker = MujocoPathProcess(
        check_timeout_s=motion["submit_lead_s"], start_timeout_s=2.0,
        model_path=motion["model_path"], protected_roots=("base",),
        cup_joint="cup_free_joint", gripper_body="gripper",
        path_step_s=motion["path_step_s"], path_clearance_m=motion["path_clearance_m"],
        velocity_limit_rad_s=motion["velocity_limit_rad_s"],
        acceleration_limit_rad_s2=motion["acceleration_limit_rad_s2"],
        allowed_pairs_by_phase=checker_pairs_by_phase(motion))
    try:
        assert checker.process.is_alive(), "the worker the checker spawned is running"
        assert checker.model_sha256 == motion["model_sha256"], (
            "the model the checker compiled IS the model the motion was admitted against - the rule the production "
            "builder enforces with APPROACH_CHECKER_MODEL_HASH_INVALID")
    finally:
        checker.close()
    assert not checker.process.is_alive(), "close() retires the worker rather than leaking it"


# ----------------------------------------------------------------------------------------------------------------------
# and the screen that consumes the checker: four callables and one model-hash equality (CP-1817)
# ----------------------------------------------------------------------------------------------------------------------

class _ContactPairs:
    def __init__(self, model_sha256):
        self.model_sha256 = model_sha256


class _Sources:
    """The screen needs `capture` and a `contact_pairs` bound to the checker's model - nothing more is read."""

    def __init__(self, model_sha256):
        self.contact_pairs = _ContactPairs(model_sha256)
        self.captured = 0

    def capture(self):
        self.captured += 1
        return {"fresh": True}


class _SearchPort:
    def validated_search_observation(self, request):
        return {"validated": request}


def _checker(motion):
    from so101_demo.adapters.act.physics import MujocoPathProcess

    return MujocoPathProcess(
        check_timeout_s=motion["submit_lead_s"], start_timeout_s=2.0,
        model_path=motion["model_path"], protected_roots=("base",),
        cup_joint="cup_free_joint", gripper_body="gripper",
        path_step_s=motion["path_step_s"], path_clearance_m=motion["path_clearance_m"],
        velocity_limit_rad_s=motion["velocity_limit_rad_s"],
        acceleration_limit_rad_s2=motion["acceleration_limit_rad_s2"],
        allowed_pairs_by_phase=checker_pairs_by_phase(motion))


def test_the_screen_mounts_over_the_real_checker_and_the_admitted_model():
    import threading

    from so101_demo.adapters.act.pick_place_approach_path_screen import PickPlaceApproachPathScreen

    motion = _route_motion()
    checker = _checker(motion)
    try:
        sources = _Sources(checker.model_sha256)
        screen = PickPlaceApproachPathScreen(search_port=_SearchPort(), sources=sources, broker=object(),
                                             path_checker=checker, cancelled=threading.Event())
        assert screen.path_checker is checker and screen.sources is sources
        # the contract's equality is what makes the screen an inspection rather than a formality: the sources that
        # measure the rows and the checker that judges the path are looking at the SAME compiled model
        assert screen.sources.contact_pairs.model_sha256 == screen.path_checker.model_sha256
    finally:
        checker.close()


def test_a_sources_bound_to_another_model_is_refused():
    """The refusal is the point: fresh measurements of one robot must not be checked against another's path."""

    import threading

    from so101_demo.adapters.act.pick_place_approach_path_screen import PickPlaceApproachPathScreen

    motion = _route_motion()
    checker = _checker(motion)
    try:
        with pytest.raises(ValueError) as error:
            PickPlaceApproachPathScreen(search_port=_SearchPort(), sources=_Sources("f" * 64), broker=object(),
                                        path_checker=checker, cancelled=threading.Event())
        assert "PICK_PLACE_APPROACH_SCREEN_CONFIG_INVALID" in str(error.value)
    finally:
        checker.close()
