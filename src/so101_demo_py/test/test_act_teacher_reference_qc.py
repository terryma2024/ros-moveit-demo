"""Data QC cross-checks the recording against the Teacher's teacher_endpoint_v2 start and end references.

This is data integrity, not task success: the Teacher's PASS/FAIL never enters it (design D2, "Old QC path").
"""

import copy

import pytest

from so101_demo.act import episode_qc

IDENTITY = {"session_id": "session-1", "reset_epoch": 3}
WINDOW = {"collection_start_s": 1.0, "collection_end_s": 9.0, "first_command_s": 1.5, "physics_end_s": 8.8,
          "outcome": "complete"}


def sample(step, *, session="session-1", epoch=3):
    return {"physics_step": step, "simulation_session_id": session, "reset_epoch": epoch,
            "simulation_time_s": step * 0.001}


STEPS = [sample(step) for step in range(1000, 9001)]


def observation(step, *, session="session-1", epoch=3, time_s=None):
    return {"position": [0.0, 0.0, 0.1], "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            "simulation_time_s": step * 0.001 if time_s is None else time_s, "frame_id": "world",
            "object_id": "plastic_cup", "session_id": session, "reset_epoch": epoch,
            "publisher_sequence": step, "simulation_step": step}


def manifest(*, task="PASS", start=None, end=None):
    start = observation(1200) if start is None else start
    end = observation(8500) if end is None else end
    return {"schema": "so101-dynamic-mujoco-execute-v2", "teacher_execution_status": "COMPLETED",
            "teacher_task_result": {"result": task, "start_observation": start, "end_observation": end},
            "teacher_start_observation": start, "teacher_end_observation": end}


def check(document, *, steps=STEPS, window=WINDOW):
    return episode_qc.verify_teacher_references(document, identity=IDENTITY, window=window, physics_steps=steps)


def test_consistent_references_pass_and_are_recorded():
    result = check(manifest())
    assert result["status"] == "PASS" and result["reason"] == ""
    assert result["details"]["start_reference"]["simulation_step"] == 1200
    assert result["details"]["end_reference"]["simulation_step"] == 8500
    assert result["details"]["recorded_physics"] == {"first_step": 1000, "last_step": 9000}


@pytest.mark.parametrize("task", ["PASS", "FAIL", "UNCONFIRMED"])
def test_the_teacher_task_result_never_changes_the_data_verdict(task):
    # A Teacher FAIL with consistent, valid data is data QC PASS: export is gated elsewhere, by the Teacher result.
    assert check(manifest(task=task))["status"] == "PASS"


@pytest.mark.parametrize("fault,code", [
    ("no_manifest", "TEACHER_REFERENCE_MANIFEST_MISSING"),
    ("wrong_schema", "TEACHER_REFERENCE_MANIFEST_MISSING"),
    ("no_start", "TEACHER_REFERENCE_START_MISSING"),
    ("no_end", "TEACHER_REFERENCE_END_MISSING"),
    ("malformed_start", "TEACHER_REFERENCE_START_MISSING"),
    ("start_session", "TEACHER_REFERENCE_SESSION_MISMATCH"),
    ("end_epoch", "TEACHER_REFERENCE_SESSION_MISMATCH"),
    ("start_before_window", "TEACHER_REFERENCE_START_NOT_IN_WINDOW"),
    ("start_after_first_command", "TEACHER_REFERENCE_START_NOT_IN_WINDOW"),
    ("end_after_recording", "TEACHER_REFERENCE_END_AFTER_RECORDING"),
    ("order", "TEACHER_REFERENCE_ORDER_INVALID"),
    ("step_absent", "TEACHER_REFERENCE_PHYSICS_STEP_ABSENT"),
    ("time_mismatch", "TEACHER_REFERENCE_PHYSICS_TIME_MISMATCH"),
])
def test_missing_or_inconsistent_references_fail_data_qc_with_a_specific_code(fault, code):
    document = manifest()
    steps = STEPS
    if fault == "no_manifest":
        document = None
    if fault == "wrong_schema":
        document["schema"] = "so101-dynamic-mujoco-execute-v1"
    if fault == "no_start":
        document["teacher_start_observation"] = None
    if fault == "no_end":
        document["teacher_end_observation"] = None
    if fault == "malformed_start":
        document["teacher_start_observation"] = {"simulation_step": "x"}
    if fault == "start_session":
        document = manifest(start=observation(1200, session="other"))
    if fault == "end_epoch":
        document = manifest(end=observation(8500, epoch=4))
    if fault == "start_before_window":
        document = manifest(start=observation(1200, time_s=0.5))
    if fault == "start_after_first_command":
        document = manifest(start=observation(1600))
    if fault == "end_after_recording":
        document = manifest(end=observation(9500))
    if fault == "order":
        document = manifest(start=observation(1400), end=observation(1300))
    if fault == "step_absent":
        steps = [item for item in STEPS if item["physics_step"] != 1200]
    if fault == "time_mismatch":
        steps = [dict(item, simulation_time_s=item["simulation_time_s"] + 0.01) if item["physics_step"] == 8500
                 else item for item in STEPS]
    result = check(document, steps=steps)
    assert result["status"] == "FAIL" and result["reason"] == code, result


def test_a_raw_sample_from_another_session_does_not_satisfy_a_reference():
    steps = [dict(item, simulation_session_id="other") if item["physics_step"] == 1200 else item for item in STEPS]
    assert check(manifest(), steps=steps)["reason"] == "TEACHER_REFERENCE_PHYSICS_STEP_ABSENT"


def test_the_check_does_not_mutate_its_inputs():
    document, steps = manifest(), copy.deepcopy(STEPS)
    before = copy.deepcopy(document)
    check(document, steps=steps)
    assert document == before and steps == STEPS
