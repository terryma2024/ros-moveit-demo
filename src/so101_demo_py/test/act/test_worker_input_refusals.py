"""Design 2026-10-10 section 1: a worker input refusal before any motion becomes a committed D8f result.

The closed allowlist (request_model boundary only): a PerceptionError starting `STALE_RGBD:` or `STALE_RGBD_OR_TF:`, a RuntimeError
`BROKER_CANDIDATE_AMBIGUOUS...`, and the perception-terminal decision that request_model returns. It is committed in the manifest-free
D8f form only when the stop is proven (stopped and confirmed, recorder proven stopped); everything else keeps today's path."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.parallel_batch.contracts.common import AttemptStatus, RunMode
from so101_demo.parallel_batch.perception import PerceptionError, PoseAdmissionCommitError
from so101_demo.parallel_batch.worker import ParallelWorker

from test_parallel_batch_worker import Fake, _capture_sealed_decisions, event_names

PREFIX = "TEACHER_FENCED_BEFORE_MOTION:INPUT_UNAVAILABLE request_model "
STALE = "STALE_RGBD: FUTURE_STAMP now=7.7 rgb=7.8 depth=7.8 reset=3.24 max_age=5.0 max_skew=0.0"
STALE_TF = "STALE_RGBD_OR_TF: AGE now=9.0 rgb=3.5 depth=3.5 reset=3.24 max_age=5.0 max_skew=0.0"


def refused(error):
    fake = Fake(RunMode.EXECUTE)
    sealed = _capture_sealed_decisions(fake)
    fake.broker.raise_request = error
    result = ParallelWorker(fake.ports()).run_one()
    return fake, sealed, result


def terminal(disposition, reason, failure_type=None, failure_message=None):
    return SimpleNamespace(perception_terminal=True, disposition=disposition, reason=reason,
                           failure_type=failure_type, failure_message=failure_message)


# ---- allowlisted inputs with a proven stop are committed in the D8f form ---------------------------------------------------

@pytest.mark.parametrize("error", [PerceptionError(STALE), PerceptionError(STALE_TF),
                                   RuntimeError("BROKER_CANDIDATE_AMBIGUOUS: 2 candidates")],
                         ids=["stale-rgbd", "stale-rgbd-or-tf", "candidate-ambiguous"])
def test_an_allowlisted_input_refusal_with_a_proven_stop_is_committed_in_the_d8f_form(error):
    fake, sealed, result = refused(error)
    (decision,) = sealed
    assert decision.status is AttemptStatus.INDETERMINATE
    assert (decision.teacher_execution_status, decision.teacher_task_result) == ("INDETERMINATE", "UNCONFIRMED")
    assert decision.act_data_status == "INVALID" and decision.act_data_reason == decision.reason
    assert decision.reason.startswith(PREFIX) and str(error).split(":")[0] in decision.reason
    assert len(decision.reason) <= len("TEACHER_FENCED_BEFORE_MOTION:") + 160
    assert result.stopped_reason == "POINT_TERMINAL" and result.terminal_status is AttemptStatus.INDETERMINATE
    assert result.failure_boundary == "request_model" and result.failure_type == "TeacherPreMotionRefused"
    assert result.failure_origin_type == type(error).__name__
    assert str(error).split(":")[0] in result.failure_message
    assert "pose_admission" not in fake.runtime.calls and "submit_motion" not in fake.runtime.calls
    assert "FINALIZING_STARTED" in event_names(fake) and "RESULT_COMMITTED" in event_names(fake)


def test_the_reason_is_bounded_at_160_characters_and_the_message_at_512_bytes():
    fake, sealed, result = refused(PerceptionError("STALE_RGBD: " + "é" * 600))
    (decision,) = sealed
    assert len(decision.reason) <= len("TEACHER_FENCED_BEFORE_MOTION:") + 160
    assert len(result.failure_message.encode("utf-8")) <= 512 and "\n" not in result.failure_message


@pytest.mark.parametrize(("disposition", "reason"), [
    ("FAILED", "PERCEPTION_NO_POSE"), ("FAILED", "PERCEPTION_MODEL_ERROR"), ("INVALID", "PERCEPTION_INFRA_ERROR"),
    ("INVALID", "PERCEPTION_QUEUE_TIMEOUT"), ("INVALID", "PERCEPTION_INFERENCE_TIMEOUT")])
def test_a_perception_terminal_decision_is_intercepted_before_admit_pose_and_committed_in_the_d8f_form(disposition, reason):
    fake = Fake(RunMode.EXECUTE)
    sealed = _capture_sealed_decisions(fake)
    fake.broker.request_model = lambda *a, **k: terminal(disposition, reason)
    result = ParallelWorker(fake.ports()).run_one()
    (decision,) = sealed
    assert decision.status is AttemptStatus.INDETERMINATE and decision.act_data_status == "INVALID"
    assert decision.reason.startswith(PREFIX + "PERCEPTION_TERMINAL:")
    assert f"PERCEPTION_TERMINAL:{disposition} {reason}" in decision.reason
    assert "pose_admission" not in fake.runtime.calls and "submit_motion" not in fake.runtime.calls
    assert result.failure_boundary == "request_model" and result.failure_origin_type == "PerceptionTerminal"


def test_a_perception_terminal_with_a_broker_failure_keeps_its_broker_type_as_the_origin():
    fake = Fake(RunMode.EXECUTE)
    fake.broker.request_model = lambda *a, **k: terminal("INVALID", "PERCEPTION_INFRA_ERROR", "BrokerResponse.INFRA_ERROR",
                                                          "INPUT_OPENED_OWNER_MODE\n" + "é" * 600)
    result = ParallelWorker(fake.ports()).run_one()
    assert result.failure_origin_type == "BrokerResponse.INFRA_ERROR" and result.failure_type == "TeacherPreMotionRefused"
    assert result.failure_message.startswith("INPUT_OPENED_OWNER_MODE ") and len(result.failure_message.encode()) <= 512


# ---- an unproven stop keeps today's path and quarantines ------------------------------------------------------------------

def unproven(fake, how):
    if how == "not-stopped":
        fake.runtime.cancel_motion = lambda lease: False
    elif how == "not-confirmed":
        fake.runtime.goal_confirmed = False
    else:
        fake.runtime.recorder_stop_proven = lambda lease: False


@pytest.mark.parametrize("how", ["not-stopped", "not-confirmed", "recorder-not-stopped"])
@pytest.mark.parametrize("error", [PerceptionError(STALE), RuntimeError("BROKER_CANDIDATE_AMBIGUOUS: 2")],
                         ids=["stale-rgbd", "candidate-ambiguous"])
def test_an_allowlisted_refusal_without_a_proven_stop_is_not_committed_in_the_d8f_form_and_quarantines(how, error):
    fake = Fake(RunMode.EXECUTE)
    sealed = _capture_sealed_decisions(fake)
    unproven(fake, how)
    fake.broker.raise_request = error
    worker = ParallelWorker(fake.ports())
    result = worker.run_one()
    (decision,) = sealed
    assert not hasattr(decision, "teacher_task_result") and not hasattr(decision, "act_data_status")
    assert decision.reason == "AUTHORIZATION_OR_PORT_FAILURE"
    assert result.failure_type == type(error).__name__ and getattr(result, "failure_origin_type", None) is None
    assert worker._quarantined is True


def test_a_perception_terminal_without_a_proven_stop_is_not_committed_in_the_d8f_form_and_quarantines():
    fake = Fake(RunMode.EXECUTE)
    sealed = _capture_sealed_decisions(fake)
    unproven(fake, "recorder-not-stopped")
    fake.broker.request_model = lambda *a, **k: terminal("FAILED", "PERCEPTION_NO_POSE")
    worker = ParallelWorker(fake.ports())
    worker.run_one()
    (decision,) = sealed
    assert not hasattr(decision, "teacher_task_result") and worker._quarantined is True
    assert "submit_motion" not in fake.runtime.calls


# ---- everything outside the allowlist keeps today's behaviour --------------------------------------------------------------

@pytest.mark.parametrize("error", [
    PerceptionError("REQUEST_IDENTITY_MISMATCH"), PerceptionError("WORKSPACE_IDENTITY_MISMATCH"),
    PerceptionError("STALE_RGBD"), PerceptionError("MODEL_SEQUENCE"),
    PoseAdmissionCommitError("POSE_ACCEPTED_REQUIRES_ADJUDICATION"),
    RuntimeError("BROKER_GENERATION_CHANGED"), RuntimeError("BROKER_RESPONSE_IDENTITY"),
    RuntimeError("RUNNING_EVIDENCE_UNAVAILABLE"), RuntimeError("boom")])
def test_an_excluded_code_at_request_model_keeps_the_generic_invalid_path(error):
    fake, sealed, result = refused(error)
    (decision,) = sealed
    assert decision.status is AttemptStatus.INVALID and decision.reason == "AUTHORIZATION_OR_PORT_FAILURE"
    assert not hasattr(decision, "teacher_task_result")
    assert result.failure_boundary == "request_model" and result.failure_type == type(error).__name__
    assert getattr(result, "failure_origin_type", None) is None


@pytest.mark.parametrize("error", [PerceptionError(STALE), RuntimeError("BROKER_CANDIDATE_AMBIGUOUS: 2"),
                                   RuntimeError("RUNNING_EVIDENCE_UNAVAILABLE")])
def test_the_allowlist_applies_at_the_request_model_boundary_only(error):
    fake = Fake(RunMode.EXECUTE)
    sealed = _capture_sealed_decisions(fake)

    def refuse(lease, chain):
        raise error
    fake.runtime.admit_pose = refuse
    result = ParallelWorker(fake.ports()).run_one()
    (decision,) = sealed
    assert decision.status is AttemptStatus.INVALID and not hasattr(decision, "teacher_task_result")
    assert result.failure_boundary == "admit_pose" and getattr(result, "failure_origin_type", None) is None


def test_an_error_after_goal_dispatch_is_unchanged():
    fake = Fake(RunMode.EXECUTE)
    sealed = _capture_sealed_decisions(fake)

    def refuse(lease, admitted):
        fake.runtime.calls.append("submit_motion")
        raise PerceptionError(STALE)
    fake.runtime.execute_expert = refuse
    result = ParallelWorker(fake.ports()).run_one()
    (decision,) = sealed
    assert not hasattr(decision, "teacher_task_result") and result.failure_boundary == "execute_expert"
    assert getattr(result, "failure_origin_type", None) is None


def test_plan_only_and_validation_runs_are_not_affected():
    fake = Fake(RunMode.PLAN_ONLY)
    fake.broker.raise_request = PerceptionError(STALE)
    result = ParallelWorker(fake.ports()).run_one()
    assert getattr(result, "failure_origin_type", None) is None


# ---- worker-run-results.json: backward compatible ---------------------------------------------------------------------------

def test_the_origin_type_is_written_only_when_it_is_set(tmp_path):
    from so101_demo.cli.mujoco_batch.worker_process import _write_worker_results
    from so101_demo.parallel_batch.worker_parts.contracts import WorkerRunResult
    resources = SimpleNamespace(worker_id="worker-01", generation=1, worker_root=tmp_path)
    plain = WorkerRunResult("task_start", None, False, "INITIAL_GATE_FAILED", failure_boundary="x", failure_type="RuntimeError",
                            failure_message="m")
    path = _write_worker_results(resources, (plain,))
    assert "failure_origin_type" not in json.loads(path.read_text())["results"][0]
    other = tmp_path / "other"
    other.mkdir()
    resources = SimpleNamespace(worker_id="worker-01", generation=1, worker_root=other)
    origin = WorkerRunResult("task_start", AttemptStatus.INDETERMINATE, True, "POINT_TERMINAL", failure_boundary="request_model",
                             failure_type="TeacherPreMotionRefused", failure_message=STALE, failure_origin_type="PerceptionError")
    document = json.loads(_write_worker_results(resources, (origin,)).read_text())["results"][0]
    assert document["failure_origin_type"] == "PerceptionError" and document["failure_type"] == "TeacherPreMotionRefused"


# ---- the recorder is proven stopped ------------------------------------------------------------------------------------------

def test_the_runtime_reports_whether_the_recorder_was_proven_stopped(tmp_path, monkeypatch):
    import test_offline_recording_switch as switch
    from so101_demo.act.collection_orchestration import CollectionOptions
    from so101_demo.act.offline.raw_recorder import STATS_SCHEMA
    for facts, expected in (({"schema": STATS_SCHEMA, "rc": 0}, True),
                            ({"schema": STATS_SCHEMA, "rc": -9, "failure": "RAW_BAG_CLOSE_TIMEOUT"}, True),
                            ({"rc": 0}, False),                                              # no stop stats were written
                            ({"schema": STATS_SCHEMA, "rc": None}, False),                  # the process did not exit
                            ({"schema": STATS_SCHEMA, "rc": 0, "failure": "RAW_PILOT_STOP_FAILED: x"}, False)):
        monkeypatch.setattr(switch.orchestration, "PilotRecording", switch.pilot_factory(facts=facts))
        runtime, group, events, clock = switch.worker_runtime(tmp_path / str(len(str(facts))) / str(expected), CollectionOptions("on"))
        runtime.start_physical_runtime()
        lease = switch._lease()
        runtime.reset_and_validate_point(lease)
        runtime._retire_recorder(runtime._lease_key(lease))
        assert runtime.recorder_stop_proven(lease) is expected, facts


def test_a_run_without_a_recorder_has_nothing_to_prove(tmp_path):
    import test_offline_recording_switch as switch
    from so101_demo.act.collection_orchestration import CollectionOptions
    runtime, group, events, clock = switch.worker_runtime(tmp_path, CollectionOptions("off"))
    assert runtime.recorder_stop_proven(switch._lease()) is True


# ---- the data side accepts the recorder-first pre-motion seal ----------------------------------------------------------------

def test_a_recorder_first_pre_motion_seal_passes_the_verifier_with_qc_not_run(tmp_path, monkeypatch):
    from test_act_result_schema3 import setup_result, lease, _verifier
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    seal.unlink()
    reason = ("TEACHER_FENCED_BEFORE_MOTION:INPUT_UNAVAILABLE request_model " + STALE)[:29 + 160 + len("INPUT_UNAVAILABLE request_model ")]
    decision = SimpleNamespace(status=AttemptStatus.INDETERMINATE, teacher_execution_status="INDETERMINATE",
                               teacher_task_result="UNCONFIRMED", act_data_status="INVALID", act_data_reason=reason,
                               episode_seal_path=seal)
    location = Path(store.seal_attempt(lease(), decision))
    result = json.loads((location / "result.json").read_bytes())
    assert result["act_data_qc"] == "NOT_RUN" and result["episode_seal_sha256"] is None and result["act_data_reason"] == reason
    verdict = _verifier(tmp_path, location, inputs).verify(lease(), str(location), RunMode.EXECUTE)
    assert verdict["status"] == "INDETERMINATE" and verdict["export_eligible"] is False and verdict["act_data_qc"] == "NOT_RUN"


# ---- the orchestrator exit code ----------------------------------------------------------------------------------------------

PRE_MOTION_REFUSAL_FIELDS = dict(result_status="INDETERMINATE", teacher_execution_status="INDETERMINATE", teacher_task_result="UNCONFIRMED",
           act_data_status="INVALID", act_data_qc="NOT_RUN", export_eligible=False,
           receipt={"act_data_reason": PREFIX + STALE})


def completion(monkeypatch, tmp_path, cleanup_error=None, **changes):
    from so101_demo.act import result_store
    from so101_demo.cli import act_diagnostic_episode
    proof = {**PRE_MOTION_REFUSAL_FIELDS, **changes}
    context = dict(coordinator_root="coordinator", location="location", scope="scope", inputs_manifest="inputs")
    written = []

    def cleanup(*args, **kwargs):
        if cleanup_error:
            raise ValueError(cleanup_error)
        return dict(cleanup_proof_path="cleanup")
    monkeypatch.setattr(result_store, "resolve_native_run", lambda root: context)
    monkeypatch.setattr(result_store, "verify_coordinator_commit", lambda *a, **k: proof)
    monkeypatch.setattr(result_store, "verify_coordinator_cleanup", cleanup)
    monkeypatch.setattr(result_store, "write_commit_proof", lambda proof, path: written.append(path) or "digest")
    code, document = act_diagnostic_episode._verified_run_completion(tmp_path)
    return code, document, written


def test_a_committed_input_refusal_exits_5_and_keeps_its_commit_proof(monkeypatch, tmp_path):
    code, document, written = completion(monkeypatch, tmp_path)
    assert code == 5 and document["status"] == "FAIL" and document["reason"] == "INPUT_UNAVAILABLE_BEFORE_MOTION"
    assert document["teacher_result_status"] == "INDETERMINATE" and written == [tmp_path / "commit-proof.json"]


@pytest.mark.parametrize("changes", [
    dict(receipt={"act_data_reason": "TEACHER_FENCED_BEFORE_MOTION:TEACHER_CHANNEL_FENCED"}),      # a D8f result for another reason
    dict(receipt={"act_data_reason": "SOMETHING INPUT_UNAVAILABLE"}),
    dict(receipt={}),
    dict(teacher_execution_status="FAILED"), dict(teacher_task_result="FAIL"), dict(act_data_status="VALID"),
    dict(act_data_qc="PASS"), dict(export_eligible=True)], ids=lambda c: next(iter(c)) + str(len(str(c))))
def test_everything_but_the_exact_input_refusal_falls_through_to_exit_1(monkeypatch, tmp_path, changes):
    code, document, written = completion(monkeypatch, tmp_path, **changes)
    assert code == 1 and document["reason"] == "TEACHER_TASK_NOT_PASSED" and written == []


def test_a_failed_cleanup_verification_is_exit_4_and_nothing_sealed_is_exit_4(monkeypatch, tmp_path):
    code, document, _ = completion(monkeypatch, tmp_path, cleanup_error="RESULT_CLEANUP_READBACK_INVALID")
    assert code == 4
    from so101_demo.act import result_store
    from so101_demo.cli import act_diagnostic_episode

    def nothing(root):
        raise ValueError("RESULT_RUN_CONTEXT_INVALID")
    monkeypatch.setattr(result_store, "resolve_native_run", nothing)
    assert act_diagnostic_episode._verified_run_completion(tmp_path)[0] == 4
