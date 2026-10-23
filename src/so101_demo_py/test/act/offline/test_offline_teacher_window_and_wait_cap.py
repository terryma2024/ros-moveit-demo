"""The Teacher's window closes when the Teacher exits."""

import os
import threading
import time
from types import SimpleNamespace

import pytest

from so101_demo.act.offline import orchestration
from so101_demo.parallel_batch.contracts.common import RunMode

from test_offline_recording_switch import (FakePilot, FakeProcesses, ScriptedGroup, _decision, pilot_factory,
                                           worker_runtime)


@pytest.fixture(autouse=True)
def _fresh_fake_pilots():
    FakePilot.instances.clear()
    FakePilot.log = None
    yield
    FakePilot.instances.clear()
    FakePilot.log = None


# ---- the Teacher's window closes when the Teacher exits ---------------------------------------------------------------------

def test_the_teacher_window_is_closed_before_the_data_work_and_the_deadline_guard_no_longer_applies(monkeypatch):
    from parallel_batch_worker_support import Fake
    from test_parallel_batch_worker_gate_watchdog import _wait_for_watchdog_fault
    from so101_demo.parallel_batch.worker import ParallelWorker

    fake = Fake(RunMode.EXECUTE)
    entered, release, callbacks = threading.Event(), threading.Event(), []
    original_execute = fake.runtime.execute_expert
    original_heartbeat = fake.coordinator.heartbeat
    fake.runtime.bind_teacher_exit = callbacks.append

    def execute_then_process(*args, **kwargs):
        callbacks[-1]()                    # the Teacher exited: the runtime tells the Worker ...
        entered.set()                      # ... and only then does the data work (the offline processing) run
        assert release.wait(5.0)
        return original_execute(*args, **kwargs)

    def lose_watchdog_heartbeat(lease):
        if threading.current_thread().name.startswith("parallel-worker-heartbeat-rpc-") and entered.is_set():
            raise RuntimeError("coordinator lost during processing")
        return original_heartbeat(lease)

    fake.runtime.execute_expert = execute_then_process
    fake.coordinator.heartbeat = lose_watchdog_heartbeat
    worker = ParallelWorker(fake.ports())
    result = []
    thread = threading.Thread(target=lambda: result.append(worker.run_one()))
    thread.start()
    assert entered.wait(1.0)
    _wait_for_watchdog_fault(worker)
    assert worker._teacher_child_running is False and worker._teacher_deadline_stop is None
    fake.clock.now += 100_000.0            # far past any Teacher bound: the processing is not the Teacher
    time.sleep(0.2)
    assert "cancel_motion" not in fake.runtime.calls and not any(
        isinstance(call, tuple) and call[0] == "revocation" for call in fake.runtime.calls)
    release.set()
    thread.join(3.0)
    assert not thread.is_alive()


def test_the_worker_runtime_tells_the_worker_the_teacher_exited_before_it_finishes_the_collection(tmp_path, monkeypatch):
    """The order inside `execute_expert`: Teacher receipt, exit callback, terminal capture, then the collection."""
    from parallel_worker_runtime_support import _write_numeric
    from so101_demo.runtime.parallel_worker_parts.receipts import ExecutionCompletionReceipt

    monkeypatch.setattr(orchestration, "PilotRecording", pilot_factory())
    order = []
    events = []
    runtime, group, events, clock = worker_runtime(
        tmp_path, __import__("so101_demo.act.collection_orchestration", fromlist=["CollectionOptions"]).CollectionOptions("on"),
        events=events, group=ScriptedGroup(events, FakeProcesses(returncode=3, outputs="invalid")),
        localize=lambda _lease, _result: SimpleNamespace(reset_epoch="reset-7"),
        capture_numeric_evidence=lambda _lease, _localized, root, boundary: _write_numeric(root, boundary + 1.0),
        admit_pose=lambda _lease, value: admitted, publish_pose=lambda value: True, resume_physics=lambda _lease, _reset: True,
        execute_result=lambda _lease, _admitted, _child: order.append("teacher_receipt") or ExecutionCompletionReceipt(_decision(), 30.0))
    admitted = SimpleNamespace(reset_epoch="reset-7", pose="accepted")
    runtime.bind_teacher_exit(lambda: order.append("teacher_exit_callback"))
    real_finish = runtime._finish_collection
    runtime._finish_collection = lambda lease, decision: order.append("collection") or real_finish(lease, decision)
    runtime.start_physical_runtime()
    from parallel_worker_runtime_support import _lease

    lease = _lease()
    runtime.reset_and_validate_point(lease)
    runtime.localize_and_admit_pose(lease, "broker-result")
    runtime.execute_expert(lease, admitted)
    assert order == ["teacher_receipt", "teacher_exit_callback", "collection"]


# ---- the Teacher has exited only when the child really exited -----------------------------------------------------

def _expert_runtime(tmp_path, monkeypatch, *, child_exited, cancel_result):
    from parallel_worker_runtime_support import _lease, _write_numeric

    from so101_demo.act.collection_orchestration import CollectionOptions
    from so101_demo.runtime.parallel_worker_parts.receipts import ExecutionCompletionReceipt

    monkeypatch.setattr(orchestration, "PilotRecording", pilot_factory())
    order, events = [], []
    runtime, group, events, clock = worker_runtime(
        tmp_path, CollectionOptions("on"), events=events, group=ScriptedGroup(events, FakeProcesses(returncode=3, outputs="invalid")),
        localize=lambda _lease, _result: SimpleNamespace(reset_epoch="reset-7"),
        capture_numeric_evidence=lambda _lease, _localized, root, boundary: _write_numeric(root, boundary + 1.0),
        admit_pose=lambda _lease, value: admitted, publish_pose=lambda value: True, resume_physics=lambda _lease, _reset: True,
        execute_result=lambda _lease, _admitted, _child: ExecutionCompletionReceipt(
            _decision(), 30.0, teacher_child_exited=child_exited))
    admitted = SimpleNamespace(reset_epoch="reset-7", pose="accepted")
    runtime.bind_teacher_exit(lambda: order.append("teacher_exit_callback"))
    runtime.cancel_motion = lambda lease: order.append("cancel_motion") or cancel_result
    real_finish = runtime._finish_collection
    runtime._finish_collection = lambda lease, decision: order.append("collection") or real_finish(lease, decision)
    runtime.start_physical_runtime()
    lease = _lease()
    runtime.reset_and_validate_point(lease)
    runtime.localize_and_admit_pose(lease, "broker-result")
    return runtime, lease, admitted, order, group


def test_a_teacher_child_that_exited_closes_the_window_and_is_not_stopped_again(tmp_path, monkeypatch):
    runtime, lease, admitted, order, group = _expert_runtime(tmp_path, monkeypatch, child_exited=True, cancel_result=True)
    runtime.execute_expert(lease, admitted)
    assert order == ["teacher_exit_callback", "collection"]


def test_a_timed_out_teacher_child_is_stopped_first_and_only_then_is_the_window_closed(tmp_path, monkeypatch):
    runtime, lease, admitted, order, group = _expert_runtime(tmp_path, monkeypatch, child_exited=False, cancel_result=True)
    decision = runtime.execute_expert(lease, admitted)
    assert order == ["cancel_motion", "teacher_exit_callback", "collection"]
    assert (decision.act_data_status, decision.act_data_reason) == ("INVALID", "TEACHER_CHILD_TIMED_OUT")
    assert not any(spec.role == "act-offline-processor" for spec in group.specs), "no processing for a Teacher that did not exit"


def test_a_teacher_child_that_cannot_be_stopped_keeps_the_window_and_its_deadline_guard_open(tmp_path, monkeypatch):
    runtime, lease, admitted, order, group = _expert_runtime(tmp_path, monkeypatch, child_exited=False, cancel_result=False)
    decision = runtime.execute_expert(lease, admitted)
    assert order == ["cancel_motion", "collection"], "the exit callback was never called"
    assert (decision.act_data_status, decision.act_data_reason) == ("INVALID", "TEACHER_CHILD_NOT_STOPPED")
    assert not any(spec.role == "act-offline-processor" for spec in group.specs)


def test_execute_result_reports_a_child_that_is_still_alive_when_the_wait_gives_up(tmp_path, monkeypatch):
    import so101_demo.runtime.parallel_ros_runtime as runtime_module
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts
    from parallel_ros_runtime_support import _lease

    for alive in (True, False):
        observations = iter((100.0, 200.0, 341.0, 342.0))
        monkeypatch.setattr(time, "monotonic", lambda: next(observations))
        monkeypatch.setattr(time, "sleep", lambda _duration: None)
        monkeypatch.setattr(os, "waitpid", (lambda pid, options: (0, 0)) if alive else (lambda pid, options: (pid, 0)))
        ports = ParallelRosRuntimePorts(SimpleNamespace(worker_root=tmp_path, session_id="session-1"), catalog={},
                                        config=SimpleNamespace(executing_hard_timeout_s=240.0))
        receipt = ports.execute_result(_lease(), SimpleNamespace(reset_epoch="reset-17"), SimpleNamespace(pid=417))
        assert receipt.teacher_child_exited is (not alive)
