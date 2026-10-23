"""E2: the initial endpoint sample must come from after the reset and before the gripper dispatch."""

import json

import pytest


from so101_demo.act.pick_place_runner import PickPlaceRunner
from so101_demo.act.episode_audit.writer import EpisodeAuditWriter
from act_episode_audit_support import _lease, scope
from test_act_release_boundary import FakePort, request as boundary_request


def _sealed(tmp_path):
    """Run one episode through the fake port with a real audit, and return the rows it wrote."""

    # the audit's identity is built from the request the run will receive, so the two agree by construction
    # rather than by relaxing the identity check the audit performs
    tmp_path.mkdir(parents=True, exist_ok=True)   # as the audit suite's own writer helper does
    request = boundary_request()
    audit_scope = dict(scope(), mode="formal")
    identity = {"session_id": request["session_id"], "attempt_id": request["attempt_id"],
                "reset_epoch": 1, "release_epoch": 1, "scene_id": audit_scope["scene_id"],
                "seed": audit_scope["seed"], "mode": audit_scope["mode"]}
    lease = _lease(attempt_id=request["attempt_id"])
    audit = EpisodeAuditWriter(tmp_path / "formal", audit_scope, {**identity, "lease": lease},
                               {"inputs_sha256": "a" * 64})
    PickPlaceRunner(FakePort(), audit=audit).run(request)
    return audit


def test_the_first_cup_pose_precedes_the_gripper_dispatch(tmp_path):
    audit = _sealed(tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "formal" / "audit" / "physics.jsonl").read_text().splitlines()]
    events = [json.loads(line) for line in (tmp_path / "formal" / "audit" / "events.jsonl").read_text().splitlines()]
    pose_rows = [row for row in rows
                 if isinstance(row.get("observation"), dict)
                 and ("cup_position_world_m" in row["observation"] or "cup_position_m" in row["observation"])]
    close_rows = [row for row in rows if row.get("kind") == "pose" and row.get("sequence") is not None]
    close_event = [event for event in events
                   if event.get("kind") == "phase_complete" and event["payload"].get("phase") == "CLOSE"]
    print("BOUNDARY poses:", len(pose_rows), "| first pose task_sequence:",
          pose_rows[0]["task_sequence"] if pose_rows else None,
          "| CLOSE task_sequence:", close_event[0]["task_sequence"] if close_event else None)
    assert pose_rows, "the run wrote no cup pose at all"
    assert close_event, "the run recorded no CLOSE phase"
    # the design's initial sample means "after the reset and before the arm-gripper dispatch", which holds exactly
    # when the first pose row precedes the CLOSE phase in the single task-level order
    assert pose_rows[0]["task_sequence"] < close_event[0]["task_sequence"]


def test_an_expired_deadline_is_refused_before_any_phase(tmp_path):
    """E2's negative list: an expired attempt is refused, and the refusal is the deadline's own name."""

    from so101_demo.act.pick_place_runner import PickPlaceError

    runner = PickPlaceRunner(FakePort(), audit=None)
    with pytest.raises(PickPlaceError, match="PICK_PLACE_VALIDATION_DEADLINE_EXPIRED"):
        runner.run({**boundary_request(), "deadline_ns": 0})


def test_evidence_from_an_older_reset_is_refused(tmp_path):
    """E2's negative list: evidence that belongs to another reset epoch cannot stand in for this attempt's."""

    from so101_demo.act.pick_place_runner import PickPlaceError

    class StaleResetPort(FakePort):
        """Reports evidence stamped with the previous reset, which the runner's scope check must refuse."""

        def run_phase(self, phase, request):
            evidence = dict(super().run_phase(phase, request))
            evidence["reset_epoch"] = evidence["reset_epoch"] - 1
            return evidence

    with pytest.raises(PickPlaceError) as refusal:
        PickPlaceRunner(StaleResetPort(), audit=None).run(boundary_request())
    print("STALE", refusal.value)
    assert "PHASE_EVIDENCE_INVALID" in str(refusal.value)
