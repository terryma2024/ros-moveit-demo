"""YOLO-only ACT outcomes never request a fallback or bypass local pose admission."""

import importlib

import pytest

from so101_demo.parallel_batch.contracts.common import AttemptStatus, ModelOutcome
from test_contract import response_document
from test_parallel_batch_perception import harness, pose, request


def module():
    return importlib.import_module("so101_demo.parallel_batch.act_perception")


@pytest.mark.parametrize("wire,outcome,disposition,status", [
    ("DETECTED", ModelOutcome.QUALIFIED, "ADMIT_POSE", None),
    ("NOT_DETECTED", ModelOutcome.NORMAL_REJECTION, "FAILED", AttemptStatus.FAILED),
    ("INPUT_INVALID", ModelOutcome.INFRA_ERROR, "INVALID", AttemptStatus.INVALID),
    ("QUEUE_FULL", ModelOutcome.INFRA_ERROR, "INVALID", AttemptStatus.INVALID),
    ("QUEUE_TIMEOUT", ModelOutcome.QUEUE_TIMEOUT, "INVALID", AttemptStatus.INVALID),
    ("INFERENCE_TIMEOUT", ModelOutcome.INFERENCE_TIMEOUT, "INVALID", AttemptStatus.INVALID),
    ("MODEL_ERROR", ModelOutcome.MODEL_ERROR, "FAILED", AttemptStatus.FAILED),
    ("INFRA_ERROR", ModelOutcome.INFRA_ERROR, "INVALID", AttemptStatus.INVALID),
])
def test_wire_outcome_reaches_real_policy_and_attempt_disposition(tmp_path, wire, outcome, disposition, status):
    document = response_document() | {"outcome": wire, "reason": wire}
    if wire != "DETECTED": document["batch"] = None
    assert module().map_inference_outcome(document) is outcome
    h = harness(tmp_path)
    policy = module().ActTeacherPerceptionPolicy(h.latch, yolo_model_id="yolo")
    assert policy.decision.next_model == "yolo"
    policy.start_request(h.req, depth_timestamp_s=101.0, depth_sha256="b" * 64)
    decision = policy.record_result(h.req, module().map_inference_outcome(document), broker_generation=1)
    assert (decision.disposition, decision.attempt_status, decision.next_model) == (disposition, status, None)
    assert h.latch.accepted is False
    assert not (h.workspace.path / "pose_accepted.json").exists()


def test_detected_candidate_still_requires_real_local_admission_and_durable_readback(tmp_path):
    h = harness(tmp_path)
    policy = module().ActTeacherPerceptionPolicy(h.latch, yolo_model_id="yolo")
    policy.start_request(h.req, depth_timestamp_s=101.0, depth_sha256="b" * 64)
    assert policy.record_result(h.req, ModelOutcome.QUALIFIED, broker_generation=1).disposition == "ADMIT_POSE"
    assert h.latch.accepted is False
    assert policy.admit_pose(h.req, pose(h.req)).disposition == "CONTINUE"
    assert h.latch.accepted is True
    assert (h.workspace.path / "pose_accepted.json").is_file()


@pytest.mark.parametrize("gate", ["geometry", "quality"])
def test_local_geometry_or_quality_gate_rejection_is_failed_without_fallback(tmp_path, gate):
    h = harness(tmp_path)
    policy = module().ActTeacherPerceptionPolicy(h.latch, yolo_model_id="yolo")
    policy.start_request(h.req, depth_timestamp_s=101.0, depth_sha256="b" * 64)
    policy.record_result(h.req, ModelOutcome.QUALIFIED, broker_generation=1)
    setattr(h.control, gate, False)
    decision = policy.admit_pose(h.req, pose(h.req))
    assert (decision.disposition, decision.attempt_status, decision.next_model) == (
        "FAILED", AttemptStatus.FAILED, None)
    assert not h.latch.accepted


def test_old_generation_result_preserves_cancelled_disposition(tmp_path):
    h = harness(tmp_path)
    policy = module().ActTeacherPerceptionPolicy(h.latch, yolo_model_id="yolo")
    policy.start_request(h.req, depth_timestamp_s=101.0, depth_sha256="b" * 64)
    decision = policy.record_result(h.req, ModelOutcome.QUALIFIED, broker_generation=2)
    assert (decision.disposition, decision.next_model) == ("CANCELLED", None)
    assert not h.latch.accepted


def test_visible_pose_write_failure_stays_invalid_and_requires_adjudication(tmp_path, monkeypatch):
    h = harness(tmp_path)
    policy = module().ActTeacherPerceptionPolicy(h.latch, yolo_model_id="yolo")
    policy.start_request(h.req, depth_timestamp_s=101.0, depth_sha256="b" * 64)
    policy.record_result(h.req, ModelOutcome.QUALIFIED, broker_generation=1)
    original = h.workspace.write_json
    def fail_after_write(path, document):
        original(path, document)
        raise OSError("simulated durable readback failure")
    monkeypatch.setattr(h.workspace, "write_json", fail_after_write)
    with pytest.raises(OSError, match="durable readback"):
        policy.admit_pose(h.req, pose(h.req))
    assert h.latch.requires_adjudication is True
    assert h.latch.accepted is False
    assert (policy.decision.disposition, policy.decision.attempt_status, policy.decision.next_model) == (
        "INVALID", AttemptStatus.INVALID, None)


def test_failed_yolo_stage_cannot_be_forced_into_grounded_request(tmp_path):
    from so101_demo.parallel_batch.perception import PerceptionError
    h = harness(tmp_path)
    policy = module().ActTeacherPerceptionPolicy(h.latch, yolo_model_id="yolo")
    policy.start_request(h.req, depth_timestamp_s=101.0, depth_sha256="b" * 64)
    policy.record_result(h.req, ModelOutcome.NORMAL_REJECTION, broker_generation=1)
    with pytest.raises(PerceptionError, match="MODEL_SEQUENCE"):
        policy.start_request(request("grounded"), depth_timestamp_s=101.0, depth_sha256="b" * 64)
