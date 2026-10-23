"""The coverage a formal seal requires of a Teacher episode, at the seal and at the readback.

The episode is written through the real `EpisodeAuditWriter` by `teacher_formal_audit`, which uses the real producers for every
record it can (Teacher event stream, normal-stop boundary, world sources, scene associations, Recorder queue). The decoupled
Recorder writes no `phase_complete`, `release` or physics rows, so the old nine-phase coverage could never be met; this is
the replacement (T1 lifecycle, T2 boundaries, T3 physics history, T4 scene and controller records, T5 release, T6 reference).
"""

from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from teacher_formal_audit import ALIGNMENT_OPERATIONS, BOUNDARY_STAGES, STATES, TeacherEpisode
from test_act_scene_association import frozen_scene  # noqa: F401  (fixture)


def seal(root, frozen_scene, **faults):
    """Write one Teacher-shaped formal episode and seal it; returns the audit manifest path."""

    writer, window = TeacherEpisode(frozen_scene, **faults).write(root)
    try:
        return writer.seal(window)
    finally:
        for stream in writer._streams.values():
            stream.close()


def test_a_teacher_episode_seals_formal_and_reads_back(tmp_path, frozen_scene):
    from so101_demo.act.episode_audit.formal_coverage import formal_coverage_ok
    from so101_demo.act.episode_audit.verification import verify_audit_manifest

    path = seal(tmp_path / "ok", frozen_scene)
    manifest = verify_audit_manifest(path)
    assert manifest["identity"]["mode"] == "formal" and formal_coverage_ok(path.parent)
    assert (path.parent / "physics.jsonl").read_bytes() == b"", "a Teacher episode retains no old-runner physics rows"
    kinds = {json.loads(line)["kind"] for line in (path.parent / "events.jsonl").read_text().splitlines()}
    assert not kinds & {"phase_complete", "release"}


#: one fault per clause, each of which the writer itself admits (the stream is well formed record by record) and only the
#: coverage rejects
CLAUSE_FAULTS = {
    "t1_no_reset_complete": dict(omit_events={"reset_complete"}),
    "t1_no_start_observation": dict(omit_events={"teacher_start_observation"}),
    "t1_no_normal_stop": dict(omit_events={"normal_stop"}),
    "t1_no_end_observation": dict(omit_events={"teacher_end_observation"}),
    "t1_no_terminal": dict(omit_events={"terminal"}),
    "t1_a_state_never_ran": dict(states=tuple(state for state in STATES if state != "LIFT")),
    "t1_states_out_of_order": dict(states=(*STATES[:3], STATES[4], STATES[3], *STATES[5:])),
    "t1_completed_with_a_failed_finish": dict(final_status="FAILED"),
    "t1_no_phase_at_all": dict(states=()),
    "t1_summary_missing": dict(omit_summary=True),
    "t1_summary_does_not_account_for_the_events": dict(summary_gap=True),
    "t2_no_verified_reset": dict(omit_boundaries={"verified_reset"}),
    "t2_no_capture_start": dict(omit_boundaries={"capture_start"}),
    "t2_no_initial_capture": dict(omit_boundaries={"initial_capture"}),
    "t2_no_normal_stop_boundary": dict(omit_boundaries={"normal_stop"}),
    "t2_no_final_capture": dict(omit_boundaries={"final_capture"}),
    "t3_history_starts_after_the_first_command": dict(raw_first_step=60),
    "t3_history_ends_before_the_stop": dict(raw_last_step=100),
    "t3_no_native_chunk_at_all": dict(raw_first_step=131),
    "t3_no_recorder_queue": dict(queue="none"),
    "t3_two_recorder_queues": dict(queue="twice"),
    "t3_queue_account_differs_from_the_bound_rows": dict(queue="many"),
    "t4_no_initial_alignment": dict(omit_alignments={"initial"}),
    "t4_no_world_sync": dict(omit_alignments={"world_sync"}),
    "t4_world_sync_after_the_first_command": dict(alignment_steps={"world_sync": 60}),
    "t4_no_attach": dict(omit_alignments={"attach"}),
    "t4_attach_outside_attach_moveit": dict(alignment_steps={"attach": 100}),
    "t4_no_detach": dict(omit_alignments={"detach", "detach_sync"}),
    "t4_detach_before_its_phase": dict(omit_alignments={"detach_sync"}, alignment_steps={"detach": 70}),
    "t4_no_controller_reference": dict(omit_continuity=True),
    "t5_detach_only_after_the_gripper_opened": dict(omit_alignments={"detach"}),
    "t5_detach_applied_after_open_gripper": dict(omit_alignments={"detach_sync"}, alignment_steps={"detach": 96}),
    # the sample is inside the window but the apply request was sent before it / after the gripper opened
    "t4_attach_requested_before_attach_moveit": dict(apply_steps={"attach": 70}),
    "t5_detach_requested_after_open_gripper": dict(omit_alignments={"detach_sync"}, apply_steps={"detach": 96}),
    "t6_no_complete_raw_reference": dict(reference="projected"),
}


@pytest.mark.parametrize("name", sorted(CLAUSE_FAULTS))
def test_each_clause_failure_refuses_the_formal_seal(tmp_path, frozen_scene, name):
    from so101_demo.act.episode_audit.formal_coverage import formal_coverage_failure

    with pytest.raises(ValueError, match="AUDIT_FORMAL_COVERAGE_INCOMPLETE"):
        seal(tmp_path / name, frozen_scene, **CLAUSE_FAULTS[name])
    # the refusal is the named clause's, not an accident of another one
    assert formal_coverage_failure(tmp_path / name / "audit") == name[:2].upper()


def test_the_phase_windows_judge_the_apply_request_not_the_frozen_sample(tmp_path, frozen_scene):
    """The real shape: the attach geometry was frozen from the grasp check's sample, before ATTACH_MOVEIT began (step 78 <
    79), and the apply request was sent inside it (step 80). The detach likewise is frozen early and applied inside."""

    from so101_demo.act.episode_audit.formal_coverage import formal_coverage_failure

    path = seal(tmp_path / "real", frozen_scene, alignment_steps={"attach": 78, "detach": 88},
                apply_steps={"attach": 80, "detach": 92})
    assert formal_coverage_failure(path.parent) is None
    rows = [json.loads(line) for line in (path.parent / "events.jsonl").read_text().splitlines()]
    attach = next(row for row in rows if row["kind"] == "source_alignment"
                  and row["payload"]["association"]["operation"] == "attach")
    assert attach["sim_time_s"] < 0.158 < attach["payload"]["association"]["apply"]["record"]["request_ros_clock"]["sim_time_ns"] / 1e9


@pytest.mark.parametrize("operation,expected", [("attach", "T4"), ("detach", "T4")])
def test_a_row_without_the_apply_request_clock_does_not_cover(tmp_path, frozen_scene, operation, expected):
    """Fail closed: no fallback to the sample time. Every row of the operation loses its request clock."""

    from so101_demo.act.episode_audit.formal_coverage import formal_coverage_failure

    path = seal(tmp_path / "ok", frozen_scene)
    assert formal_coverage_failure(path.parent) is None

    def rewrite(rows):
        count = 0
        for row in rows:
            if row["kind"] == "source_alignment" and row["payload"]["association"]["operation"] == operation:
                row["payload"]["association"]["apply"]["record"]["request_ros_clock"] = None
                count += 1
        assert count
        return rows

    resigned = _resigned_copy(path, tmp_path, rewrite)
    assert formal_coverage_failure(resigned.parent) == expected


def test_the_fault_catalogue_names_every_boundary_and_alignment():
    assert {stage for stage in BOUNDARY_STAGES} == {"verified_reset", "capture_start", "initial_capture", "normal_stop",
                                                    "final_capture"}
    assert "detach_sync" in ALIGNMENT_OPERATIONS


def _resigned_copy(path, tmp_path, rewrite):
    """A copy of a sealed audit whose events were rewritten and whose manifest was re-signed, so only the semantics can catch it."""

    copied = tmp_path / "resigned"
    shutil.copytree(path.parent, copied)
    rows = [json.loads(line) for line in (copied / "events.jsonl").read_text().splitlines()]
    rows = rewrite(rows)
    payload = b"".join(json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n" for row in rows)
    (copied / "events.jsonl").write_bytes(payload)
    manifest = json.loads((copied / "audit-manifest.json").read_bytes())
    manifest["files"]["events.jsonl"].update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    (copied / "audit-manifest.json").write_bytes(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
    return copied / "audit-manifest.json"


def _without(kind, **match):
    def rewrite(rows):
        kept = [row for row in rows if not (row["kind"] == kind and all(
            row["payload"].get("teacher_event", {}).get(key) == value for key, value in match.items()))]
        assert len(kept) == len(rows) - 1
        for number, row in enumerate(kept, start=1):
            row["sequence"] = number
        return kept
    return rewrite


@pytest.mark.parametrize("kind,match", [("controller_reference", {}), ("teacher_event", {"type": "teacher_end_observation"}),
                                        ("teacher_event", {"type": "normal_stop"})])
def test_the_readback_refuses_a_resigned_audit_with_one_event_removed(tmp_path, frozen_scene, kind, match):
    from so101_demo.act.episode_audit.verification import verify_audit_manifest

    path = seal(tmp_path / "ok", frozen_scene)
    assert verify_audit_manifest(path)["identity"]["mode"] == "formal"
    tampered = _resigned_copy(path, tmp_path, _without(kind, **match))
    with pytest.raises(ValueError, match="AUDIT_FORMAL_COVERAGE_INCOMPLETE"):
        verify_audit_manifest(tampered)


def test_a_teacher_that_failed_still_seals_formal_and_reads_back(tmp_path, frozen_scene):
    from so101_demo.act.episode_audit.verification import verify_audit_manifest

    path = seal(tmp_path / "failed", frozen_scene, **FAILED_TEACHER)
    assert verify_audit_manifest(path)["identity"]["mode"] == "formal"
    terminal = [json.loads(line)["payload"]["teacher_event"]["payload"]
                for line in (path.parent / "events.jsonl").read_text().splitlines()
                if json.loads(line)["payload"].get("teacher_event", {}).get("type") == "terminal"]
    assert terminal[0]["teacher_execution_status"] == "FAILED"


FAILED_TEACHER = dict(states=STATES[:5], final_status="FAILED", terminal="FAILED",
                      omit_alignments={"attach", "detach", "detach_sync"})


@pytest.mark.parametrize("name,faults", [
    ("no_start_observation", dict(omit_events={"teacher_start_observation"})),
    ("no_boundary", dict(omit_boundaries={"final_capture"})),
    ("no_queue", dict(queue="none")),
    ("no_world_sync", dict(omit_alignments={"attach", "detach", "detach_sync", "world_sync"})),
    ("no_reference", dict(reference="projected")),
])
def test_a_failed_teacher_is_held_to_the_structure_every_episode_has(tmp_path, frozen_scene, name, faults):
    with pytest.raises(ValueError, match="AUDIT_FORMAL_COVERAGE_INCOMPLETE"):
        seal(tmp_path / name, frozen_scene, **{**FAILED_TEACHER, **faults})


def test_a_teacher_failed_episode_is_never_exportable():
    """It may seal; no gate lets it out. The result store refuses eligibility and the export gate refuses the result."""

    from so101_demo.act.bundle import _export_gates
    from so101_demo.act.result_store import export_eligible

    assert export_eligible("PASSED", "PASS", "formal") is True
    for status in ("FAILED", "INVALID", "INDETERMINATE"):
        assert export_eligible(status, "PASS", "formal") is False
    proof = {"status": "PASS", "result_schema_version": 3, "result_status": "FAILED", "act_data_qc": "PASS",
             "export_eligible": False}
    with pytest.raises(ValueError, match="EXPORT_EPISODE_NOT_PASSED"):
        _export_gates({"mode": "formal"}, proof, {})
    with pytest.raises(ValueError, match="EXPORT_EPISODE_DATA_QC_NOT_PASSED"):
        _export_gates({"mode": "formal"}, dict(proof, result_status="PASSED", act_data_qc="FAIL"), {})


def test_an_old_runner_shaped_stream_no_longer_seals_formal_by_itself(tmp_path):
    """Nine `phase_complete` rows, a `release` event, an accepted reference and the four physics kinds were the old coverage;
    without the Teacher's facts they are nothing."""

    from act_episode_audit_support import ZERO, _formal_writer, _lease, _window, identity
    from so101_demo.act.acquisition import AcquisitionMinter
    from so101_demo.act.joints import ARM_JOINTS

    writer = _formal_writer(tmp_path / "formal")
    minter = AcquisitionMinter()
    frames = {}
    for camera in ("head", "wrist"):
        for stamp in (1.0, 1.1, 1.2):
            frame = minter.mint(camera, session_id="s", reset_epoch=1, stamp_s=stamp,
                                received_monotonic_ns=int(stamp * 1e9) + 1, pixels=ZERO)
            writer.append_acquisition(frame)
            frames[(camera, stamp)] = frame
    writer.append_source("references", {
        "reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE", "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
        "accepted": True, "joint_names": list(ARM_JOINTS), "sim_stamp_ns": 1_100_000_000,
        "received_monotonic_ns": 1_100_000_001, "velocities": [0.0] * 6})
    for kind in ("support", "contact", "pose", "retract"):
        writer.append_source("physics", {"kind": kind, "sim_time_s": 1.1, "release_epoch": 1, "observation": {
            "simulation_time_s": 1.1, "simulation_step": 1, "cup_position_world_m": [0.0, 0.0, 0.0],
            **({"supported": True, "table_contact": True} if kind == "support" else {}),
            **({"left_contact_count": 0, "right_contact_count": 0, "table_contact": True} if kind == "contact" else {})}})
    old_phases = ("SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN", "RELEASE", "RADIAL_RETREAT", "FINAL_CHECK")
    for kind, payload in [*[("phase_complete", {"phase": phase, "physics_step": 1}) for phase in old_phases],
                          ("release", {"release_epoch": 1, "supported": True, "no_fingertip_contact": True})]:
        writer.append_source("events", {"kind": kind, "identity": {**identity(), "lease": _lease()}, "sim_time_s": 1.1,
                                        "monotonic_ns": 1, "payload": payload})
    writer.bind_row(0, 1.0, frames[("head", 1.0)].acquisition_id, frames[("wrist", 1.0)].acquisition_id, 1)
    with pytest.raises(ValueError, match="AUDIT_FORMAL_COVERAGE_INCOMPLETE"):
        writer.seal({**_window(), "first_command_s": 1.1, "physics_end_s": 1.1})


def test_the_audit_names_the_teacher_s_states():
    """The audit's declared states are the registered Teacher success trace without its IDLE and DONE bookends."""

    from so101_demo.application.e2e_acceptance import SUCCESS_STATE_TRACE
    from so101_demo.act.episode_audit.formal_coverage import TEACHER_STATES

    assert tuple(TEACHER_STATES) == tuple(SUCCESS_STATE_TRACE[1:-1]) == tuple(STATES)


def test_the_old_nine_phase_coverage_is_gone():
    from so101_demo.act.episode_audit import checks

    assert not hasattr(checks, "FORMAL_PHASES") and not hasattr(checks, "_formal_coverage_ok")


def test_a_stalled_host_does_not_move_the_stamps_of_a_written_episode(tmp_path, frozen_scene, monkeypatch):
    """The 100 ms bound between a source receipt and its request is the verifier's, not the host's: a stall of the writing
    process (a GC pause, load) between two readings of the episode's clock must not change what the episode proves."""

    import time
    import teacher_formal_audit
    from so101_demo.act.episode_audit.verification import verify_audit_manifest

    reading = teacher_formal_audit._TickClock.monotonic_ns
    readings = []

    def stalled(self):
        readings.append(1)
        if len(readings) % 5 == 0:
            time.sleep(0.12)
        return reading(self)

    monkeypatch.setattr(teacher_formal_audit._TickClock, "monotonic_ns", stalled)
    path = seal(tmp_path / "stalled", frozen_scene)
    assert len(readings) > 50
    assert verify_audit_manifest(path)["identity"]["mode"] == "formal"
