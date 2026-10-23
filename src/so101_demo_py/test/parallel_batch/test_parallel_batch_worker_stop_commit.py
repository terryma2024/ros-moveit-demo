"""Stop fencing, commit acknowledgements, seal failures and the committed diagnostics."""

import threading
from types import SimpleNamespace

from parallel_batch_worker_support import Decision, Fake, event_names
import pytest

from so101_demo.parallel_batch.contracts.common import (
    AttemptStatus,
    RunMode,
)
from so101_demo.parallel_batch.worker import ParallelWorker


def test_stop_is_atomic_fence_before_worker_can_start_new_work():
    fake = Fake(RunMode.PLAN_ONLY)
    worker = ParallelWorker(fake.ports())

    worker.request_stop()
    outcome = worker.run_one()

    assert outcome.stopped_reason == "STOP_REQUESTED"
    assert fake.coordinator.calls == []
    assert fake.runtime.calls == []
    assert fake.broker.calls == []


def test_stop_racing_lease_reply_fences_all_runtime_and_broker_side_effects():
    fake = Fake(RunMode.PLAN_ONLY)
    worker = ParallelWorker(fake.ports())
    entered, release = threading.Event(), threading.Event()
    original = fake.coordinator.grant_lease

    def blocked_grant(*args, **kwargs):
        entered.set()
        release.wait(1.0)
        return original(*args, **kwargs)

    fake.coordinator.grant_lease = blocked_grant
    result = []
    thread = threading.Thread(target=lambda: result.append(worker.run_one()))
    thread.start()
    assert entered.wait(1.0)
    worker.request_stop()
    release.set()
    thread.join(timeout=1.0)

    assert not thread.is_alive()
    assert result[0].stopped_reason == "LEASE_ACK_FAILED"
    assert fake.runtime.calls == ["worker_ready_gate"]
    assert fake.broker.calls == []


def test_stop_ack_does_not_wait_for_blocked_broker_boundary():
    fake = Fake(RunMode.PLAN_ONLY)
    worker = ParallelWorker(fake.ports())
    fake.broker.block = threading.Event()
    result = []
    run_thread = threading.Thread(target=lambda: result.append(worker.run_one()))
    run_thread.start()
    assert fake.broker.entered.wait(1.0)

    stopped = threading.Event()
    stop_thread = threading.Thread(
        target=lambda: (worker.request_stop(), stopped.set())
    )
    stop_thread.start()
    assert stopped.wait(0.1), "stop ACK waited for the Broker boundary"

    fake.broker.block.set()
    run_thread.join(timeout=1.0)
    stop_thread.join(timeout=1.0)
    assert "pose_admission" not in fake.runtime.calls
    assert "submit_plan" not in fake.runtime.calls
    assert "submit_motion" not in fake.runtime.calls


def test_stop_ack_does_not_wait_for_blocked_action_or_allow_later_boundary():
    fake = Fake(RunMode.EXECUTE)
    worker = ParallelWorker(fake.ports())
    entered, release = threading.Event(), threading.Event()
    original = fake.runtime.execute_expert

    def blocked_action(*args, **kwargs):
        entered.set()
        release.wait(1.0)
        return original(*args, **kwargs)

    fake.runtime.execute_expert = blocked_action
    result = []
    run_thread = threading.Thread(target=lambda: result.append(worker.run_one()))
    run_thread.start()
    assert entered.wait(1.0)

    stopped = threading.Event()
    stop_thread = threading.Thread(
        target=lambda: (worker.request_stop(), stopped.set())
    )
    stop_thread.start()
    assert stopped.wait(0.1), "stop ACK waited for the action boundary"

    release.set()
    run_thread.join(timeout=1.0)
    stop_thread.join(timeout=1.0)
    assert fake.runtime.calls.count("submit_motion") == 1
    assert "capture_terminal" not in fake.runtime.calls


def test_a_committed_status_that_differs_from_the_teacher_decision_is_refused_not_adopted():
    """The old contract let an authoritative failing QC turn the worker's PASSED into FAILED (a `qc_downgrade`).

    The committed status is the Teacher's own; a commit that disagrees with the sealed decision is a protocol fault.
    """
    fake=Fake()
    original=fake.coordinator.commit_result
    def committed_failure(lease,location,*,request_key):
        reply=original(lease,location,request_key=request_key)
        reply['status']=AttemptStatus.FAILED
        return reply
    fake.coordinator.commit_result=committed_failure
    result=ParallelWorker(fake.ports()).run_one()
    assert fake.coordinator.sealed_statuses==[AttemptStatus.PASSED]
    assert result.terminal_status is None and result.stopped_reason=='TERMINAL_ACK_FAILED'
    assert result.recovered is False


def test_the_worker_has_no_qc_downgrade_path_left():
    import inspect

    from so101_demo.parallel_batch import worker as worker_module
    from so101_demo.parallel_batch.worker_parts import commit, contracts, protocol, revocation, watchdog
    for module in (worker_module, commit, contracts, protocol, revocation, watchdog):
        assert 'qc_downgrade' not in inspect.getsource(module)


@pytest.mark.parametrize('claim,committed',[(AttemptStatus.FAILED,AttemptStatus.PASSED),
    (AttemptStatus.PASSED,AttemptStatus.INVALID),(AttemptStatus.INDETERMINATE,AttemptStatus.FAILED)])
def test_a_commit_ack_that_disagrees_with_the_sealed_decision_is_never_accepted(claim,committed):
    fake=Fake()
    fake.runtime.execute_decision=Decision(claim)
    original=fake.coordinator.commit_result
    def wrong_reply(lease,location,*,request_key):
        reply=original(lease,location,request_key=request_key);reply['status']=committed
        return reply
    fake.coordinator.commit_result=wrong_reply
    result=ParallelWorker(fake.ports()).run_one()
    assert result.terminal_status is None and result.stopped_reason=='TERMINAL_ACK_FAILED'


@pytest.mark.parametrize('prior_execution_failure', [False, True])
def test_terminal_seal_failure_preserves_first_bounded_original_refusal(prior_execution_failure):
    fake = Fake()
    if prior_execution_failure:
        fake.broker.raise_request = PermissionError('first request rejected\n' + 'é' * 600)
    def broken_seal(lease, decision):
        fake.results.calls.append(('seal_attempt', decision.status, decision.reason))
        raise OSError('terminal seal rejected\n' + 'é' * 600)
    fake.results.seal_attempt = broken_seal
    worker = ParallelWorker(fake.ports())
    result = worker.run_one()
    assert result.terminal_status is None and result.stopped_reason == 'TERMINAL_ACK_FAILED'
    assert result.recovered is False and worker._quarantined is True
    assert result.failure_boundary == ('request_model' if prior_execution_failure else 'seal_and_commit')
    assert result.failure_type == ('PermissionError' if prior_execution_failure else 'OSError')
    assert result.failure_message.startswith('first request rejected ' if prior_execution_failure
        else 'terminal seal rejected ')
    assert len(result.failure_message.encode('utf-8')) <= 512 and '\n' not in result.failure_message
    assert fake.results.calls[0][0] == 'seal_attempt' and fake.coordinator.recovery == []
    assert 'RESULT_COMMITTED' not in event_names(fake)


def test_worker_rejects_unregistered_workload_object():
    fake = Fake()
    ports = fake.ports()
    ports["workload"] = object()
    with pytest.raises(Exception, match="WORKLOAD_PORT_INVALID"):
        ParallelWorker(ports)


def test_prepare_for_start_is_idempotent_and_never_requests_a_lease():
    fake = Fake(RunMode.PLAN_ONLY)
    worker = ParallelWorker(fake.ports())

    assert worker.prepare_for_start() is True
    assert worker.prepare_for_start() is True
    assert fake.coordinator.calls == [("register_worker", "w1", 1)]
    assert fake.runtime.calls == ["worker_ready_gate"]


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (SimpleNamespace(point_id=None, terminal_status=None, recovered=False,
                         stopped_reason="NO_POINT"), False),
        (SimpleNamespace(point_id=None, terminal_status=None, recovered=False,
                         stopped_reason="STOP_REQUESTED"), False),
        (SimpleNamespace(point_id="p1", terminal_status=AttemptStatus.FAILED,
                         recovered=True, stopped_reason="POINT_TERMINAL"), False),
        (SimpleNamespace(point_id="p1", terminal_status=AttemptStatus.INVALID,
                         recovered=True, stopped_reason="INITIAL_GATE_FAILED"), True),
        (SimpleNamespace(point_id="p1", terminal_status=AttemptStatus.PASSED,
                         recovered=False, stopped_reason="POINT_TERMINAL"), True),
        (SimpleNamespace(point_id=None, terminal_status=None, recovered=False,
                         stopped_reason="WORKER_NOT_READY"), True),
    ],
)
def test_adaptive_worker_result_infrastructure_classification(result, expected):
    from so101_demo.parallel_batch.worker_parts.contracts import adaptive_result_is_infrastructure

    assert adaptive_result_is_infrastructure(result) is expected


@pytest.mark.parametrize(
    "boundary,message",
    [
        ("reset_point", "reset failed"),
        ("point_initial_gate", "initial gate rejected second line"),
    ],
)
def test_initial_boundary_failure_reports_bounded_structured_diagnostic(
    boundary, message
):
    fake = Fake(RunMode.EXECUTE)
    fake.runtime.raise_at = boundary

    result = ParallelWorker(fake.ports()).run_one()

    assert result.stopped_reason == "INITIAL_GATE_FAILED"
    assert result.failure_boundary == boundary
    assert result.failure_type == "RuntimeError"
    assert result.failure_message == message
    assert len(result.failure_message.encode("utf-8")) <= 512
    assert "\n" not in result.failure_message


@pytest.mark.parametrize(
    "mode,boundary,target",
    [
        (RunMode.EXECUTE, "inference_snapshot", "runtime"),
        (RunMode.EXECUTE, "request_model", "broker"),
        (RunMode.EXECUTE, "admit_pose", "runtime"),
        (RunMode.EXECUTE, "execute_expert", "runtime"),
        (RunMode.PLAN_ONLY, "plan_expert", "runtime"),
    ],
)
def test_authorized_boundary_failure_reports_bounded_structured_diagnostic(
    mode, boundary, target
):
    fake = Fake(mode)
    message = "request rejected\n" + "é" * 600
    error = RuntimeError(message)
    if target == "broker":
        fake.broker.raise_request = error
    else:
        setattr(
            fake.runtime,
            boundary,
            lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
        )

    result = ParallelWorker(fake.ports()).run_one()

    assert result.stopped_reason == "POINT_TERMINAL"
    assert result.failure_boundary == boundary
    assert result.failure_type == "RuntimeError"
    assert result.failure_message.startswith("request rejected ")
    assert len(result.failure_message.encode("utf-8")) <= 512
    assert "\n" not in result.failure_message
    assert fake.results.calls[0][2] == "AUTHORIZATION_OR_PORT_FAILURE"


def test_broker_terminal_diagnostic_is_projected_into_the_committed_input_refusal():
    """Design 2026-10-10 section 1: a perception-terminal decision is an input refusal before motion. It is committed in the
    D8f form; the broker diagnostic stays in failure_message and its type moves to failure_origin_type."""
    fake = Fake(RunMode.EXECUTE)
    terminal = SimpleNamespace(
        perception_terminal=True,
        disposition="INVALID",
        reason="PERCEPTION_INFRA_ERROR",
        failure_type="BrokerResponse.INFRA_ERROR",
        failure_message="INPUT_OPENED_OWNER_MODE\n" + "é" * 600,
    )
    fake.broker.request_model = lambda *_args, **_kwargs: terminal

    result = ParallelWorker(fake.ports()).run_one()

    assert result.failure_boundary == "request_model"
    assert result.failure_type == "TeacherPreMotionRefused"
    assert result.failure_origin_type == "BrokerResponse.INFRA_ERROR"
    assert result.failure_message.startswith("INPUT_OPENED_OWNER_MODE ")
    assert len(result.failure_message.encode("utf-8")) <= 512
    assert "\n" not in result.failure_message
    assert fake.results.calls[0][2].startswith(
        "TEACHER_FENCED_BEFORE_MOTION:INPUT_UNAVAILABLE request_model PERCEPTION_TERMINAL:INVALID PERCEPTION_INFRA_ERROR")
