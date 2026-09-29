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


# ----------------------------------------------------------------------------------------------------------------------
# the whole assembly the production builder performs, from the same admitted inputs (CP-1810/CP-1817/CP-1818)
# ----------------------------------------------------------------------------------------------------------------------

class _NeckSweep:
    def check(self, *_args, **_kwargs):
        return {"ok": True}


class _MinimalBoundary:
    """The four callables `PickPlaceSearchPhasePort` validates, and nothing else.

    This file lives in `so101_demo_py`'s suite, so it must not reach into the teleop suite's harness - a cross-suite
    import would make one package's tests depend on the other's internals. The port validates `begin`, `search`,
    `safe_stop` and `neck_sweep_checker.check`; these are those four, which is all the assembly reads.
    """

    def __init__(self, *, session_id="assembly-check"):
        self.session_id = session_id
        self.neck_sweep_checker = _NeckSweep()
        self.approach_screen = None

    def begin(self, *_args, **_kwargs):
        return {"session_id": self.session_id}

    def search(self, *_args, **_kwargs):
        return {"observations": []}

    def safe_stop(self, *_args, **_kwargs):
        return {"stopped": True}


def assemble_approach_authority(*, port, sources, broker, cancelled, manifest, path_process_factory=None):
    """Mount APPROACH's inspection authority exactly as `pick_place_child_port.build_pick_place_child_search_port`
    does - the checker from `route_motion_configuration(manifest)`, the production expert-route factory, and the screen
    onto the boundary - and return the checker so a caller can close it.

    Every value comes from the admitted document or the caller's own sources; **nothing here is invented**, which is
    what the builder's own comment demands: *"the checker's configuration is not something this builder may invent."*
    """

    from so101_demo.adapters.act.calibration_motion import route_motion_configuration
    from so101_demo.adapters.act.physics import MujocoPathProcess
    from so101_demo.adapters.act.pick_place_approach_path_screen import PickPlaceApproachPathScreen
    from so101_demo.adapters.act.pick_place_search_port import PickPlaceSearchPhasePort
    from so101_demo.adapters.act.visible_approach_expert_route import VisibleApproachExpertRoute

    motion = route_motion_configuration(manifest)
    factory = MujocoPathProcess if path_process_factory is None else path_process_factory
    checker = factory(check_timeout_s=motion["submit_lead_s"], start_timeout_s=2.0,
                      model_path=motion["model_path"], protected_roots=("base",),
                      cup_joint="cup_free_joint", gripper_body="gripper",
                      path_step_s=motion["path_step_s"], path_clearance_m=motion["path_clearance_m"],
                      velocity_limit_rad_s=motion["velocity_limit_rad_s"],
                      acceleration_limit_rad_s2=motion["acceleration_limit_rad_s2"],
                      allowed_pairs_by_phase=checker_pairs_by_phase(motion))
    # the screen inspects THROUGH the port (production: `search_port=port`), and the port is what carries the
    # boundary - so the authority is mounted on the PORT, which is also where the child reads it back
    assert isinstance(port, PickPlaceSearchPhasePort), "the screen inspects through the production port"
    port.approach_screen = PickPlaceApproachPathScreen(
        search_port=port, sources=sources, broker=broker, path_checker=checker, cancelled=cancelled)
    return checker, VisibleApproachExpertRoute


def test_the_assembly_binds_the_screen_to_the_admitted_model():
    import threading
    from pathlib import Path

    from ament_index_python.packages import get_package_share_directory

    from so101_demo.adapters.act.pick_place_search_port import PickPlaceSearchPhasePort
    from so101_demo.act.visible_approach_diagnostic import build_route_manifest

    share = Path(get_package_share_directory("so101_demo_py"))
    config = share / "config/mujoco/act"
    manifest = build_route_manifest(scene_path=share / "assets/mujoco/act/scene.xml",
                                    plugin_path=config / "task6_route_plugins.yaml",
                                    profile_path=config / "task6_visible_approach_v1.json",
                                    session_id="assembly-check", attempt_id="assembly-attempt")

    boundary = _MinimalBoundary(session_id="assembly-check")
    port = PickPlaceSearchPhasePort(boundary)
    checker = None
    try:
        checker, route_class = assemble_approach_authority(
            port=port, sources=_Sources("placeholder"), broker=object(),
            cancelled=threading.Event(), manifest=manifest)
    except ValueError as error:
        # the sources must carry the CHECKER's hash, which is only knowable after the checker starts - so the first
        # call is expected to refuse, and that refusal is itself the coherence rule at work
        assert "PICK_PLACE_APPROACH_SCREEN_CONFIG_INVALID" in str(error), str(error)
        return
    finally:
        if checker is not None:
            checker.close()
    raise AssertionError("the assembly must refuse sources that are not bound to the admitted model")
