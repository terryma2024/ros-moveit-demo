"""CP-3457: the P3 review rework.

1. The Teacher's own execution bound stays at the frozen 240 s when the stage and lease bounds are raised for offline processing.
2. The Teacher's window closes when the Teacher exits; the processor's wait is capped by the time left on the lease.
3. A `normal_stop` after the terminal event is refused.
4. The QC memo is bound to the source of the QC code.
"""

import copy
import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.act import episode_qc, qc_memo
from so101_demo.act.offline import orchestration
from so101_demo.act.offline.orchestration import MIN_PROCESSING_S, SEAL_MARGIN_S, OfflineCollection
from so101_demo.parallel_batch import contracts
from so101_demo.parallel_batch.contracts import RunMode, teacher_execution_bound_s

from test_p3_offline_switch import (IDENTITY, LEASE, Clock, FakePilot, FakeProcesses, ScriptedGroup, _decision, _exit_code,
                                    collection_for, pilot_factory, worker_runtime)
from test_p3_qc_memo import episode, paths
from paths import PACKAGE_ROOT

PACKAGE = PACKAGE_ROOT
ACT_FILE = PACKAGE / "config/mujoco/parallel_batch_v3_act_offline.yaml"
ORIGINAL_FILE = PACKAGE / "config/mujoco/parallel_batch_v3.yaml"


@pytest.fixture(autouse=True)
def _fresh_fake_pilots():
    FakePilot.instances.clear()
    FakePilot.log = None
    yield
    FakePilot.instances.clear()
    FakePilot.log = None


# ---- 1. the Teacher's bound is separate from the stage bound ---------------------------------------------------------------------

def test_the_act_config_raises_the_stage_and_lease_bounds_and_the_teacher_bound_stays_at_the_frozen_value():
    act = contracts.load_parallel_runtime_config_v3(ACT_FILE)
    original = contracts.load_parallel_runtime_config_v3(ORIGINAL_FILE)
    assert (act.executing_hard_timeout_s, act.lease_duration_s) == (1500.0, 1500.0)
    assert contracts.TEACHER_EXECUTION_BOUND_S == 240.0
    assert teacher_execution_bound_s(act) == 240.0, "the stage bound is 1500 s; the Teacher's bound is not"
    assert teacher_execution_bound_s(original) == 240.0
    differing = {name for name in act.__slots__ if getattr(act, name) != getattr(original, name)}
    assert differing == {"executing_hard_timeout_s", "lease_duration_s"}
    assert "teacher_execution_timeout_s" not in {item.name for item in contracts.fields(contracts.ParallelRuntimeConfigV3)}


def test_the_teacher_bound_helper_never_exceeds_the_frozen_value_and_honours_a_smaller_one():
    assert teacher_execution_bound_s(SimpleNamespace(executing_hard_timeout_s=240.0)) == 240.0
    assert teacher_execution_bound_s(SimpleNamespace(executing_hard_timeout_s=1500.0)) == 240.0
    assert teacher_execution_bound_s(SimpleNamespace(executing_hard_timeout_s=10.0)) == 10.0
    assert teacher_execution_bound_s(SimpleNamespace()) == 180.0


def test_the_stage_and_lease_floors_still_refuse_a_value_below_the_original(tmp_path):
    for field, bad in (("executing_hard_timeout_s", "239.0"), ("lease_duration_s", "299.0")):
        broken = tmp_path / f"{field}.yaml"
        broken.write_text(ACT_FILE.read_text().replace(f"{field}: 1500.0", f"{field}: {bad}"))
        with pytest.raises(contracts.ContractError, match="FROZEN_RUNTIME_VALUE"):
            contracts.load_parallel_runtime_config_v3(broken)


def test_versions_four_to_six_keep_every_pin_exactly():
    for pins in (contracts.FROZEN_RUNTIME_VALUES_V4, contracts.FROZEN_RUNTIME_VALUES_V5, contracts.FROZEN_RUNTIME_VALUES_V6):
        assert pins["executing_hard_timeout_s"] == 240.0 and pins["lease_duration_s"] == 300.0
    assert contracts._FROZEN_RUNTIME_VALUES_V3["executing_hard_timeout_s"] == 240.0
    # the v3 closed field list is exactly the dataclass (the v4 work froze that surface) and the v4 list is untouched by this change
    assert set(contracts.EXECUTION_V3_FIELDS) == {item.name for item in contracts.fields(contracts.ParallelRuntimeConfigV3)} - {
        "schema_version", "start_guard"}


def test_a_teacher_that_runs_past_240_s_is_still_waited_for_only_240_s_under_the_act_config(tmp_path, monkeypatch):
    """`execute_result` waits for the Teacher child no longer than the Teacher bound, whatever the stage bound is."""
    import so101_demo.runtime.parallel_ros_runtime as runtime_module
    from so101_demo.parallel_batch.contracts import AttemptStatus
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts
    from test_parallel_ros_runtime import _lease

    observations = iter((100.0, 200.0, 300.0, 341.0, 342.0))   # the deadline is 100 + 240 = 340 s
    waitpid_calls = []
    monkeypatch.setattr(runtime_module.time, "monotonic", lambda: next(observations))
    monkeypatch.setattr(runtime_module.time, "sleep", lambda _duration: None)
    monkeypatch.setattr(os, "waitpid", lambda pid, options: (waitpid_calls.append((pid, options)) or (0, 0)))
    ports = ParallelRosRuntimePorts(SimpleNamespace(worker_root=tmp_path, session_id="session-1"), catalog={},
                                    config=contracts.load_parallel_runtime_config_v3(ACT_FILE))
    receipt = ports.execute_result(_lease(), SimpleNamespace(reset_epoch="reset-17"), SimpleNamespace(pid=417))
    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert waitpid_calls == [(417, os.WNOHANG), (417, os.WNOHANG)], "it gave up at 340 s, not at 1600 s"


def _worker_with(config):
    from test_parallel_batch_worker import Fake

    fake = Fake(RunMode.EXECUTE)
    ports = fake.ports()
    ports["config"] = config
    return fake, ports


def test_the_workers_teacher_deadline_guard_still_fires_at_240_s_under_the_act_config(monkeypatch):
    from test_parallel_batch_worker import _expert_blocked_with_a_lost_coordinator, _wait_for_watchdog_fault
    from test_parallel_batch_worker import Fake

    act = contracts.load_parallel_runtime_config_v3(ACT_FILE)
    real_ports = Fake.ports
    monkeypatch.setattr(Fake, "ports", lambda self: {**real_ports(self), "config": act})
    fake = Fake(RunMode.EXECUTE)
    worker, thread, result, release = _expert_blocked_with_a_lost_coordinator(fake)
    _wait_for_watchdog_fault(worker)
    time.sleep(0.1)
    assert "cancel_motion" not in fake.runtime.calls
    fake.clock.now += 240.0 - 1.0
    time.sleep(0.1)
    assert "cancel_motion" not in fake.runtime.calls, "cancelled before the Teacher bound"
    fake.clock.now += 1.0
    deadline = time.monotonic() + 2.0
    while "confirm_no_controller_goal" not in fake.runtime.calls:
        assert time.monotonic() < deadline, "the Teacher deadline guard never fired at 240 s under the ACT config"
        time.sleep(0.01)
    receipts = [call for call in fake.runtime.calls if isinstance(call, tuple) and call[0] == "revocation"]
    assert dict(receipts[0][3])["reason"] == "TEACHER_EXECUTION_DEADLINE"
    release.set()
    thread.join(3.0)
    assert not thread.is_alive()


# ---- 2. the Teacher's window closes when the Teacher exits ---------------------------------------------------------------------

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
    from so101_demo.runtime.parallel_worker_runtime import ExecutionCompletionReceipt

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


# ---- 2. the processor's wait is capped by the time left on the lease ------------------------------------------------------------

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


# ---- 3. a normal_stop after the terminal event is refused ---------------------------------------------------------------------

def _event(seq, kind, sim_ns, **payload):
    return {"seq": seq, "type": kind, "sim_time_ns": sim_ns, "session_id": "s", "reset_epoch": 1, "attempt_id": "a",
            "payload": payload}


def test_a_normal_stop_after_the_terminal_event_is_counted_and_never_becomes_the_episodes_stop():
    from so101_demo.act.offline.scan import timeline

    events = [_event(1, "reset_complete", 1_000, simulation_time_s=1e-6), _event(2, "phase_begin", 2_000, goal_sent=True),
              _event(3, "normal_stop", 5_000), _event(4, "terminal", 6_000), _event(5, "normal_stop", 9_000)]
    facts = timeline(events)
    assert facts["normal_stop_after_terminal"] == 1
    assert facts["normal_stop_sim_ns"] == 5_000 and facts["final_normal_stop_seq"] == 3 and facts["normal_stop_count"] == 1
    clean = timeline(events[:4])
    assert clean["normal_stop_after_terminal"] == 0 and clean["normal_stop_sim_ns"] == 5_000


def test_the_scan_names_a_stop_after_the_terminal_as_a_reason(tmp_path):
    from std_msgs.msg import String

    from so101_demo.act.offline.bag_io import BagWriter
    from so101_demo.act.offline.raw_recorder import EVENTS_TOPIC
    from so101_demo.act.offline.scan import scan_bag

    def scan(events):
        bag = tmp_path / f"bag{len(events)}"
        writer = BagWriter(bag)
        try:
            writer.create(EVENTS_TOPIC, "std_msgs/msg/String")
            for index, event in enumerate(events):
                writer.write(EVENTS_TOPIC, String(data=json.dumps(event)), index + 1)
        finally:
            writer.close()
        return scan_bag(bag)["reasons"]

    base = [_event(1, "reset_complete", 1_000, simulation_time_s=1e-6), _event(2, "phase_begin", 2_000, goal_sent=True),
            _event(3, "normal_stop", 5_000), _event(4, "terminal", 6_000)]
    assert not any(reason.startswith("OFFLINE_NORMAL_STOP_AFTER_TERMINAL") for reason in scan(base))
    assert "OFFLINE_NORMAL_STOP_AFTER_TERMINAL: 1" in scan(base + [_event(5, "normal_stop", 9_000)])


# ---- 4. the memo is bound to the QC code ----------------------------------------------------------------------------------------

def test_the_code_digest_covers_the_qc_chain_and_is_stable():
    digest = qc_memo.code_digest()
    assert len(digest) == 64 and digest == qc_memo.code_digest()
    assert {"episode_qc", "episode_audit", "recorder", "qc_memo"} <= set(qc_memo.CODE_MODULES)
    package = Path(qc_memo.__file__).parent
    assert all((package / f"{name}.py").is_file() for name in qc_memo.CODE_MODULES)


def test_a_memo_written_by_other_qc_code_triggers_a_full_recompute(tmp_path, monkeypatch):
    from so101_demo.act import result_store

    root, scope, inputs, teacher, report, report_path = episode(tmp_path)
    monkeypatch.setattr(qc_memo, "code_digest", lambda: "a" * 64)          # the QC code that wrote the memo
    qc_memo.write_memo(report_path, report, **paths(root, scope, inputs, teacher))
    assert qc_memo.memo_matches(report_path, report, **paths(root, scope, inputs, teacher)) is True
    monkeypatch.setattr(qc_memo, "code_digest", lambda: "b" * 64)          # a Coordinator from another install
    assert qc_memo.memo_matches(report_path, report, **paths(root, scope, inputs, teacher)) is False
    calls = []
    monkeypatch.setattr(episode_qc, "recompute_native_qc", lambda *a, **k: calls.append(1) or copy.deepcopy(report))
    assert result_store._recomputed_or_memoised(report_path, report, episode_root=root, scope=scope, inputs_manifest=inputs,
                                                trust_memo=True, reader=episode_qc.recompute_native_qc) == report
    assert calls == [1], "the code digest differs: recomputed in full"


def test_a_memo_without_a_code_digest_or_with_the_old_schema_is_not_trusted(tmp_path):
    root, scope, inputs, teacher, report, report_path = episode(tmp_path)
    memo = qc_memo.write_memo(report_path, report, **paths(root, scope, inputs, teacher))
    document = json.loads(memo.read_text())
    for change in ({"code_digest": None}, {"schema_version": 1}):
        mutated = {**document, **change}
        if change.get("code_digest", 1) is None:
            del mutated["code_digest"]
        memo.write_text(json.dumps(mutated))
        assert qc_memo.memo_matches(report_path, report, **paths(root, scope, inputs, teacher)) is False, change


# ---- review items 7 and 8: the recorder's reported losses are a recorded fact; the clock-map limit is 2 ms ----------------------

def test_the_transport_loss_the_recorder_reports_is_parsed_into_its_stats():
    from so101_demo.act.offline.raw_recorder import transport_lost_from_log

    log = ("[INFO] recording\n[WARN] [1791425951.943280991] [so101_raw_recorder]: Number of messages lost on the transport layer: 6\n"
           "[INFO] done\n")
    assert transport_lost_from_log(log) == 6
    assert transport_lost_from_log("[INFO] nothing lost\n") == 0
    assert transport_lost_from_log(log + log) == 12


def test_the_clock_map_limit_is_two_milliseconds_and_a_larger_residual_is_a_reason(tmp_path, monkeypatch):
    from so101_demo.act.offline import bag_io, processor, scan

    assert processor.CLOCK_RESIDUAL_LIMIT_NS == 2_000_000
    observed = [918, 2848]                                    # the two real bags
    assert max(observed) * 700 < processor.CLOCK_RESIDUAL_LIMIT_NS

    def run(residual):
        monkeypatch.setattr(bag_io, "bag_info", lambda bag: {"message_count": 1, "duration_ns": 1, "topics": {}})
        monkeypatch.setattr(processor, "load_clock_map", lambda bag, stats_file=None: ({}, {"max_residual_ns": residual}))
        monkeypatch.setattr(scan, "scan_bag", lambda bag, info=None, **loss: {"reasons": [], "timeline": {"identity": None}, "continuity": {},
                                                                      "counts": {}})
        return processor.process_bag(tmp_path / "bag", tmp_path / "out", inputs_manifest=tmp_path / "i.json", lease=LEASE)

    assert not any(reason.startswith("OFFLINE_CLOCK_MAP_INCONSISTENT") for reason in run(2_000_000)["reasons"])
    assert any(reason.startswith("OFFLINE_CLOCK_MAP_INCONSISTENT") for reason in run(2_000_001)["reasons"])


# ---- review item 12: recorder_late records its evidence ----------------------------------------------------------------------

def test_recorder_late_records_when_the_teachers_setup_evidence_was_seen_and_when_the_bag_was_started(tmp_path):
    processes = FakeProcesses()
    collection, point, clock = collection_for(tmp_path, fault="recorder_late", processes=processes, late_delay_s=5.0)
    collection.start_before_teacher()
    trigger = point / "dynamic" / "reachability-observed.json"
    collection.teacher_started_now()
    collection.arm_late_start(trigger)
    trigger.write_text("{}")
    collection._late_thread.join(timeout=10)
    outcome = collection.finish(lease=LEASE)
    evidence = outcome.facts["late_evidence"]
    assert outcome.reason == "RECORDER_STARTED_AFTER_TEACHER" and evidence["delay_s"] == 5.0
    assert evidence["trigger_seen_system_ns"] <= evidence["start_requested_system_ns"]
    assert "bag_first_stamp_ns" in evidence or "bag_first_stamp_error" in evidence


# ---- re-review R1: VALID data needs the memo; a missing or stale memo never costs the Teacher its sealed result -----------------

def test_the_default_memo_check_is_the_real_memo_match(tmp_path, monkeypatch):
    root, scope, inputs, teacher, report, report_path = episode(tmp_path)
    monkeypatch.setattr(episode_qc, "read_qc_report", lambda path: copy.deepcopy(report))
    kwargs = dict(qc_output=report_path, episode_root=root, scope=scope, inputs_manifest=inputs)
    assert orchestration._memo_covers(**kwargs) is False, "no memo yet"
    qc_memo.write_memo(report_path, report, **paths(root, scope, inputs, teacher))
    assert orchestration._memo_covers(**kwargs) is True
    (root / "audit" / "events.jsonl").write_text('{"x": 99}\n')
    assert orchestration._memo_covers(**kwargs) is False, "stale: the episode changed after the memo"
    monkeypatch.setattr(episode_qc, "read_qc_report", lambda path: (_ for _ in ()).throw(ValueError("unreadable")))
    assert orchestration._memo_covers(**kwargs) is False


@pytest.mark.parametrize("memo", ["missing", "stale"])
def test_a_processor_verdict_without_a_covering_memo_is_invalid_data_not_valid_data(tmp_path, memo):
    collection, point, _ = collection_for(tmp_path, memo_check=lambda **kwargs: False)
    collection.start_before_teacher()
    outcome = collection.finish(lease=LEASE, deadline_s=collection._clock() + 100_000.0)
    assert (outcome.data_status, outcome.reason) == ("INVALID", "OFFLINE_QC_MEMO_NOT_VALID")
    assert "qc_report_path" not in outcome.facts


@pytest.mark.parametrize("memo", ["missing", "stale"])
def test_a_missing_or_stale_memo_keeps_the_teacher_pass_sealed_instead_of_losing_it_to_the_lease_deadline(tmp_path, monkeypatch, memo):
    from act_result_teacher import sealed_teacher
    from test_act_result_schema3 import setup_result
    from test_parallel_worker_runtime import _lease

    from so101_demo.act.collection_orchestration import CollectionOptions

    monkeypatch.setattr(orchestration, "PilotRecording", pilot_factory())
    monkeypatch.setattr(orchestration, "_memo_covers", lambda **kwargs: False)         # no memo, or a memo of other bytes
    events = []
    runtime, group, events, clock = worker_runtime(tmp_path / "w", CollectionOptions("on"), events=events,
                                                   group=ScriptedGroup(events, FakeProcesses()))
    runtime.start_physical_runtime()
    lease = _lease()
    runtime.reset_and_validate_point(lease)
    baseline = _decision()
    decision = runtime._finish_collection(lease, baseline)
    assert (decision.act_data_status, decision.act_data_reason) == ("INVALID", "OFFLINE_QC_MEMO_NOT_VALID")
    assert decision.qc_report_path is None, "the store never sees a QC report it would have to recompute"
    assert (decision.status, decision.teacher_execution_status, decision.teacher_task_result) == (
        baseline.status, baseline.teacher_execution_status, baseline.teacher_task_result)
    (tmp_path / "store").mkdir()
    store, seal, document, inputs = setup_result(tmp_path / "store", monkeypatch)
    monkeypatch.setattr(episode_qc, "recompute_native_qc", lambda *a, **k: pytest.fail("the store recomputed the QC (290 s)"))
    location = store.seal(seal, teacher=sealed_teacher(store, "PASSED", data=decision.act_data_status, reason=decision.act_data_reason))
    sealed = json.loads((location / "result.json").read_bytes())
    assert sealed["status"] == "PASSED" and sealed["act_data_status"] == "INVALID" and sealed["act_data_qc"] == "NOT_RUN"
    assert _exit_code(sealed, monkeypatch) == 3


# ---- re-review R2: the Teacher has exited only when the child really exited -----------------------------------------------------

def _expert_runtime(tmp_path, monkeypatch, *, child_exited, cancel_result):
    from test_parallel_worker_runtime import _lease, _write_numeric

    from so101_demo.act.collection_orchestration import CollectionOptions
    from so101_demo.runtime.parallel_worker_runtime import ExecutionCompletionReceipt

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
        monkeypatch.setattr(runtime_module.time, "monotonic", lambda: next(observations))
        monkeypatch.setattr(runtime_module.time, "sleep", lambda _duration: None)
        monkeypatch.setattr(os, "waitpid", (lambda pid, options: (0, 0)) if alive else (lambda pid, options: (pid, 0)))
        ports = ParallelRosRuntimePorts(SimpleNamespace(worker_root=tmp_path, session_id="session-1"), catalog={},
                                        config=SimpleNamespace(executing_hard_timeout_s=240.0))
        receipt = ports.execute_result(_lease(), SimpleNamespace(reset_epoch="reset-17"), SimpleNamespace(pid=417))
        assert receipt.teacher_child_exited is (not alive)
