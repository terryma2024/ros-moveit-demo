"""Watchdog diagnostics and the pre-motion teacher refusal."""

import json
import threading
import time
from types import SimpleNamespace

from parallel_batch_worker_support import Fake, event_names
import pytest

from so101_demo.parallel_batch.contracts.common import (
    AttemptStatus,
    RunMode,
)
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
from so101_demo.parallel_batch.worker import ParallelWorker


def _diagnostic_lines(captured, tag):
    return [json.loads(line[len(tag) + 1:]) for line in captured.splitlines()
            if line.startswith(tag + " ")]


def _watchdog_lease():
    return LeaseIdentity("batch-a", 1, "w1", 1, "p1", "p1-lease-1", 1, 10.0, 310.0)


def _watchdog_owner(revoked, **overrides):
    values = dict(
        _stop_requested=threading.Event(),
        _now=time.monotonic,
        _config=SimpleNamespace(heartbeat_timeout_s=0.05, heartbeat_interval_s=1.0),
        _ordered_receipts=False,
        _worker_id="w1",
        _heartbeat_transaction=lambda lease, deadline: lease,
        _accept_heartbeat=lambda ack, lease: True,
        _watchdog_revoked=lambda lease, reason: revoked.append(reason),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _run_watchdog(owner):
    from so101_demo.parallel_batch.worker_parts.watchdog import _HeartbeatWatchdog

    watchdog = _HeartbeatWatchdog(owner, _watchdog_lease())
    watchdog.start()
    watchdog._thread.join(2)
    assert not watchdog._thread.is_alive()
    return watchdog


def test_watchdog_exception_line_is_emitted_and_reason_is_unchanged(capfd):
    revoked = []

    def raising_acknowledged(ack, lease):
        raise PermissionError("X")

    owner = _watchdog_owner(revoked, _accept_heartbeat=raising_acknowledged)
    watchdog = _run_watchdog(owner)
    assert revoked == ["COORDINATOR_LOST"]
    assert watchdog.reason == "COORDINATOR_LOST"
    lines = _diagnostic_lines(capfd.readouterr().err, "WORKER_WATCHDOG_EXCEPTION")
    assert len(lines) == 1
    line = lines[0]
    assert line["reason"] == "COORDINATOR_LOST"
    assert line["worker_id"] == "w1"
    assert line["error_type"] == "PermissionError"
    assert line["error_message"] == "X"
    assert any(frame.endswith(":raising_acknowledged") for frame in line["frames"])
    assert len(line["frames"]) <= 12
    assert line["elapsed_s"] >= 0
    assert "now_s" in line


def test_watchdog_exception_line_uses_heartbeat_thread_traceback_and_bounds_message(capfd):
    revoked = []

    def failing_transaction(lease, deadline):
        raise RuntimeError("Y" * 1000)

    owner = _watchdog_owner(revoked, _heartbeat_transaction=failing_transaction)
    _run_watchdog(owner)
    assert revoked == ["COORDINATOR_LOST"]
    err = capfd.readouterr().err
    (line,) = _diagnostic_lines(err, "WORKER_WATCHDOG_EXCEPTION")
    assert line["error_type"] == "RuntimeError"
    assert line["error_message"] == "Y" * 300
    assert any(frame.endswith(":failing_transaction") for frame in line["frames"])
    assert all(len(row) < 4096 for row in err.splitlines())


def test_watchdog_timeout_line_is_emitted_without_frames(capfd):
    revoked = []
    release = threading.Event()

    def blocked(lease, deadline):
        release.wait(2)
        return lease

    owner = _watchdog_owner(revoked, _heartbeat_transaction=blocked)
    try:
        _run_watchdog(owner)
    finally:
        release.set()
    assert revoked == ["HEARTBEAT_ACK_TIMEOUT"]
    (line,) = _diagnostic_lines(capfd.readouterr().err, "WORKER_WATCHDOG_EXCEPTION")
    assert line["reason"] == "HEARTBEAT_ACK_TIMEOUT"
    assert line["worker_id"] == "w1"
    assert "frames" not in line
    assert line["elapsed_s"] >= 0.05


def test_watchdog_invalid_ack_line_is_emitted_without_frames(capfd):
    revoked = []
    owner = _watchdog_owner(revoked, _accept_heartbeat=lambda ack, lease: False)
    _run_watchdog(owner)
    assert revoked == ["HEARTBEAT_ACK_INVALID"]
    (line,) = _diagnostic_lines(capfd.readouterr().err, "WORKER_WATCHDOG_EXCEPTION")
    assert line["reason"] == "HEARTBEAT_ACK_INVALID"
    assert "frames" not in line


def test_watchdog_diagnostic_never_raises_when_stderr_is_broken(monkeypatch):
    class Broken:
        def write(self, text):
            raise OSError("closed")

        def flush(self):
            raise OSError("closed")

    monkeypatch.setattr("sys.stderr", Broken())
    revoked = []

    def raising_acknowledged(ack, lease):
        raise PermissionError("X")

    _run_watchdog(_watchdog_owner(revoked, _accept_heartbeat=raising_acknowledged))
    assert revoked == ["COORDINATOR_LOST"]


def test_current_heartbeat_exception_emits_one_line_and_reraises_same_object(capfd):
    fake = Fake()
    error = RuntimeError("coordinator down")
    fake.coordinator.heartbeat_reply = error
    worker = ParallelWorker(fake.ports())
    worker._active_lease = _watchdog_lease()
    with pytest.raises(RuntimeError) as raised:
        worker._current()
    assert raised.value is error
    (line,) = _diagnostic_lines(capfd.readouterr().err, "WORKER_CURRENT_HEARTBEAT_EXCEPTION")
    assert line["worker_id"] == "w1"
    assert line["error_type"] == "RuntimeError"
    assert line["error_message"] == "coordinator down"
    assert line["frames"]
    assert "elapsed_s" in line and "now_s" in line


def test_current_heartbeat_exception_lines_are_bounded_per_worker(capfd):
    fake = Fake()
    fake.coordinator.heartbeat_reply = RuntimeError("down")
    worker = ParallelWorker(fake.ports())
    worker._active_lease = _watchdog_lease()
    for _ in range(25):
        with pytest.raises(RuntimeError):
            worker._current()
    lines = _diagnostic_lines(capfd.readouterr().err, "WORKER_CURRENT_HEARTBEAT_EXCEPTION")
    assert len(lines) == 20


def _capture_sealed_decisions(fake):
    sealed = []
    original = fake.results.seal_attempt
    def seal(lease, decision):
        sealed.append(decision)
        return original(lease, decision)
    fake.results.seal_attempt = seal
    return sealed


def test_a_pre_motion_teacher_refusal_after_the_start_ack_is_committed_as_a_teacher_attempt_that_did_not_pass():
    from so101_demo.parallel_batch.contracts.common import TeacherPreMotionRefused
    from so101_demo.parallel_batch.dynamic_manifest import teacher_attempt_status
    fake = Fake(RunMode.EXECUTE)
    sealed = _capture_sealed_decisions(fake)
    diagnostics = {"start_acknowledged": True, "broker_motion_enabled": False, "goal_dispatched": False}
    def refuse(lease, chain):
        raise TeacherPreMotionRefused("TEACHER_RESET_BINDING_SOURCE_INVALID", diagnostics)
    fake.runtime.admit_pose = refuse
    result = ParallelWorker(fake.ports()).run_one()
    assert result.stopped_reason == "POINT_TERMINAL" and result.failure_boundary == "admit_pose"
    (decision,) = sealed
    assert decision.status is AttemptStatus.INDETERMINATE
    assert (decision.teacher_execution_status, decision.teacher_task_result) == ("INDETERMINATE", "UNCONFIRMED")
    assert teacher_attempt_status(decision.teacher_execution_status, decision.teacher_task_result) is decision.status
    assert decision.act_data_status == "INVALID"
    assert decision.reason.startswith("TEACHER_FENCED_BEFORE_MOTION:TEACHER_RESET_BINDING_SOURCE_INVALID")
    assert decision.act_data_reason == decision.reason
    assert result.terminal_status is AttemptStatus.INDETERMINATE
    names = event_names(fake)
    assert "ATTEMPT_STARTED" in names or any("START" in name for name in names)
    assert "FINALIZING_STARTED" in names and "RESULT_COMMITTED" in names, "committed through the normal path"
    assert "submit_motion" not in fake.runtime.calls, "no motion was ever submitted"


def test_started_non_pass_outcomes_count_in_the_teacher_attempt_denominator_and_invalid_does_not():
    from so101_demo.parallel_batch.contracts import identity as contracts_identity
    assert AttemptStatus.INDETERMINATE in contracts_identity._TEACHER_STARTED and AttemptStatus.FAILED in contracts_identity._TEACHER_STARTED
    assert AttemptStatus.INVALID not in contracts_identity._TEACHER_STARTED


def test_the_pre_motion_result_is_exactly_the_manifest_free_contract_the_result_store_already_accepts(tmp_path):
    from so101_demo.act.result_store import _check_teacher_manifest, _teacher_claim
    claim = _teacher_claim({"execution_status": "INDETERMINATE", "task_result": "UNCONFIRMED",
                            "data_status": "INVALID", "data_reason": "TEACHER_FENCED_BEFORE_MOTION:X"})
    # an INDETERMINATE/UNCONFIRMED claim asserts nothing positive and needs no Teacher manifest
    assert _check_teacher_manifest(tmp_path / "dynamic" / "dynamic-execute-manifest.json", claim) is None


@pytest.mark.parametrize("boundary,patch", [("reset_point", "reset_point"), ("point_initial_gate", "point_initial_gate")])
def test_a_failure_before_the_start_ack_stays_invalid_even_for_a_teacher_refusal(boundary, patch):
    from so101_demo.parallel_batch.contracts.common import TeacherPreMotionRefused
    fake = Fake(RunMode.EXECUTE)
    sealed = _capture_sealed_decisions(fake)
    def refuse(*args, **kwargs):
        raise TeacherPreMotionRefused("TEACHER_CHANNEL_FENCED")
    setattr(fake.runtime, patch, refuse)
    result = ParallelWorker(fake.ports()).run_one()
    assert result.stopped_reason == "INITIAL_GATE_FAILED" and result.failure_boundary == boundary
    (decision,) = sealed
    assert decision.status is AttemptStatus.INVALID
    assert not hasattr(decision, "teacher_execution_status")
    assert "submit_motion" not in fake.runtime.calls


def test_an_ordinary_pose_admission_failure_keeps_its_invalid_path():
    fake = Fake(RunMode.EXECUTE)
    sealed = _capture_sealed_decisions(fake)
    def refuse(lease, chain):
        raise RuntimeError("TEACHER_CONSUMER_START_AUTHORITY_UNAVAILABLE")
    fake.runtime.admit_pose = refuse
    ParallelWorker(fake.ports()).run_one()
    (decision,) = sealed
    assert decision.status is AttemptStatus.INVALID and not hasattr(decision, "teacher_task_result")
