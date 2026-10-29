"""The fixed collection workload executes one real lease, never a serial campaign."""

import importlib
import json
import hashlib
from types import SimpleNamespace as NS

from parallel_batch_worker_support import Fake
import pytest

from so101_demo.parallel_batch.contracts.common import AttemptStatus, RunMode
from so101_demo.parallel_batch.worker import ParallelWorker
from so101_demo.act.parallel_collection import ActFixedCollectionWorkload


def terminal_case(tmp_path, outcome, *, geometry_rejected=False):
    from test_act_ros_runtime import build_case
    from so101_demo.parallel_batch.act_inference import ActInferenceResult
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    identity = dict(batch_id="batch-a", coordinator_epoch=1, worker_id="w1", worker_generation=1,
                    point_id="p1", attempt_id="p1-lease-1", lease_generation=1)
    h = build_case(tmp_path, radius=0.07 if geometry_rejected else 0.04,
                   identity=identity, reset_epoch="reset-1")
    if outcome != "DETECTED":
        h.result = ActInferenceResult(h.request, 1, h.wire | {
            "outcome": outcome, "batch": None, "reason": "service-original-reason"}, 1, 5)
    def infer(_model, *, before_send):
        before_send(h.request)
        return h.result
    terminal = h.ports.run_perception_chain(h.lease, ExecutionKind.ATTEMPT, h.frame, infer)
    return h, terminal


@pytest.mark.parametrize("outcome, expected", [("NOT_DETECTED", "FAILED"), ("INPUT_INVALID", "INVALID"),
    ("QUEUE_FULL", "INVALID"), ("QUEUE_TIMEOUT", "INVALID"), ("INFERENCE_TIMEOUT", "INVALID"),
    ("MODEL_ERROR", "FAILED"), ("INFRA_ERROR", "INVALID"), ("DETECTED", "FAILED")])
def test_actual_perception_port_terminal_reaches_worker_attempt_status(tmp_path, outcome, expected):
    _h, terminal = terminal_case(tmp_path, outcome, geometry_rejected=outcome == "DETECTED")
    fake = Fake(RunMode.EXECUTE)
    fake.broker.request_model = lambda *_args, **_kwargs: terminal
    fake.runtime.execute_expert = lambda *_args: pytest.fail("Teacher motion started for a perception terminal")
    ports = fake.ports()
    ports["workload"] = ActFixedCollectionWorkload(scene_ids=("p1",))
    result = ParallelWorker(ports).run_one()
    assert result.terminal_status is AttemptStatus(expected)
    assert len([call for call in fake.results.calls if call[0] == "seal_attempt"]) == 1
    assert fake.coordinator.sealed_statuses == [AttemptStatus(expected)]
    assert fake.results.calls[0][2] == terminal.reason


def test_latch_acceptance_reaches_actual_teacher_boundary_and_never_manufactures_pass(tmp_path):
    from test_act_ros_runtime import build_case, run
    h = build_case(tmp_path, identity=dict(batch_id="batch-a", coordinator_epoch=1,
        worker_id="w1", worker_generation=1, point_id="p1", attempt_id="p1-lease-1", lease_generation=1),
        reset_epoch="reset-1")
    admitted = run(h)
    fake = Fake(RunMode.EXECUTE)
    fake.broker.request_model = lambda *_args, **_kwargs: admitted
    fake.runtime.admit_pose = lambda *_args: admitted
    teacher_calls = []
    fake.runtime.execute_expert = lambda lease, pose: teacher_calls.append((lease, pose)) or NS(
        status=AttemptStatus.FAILED, reason="TEACHER_GRASP_FAILED", physical_action_proven_absent=False)
    ports = fake.ports()
    ports["workload"] = ActFixedCollectionWorkload(scene_ids=("p1",))
    result = ParallelWorker(ports).run_one()
    assert result.terminal_status is AttemptStatus.FAILED
    assert len(teacher_calls) == 1
    assert "TEACHER_GRASP_FAILED" in fake.results.calls[0][2]


def test_fixed_workload_refuses_scene_outside_manifest_before_request():
    fake = Fake(RunMode.EXECUTE)
    fake.broker.request_model = lambda *_args, **_kwargs: pytest.fail("unknown scene sent")
    ports = fake.ports()
    ports["workload"] = ActFixedCollectionWorkload(scene_ids=("other",))
    result = ParallelWorker(ports).run_one()
    assert result.terminal_status is not AttemptStatus.PASSED
    assert "ACT_COLLECTION_SCENE_NOT_RESERVED" in result.failure_message


@pytest.mark.parametrize("flag", ["fenced", "motion_stopped", "controllers_stopped", "recorder_stopped"])
def test_unconfirmed_stop_never_becomes_normal_business_failure(tmp_path, flag):
    _h, terminal = terminal_case(tmp_path, "NOT_DETECTED")
    module = importlib.import_module("so101_demo.parallel_batch.act_attempt")
    facts = dict(fenced=True, motion_stopped=True, controllers_stopped=True, recorder_stopped=True)
    facts[flag] = False
    value = module.ActPerceptionDecision.from_terminal(terminal, stop_facts=facts)
    assert value.status is AttemptStatus.INDETERMINATE
    assert value.reason == "ACT_PERCEPTION_STOP_UNCONFIRMED"


@pytest.mark.parametrize("flag", ["fenced", "motion_stopped", "controllers_stopped", "recorder_stopped"])
def test_actual_worker_keeps_uncertain_act_cleanup_quarantined(tmp_path, flag):
    _h, terminal = terminal_case(tmp_path, "NOT_DETECTED")
    fake = Fake(RunMode.EXECUTE)
    fake.broker.request_model = lambda *_args, **_kwargs: terminal
    if flag == "fenced":
        fake.broker.cancel_generation = lambda *_args: False
    if flag == "motion_stopped":
        fake.runtime.cancel_motion = lambda *_args: False
    if flag == "controllers_stopped":
        fake.runtime.confirm_no_controller_goal = lambda *_args: False
    if flag == "recorder_stopped":
        fake.runtime.recorder_stop_proven = lambda *_args: False
    ports = fake.ports()
    ports["workload"] = ActFixedCollectionWorkload(scene_ids=("p1",))
    worker = ParallelWorker(ports)
    result = worker.run_one()
    assert result.terminal_status is AttemptStatus.INDETERMINATE
    assert result.recovered is False
    assert worker.run_one().stopped_reason == "WORKER_NOT_READY"
    assert not fake.coordinator.recovery


def test_generic_worker_keeps_its_existing_d8f_pre_motion_result(tmp_path):
    _h, terminal = terminal_case(tmp_path, "INFRA_ERROR")
    fake = Fake(RunMode.EXECUTE)
    fake.broker.request_model = lambda *_args, **_kwargs: terminal
    result = ParallelWorker(fake.ports()).run_one()
    assert result.terminal_status is AttemptStatus.INDETERMINATE


def test_workload_accepts_only_unique_explicit_scene_ids_and_execute_mode():
    for bad in ((), ("p1", "p1"), ("../escape",), ["p1"]):
        with pytest.raises(ValueError, match="ACT_COLLECTION_SCENES_INVALID"):
            ActFixedCollectionWorkload(scene_ids=bad)
    workload = ActFixedCollectionWorkload(scene_ids=("p1",))
    for mode in (RunMode.PLAN_ONLY, RunMode.DRY_RUN):
        ports = Fake(mode).ports()
        ports["workload"] = workload
        with pytest.raises(Exception, match="WORKLOAD_PORT_INVALID"):
            ParallelWorker(ports)


def test_terminal_reader_checks_actual_port_receipt_and_original_wire_bytes(tmp_path):
    h, terminal = terminal_case(tmp_path, "QUEUE_FULL")
    module = importlib.import_module("so101_demo.parallel_batch.act_attempt")
    read = module.read_act_perception_terminal(h.workspace.path)
    assert read == terminal and read.wire_outcome == "QUEUE_FULL"
    assert read.failure_message == "service-original-reason"


@pytest.mark.parametrize("fault", ["infra_as_failed", "wire_outcome_changed", "request_changed",
    "raw_audit_changed", "unknown_kind", "extra_field", "original_reason_changed", "cancel_hidden"])
def test_terminal_reader_rejects_forged_or_unlinked_pre_motion_outcome(tmp_path, fault):
    h, _terminal = terminal_case(tmp_path, "INFRA_ERROR")
    module = importlib.import_module("so101_demo.parallel_batch.act_attempt")
    path = h.workspace.path / "perception/terminal.json"
    document = json.loads(path.read_text())
    if fault == "infra_as_failed":
        document["terminal"]["disposition"] = "FAILED"
    if fault == "wire_outcome_changed":
        document["terminal"]["wire_outcome"] = "NOT_DETECTED"
    if fault == "request_changed":
        document["terminal"]["request"]["lease_generation"] = 2
    if fault == "raw_audit_changed":
        audit = h.workspace.path / "perception/inference/r1.json"
        audit.write_text(audit.read_text() + " ")
    if fault == "unknown_kind":
        document["kind"] = "OLD_PERCEPTION_TERMINAL"
    if fault == "extra_field":
        document["passed"] = True
    if fault == "original_reason_changed":
        document["terminal"]["failure_message"] = "invented reason"
    if fault == "cancel_hidden":
        audit_path = h.workspace.path / "perception/inference/r1.json"
        audit = json.loads(audit_path.read_text())
        audit["cancelled"] = True
        audit_path.write_text(json.dumps(audit))
        document["inference_audit_sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="ACT_PERCEPTION"):
        module.read_act_perception_terminal(h.workspace.path)


def test_generic_admission_return_cannot_replace_act_pose_before_teacher(tmp_path):
    from test_act_ros_runtime import build_case, run
    h = build_case(tmp_path, identity=dict(batch_id="batch-a", coordinator_epoch=1,
        worker_id="w1", worker_generation=1, point_id="p1", attempt_id="p1-lease-1", lease_generation=1),
        reset_epoch="reset-1")
    admitted = run(h)
    fake = Fake(RunMode.EXECUTE)
    fake.broker.request_model = lambda *_args, **_kwargs: admitted
    fake.runtime.admit_pose = lambda *_args: object()
    fake.runtime.execute_expert = lambda *_args: pytest.fail("unbound pose reached Teacher")
    ports = fake.ports()
    ports["workload"] = ActFixedCollectionWorkload(scene_ids=("p1",))
    result = ParallelWorker(ports).run_one()
    assert result.terminal_status is AttemptStatus.INVALID
    assert "ACT_COLLECTION_ADMITTED_POSE_CHANGED" in result.failure_message


def test_a_pose_source_replaces_the_pose_before_admission_and_the_teacher_gets_the_replaced_chain(tmp_path):
    import dataclasses

    from test_act_ros_runtime import build_case, run
    from so101_demo.core.task_geometry import Pose7
    h = build_case(tmp_path, identity=dict(batch_id="batch-a", coordinator_epoch=1,
        worker_id="w1", worker_generation=1, point_id="p1", attempt_id="p1-lease-1", lease_generation=1),
        reset_epoch="reset-1")
    admitted = run(h)
    replaced = dataclasses.replace(admitted, pose_world=Pose7((0.5, 0.25, 0.1, 0.0, 0.0, 0.0, 1.0)))
    seen = []

    def pose_source(lease, chain):
        seen.append((lease, chain))
        return replaced

    fake = Fake(RunMode.EXECUTE)
    fake.broker.request_model = lambda *_args, **_kwargs: admitted
    fake.runtime.admit_pose = lambda lease, chain: chain
    teacher_calls = []
    fake.runtime.execute_expert = lambda lease, pose: teacher_calls.append(pose) or NS(
        status=AttemptStatus.FAILED, reason="TEACHER_GRASP_FAILED", physical_action_proven_absent=False)
    ports = fake.ports()
    ports["workload"] = ActFixedCollectionWorkload(scene_ids=("p1",), pose_source=pose_source)
    ParallelWorker(ports).run_one()
    assert len(seen) == 1 and seen[0][1] is admitted and seen[0][0].point_id == "p1"
    assert teacher_calls == [replaced] and teacher_calls[0].pose_world.values[:3] == (0.5, 0.25, 0.1)


def test_a_pose_source_is_never_asked_for_a_perception_terminal_and_must_be_callable(tmp_path):
    _h, terminal = terminal_case(tmp_path, "NOT_DETECTED")
    fake = Fake(RunMode.EXECUTE)
    fake.broker.request_model = lambda *_args, **_kwargs: terminal
    fake.runtime.execute_expert = lambda *_args: pytest.fail("Teacher motion started for a perception terminal")
    ports = fake.ports()
    ports["workload"] = ActFixedCollectionWorkload(scene_ids=("p1",), pose_source=lambda *_args: pytest.fail("pose source asked"))
    assert ParallelWorker(ports).run_one().terminal_status is AttemptStatus.FAILED
    with pytest.raises(ValueError, match="ACT_COLLECTION_POSE_SOURCE_INVALID"):
        ActFixedCollectionWorkload(scene_ids=("p1",), pose_source=5)


# --- indoor P3 / D2: the camera perception is recorded and never gates a privileged-pose episode ---------------------------------------
def privileged_source(tmp_path, *, evidence_epoch=1, kind="randomised", source="privileged_pose", rig="side-wrist-indoor"):
    from so101_demo.runtime.container_campaign.privileged_pose import PoseSource

    truth = (0.0301, -0.2502, 0.16485)
    evidence = lambda session: NS(simulation_session_id=session, reset_epoch=evidence_epoch, paused=True, simulation_time_s=2.5,   # noqa: E731
                                  object_state=NS(position_world=truth))
    return PoseSource(source=source, kind=kind, rig=rig, evidence=evidence, session_id="s1", tolerance_m=0.010,
                      record_directory=tmp_path / "records", task_id="task-9"), truth


@pytest.mark.parametrize("outcome, geometry_rejected", [("NOT_DETECTED", False), ("DETECTED", True), ("MODEL_ERROR", False), ("QUEUE_TIMEOUT", False)])
def test_a_forced_perception_miss_or_ambiguity_does_not_lose_a_privileged_episode_and_is_recorded(tmp_path, outcome, geometry_rejected):
    from so101_demo.runtime.container_campaign.privileged_pose import PrivilegedAdmittedPose

    _h, terminal = terminal_case(tmp_path, outcome, geometry_rejected=geometry_rejected)
    source, truth = privileged_source(tmp_path)
    fake = Fake(RunMode.EXECUTE)
    fake.broker.request_model = lambda *_args, **_kwargs: terminal
    fake.runtime.snapshot = NS(source_stamp_ns=7_000_000_000)
    given = []
    fake.runtime.execute_expert = lambda lease, pose: given.append(pose) or NS(
        status=AttemptStatus.FAILED, reason="TEACHER_GRASP_FAILED", physical_action_proven_absent=False)
    ports = fake.ports()
    ports["workload"] = ActFixedCollectionWorkload(scene_ids=("p1",), pose_source=source)
    ParallelWorker(ports).run_one()
    # the Teacher got the simulator's pose; the episode was not sealed as a perception terminal
    assert len(given) == 1 and type(given[0]) is PrivilegedAdmittedPose and given[0].localized is None
    assert given[0].pose_world.values == (*truth, 0.0, 0.0, 0.0, 1.0) and given[0].source_stamp_ns == 7_000_000_000
    assert given[0].reset_epoch == "reset-1" and fake.runtime.chain is given[0]
    assert "PERCEPTION" not in fake.results.calls[0][2]
    record = json.loads((tmp_path / "records" / "task-9.teacher-source.json").read_text())
    assert record["camera_detected"] is False and record["camera_outcome"] == terminal.wire_outcome and record["camera_reason"] == terminal.reason
    assert record["camera_rejection_reason"] == terminal.rejection_reason and record["camera_position_m"] is None
    assert record["applied"] is True and record["teacher_source"] == "privileged_pose" and record["published_position_m"] == list(truth)


def test_a_camera_terminal_still_ends_a_nominal_episode_as_a_perception_result(tmp_path):
    _h, terminal = terminal_case(tmp_path, "NOT_DETECTED")
    source, _ = privileged_source(tmp_path, kind="nominal", source="camera_rgbd")
    fake = Fake(RunMode.EXECUTE)
    fake.broker.request_model = lambda *_args, **_kwargs: terminal
    fake.runtime.execute_expert = lambda *_args: pytest.fail("Teacher motion started for a perception terminal")
    ports = fake.ports()
    ports["workload"] = ActFixedCollectionWorkload(scene_ids=("p1",), pose_source=source)
    assert ParallelWorker(ports).run_one().terminal_status is AttemptStatus.FAILED
    assert not (tmp_path / "records").exists()


def test_a_detected_privileged_episode_records_the_detection_and_is_given_the_truth(tmp_path):
    from test_act_ros_runtime import build_case, run
    h = build_case(tmp_path, identity=dict(batch_id="batch-a", coordinator_epoch=1, worker_id="w1", worker_generation=1, point_id="p1",
                                           attempt_id="p1-lease-1", lease_generation=1), reset_epoch="reset-1")
    admitted = run(h)
    source, truth = privileged_source(tmp_path / "d")
    fake = Fake(RunMode.EXECUTE)
    fake.broker.request_model = lambda *_args, **_kwargs: admitted
    given = []
    fake.runtime.execute_expert = lambda lease, pose: given.append(pose) or NS(
        status=AttemptStatus.FAILED, reason="TEACHER_GRASP_FAILED", physical_action_proven_absent=False)
    ports = fake.ports()
    ports["workload"] = ActFixedCollectionWorkload(scene_ids=("p1",), pose_source=source)
    ParallelWorker(ports).run_one()
    assert given[0].pose_world.values[:3] == truth and given[0].localized is admitted.localized
    record = json.loads((tmp_path / "d" / "records" / "task-9.teacher-source.json").read_text())
    assert record["camera_detected"] is True and record["camera_outcome"] == "DETECTED" and record["applied"] is True
