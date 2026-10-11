"""The Teacher's window closes when the Teacher exits, and the processor's wait is capped by the time left on the lease."""

import json
import os
import threading
import time
from types import SimpleNamespace

import pytest

from so101_demo.act.offline import orchestration
from so101_demo.act.offline.orchestration import MIN_PROCESSING_S, SEAL_MARGIN_S, OfflineCollection
from so101_demo.parallel_batch.contracts import RunMode

from test_offline_recording_switch import (LEASE, FakePilot, FakeProcesses, ScriptedGroup, _decision, _exit_code,
                                    collection_for, pilot_factory, worker_runtime)


@pytest.fixture(autouse=True)
def _fresh_fake_pilots():
    FakePilot.instances.clear()
    FakePilot.log = None
    yield
    FakePilot.instances.clear()
    FakePilot.log = None


# ---- the Teacher's window closes when the Teacher exits ---------------------------------------------------------------------

def test_the_teacher_window_is_closed_before_the_data_work_and_the_deadline_guard_no_longer_applies(monkeypatch):
    from test_parallel_batch_worker import Fake, _wait_for_watchdog_fault
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
    from test_parallel_worker_runtime import _write_numeric
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
    from test_parallel_worker_runtime import _lease

    lease = _lease()
    runtime.reset_and_validate_point(lease)
    runtime.localize_and_admit_pose(lease, "broker-result")
    runtime.execute_expert(lease, admitted)
    assert order == ["teacher_receipt", "teacher_exit_callback", "collection"]


# ---- the processor's wait is capped by the time left on the lease ------------------------------------------------------------

def _collection_with_deadline(tmp_path, *, left_s, processes=None, **kwargs):
    processes = processes or FakeProcesses()
    collection, point, clock = collection_for(tmp_path, processes=processes, **kwargs)
    collection.start_before_teacher()
    deadline = clock() + left_s
    return collection, processes, deadline, clock


def test_the_processor_wait_is_the_time_left_on_the_lease_minus_the_seal_margin_when_that_is_shorter_than_the_cap(tmp_path):
    processes = FakeProcesses(exits=False, outputs=None)
    collection, processes, deadline, _clock = _collection_with_deadline(tmp_path, left_s=500.0, processes=processes)
    outcome = collection.finish(lease=LEASE, deadline_s=deadline)
    assert ("wait_exit", 500.0 - SEAL_MARGIN_S) in processes.events
    assert (outcome.data_status, outcome.reason) == ("INVALID", f"OFFLINE_PROCESSOR_TIMEOUT: {500.0 - SEAL_MARGIN_S:.0f}s")
    assert ("terminate", orchestration.PROCESSOR_TERM_GRACE_S) in processes.events
    assert outcome.facts["processing_budget"]["budget_s"] == 440.0 and outcome.facts["processing_budget"]["seal_margin_s"] == SEAL_MARGIN_S


def test_with_plenty_of_time_left_the_cap_is_the_fixed_bound(tmp_path):
    collection, processes, deadline, _clock = _collection_with_deadline(tmp_path, left_s=100_000.0)
    outcome = collection.finish(lease=LEASE, deadline_s=deadline)
    assert outcome.data_status == "VALID" and ("wait_exit", orchestration.PROCESSING_TIMEOUT_S) in processes.events


@pytest.mark.parametrize("left_s", [SEAL_MARGIN_S + MIN_PROCESSING_S - 0.5, SEAL_MARGIN_S, 10.0, -5.0])
def test_without_enough_time_left_the_processor_is_not_started_and_the_data_is_invalid(tmp_path, left_s):
    collection, processes, deadline, _clock = _collection_with_deadline(tmp_path, left_s=left_s)
    outcome = collection.finish(lease=LEASE, deadline_s=deadline)
    assert outcome.data_status == "INVALID" and outcome.reason.startswith("OFFLINE_PROCESSOR_NO_TIME_LEFT")
    assert processes.specs == [] and FakePilot.instances[0].finished, "the bag was still closed"


def test_just_enough_time_starts_the_processor(tmp_path):
    collection, processes, deadline, _clock = _collection_with_deadline(tmp_path, left_s=SEAL_MARGIN_S + MIN_PROCESSING_S + 1.0)
    assert collection.finish(lease=LEASE, deadline_s=deadline).data_status == "VALID"
    assert ("wait_exit", MIN_PROCESSING_S + 1.0) in processes.events


@pytest.mark.parametrize("scenario", ["no_time_left", "cap_hit"])
def test_the_teacher_pass_survives_the_seal_when_the_budget_is_exhausted(tmp_path, monkeypatch, scenario):
    """Data INVALID because of the budget; the real store seals the Teacher's PASS (never RESULT_AFTER_LEASE_DEADLINE)."""
    from act_result_teacher import sealed_teacher
    from test_act_result_schema3 import setup_result
    from test_parallel_worker_runtime import _lease

    from so101_demo.act.collection_orchestration import CollectionOptions

    monkeypatch.setattr(orchestration, "PilotRecording", pilot_factory())
    processor = FakeProcesses(exits=False, outputs=None)
    events = []
    runtime, group, events, clock = worker_runtime(tmp_path / "w", CollectionOptions("on"), events=events,
                                                   group=ScriptedGroup(events, processor))
    runtime.start_physical_runtime()
    lease = _lease()                        # issued 10, deadline 310 on the worker tests' clock (the recorder clock starts at 100)
    runtime.reset_and_validate_point(lease)
    if scenario == "no_time_left":
        clock.now = lease.lease_deadline_monotonic_s - SEAL_MARGIN_S - 10.0       # the Teacher ran long: 10 s of budget remain
    baseline = _decision()
    decision = runtime._finish_collection(lease, baseline)
    assert decision.act_data_status == "INVALID" and decision.qc_report_path is None
    expected = "OFFLINE_PROCESSOR_NO_TIME_LEFT" if scenario == "no_time_left" else "OFFLINE_PROCESSOR_TIMEOUT"
    assert decision.act_data_reason.startswith(expected)
    assert (decision.status, decision.reason, decision.teacher_execution_status, decision.teacher_task_result) == (
        baseline.status, baseline.reason, baseline.teacher_execution_status, baseline.teacher_task_result)
    assert (scenario == "cap_hit") == any(spec.role == "act-offline-processor" for spec in group.specs)
    (tmp_path / "store").mkdir()
    store, seal, document, inputs = setup_result(tmp_path / "store", monkeypatch)
    claim = sealed_teacher(store, "PASSED", data=decision.act_data_status, reason=decision.act_data_reason)
    location = store.seal(seal, teacher=claim)
    sealed = json.loads((location / "result.json").read_bytes())
    assert sealed["status"] == "PASSED" and sealed["teacher_task_result"] == "PASS" and sealed["act_data_status"] == "INVALID"
    assert _exit_code(sealed, monkeypatch) == 3


def test_the_runtime_passes_the_lease_deadline_to_the_collection(tmp_path, monkeypatch):
    from test_parallel_worker_runtime import _lease

    from so101_demo.act.collection_orchestration import CollectionOptions

    monkeypatch.setattr(orchestration, "PilotRecording", pilot_factory())
    seen = {}
    real = OfflineCollection.finish
    monkeypatch.setattr(OfflineCollection, "finish", lambda self, **kwargs: seen.update(kwargs) or real(self, **kwargs))
    events = []
    runtime, group, events, clock = worker_runtime(tmp_path, CollectionOptions("on"), events=events,
                                                   group=ScriptedGroup(events, FakeProcesses(returncode=3, outputs="invalid")))
    runtime.start_physical_runtime()
    lease = _lease()
    runtime.reset_and_validate_point(lease)
    runtime._finish_collection(lease, _decision())
    assert seen["deadline_s"] == lease.lease_deadline_monotonic_s == 310.0

# ---- the Teacher has exited only when the child really exited -----------------------------------------------------

def _expert_runtime(tmp_path, monkeypatch, *, child_exited, cancel_result):
    from test_parallel_worker_runtime import _lease, _write_numeric

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
    from test_parallel_ros_runtime import _lease

    for alive in (True, False):
        observations = iter((100.0, 200.0, 341.0, 342.0))
        monkeypatch.setattr(time, "monotonic", lambda: next(observations))
        monkeypatch.setattr(time, "sleep", lambda _duration: None)
        monkeypatch.setattr(os, "waitpid", (lambda pid, options: (0, 0)) if alive else (lambda pid, options: (pid, 0)))
        ports = ParallelRosRuntimePorts(SimpleNamespace(worker_root=tmp_path, session_id="session-1"), catalog={},
                                        config=SimpleNamespace(executing_hard_timeout_s=240.0))
        receipt = ports.execute_result(_lease(), SimpleNamespace(reset_epoch="reset-17"), SimpleNamespace(pid=417))
        assert receipt.teacher_child_exited is (not alive)
