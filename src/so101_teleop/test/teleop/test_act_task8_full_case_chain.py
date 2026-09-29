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


def _mount_approach_screen(port, authority) -> None:
    """Mount the screen on the port, with sources bound to the checker's model - the two-phase rule."""

    import threading

    from so101_demo.adapters.act.pick_place_approach_path_screen import PickPlaceApproachPathScreen

    boundary = port.boundary
    boundary.contact_pairs = SimpleNamespace(model_sha256=authority["checker"].model_sha256)
    if not callable(getattr(boundary, "capture", None)):
        # the screen reads fresh measurements through `sources.capture`, which the PRODUCTION boundary provides; this
        # harness's boundary is the ROS/MuJoCo/controller surface, so the capture it offers is the one it already has
        boundary.capture = lambda *args, **kwargs: {"rows": list(getattr(boundary, "rows", []))}
    port.approach_screen = PickPlaceApproachPathScreen(
        search_port=port, sources=boundary, broker=boundary, path_checker=authority["checker"],
        cancelled=threading.Event())


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
    child, phase_request, port = _prepare_child_case(
        evidence, monkeypatch, case_id="full-01", session_id="session-298",
        attempt_id="full-01", campaign_id="case-298",
        expert_route_factory=authority["factory"], route_motion=authority["motion"])
    _mount_approach_screen(port, authority)

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
