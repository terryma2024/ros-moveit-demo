"""Teacher/ACT decoupling (Phase A4c): the Teacher holds no data side at all.

The Recorder is an independent process. From the Teacher's side the only thing collection changes is the confirmed final
normal-stop proof (`final_stop_proof_enabled`, set by `--collection on`): every request it sends and every field of its
result are otherwise identical with collection off, on, and under each fault, because every fault is Recorder-side or
orchestrator-side and cannot reach the Teacher process. The data-side consumer logic that used to be tested here moved,
with the code, to `test_act_recorder_data_side.py`.
"""

import copy
import time
from types import SimpleNamespace

import pytest

from so101_demo.act.teacher_event_stream import StreamEventSink
from so101_demo.core.domain import ActionStatus, State
from so101_demo.core.dynamic_pick import DYNAMIC_MOTION_STATES
from so101_demo.core.workflow import SO101_WORKFLOW
from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
from test_dynamic_teacher_result import START, _adapter, _end_sampler, _end_pose, _sample

CONTEXT = dict(broker_socket="/tmp/component-only.sock", owner="teacher", session_id="s",
               attempt_id="a", lease_token="t")
FORBIDDEN = {"revoke", "cancel", "pause", "reset", "fence", "teacher_stop", "stop_teacher"}
TEACHER_FIELDS = ("status", "failure", "current_state", "state_trace", "teacher_execution_status",
                  "teacher_task_result", "teacher_start_observation", "teacher_end_observation",
                  "process_diagnostics")


def _workflow_states():
    """Every action state of the shared workflow up to DONE; the last one (RETREAT) closes the expert sequence."""
    state, trace = State.IDLE, []
    while state not in SO101_WORKFLOW.terminal_states:
        state = SO101_WORKFLOW.transitions[state][0]
        if state in SO101_WORKFLOW.action_states:
            trace.append(state)
    return trace


def _connection(operations, boundary, content=None):
    sequence = [0]

    def request(operation, context, **extra):
        operations.append(operation)
        if content is not None:
            content.append((operation, {key: value for key, value in extra.items() if key != "verified_reset_boundary"}))
        if operation == "teacher_phase_begin_v1":
            sequence[0] += 1
            return dict(accepted=True, phase=extra["phase"], phase_sequence=sequence[0], reset_epoch=3,
                        command_authority=False, verified_reset_boundary=copy.deepcopy(boundary))
        if operation == "teacher_phase_finish_v1":
            return dict(accepted=True, phase=extra["phase"], phase_sequence=sequence[0], reset_epoch=3,
                        command_authority=False)
        pytest.fail("the Teacher child reached an unexpected broker operation: " + operation)
    return SimpleNamespace(request=request)


def _run_teacher(monkeypatch, *, collection=False):
    """Perform the whole DONE workflow through the real perform/finish; `collection` is `--collection on`."""
    import rclpy
    operations, content, published = [], [], []
    monkeypatch.setattr(rclpy, "spin_once", lambda *args, **kwargs: None)
    if collection:
        monkeypatch.setattr(RosDynamicMujocoExecution, "final_stop_proof_enabled", True)
        monkeypatch.setattr(RosDynamicMujocoExecution, "_normal_stop_proof",
                            lambda self: self._publish_teacher_event("normal_stop", {"proof": {}}) or {})
    adapter = _adapter()
    adapter._node = SimpleNamespace(get_clock=lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=2_000_000_000)))
    adapter._event_stream = SimpleNamespace(offer=lambda kind, payload: published.append(kind) or True)
    adapter._event_sink = StreamEventSink(adapter._event_stream)
    adapter._scene_source_binding = None
    adapter._scene_source_observer = None
    adapter._targets.for_state = lambda state: object()
    adapter._before_micro_lift, adapter._attached = None, False
    clock_progress = adapter._progress

    def progress():
        clock_progress()
        RosDynamicMujocoExecution._progress(adapter)
    adapter._progress = progress
    start = _sample(START[:3], START[3:], time_s=1.0)

    def snapshot():
        adapter._progress()
        return start
    adapter._snapshot = snapshot
    for name in ("_motion", "_attach", "_detach_or_sync", "_open_supported_gripper", "_wait_release",
                 "_validate_final", "_set_touch_collision"):
        setattr(adapter, name, lambda *args, **kwargs: None)
    adapter._command_gripper = lambda state, target, before=None: adapter._record(state, start, start)
    adapter._wait_stable = lambda predicate, duration, timeout: start
    results = []
    for state in _workflow_states():
        target = object() if state in DYNAMIC_MOTION_STATES else None
        results.append(adapter.perform(state, target))
    _end_sampler(adapter, _end_pose()[:3], _end_pose()[3:])
    adapter.finish(SimpleNamespace(status=SimpleNamespace(value="DONE"), current_state=State.DONE,
                                   transition_count=len(results), state_trace=(State.IDLE, State.DONE),
                                   failure=None))
    return adapter, results, operations, content, published


def _teacher_view(adapter):
    return {name: copy.deepcopy(adapter._document[name]) for name in TEACHER_FIELDS}


def test_the_baseline_teacher_runs_to_a_passing_done_and_claims_no_data_verdict(monkeypatch):
    adapter, results, operations, _, published = _run_teacher(monkeypatch)
    assert all(result.status is ActionStatus.SUCCEEDED for result in results), [
        (state.value, result.failure.message) for state, result in zip(_workflow_states(), results)
        if result.status is not ActionStatus.SUCCEEDED]
    assert len(results) >= 12
    document = adapter._document
    assert document["status"] == "DONE" and document["teacher_execution_status"] == "COMPLETED"
    assert document["teacher_task_result"]["result"] == "PASS"
    assert document["act_data_status"] == "DISABLED" and "act_data_invalid" not in document
    # REPLACED_BY V2 events: one phase_begin and one phase_finish per state, and the run ends with normal end facts
    assert published.count("phase_begin") == len(results) == published.count("phase_finish")
    assert _workflow_states()[-1] is State.RETREAT
    assert "sequence_complete" not in published and published[-1] == "terminal"


@pytest.mark.parametrize("collection", [False, True])
def test_the_teacher_is_identical_with_collection_off_and_on(monkeypatch, collection):
    """Request content and every Teacher manifest field are the same whether an independent Recorder is collecting.

    Faults (`recorder_absent`, `recorder_late`, `queue_overflow`, `source_gap`, `output_write_failure`) act on the
    Recorder or the orchestrator and never on this process; their Teacher argv equality is held in
    test_act_collection_orchestration. The one Teacher-side effect of `--collection on` is the final normal-stop proof,
    which is a stream event here (the owner request itself is stubbed identically for both runs).
    """
    baseline, base_results, base_operations, base_content, base_published = _run_teacher(monkeypatch)
    adapter, results, operations, content, published = _run_teacher(monkeypatch, collection=collection)
    assert [result.status for result in results] == [result.status for result in base_results]
    assert operations == base_operations == [] and content == base_content == []
    assert _teacher_view(adapter) == _teacher_view(baseline)
    assert adapter._document["act_data_status"] == baseline._document["act_data_status"] == "DISABLED"
    assert ("normal_stop" in published) is collection
    assert [kind for kind in published if kind != "normal_stop"] == [
        kind for kind in base_published if kind != "normal_stop"]


FORMER_TEACHER_SIDE_DATA_NAMES = (
    "_service_data_side", "_drain_collection", "_drain_teacher_events_step", "_step_data_capture_start",
    "_bind_collection_sources", "_refresh_collection_scene", "_finish_data_side", "_latch_act_data_invalid",
    "_record_data_failure_context", "record_data_failure", "_data_invalid_latched", "_act_data_status",
    "_scene_transaction", "_publish_scene_association", "_associate_scene_best_effort", "_plan_attach_association",
    "_attach_association", "_detach_association", "_consume_teacher_event", "_data_retain_dispatch",
    "_capture_native_initial_step", "_finish_native_collection", "original_collection_worlds",
    "_drain_world_sources", "_step_data_initial_boundary")


def test_the_first_state_has_nothing_between_the_start_observation_and_the_first_motion(monkeypatch):
    import rclpy
    monkeypatch.setattr(rclpy, "spin_once", lambda *args, **kwargs: None)
    monkeypatch.setattr(time, "sleep", lambda duration: pytest.fail("the first state slept"))
    events = []
    adapter = _adapter()
    adapter._node = object()
    adapter._scene_source_binding, adapter._scene_source_observer = None, None
    start = _sample(START[:3], START[3:], time_s=1.0)
    adapter._snapshot = lambda: events.append("snapshot") or start
    adapter._command_gripper = lambda state, target, before=None: events.append("first.motion")
    assert adapter.perform(State.PREPARE_OPEN_GRIPPER, None).status is ActionStatus.SUCCEEDED
    assert events == ["snapshot", "first.motion"]


def test_a_teacher_own_state_source_that_is_unavailable_is_still_an_execution_error(monkeypatch):
    from so101_demo.core.domain import Failure
    adapter = _adapter()

    def unavailable():
        raise RuntimeError("DYNAMIC_EVIDENCE_TIMEOUT")
    adapter._snapshot = unavailable
    result = adapter.perform(State.PREPARE_OPEN_GRIPPER, None)
    assert result.status is ActionStatus.FAILED and result.failure.code == "DYNAMIC_EVIDENCE_TIMEOUT"
    assert adapter._document["last_error"] == "DYNAMIC_EVIDENCE_TIMEOUT"
    # ... and the manifest classifies it from the Teacher fields, not from any data status.
    failed = SimpleNamespace(status=SimpleNamespace(value="ERROR"), current_state=State.ERROR, transition_count=0,
                             state_trace=(State.IDLE, State.ERROR), failure=Failure(
                                 result.failure.category, "DYNAMIC_EVIDENCE_TIMEOUT", "x"))
    adapter.finish(failed)
    assert adapter._document["teacher_execution_status"] == "FAILED"
    assert adapter._document["teacher_task_result"]["result"] == "UNCONFIRMED"
