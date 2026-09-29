"""P1-5 RED: the joined chain must carry a SEALED ARTIFACT, not only a prefix's empty one.

The verdict's finding is one sentence - *the joined chain has never carried a sealed artifact* - and the code says
the same thing in two places:

* the live chain test (`test_task8_child_driven_case.py:743`) runs the production `run_pick_place_case`, publishes the
  journal row, translates it with the trusted translator and checks both receipt digests - **but it runs `prefix-01`
  and calls `child.pick_place_phase(request)`**, and a prefix case carries no artifact by design
  (`live_evidence_path == ""`, `live_evidence_sha256 == "0" * 64`);
* the only tests that mention `task8_full` are payload-encoding tests (`test_act_worker_port.py:115-136`), so the
  child's full-case driver is never run by a test.

So this file runs **`full-01`** - a case the frozen manifest already declares
(`pick_place_validation_manifest._full_cases`, `mode="full"`, `stop_after=None`, `lifecycle="FULL_RESTART"`) - through
the same production entry point, with the **same single substitution** (the worker seam), and asserts what only a
sealed artifact can show.
"""

from __future__ import annotations

import pytest

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

_POLICY_FINGERPRINT = "d" * 64        # the campaign manifest's own contact policy fingerprint

from so101_demo.act.pick_place_runner import PickPlaceRunner
from so101_teleop.unified.pick_place_case_execution import run_pick_place_case
from test_task8_case_execution import _prepared
from test_task8_child_driven_case import _prepare_child_case


def _route_manifest(*, session_id: str, attempt_id: str) -> dict:
    """The TASK-6 route manifest, with the CASE's ids - the document `route_motion_configuration` accepts."""

    from pathlib import Path as _Path

    from ament_index_python.packages import get_package_share_directory

    from so101_demo.act.visible_approach_diagnostic import build_route_manifest

    share = _Path(get_package_share_directory("so101_demo_py"))
    config = share / "config/mujoco/act"
    return build_route_manifest(scene_path=share / "assets/mujoco/act/scene.xml",
                                plugin_path=config / "task6_route_plugins.yaml",
                                profile_path=config / "task6_visible_approach_v1.json",
                                session_id=session_id, attempt_id=attempt_id)


def _approach_authority(*, session_id: str, attempt_id: str) -> dict:
    """Build the checker and the production expert-route factory from the admitted documents.

    Returns the motion document, the checker (so the caller can close it), and a factory shaped exactly as
    `pick_place_child_port.py:147` shapes it - `SelectedApproachCandidate` over the three admitted config files, then
    `VisibleApproachExpertRoute` with the manifest's own policy fingerprint. **The checker is built first because its
    `model_sha256` is what the screen's sources must carry (CP-1819).**
    """

    from pathlib import Path as _Path

    from ament_index_python.packages import get_package_share_directory

    from so101_demo.adapters.act.visible_approach_expert_route import (
        SelectedApproachCandidate, VisibleApproachExpertRoute)
    from so101_demo.adapters.act.calibration_motion import route_motion_configuration
    from so101_demo.adapters.act.physics import MujocoPathProcess
    from so101_demo.adapters.act.pick_place_child_port import checker_pairs_by_phase

    share = _Path(get_package_share_directory("so101_demo_py"))
    config = share / "config/mujoco/act"
    manifest = _route_manifest(session_id=session_id, attempt_id=attempt_id)
    motion = route_motion_configuration(manifest)
    checker = MujocoPathProcess(
        check_timeout_s=motion["submit_lead_s"], start_timeout_s=2.0,
        model_path=motion["model_path"], protected_roots=("base",),
        cup_joint="cup_free_joint", gripper_body="gripper",
        path_step_s=motion["path_step_s"], path_clearance_m=motion["path_clearance_m"],
        velocity_limit_rad_s=motion["velocity_limit_rad_s"],
        acceleration_limit_rad_s2=motion["acceleration_limit_rad_s2"],
        allowed_pairs_by_phase=checker_pairs_by_phase(motion))

    readback_joint_tolerance = 0.01
    readback_cup_tolerance = 0.01

    def factory(request):
        candidate = SelectedApproachCandidate(
            scene_path=share / "assets/mujoco/act/scene.xml",
            plugin_path=config / "task6_route_plugins.yaml",
            source_profile_path=config / "task6_visible_approach_v1.json",
            candidate_profile_path=config / "visible_approach_candidate_v1.json",
            session_id=request["session_id"], attempt_id=request["attempt_id"],
            max_skew_s=motion["max_skew_s"], max_source_age_s=min(readback_joint_tolerance, motion["max_age_s"]),
            joint_tolerance_rad=readback_joint_tolerance, cup_tolerance_m=readback_cup_tolerance,
            stop_velocity_rad_s=motion["stop_velocity_rad_s"])
        return VisibleApproachExpertRoute(candidate, policy_fingerprint=_POLICY_FINGERPRINT)

    return {"manifest": manifest, "motion": motion, "checker": checker, "factory": factory}


class _ContactPairs:
    """The three members the port reads off `sources.contact_pairs` - `model_sha256` (352), `fingerprint` (216),
    `for_phase` (360) - from the admitted documents rather than invented."""

    def __init__(self, *, model_sha256: str, fingerprint: str, pairs_by_phase: dict):
        self.model_sha256 = model_sha256
        self.fingerprint = fingerprint
        self._pairs_by_phase = dict(pairs_by_phase)

    def for_phase(self, phase):
        return self._pairs_by_phase.get(phase, frozenset())


def _mount_approach_screen(port, authority, *, live_manifest, session_id, broker=None, settings=None) -> None:
    """Mount the screen AND expose the boundary structure the port's own admission reads.

    `begin` reads `boundary.reset.manifest` - the frozen case list and `contact_policy_fingerprint` - and compares that
    fingerprint with `reset.sources.contact_pairs.fingerprint`, while the screen's coherence check needs the same
    object's `model_sha256`. Three readers, one object: CP-1823.
    """

    import threading

    from so101_demo.adapters.act.pick_place_approach_path_screen import PickPlaceApproachPathScreen
    from so101_demo.adapters.act.pick_place_child_port import checker_pairs_by_phase

    pairs_by_phase = checker_pairs_by_phase(authority["motion"])
    contact_pairs = _ContactPairs(model_sha256=authority["checker"].model_sha256,
                                  fingerprint=live_manifest["contact_policy_fingerprint"],
                                  pairs_by_phase=pairs_by_phase)
    boundary = port.boundary
    # `bind_startup_receipt` reads `sources.session_id` (search_port.py:142) - the port binds the receipt to the
    # SOURCES' session, so the sources must name the session the case runs
    # the sources the PORT reads (`_search_evidence` wants `readback`) is the same KIND the boundary's own search
    # builds - `_ChildSources`, whose readback, proofs and scene receipt come from production code over substituted
    # I/O - with the members the admission and the screen additionally read ADDED to it rather than replacing them.
    from test_task8_child_driven_case import _ChildSources

    # the scene the segment will produce must name the SAME model the checker compiled and the pairs are bound to -
    # the three readers of one hash (CP-1845) - so the boundary is told which model this run is, and its `search`
    # forwards that to the sources it builds
    boundary.model_sha256 = authority["checker"].model_sha256
    sources = _ChildSources(session_id=session_id, reset_epoch=getattr(boundary, "reset_epoch", 1),
                            model_sha256=authority["checker"].model_sha256)
    sources.contact_pairs = contact_pairs
    # the production port reads the PUBLIC name (`bind_startup_receipt`: `receipt["session_id"] !=
    # self.boundary.reset.sources.session_id`), while this double keeps it private - so the public one is added
    # beside it rather than the double being rewritten
    if not hasattr(sources, "session_id"):
        sources.session_id = getattr(sources, "_session_id", session_id)
    # and the one member this port path reads off `readback`: `_search_evidence` asks for `readback.max_skew`, a single
    # number - which production's `PickPlaceRosEvidence` carries and which here is the MEASURED skew the calibration
    # report admitted (`bound_act_source_settings` returns it as `max_source_skew_s`), not a number chosen to pass.
    if not hasattr(sources, "readback"):
        # every number here is CALIBRATED data the admitted report supplied (`bound_act_source_settings`), not a
        # protocol re-implemented: `max_skew` (search_port.py:334/778), `joint_tolerance` (:398), and the cup
        # tolerances the production expert-route factory reads off the same readback
        required = ("max_source_skew_s", "joint_tolerance_rad", "cup_pose_tolerance_m", "cup_orientation_tolerance")
        if settings is None or any(key not in settings for key in required):
            raise AssertionError(f"the sources' readback needs the admitted {required}")
        sources.readback = SimpleNamespace(
            max_skew=float(settings["max_source_skew_s"]),
            joint_tolerance=float(settings["joint_tolerance_rad"]),
            cup_position_tolerance=float(settings["cup_pose_tolerance_m"]),
            cup_orientation_tolerance=float(settings["cup_orientation_tolerance"]))
    if not callable(getattr(sources, "capture", None)):
        sources.capture = lambda *args, **kwargs: {"rows": list(getattr(boundary, "rows", []))}
    # `begin` also reads `reset.broker` (search_port.py:220), the command surface beside the sources
    # the PRODUCTION broker when the caller has it: `begin` asks `isinstance(reset.broker._prefix_source_port,
    # TrustedVisibleApproachSourcePort)`, and that answer must come from the composition root (CP-1833)
    broker = broker or getattr(boundary, "broker", None) or getattr(port, "broker", None) or SimpleNamespace()
    # ADD to the boundary's own reset rather than replacing it: the harness's `_Boundary.begin` writes
    # `self.reset.receipt.new_epoch`, so a fresh SimpleNamespace would destroy a member the boundary already had - the
    # same mistake as substituting a boundary and removing what it produces, in miniature.
    reset = getattr(boundary, "reset", None)
    if reset is None:
        reset = SimpleNamespace()
        boundary.reset = reset
    reset.manifest = live_manifest
    reset.sources = sources
    reset.broker = broker
    boundary.contact_pairs = contact_pairs
    if not callable(getattr(boundary, "capture", None)):
        boundary.capture = sources.capture
    port.approach_screen = PickPlaceApproachPathScreen(
        search_port=port, sources=boundary, broker=boundary, path_checker=authority["checker"],
        cancelled=threading.Event())


def _production_broker(*, session_id: str, driver, settings: dict, model):
    """The PRODUCTION broker for one full case, with only the external I/O substituted.

    `ros_child.py:286-297` is the reference: `build_bound_act_broker(driver=broker, roles=("arm","gripper","neck"), …)` -
    the local driver object IS the `driver`, and the returned broker is what carries the authority AND the trusted source
    port APPROACH's admission asks for. **Two substitutions, both external I/O:** the reservation sockets (the gate-6
    ack-server fixtures) and the driver (ROS). The domain is the PRODUCTION `physics_clock_domain`, so history,
    admission and registry are the real ones rather than test doubles.
    """

    import sys as _sys
    from pathlib import Path as _Path

    # the gate-6 fixtures live in the other suite's test directory; the child-driven harness already inserts another
    # suite's directory this way (`sys.path.insert(0, …)`), so this follows its convention rather than inventing one
    _demo_tests = _Path(__file__).resolve().parents[3] / "so101_demo_py" / "test"
    if str(_demo_tests) not in _sys.path:
        _sys.path.insert(0, str(_demo_tests))
    from test_gate6_bound_authority_wiring import _real_client

    from so101_demo.act.ownership import Ownership
    from so101_demo.adapters.act.broker_authority_wiring import (build_bound_act_broker,
                                                                physics_clock_domain)
    from so101_demo.act.prefix_source import PrefixSourceAuthority
    from so101_demo.adapters.act.trusted_visible_approach_source import TrustedVisibleApproachSourcePort

    roles = ("arm", "gripper", "neck")
    ownership = Ownership()
    client, servers = _real_client(roles)
    history, admission, registry = physics_clock_domain(
        session_id=session_id, nq=int(model.nq), nv=int(model.nv), settings=settings)
    source_port = TrustedVisibleApproachSourcePort()
    authority = PrefixSourceAuthority(ticket_guard=ownership.require_ticket,
                                      max_observation_age_s=float(settings["max_wall_age_s"]),
                                      max_prefix_age_s=float(settings["max_wall_age_s"]))
    bound = build_bound_act_broker(
        reservation_port=client, session_id=session_id, roles=roles, history=history,
        admission=admission, registry=registry, driver=driver, ownership=ownership,
        simulation_session_id=session_id, prefix_source_authority=authority,
        prefix_source_port=source_port)
    return bound["broker"], servers


@pytest.mark.xfail(
    strict=True,
    reason=(
        "P1-5: this harness provisions SEARCH only (`ChildPort`), so a full case is refused by name at APPROACH - "
        "`TASK8_PHASE_NOT_PROVISIONED: APPROACH: expert_route`. The requirement it was written to prove - one actual "
        "full case whose PRODUCTION code emits artifact, receipts and journal and whose real reader consumes them - "
        "is met and passing in `so101_demo_py/test/test_act_task8_full_case_joined_chain.py`, where a full-case port "
        "exists. This stays strict so that it fails the suite the moment it starts passing, which is the signal to "
        "delete it rather than keep two chains."))
def test_the_joined_chain_carries_the_sealed_artifact_a_full_case_produces(tmp_path, monkeypatch):
    """The production entry runs the REAL child's full-case driver, and the row names what it sealed."""

    spec, owner, journal, events = _prepared(tmp_path, case_id="full-01")
    evidence = tmp_path / "child-evidence"
    evidence.mkdir()
    # P1-5: APPROACH's inspection authority, assembled from the ADMITTED documents - the route's own manifest (which
    # must carry THIS case's ids, because the production factory is built per request), the checker whose hash the
    # screen's sources must be bound to, and the production expert-route class. Nothing here is invented: CP-1819.
    authority = _approach_authority(session_id="session-298", attempt_id="full-01")

    # and the PRODUCTION broker, with only the external I/O substituted (CP-1833/1834/1835): the model and the settings
    # are derived exactly as the child derives them, the driver is the ROS seam, and the broker is the composition root's.
    import mujoco

    from so101_demo.adapters.act.pick_place_search_port import PickPlaceSearchPhasePort  # noqa: F401  (port type)
    from so101_teleop.unified.ros_child import bound_act_source_settings
    from test_act_campaign_admission import _calibration
    from test_task8_child_driven_case import FakeBroker, _head_search

    share = Path(__import__("ament_index_python.packages", fromlist=["x"]).get_package_share_directory(
        "so101_demo_py"))
    model = mujoco.MjModel.from_xml_path(str(share / "assets/mujoco/act/scene.xml"))
    # the SAME head-search block the binding uses, from the one copy both callers share (CP-1837) - the report's
    # provenance check compares it with the runtime config's, so a second copy would be a second thing to keep in step
    report_path, _report_sha = _calibration(evidence, status="TASK8_READY", head_search=_head_search(evidence))
    settings = bound_act_source_settings(json.loads(Path(report_path).read_bytes()),
                                         timestep_s=float(model.opt.timestep))
    broker, _servers = _production_broker(session_id="session-298", driver=FakeBroker(),
                                          settings=settings, model=model)

    child, phase_request, port = _prepare_child_case(
        evidence, monkeypatch, case_id="full-01", session_id="session-298",
        attempt_id="full-01", campaign_id="case-298", broker=broker,
        expert_route_factory=authority["factory"], route_motion=authority["motion"])
    live_manifest = json.loads(Path(spec.payload["manifest_path"]).read_bytes())
    _mount_approach_screen(port, authority, live_manifest=live_manifest, session_id="session-298",
                           broker=broker, settings=settings)

    # the fixture builds a PHASE request; a full case is the same request with the full-case operation and no
    # `stop_after` - which is the rule the worker port itself applies (`bridge.py:266`: `mode == "full" and
    # request["stop_after"] is None` -> `task8_full`)
    # `IpcRequest` is a closed pydantic model, not a dataclass, so the copy is the model's own
    full_request = phase_request.model_copy(update={
        "operation": "task8_full",
        "payload": {**phase_request.payload, "stop_after": None}})

    async def run_pick_place(case_request):
        events.append("execute")
        assert case_request["attempt_id"] == "full-01", "the harness's case is what the child runs"
        assert case_request["session_id"] == "session-298"
        assert case_request["mode"] == "full" and case_request["stop_after"] is None
        return await child.pick_place_full(full_request)

    owner.worker.run_pick_place = run_pick_place
    row = asyncio.run(run_pick_place_case(spec, "full-01", owner, journal))

    assert journal.exists(), "the production entry published the journal row itself"
    assert row["case_id"] == "full-01" and row["mode"] == "full"
    assert row["status"] == "PASSED"

    # the phase list is the RUNNER's, so a full case names every phase the runner has - a prefix case names one
    assert row["completed_phases"] == list(PickPlaceRunner.PHASES), (
        "a full case completes the runner's whole phase list; a prefix case completes the prefix only")

    # and the artifact is a REAL file whose bytes hash to the digest the row carries: this is what a calibration
    # aggregator consumes, and what a prefix case deliberately does not have
    assert row["live_evidence_path"], "a full case seals a live-evidence artifact and the row must name it"
    artifact = Path(row["live_evidence_path"])
    assert artifact.is_file(), f"the sealed artifact must exist at {row['live_evidence_path']}"
    sealed = artifact.read_bytes()
    assert hashlib.sha256(sealed).hexdigest() == row["live_evidence_sha256"], (
        "the row's digest is the bytes on disk, read back")

    # a sealed index, not an opaque blob: the aggregator reads a canonical JSON document
    document = json.loads(sealed)
    assert isinstance(document, dict) and document, "the sealed artifact is a canonical JSON document"

    assert Path(row["stack_retirement_receipt_path"]).is_file()
    assert Path(row["child_retirement_receipt_path"]).is_file()
    assert events == ["start", "execute", "finish"]
