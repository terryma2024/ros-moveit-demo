"""The switch. The record-only bag recorder is the only data path; the offline processor builds the episode after the
Teacher ended and its verdict (episode seal, fresh-process QC) is the attempt's data verdict.

Everything here runs with fakes: no stack, no ROS graph, no live process. The bag fault helper is tested on a real (tiny) bag.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.act.collection_orchestration import (
    COLLECTION_FAULTS, CollectionOptions, CollectionRefused, collection_from_document, validate_collection_request)
from so101_demo.act.offline.engine import RESULT_SCHEMA
from so101_demo.act.offline import orchestration
from so101_demo.act.offline.orchestration import (
    BAG_FAULTS, FAULT_DROP_COUNT, FAULT_TOPIC, OfflineCollection, drop_bag_messages)
from so101_demo.parallel_batch.contracts.common import AttemptStatus, RunMode
from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime
from so101_demo.runtime.parallel_worker_parts.receipts import RuntimeDecision
from so101_demo.runtime.task_stack import StackProcessSpec
from parallel_worker_runtime_support import _lease, _ProcessGroup, _resources, _write_capture
from paths import PACKAGE_ROOT

POLICY = {"ready_timeout_s": 10.0, "policy_sha256": "p" * 64}
IDENTITY = {"session_id": "session-worker-1", "reset_epoch": 7, "attempt_id": "attempt-1"}
LEASE = {"batch_id": "batch-1", "coordinator_epoch": 1, "worker_id": "worker-1", "worker_generation": 1, "point_id": "P01",
         "attempt_id": "attempt-1", "lease_generation": 1, "lease_issued_monotonic_s": 10.0, "lease_deadline_monotonic_s": 310.0}


# ---- the collection request: the bag recorder is the only data path ---------------------------------------------------------

def test_the_bag_recorder_is_on_exactly_when_the_collection_is():
    assert CollectionOptions("on").raw_pilot is True and CollectionOptions("off").raw_pilot is False
    assert validate_collection_request("on", "none", run_mode="formal", run_root="/r").raw_pilot is True
    assert validate_collection_request("off", "none", run_mode="formal", run_root="/r").enabled is False


def test_the_retired_raw_pilot_switch_is_a_no_op_on_and_refused_off():
    on = validate_collection_request("on", "none", run_mode="formal", run_root="/r", raw_pilot=True)
    assert on == validate_collection_request("on", "none", run_mode="formal", run_root="/r")
    with pytest.raises(CollectionRefused, match="COLLECTION_RAW_RECORDER_IS_THE_ONLY_DATA_PATH"):
        validate_collection_request("on", "none", run_mode="formal", run_root="/r", raw_pilot=False)
    with pytest.raises(CollectionRefused, match="COLLECTION_RAW_PILOT_REQUIRES_COLLECTION_ON"):
        validate_collection_request("off", "none", run_mode="formal", run_root="/r", raw_pilot=True)


def test_the_worker_specification_round_trips_and_a_forged_one_is_refused(tmp_path):
    plain = CollectionOptions("on")
    assert collection_from_document(plain.document()) == plain
    assert collection_from_document({k: v for k, v in plain.document().items() if k != "raw_pilot"}) == plain
    faulty = CollectionOptions("on", "source_gap", tmp_path / "run" / "fault-sandbox")
    assert collection_from_document(faulty.document()) == faulty
    for forged in ({**plain.document(), "raw_pilot": False}, {**CollectionOptions("off").document(), "raw_pilot": True},
                   {**plain.document(), "mode": "maybe"}, {**plain.document(), "fault": "bogus"}):
        with pytest.raises(CollectionRefused):
            collection_from_document(forged)


# ---- the stage bounds a data pipeline with offline processing needs (frozen runtime config, version three) -------------------

def test_the_act_runtime_config_carries_stage_bounds_long_enough_for_offline_processing():
    from so101_demo.parallel_batch.contracts.macos_single_worker import (
        load_runtime_config_any_schema,
    )

    package = PACKAGE_ROOT
    act = load_runtime_config_any_schema(package / "config/mujoco/parallel_batch_act_offline.yaml")
    original = load_runtime_config_any_schema(package / "config/mujoco/parallel_batch_linux_cuda.yaml")
    assert act.executing_hard_timeout_s == act.lease_duration_s == 1500.0
    assert (original.executing_hard_timeout_s, original.lease_duration_s) == (240.0, 300.0)
    # everything else is the frozen v3 content
    differing = {name for name in vars(original) if getattr(original, name) != getattr(act, name)} if hasattr(original, "__dict__") else None
    if differing is not None:
        assert differing <= {"executing_hard_timeout_s", "lease_duration_s"}


def test_below_the_original_floor_a_version_three_config_is_refused_and_other_versions_stay_pinned(tmp_path):
    from so101_demo.parallel_batch.contracts import common as contracts_common
    from so101_demo.parallel_batch.contracts import linux_cuda as contracts_linux_cuda
    from so101_demo.parallel_batch.contracts import macos_two_worker as contracts_macos_two_worker

    package = PACKAGE_ROOT
    text = (package / "config/mujoco/parallel_batch_act_offline.yaml").read_text()
    for field, bad in (("executing_hard_timeout_s", "239.0"), ("lease_duration_s", "299.0")):
        broken = tmp_path / f"{field}.yaml"
        broken.write_text(text.replace(f"{field}: 1500.0", f"{field}: {bad}"))
        with pytest.raises(contracts_common.ContractError, match="FROZEN_RUNTIME_VALUE"):
            contracts_linux_cuda.load_parallel_runtime_config_linux_cuda(broken)
    assert contracts_macos_two_worker.FROZEN_RUNTIME_VALUES_MACOS_MPS_TWO_WORKER["executing_hard_timeout_s"] == 240.0
    assert contracts_macos_two_worker.FROZEN_RUNTIME_VALUES_MACOS_MPS_TWO_WORKER["lease_duration_s"] == 300.0


def test_the_collection_config_binds_the_act_runtime_config_and_the_input_inspector_reads_that_file():
    import hashlib

    import yaml

    from so101_demo.act import diagnostic_episode_inputs

    package = PACKAGE_ROOT
    document = yaml.safe_load((package / "config/act/parallel_collection.yaml").read_bytes())
    runtime = package / document["parallel_runtime"]["path"]
    assert runtime.name == "parallel_batch_act_offline.yaml"
    assert document["parallel_runtime"]["sha256"] == hashlib.sha256(runtime.read_bytes()).hexdigest()
    assert diagnostic_episode_inputs.RUNTIME_CONFIG_FILE.endswith("config/mujoco/parallel_batch_act_offline.yaml")


# ---- the bag fault helper, on a real bag -------------------------------------------------------------------------------------

def _tiny_bag(path, counts):
    from std_msgs.msg import String

    from so101_demo.act.offline.bag_io import BagWriter

    writer = BagWriter(path)
    try:
        for topic, count in counts.items():
            writer.create(topic, "std_msgs/msg/String")
        stamp = 1
        for index in range(max(counts.values())):
            for topic, count in counts.items():
                if index < count:
                    writer.write(topic, String(data=f"{topic}:{index}"), stamp)
                    stamp += 1
    finally:
        writer.close()


def _read_all(path):
    from rclpy.serialization import deserialize_message
    from std_msgs.msg import String

    from so101_demo.act.offline.bag_io import read_messages

    return [(topic, deserialize_message(data, String).data, stamp) for topic, _type, stamp, data in read_messages(path)]


def test_dropping_messages_removes_a_burst_from_the_middle_of_one_topic_and_nothing_else(tmp_path):
    _tiny_bag(tmp_path / "bag", {"/a": 30, "/b": 12})
    facts = drop_bag_messages(tmp_path / "bag", tmp_path / "copy", topic="/a", count=6)
    original, copy = _read_all(tmp_path / "bag"), _read_all(tmp_path / "copy")
    assert facts["dropped"] == 6
    removed = [item for item in original if item not in copy]
    assert [item[1] for item in removed] == [f"/a:{index}" for index in range(12, 18)]
    assert [item for item in original if item[0] == "/b"] == [item for item in copy if item[0] == "/b"]
    assert len(copy) == len(original) - 6 and facts["first_dropped_stamp_ns"] == removed[0][2]


def test_a_topic_too_short_to_drop_from_is_refused(tmp_path):
    _tiny_bag(tmp_path / "bag", {"/a": 5})
    with pytest.raises(ValueError, match="FAULT_BAG_TOPIC_TOO_SHORT"):
        drop_bag_messages(tmp_path / "bag", tmp_path / "copy", topic="/a", count=6)


def test_the_two_bag_faults_target_sources_the_scan_judges():
    from so101_demo.act.offline.scan import CHUNK_TOPIC, CONTROLLER_STATE_TOPICS

    assert FAULT_TOPIC["queue_overflow"] == CHUNK_TOPIC and FAULT_TOPIC["source_gap"] == CONTROLLER_STATE_TOPICS[0]
    assert set(BAG_FAULTS) == {"queue_overflow", "source_gap"} and all(FAULT_DROP_COUNT[name] > 1 for name in BAG_FAULTS)


# ---- the data lifecycle of one attempt, with fakes ---------------------------------------------------------------------------

class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakePilot:
    """PilotRecording's surface, scripted."""

    instances = []
    log = None   # a shared event list: ("start", "act-raw-pilot") is appended when the (faked) bag recorder starts

    def __init__(self, *, ready=True, failure=None, facts=None, raises=None, **kwargs):
        self.kwargs, self.ready, self.failure, self.raises = kwargs, ready, failure, raises
        self.root = Path(kwargs["root"])
        self.started = self.finished = False
        self._facts = {"ready": ready, "failure": None, "closed": True, "rc": 0, "missing_core_topics": [], **(facts or {})}
        FakePilot.instances.append(self)

    def start(self):
        if self.raises:
            raise RuntimeError(self.raises)
        self.started = True
        if FakePilot.log is not None:
            FakePilot.log.append(("start", "act-raw-pilot"))
        (self.root / "bag").mkdir(parents=True, exist_ok=True)
        (self.root / "bag" / "metadata.yaml").write_text("rosbag2_bagfile_information: {}\n")

    def finish(self):
        self.finished = True
        return dict(self._facts)


@pytest.fixture(autouse=True)
def _fresh_fake_pilots():
    FakePilot.instances.clear()
    FakePilot.log = None
    yield
    FakePilot.instances.clear()
    FakePilot.log = None


def pilot_factory(**options):
    return lambda **kwargs: FakePilot(**options, **kwargs)


class FakeProcesses:
    """The Worker's process tree surface for the processor: scripted return code, writes what the real processor would."""

    def __init__(self, *, returncode=0, outputs="valid", exits=True, on_start=None, report=None):
        self.returncode, self.outputs, self.exits, self.on_start, self.report = returncode, outputs, exits, on_start, report
        self.specs, self.environments, self.events = [], [], []

    def start(self, spec, *, environment=None, pass_fds=()):
        self.specs.append(spec)
        self.environments.append(environment)
        self.events.append(("start", spec.role))
        argv = spec.argv
        self.out = Path(argv[argv.index("--out") + 1])
        self.qc = Path(argv[argv.index("--qc-output") + 1])
        if self.on_start is not None:
            self.on_start(self, argv)
        if self.outputs == "valid":
            self._write_outputs(valid=True)
        elif self.outputs == "invalid":
            self._write_outputs(valid=False)
        return SimpleNamespace(role=spec.role, pid=4242)

    def _write_outputs(self, *, valid):
        self.out.mkdir(parents=True, exist_ok=True)
        verdict = "VALID" if valid else "INVALID"
        report = self.report or {"verdict": verdict, "rc": 0 if valid else 3,
                                 "reasons": [] if valid else ["OFFLINE_SOURCE_GAP: arm", "OFFLINE_X: y"],
                                 "qc": {"status": "PASS"} if valid else {"status": "NOT_RUN"}, "timing": {"wall_s": 1.0}}
        (self.out / "offline-processor-report.json").write_text(json.dumps(report))
        (self.out / "recorder-result.json").write_text(json.dumps({
            "schema": RESULT_SCHEMA, "status": verdict, "rc": 0 if valid else 3, "reasons": [], "identity": dict(IDENTITY),
            "listening": True, "seal": {"path": "episode/seal.json", "sha256": "a" * 64} if valid else None}))
        if valid:
            self.qc.parent.mkdir(parents=True, exist_ok=True)
            self.qc.write_text("{}")

    def wait_exit(self, identity, timeout_s):
        self.events.append(("wait_exit", timeout_s))
        return self.returncode if self.exits else None

    def terminate(self, identity, grace_s):
        self.events.append(("terminate", grace_s))
        return -15

    def stop(self, identity):
        self.events.append(("stop",))
        return True


def collection_for(tmp_path, *, fault="none", processes=None, pilot=None, **extra):
    point = tmp_path / "attempts" / "P01" / "attempt-1" / "working"
    (point / "dynamic").mkdir(parents=True)
    sandbox = None if fault == "none" else tmp_path / "run" / "fault-sandbox"
    clock = Clock()
    FakePilot.instances.clear()
    options = dict(processes=processes or FakeProcesses(), point_root=point, sandbox_root=sandbox, fault=fault,
                   environment={"ROS_DOMAIN_ID": "181"}, spec_factory=lambda role, argv: StackProcessSpec(role, tuple(argv)),
                   inputs_manifest=tmp_path / "inputs" / "inputs-manifest.json", scope=tmp_path / "scope.json",
                   identity=dict(IDENTITY), policy=POLICY, clock=clock, sleep=clock.sleep,
                   pilot_factory=pilot or pilot_factory())
    options.update(extra)
    return OfflineCollection(**options), point, clock


def test_a_recorder_that_never_became_ready_is_invalid_and_nothing_is_processed(tmp_path):
    processes = FakeProcesses()
    collection, _, _ = collection_for(tmp_path, processes=processes,
                                      pilot=pilot_factory(ready=False, failure="RAW_PILOT_READY_TIMEOUT"))
    collection.start_before_teacher()
    assert collection.ready is False and collection.events[-1] == "recorder_not_ready:RAW_PILOT_READY_TIMEOUT"
    outcome = collection.finish(lease=LEASE)
    assert (outcome.data_status, outcome.reason) == ("INVALID", "RAW_PILOT_READY_TIMEOUT") and processes.specs == []


def test_a_recorder_that_cannot_be_started_is_invalid_data_and_never_an_exception(tmp_path):
    processes = FakeProcesses()
    collection, _, _ = collection_for(tmp_path, processes=processes, pilot=pilot_factory(raises="no ros2"))
    collection.start_before_teacher()
    outcome = collection.finish(lease=LEASE)
    assert outcome.data_status == "INVALID" and outcome.reason == "RAW_PILOT_START_FAILED: no ros2" and processes.specs == []


@pytest.mark.parametrize("facts", [{"closed": False}, {"failure": "RAW_PILOT_STOP_FAILED: x"}, {"rc": 3}])
def test_a_bag_that_was_not_closed_cleanly_is_invalid_and_nothing_is_processed(tmp_path, facts):
    processes = FakeProcesses()
    collection, _, _ = collection_for(tmp_path, processes=processes, pilot=pilot_factory(facts=facts))
    collection.start_before_teacher()
    outcome = collection.finish(lease=LEASE)
    assert outcome.data_status == "INVALID" and outcome.reason.startswith("RAW_BAG_NOT_CLOSED_CLEANLY") and processes.specs == []


def test_a_data_verdict_already_made_closes_the_bag_and_skips_the_processor(tmp_path):
    processes = FakeProcesses()
    collection, _, _ = collection_for(tmp_path, processes=processes)
    collection.start_before_teacher()
    outcome = collection.finish(lease=LEASE, skip_processing="TERMINAL_CAPTURE_FAILED: x")
    assert (outcome.data_status, outcome.reason) == ("INVALID", "TERMINAL_CAPTURE_FAILED: x")
    assert FakePilot.instances[0].finished and processes.specs == []


def test_a_bag_that_is_missing_is_invalid(tmp_path):
    class NoBag(FakePilot):
        def start(self):
            self.started = True

    collection, _, _ = collection_for(tmp_path, pilot=lambda **kw: NoBag(**kw))
    collection.start_before_teacher()
    assert collection.finish(lease=LEASE).reason == "RAW_BAG_MISSING"


# ---- the five faults ---------------------------------------------------------------------------------------------------------

def test_recorder_absent_records_nothing_and_is_invalid(tmp_path):
    processes = FakeProcesses()
    collection, point, _ = collection_for(tmp_path, fault="recorder_absent", processes=processes)
    collection.start_before_teacher()
    assert FakePilot.instances == [] and collection.events == ["recorder_not_started:fault_recorder_absent"]
    outcome = collection.finish(lease=LEASE)
    assert (outcome.data_status, outcome.reason) == ("INVALID", "RECORDER_ABSENT") and processes.specs == []


def test_recorder_late_starts_the_bag_only_after_the_teachers_setup_evidence_and_is_invalid(tmp_path):
    processes = FakeProcesses()
    collection, point, clock = collection_for(tmp_path, fault="recorder_late", processes=processes, late_delay_s=5.0)
    collection.start_before_teacher()
    assert FakePilot.instances == [], "no bag before the Teacher"
    trigger = point / "dynamic" / "reachability-observed.json"
    collection.teacher_started_now()
    collection.arm_late_start(trigger)
    trigger.write_text("{}")
    collection._late_thread.join(timeout=10)
    assert FakePilot.instances and FakePilot.instances[0].started and collection.late_started is True
    assert 5.0 in clock.sleeps, "the late start waited for the Teacher's first command"
    outcome = collection.finish(lease=LEASE)
    assert (outcome.data_status, outcome.reason) == ("INVALID", "RECORDER_STARTED_AFTER_TEACHER") and processes.specs == []


def test_a_fault_output_outside_the_sandbox_is_refused_before_any_process_starts(tmp_path):
    with pytest.raises(CollectionRefused, match="COLLECTION_FAULT_OUTSIDE_SANDBOX"):
        collection_for(tmp_path, fault="source_gap", sandbox_root=tmp_path / "run" / "not-a-sandbox")


def test_every_fault_name_is_known():
    assert set(COLLECTION_FAULTS) == {"none", "recorder_absent", "recorder_late", "queue_overflow", "source_gap", "output_write_failure"}


# ---- the Worker runtime -------------------------------------------------------------------------------------------------------

class Group(_ProcessGroup):
    def __init__(self, events):
        super().__init__(events)
        self.processor = FakeProcesses()

    def exit_code(self, identity):
        return None

    def wait_exit(self, identity, timeout_s):
        self.events.append(("wait_exit", identity.role))
        return 0

    def terminate(self, identity, grace_s):
        self.events.append(("terminate", identity.role))
        return -15


def worker_runtime(tmp_path, collection, *, events=None, group=None, **extra):
    events = [] if events is None else events
    resources = _resources(tmp_path, "worker-1", 0, 181)
    group = group or Group(events)
    clock = Clock()

    def capture(path, boundary):
        events.append(("capture", path.name))
        return _write_capture(path, boundary + 1.0)

    runtime = build_worker_runtime(
        resources, RunMode.EXECUTE, process_group=group, station_config=lambda _resources_: SimpleNamespace(processes=()),
        episode_scope_path=str(tmp_path / "scope.json"), episode_inputs_manifest=str(tmp_path / "inputs/inputs-manifest.json"),
        collection=collection, recorder_policy=POLICY, recorder_clock=clock, recorder_sleep=clock.sleep,
        reset_point=lambda _lease: SimpleNamespace(reset_epoch="reset-7", reset_completed_monotonic_s=10.0),
        initial_gate=lambda _lease, receipt: receipt, capture_rgb=capture,
        consumer_ready=lambda child: events.append(("ready", child.role)) or True,
        pause_physics=lambda _lease, _reset: events.append(("pause",)) or True, **extra)
    return runtime, group, events, clock


def _decision(**changes):
    values = dict(status=AttemptStatus.PASSED, reason="OK", physical_action_proven_absent=False,
                  teacher_execution_status="COMPLETED", teacher_task_result="PASS", act_data_status="DISABLED")
    values.update(changes)
    return RuntimeDecision(**values)


def test_the_bag_recorder_starts_before_the_teacher_and_the_teacher_starts_even_if_it_never_became_ready(tmp_path, monkeypatch):
    for ready in (True, False):
        monkeypatch.setattr(orchestration, "PilotRecording", pilot_factory(ready=ready, failure=None if ready else "RAW_PILOT_READY_TIMEOUT"))
        events = []
        monkeypatch.setattr(FakePilot, "log", events)
        runtime, group, events, clock = worker_runtime(tmp_path / str(ready), CollectionOptions("on"), events=events)
        runtime.start_physical_runtime()
        events.clear()
        runtime.reset_and_validate_point(_lease())
        assert ("ready", "dynamic-consumer") in events, "the Teacher was started and made ready"
        assert [event for event in events if event[0] == "start"] == [("start", "act-raw-pilot"), ("start", "dynamic-consumer")], \
            "the bag recorder first, the Teacher second, whatever became of the recorder"
        collection, = runtime._recorders.values()
        assert collection.ready is ready and FakePilot.instances[-1].started
        assert clock.sleeps == [], "the (faked) wait for RECORDING is the recorder's own; the worker adds none"


def test_collection_off_records_nothing_processes_nothing_and_the_data_is_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestration, "PilotRecording", lambda **kw: pytest.fail("a bag recorder was created with collection off"))
    runtime, group, events, clock = worker_runtime(tmp_path, CollectionOptions("off"))
    runtime.start_physical_runtime()
    events.clear()
    lease = _lease()
    runtime.reset_and_validate_point(lease)
    assert [event for event in events if event[0] == "start"] == [("start", "dynamic-consumer")]
    decision = runtime._finish_collection(lease, _decision())
    assert decision.act_data_status == "DISABLED" and decision.qc_report_path is None
    assert not any(spec.role == "act-offline-processor" for spec in group.specs)




def test_a_teacher_decision_whose_data_is_already_invalid_is_not_processed(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestration, "PilotRecording", pilot_factory())
    runtime, group, events, clock = worker_runtime(tmp_path, CollectionOptions("on"))
    runtime.start_physical_runtime()
    lease = _lease()
    runtime.reset_and_validate_point(lease)
    decision = runtime._finish_collection(lease, _decision(act_data_status="INVALID", act_data_reason="TERMINAL_CAPTURE_FAILED: x"))
    assert (decision.act_data_status, decision.act_data_reason) == ("INVALID", "TERMINAL_CAPTURE_FAILED: x")
    assert not any(spec.role == "act-offline-processor" for spec in group.specs)
    assert FakePilot.instances[-1].finished


def test_a_cancelled_attempt_closes_its_bag_without_touching_the_teachers_result(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestration, "PilotRecording", pilot_factory())
    runtime, group, events, clock = worker_runtime(tmp_path, CollectionOptions("on"))
    runtime.start_physical_runtime()
    lease = _lease()
    runtime.reset_and_validate_point(lease)
    runtime._retire_recorder(runtime._lease_key(lease))
    assert FakePilot.instances[-1].finished and not runtime._recorders


def test_the_teacher_argv_differs_from_off_by_exactly_the_final_stop_proof(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestration, "PilotRecording", pilot_factory())
    argvs = {}
    for mode in ("on", "off"):
        runtime, group, events, clock = worker_runtime(tmp_path / mode, CollectionOptions(mode))
        runtime.start_physical_runtime()
        runtime.reset_and_validate_point(_lease())
        argvs[mode] = [item.replace(str(tmp_path / mode), "ROOT") for item in
                       next(spec.argv for spec in group.specs if spec.role == "dynamic-consumer")]
    assert [item for item in argvs["on"] if item not in argvs["off"]] == ["--final-stop-proof"]


# ---- the processor's exit code for an infrastructure defect (output_write_failure) -------------------------------------------

def test_an_unwritable_output_directory_is_exit_code_4_with_the_traceback_on_stderr_not_an_uncaught_exception(tmp_path, monkeypatch, capsys):
    from so101_demo.act.offline import processor

    lease = tmp_path / "lease.json"
    lease.write_text(json.dumps(LEASE))

    def refuse(*args, **kwargs):
        raise PermissionError(13, "Permission denied", str(tmp_path / "out" / "offline-evidence"))

    monkeypatch.setattr(processor, "process_bag", refuse)
    code = processor.main(["--bag", str(tmp_path / "bag"), "--inputs", str(tmp_path / "inputs.json"), "--out", str(tmp_path / "out"),
                           "--lease", str(lease)])
    captured = capsys.readouterr()
    assert code == processor.RC_INFRA == 4
    assert "OFFLINE_INFRASTRUCTURE" in captured.err and "PermissionError" in captured.err and "Traceback" in captured.err


# ---- ported from the retired Recorder orchestration tests: the same guarantees, on the bag path ------------------------------

class ScriptedGroup(Group):
    """The processor is a process of the Worker's group: script it, leave every other role to the ordinary fake group."""

    def __init__(self, events, processor):
        super().__init__(events)
        self.scripted = processor

    def start(self, spec, *, environment=None, pass_fds=()):
        if spec.role == "act-offline-processor":
            self.events.append(("start", spec.role))
            self.specs.append(spec)
            return self.scripted.start(spec, environment=environment)
        return super().start(spec, environment=environment, pass_fds=pass_fds)

    def wait_exit(self, identity, timeout_s):
        return self.scripted.wait_exit(identity, timeout_s)

    def terminate(self, identity, grace_s):
        return self.scripted.terminate(identity, grace_s)

    def stop(self, identity):
        return self.scripted.stop(identity) if identity.role == "act-offline-processor" else super().stop(identity)


@pytest.mark.parametrize("fault", [fault for fault in COLLECTION_FAULTS if fault != "none"])
def test_a_fault_outside_the_sandbox_is_refused_before_any_process_starts(tmp_path, monkeypatch, fault):
    monkeypatch.setattr(orchestration, "PilotRecording", pilot_factory())
    events = []
    bad = CollectionOptions("on", fault, tmp_path / "run" / "not-a-sandbox")
    runtime, group, events, clock = worker_runtime(tmp_path, bad, events=events)
    runtime.start_physical_runtime()
    events.clear()
    with pytest.raises(CollectionRefused, match="COLLECTION_FAULT_OUTSIDE_SANDBOX"):
        runtime.reset_and_validate_point(_lease())
    assert [event for event in events if event[0] == "start"] == [], "neither the bag recorder nor the Teacher was started"


DEFERRED_FAULTS = BAG_FAULTS + ("output_write_failure",)


@pytest.mark.parametrize("fault", [fault for fault in COLLECTION_FAULTS if fault != "none"])
def test_each_fault_is_invalid_data_at_the_recorder_or_deferred_to_the_processor(tmp_path, monkeypatch, fault):
    """Phase 1: a recorder fault gives INVALID data as before and the real store seals a PASSED attempt with INVALID data (never
    exportable). A bag or output fault acts on the processing, which phase 1 does not run: the data is PENDING_QC, the fault is
    recorded for the processor, and no processor is started."""
    from act_result_teacher import sealed_teacher
    from test_act_result_schema3 import setup_result

    monkeypatch.setattr(orchestration, "PilotRecording", pilot_factory())
    events = []
    options = CollectionOptions("on", fault, tmp_path / "orch" / "run" / "fault-sandbox")
    runtime, group, events, clock = worker_runtime(tmp_path / "orch", options, events=events, group=ScriptedGroup(events, FakeProcesses()))
    runtime.start_physical_runtime()
    lease = _lease()
    runtime.reset_and_validate_point(lease)
    if fault == "recorder_late":
        next(iter(runtime._recorders.values())).start_late()
    point = runtime._point_root(lease)[1]
    (point / "dynamic").mkdir(exist_ok=True)
    (point / "dynamic" / "dynamic-execute-manifest.json").write_text("{}\n")
    (tmp_path / "orch" / "inputs").mkdir(exist_ok=True)
    (tmp_path / "orch" / "inputs" / "inputs-manifest.json").write_text("{}\n")
    (tmp_path / "orch" / "scope.json").write_text("{}\n")
    baseline = _decision()
    decision = runtime._finish_collection(lease, baseline)
    deferred = fault in DEFERRED_FAULTS
    assert decision.act_data_status == ("PENDING_QC" if deferred else "INVALID") and decision.qc_report_path is None
    assert (decision.act_data_reason is None) is deferred
    assert (decision.status, decision.reason, decision.teacher_execution_status, decision.teacher_task_result) == (
        baseline.status, baseline.reason, baseline.teacher_execution_status, baseline.teacher_task_result)
    started_pilots = [pilot for pilot in FakePilot.instances if pilot.started]
    assert bool(started_pilots) is (fault != "recorder_absent")
    assert not any(spec.role == "act-offline-processor" for spec in group.specs)
    if deferred:
        record = json.loads((runtime._point_root(lease)[1] / "recorder-orchestration.json").read_text())
        assert record["fault_deferred_to_processing"] == fault
        return
    (tmp_path / "store").mkdir()
    store, seal, document, inputs = setup_result(tmp_path / "store", monkeypatch)
    claim = sealed_teacher(store, "PASSED", data=decision.act_data_status, reason=decision.act_data_reason)
    location = store.seal(seal, teacher=claim)
    sealed = json.loads((location / "result.json").read_bytes())
    assert sealed["status"] == "PASSED" and sealed["act_data_status"] == "INVALID"
    assert sealed["act_data_qc"] == "NOT_RUN" and sealed["export_eligible"] is False


def test_seal_attempt_hands_the_processors_qc_report_to_the_store(tmp_path, monkeypatch):
    from test_act_result_schema3 import setup_result

    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    captured = {}
    store.seal = lambda path, *, teacher, qc_report_path=None, recording_receipt_path=None: captured.update(path=path, teacher=teacher, qc=qc_report_path) or "sealed"
    decision = SimpleNamespace(status=AttemptStatus.PASSED, teacher_execution_status="COMPLETED", teacher_task_result="PASS",
                               act_data_status="VALID", act_data_reason=None, episode_seal_path=seal,
                               qc_report_path=store.working / "qc-report.json")
    assert store.seal_attempt(store.lease, decision) == "sealed"
    assert captured["qc"] == store.working / "qc-report.json" and captured["teacher"]["data_status"] == "VALID"
    del decision.qc_report_path
    store.seal_attempt(store.lease, decision)
    assert captured["qc"] is None


def test_the_teachers_argv_is_identical_for_every_fault_and_differs_from_off_by_exactly_the_final_stop_proof(tmp_path):
    lease = _lease()
    reference = None
    for fault in COLLECTION_FAULTS:
        options = CollectionOptions("on", fault, None if fault == "none" else tmp_path / "run" / "fault-sandbox")
        runtime = worker_runtime(tmp_path / fault, options)[0]
        argv = tuple(item.replace(str(tmp_path / fault), "ROOT") for item in runtime.consumer_argv("reset-7", lease))
        reference = reference or argv
        assert argv == reference, fault
    off = tuple(item.replace(str(tmp_path / "off"), "ROOT") for item in worker_runtime(
        tmp_path / "off", CollectionOptions("off"))[0].consumer_argv("reset-7", lease))
    assert [item for item in reference if item not in off] == ["--final-stop-proof"]
    assert [item for item in off if item not in reference] == []


def test_execute_expert_adds_the_pending_data_status_beside_the_teachers_fields(tmp_path, monkeypatch):
    """The Teacher's receipt passes through `execute_expert`; the data status is added beside it, never over it, and no processor ran."""
    from parallel_worker_runtime_support import _write_numeric

    from so101_demo.runtime.parallel_worker_parts.receipts import ExecutionCompletionReceipt

    monkeypatch.setattr(orchestration, "PilotRecording", pilot_factory())
    events = []
    runtime, group, events, clock = worker_runtime(
        tmp_path, CollectionOptions("on"), events=events, group=ScriptedGroup(events, FakeProcesses()),
        localize=lambda _lease, _result: SimpleNamespace(reset_epoch="reset-7"),
        capture_numeric_evidence=lambda _lease, _localized, root, boundary: _write_numeric(root, boundary + 1.0),
        admit_pose=lambda _lease, value: admitted, publish_pose=lambda value: True, resume_physics=lambda _lease, _reset: True,
        execute_result=lambda _lease, _admitted, _child: ExecutionCompletionReceipt(_decision(), 30.0))
    admitted = SimpleNamespace(reset_epoch="reset-7", pose="accepted")
    runtime.start_physical_runtime()
    lease = _lease()
    runtime.reset_and_validate_point(lease)
    runtime.localize_and_admit_pose(lease, "broker-result")
    point = runtime._point_root(lease)[1]
    (point / "dynamic").mkdir(exist_ok=True)
    (point / "dynamic" / "dynamic-execute-manifest.json").write_text("{}\n")
    (tmp_path / "inputs").mkdir(exist_ok=True)
    (tmp_path / "inputs" / "inputs-manifest.json").write_text("{}\n")
    (tmp_path / "scope.json").write_text("{}\n")
    decision = runtime.execute_expert(lease, admitted)
    assert decision.status is AttemptStatus.PASSED
    assert (decision.teacher_execution_status, decision.teacher_task_result) == ("COMPLETED", "PASS")
    assert decision.act_data_status == "PENDING_QC" and decision.act_data_reason is None
    assert not any(spec.role == "act-offline-processor" for spec in group.specs)
