"""Orchestration of the independent Recorder around one Teacher attempt (Phase A4c).

Direction of dependence under test: the Recorder is started first and waited for a bounded time, the Teacher starts
whatever happened to it and never waits on data after its own start, every defect on the data side is INVALID data with
the Teacher's fields untouched, and a fault outside `<run>/fault-sandbox/` is refused before any process starts. All with
fakes: no stack, no ROS, no live Recorder.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.act.collection_orchestration import (
    COLLECTION_FAULTS, RECORDER_PROCESS_FAULTS, RECORDER_ROLE, CollectionOptions, CollectionRefused, RecorderLaunch,
    RecorderOrchestrator, collection_from_document, require_under_sandbox, validate_collection_request)
from so101_demo.act.episode_recorder_process import READY_SCHEMA, RESULT_SCHEMA, load_recorder_policy
from so101_demo.parallel_batch.contracts import AttemptStatus, RunMode
from so101_demo.runtime.parallel_worker_runtime import ExecutionCompletionReceipt, RuntimeDecision, build_worker_runtime
from so101_demo.runtime.task_stack import StackProcessSpec
from test_parallel_worker_runtime import _ProcessGroup, _lease, _resources, _write_capture, _write_numeric

POLICY = load_recorder_policy(Path(__file__).parents[1] / "config/act/episode_recorder_v1.yaml")
IDENTITY = {"session_id": "session-worker-1", "reset_epoch": 7, "attempt_id": "attempt-1"}


# ---- fakes ---------------------------------------------------------------------------------------------------------

class Clock:
    """A fake monotonic clock that only moves when somebody sleeps."""

    def __init__(self):
        self.now = 100.0
        self.sleeps = []
        self.forbidden_while = None

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        if self.forbidden_while is not None and self.forbidden_while():
            raise AssertionError("the orchestrator slept while the Teacher was running")
        self.sleeps.append(seconds)
        self.now += seconds


def ready_document(**changes):
    return {"schema": READY_SCHEMA, **IDENTITY, "pid": 1, "state": "LISTENING", **changes}


def result_document(status="VALID", **changes):
    document = {"schema": RESULT_SCHEMA, "status": status, "rc": 0 if status == "VALID" else 3,
                "reasons": [] if status == "VALID" else ["TEACHER_EVENT_SEQUENCE_GAP: expected 4 got 5"],
                "identity": dict(IDENTITY), "listening": True,
                "seal": {"path": "episode/seal.json", "sha256": "a" * 64} if status == "VALID" else None}
    document.update(changes)
    return document


class FakeTree:
    """The Worker's owned process tree surface the orchestrator uses, with scripted Recorder behaviour."""

    def __init__(self, launch, *, ready_after_polls=0, exit_code=0, exits=True, result=None, start_error=None,
                 clock=None, dies_on_start=False, ready_state="CAPTURING", capturing_after_polls=None):
        self.launch, self.ready_after_polls, self.code, self.exits = launch, ready_after_polls, exit_code, exits
        self.ready_state, self.capturing_after_polls = ready_state, capturing_after_polls
        self.dies_on_start = dies_on_start
        self.result, self.start_error, self.clock = result, start_error, clock
        self.events, self.polls, self.running = [], 0, False
        self.identity = SimpleNamespace(role=RECORDER_ROLE, pid=4242)

    def start(self, spec, *, environment=None, pass_fds=()):
        if self.start_error is not None:
            raise RuntimeError(self.start_error)
        assert spec.role == RECORDER_ROLE
        self.events.append("start")
        self.running = not self.dies_on_start
        if self.ready_after_polls is not None and self.ready_after_polls == 0:
            self._write_ready()
        return self.identity

    def _write_ready(self, state=None):
        self.launch.ready_file.parent.mkdir(parents=True, exist_ok=True)
        self.launch.ready_file.write_text(json.dumps(ready_document(state=state or self.ready_state)))

    def exit_code(self, identity):
        self.polls += 1
        if self.ready_after_polls and self.polls >= self.ready_after_polls and not self.launch.ready_file.exists():
            self._write_ready()
        if (self.capturing_after_polls is not None and self.polls >= self.capturing_after_polls
                and self.launch.ready_file.exists()):
            self._write_ready("CAPTURING")           # the Recorder rewrites its ready file when the capture is committed
        return None if self.running else self.code

    def wait_exit(self, identity, timeout_s):
        self.events.append(("wait_exit", timeout_s))
        if not self.exits:
            return None
        self.running = False
        if self.result is not None:
            self.launch.result_file.parent.mkdir(parents=True, exist_ok=True)
            self.launch.result_file.write_text(json.dumps(self.result))
        return self.code

    def terminate(self, identity, grace_s):
        self.events.append(("terminate", grace_s))
        self.running = False
        return -15

    def stop(self, identity):
        self.events.append("stop")
        return True


def launch_in(tmp_path):
    working = tmp_path / "working"
    return RecorderLaunch(argv=("recorder",), environment={}, ready_file=working / "recorder-ready.json",
                          result_file=working / "recorder-result.json", episode_root=working / "episode",
                          identity=dict(IDENTITY))


def orchestrator(tmp_path, *, fault="none", **tree_options):
    launch, clock = launch_in(tmp_path), Clock()
    tree = FakeTree(launch, clock=clock, **tree_options)
    orch = RecorderOrchestrator(processes=tree, launch=launch, policy=POLICY, fault=fault,
                                spec_factory=lambda current: StackProcessSpec(RECORDER_ROLE, current.argv),
                                clock=clock, sleep=clock.sleep)
    return orch, tree, clock


# ---- the Recorder is started first, waited for a bounded time, and the Teacher starts regardless -------------------

def test_a_ready_recorder_ends_the_bounded_wait_at_once(tmp_path):
    orch, tree, clock = orchestrator(tmp_path, ready_after_polls=3, result=result_document())
    orch.start_before_teacher()
    assert orch.ready is True and tree.events[0] == "start"
    assert 0 < len(clock.sleeps) <= 3 and clock.now - 100.0 < POLICY["ready_timeout_s"]
    orch.teacher_started_now()
    outcome = orch.finish()
    assert (outcome.data_status, outcome.reason) == ("VALID", None)
    assert outcome.facts["seal"]["sha256"] == "a" * 64


def test_the_teacher_waits_for_capturing_not_for_listening(tmp_path):
    """CP-3425: the wait ends when the capture is running with its initial boundary committed."""
    orch, tree, clock = orchestrator(tmp_path, ready_after_polls=0, ready_state="LISTENING", capturing_after_polls=6,
                                     result=result_document())
    orch.start_before_teacher()
    assert orch.ready is True and "recorder_listening" in orch.events and orch.events.index("recorder_listening") < orch.events.index("recorder_ready")
    assert tree.polls >= 6, "it did not stop at LISTENING"
    assert clock.now - 100.0 < POLICY["capturing_timeout_s"]
    orch.teacher_started_now()
    assert orch.finish().data_status == "VALID"


def test_a_recorder_that_listens_but_never_captures_costs_the_capturing_timeout_and_the_teacher_starts_anyway(tmp_path):
    orch, tree, clock = orchestrator(tmp_path, ready_after_polls=0, ready_state="LISTENING", result=result_document())
    orch.start_before_teacher()
    waited = clock.now - 100.0
    assert POLICY["capturing_timeout_s"] <= waited < POLICY["capturing_timeout_s"] + 1.0, "bounded by the frozen policy"
    assert orch.ready is False and orch.ready_reason == "RECORDER_NOT_CAPTURING_BEFORE_TEACHER_START"
    orch.teacher_started_now()           # the Teacher starts regardless, and its result is not touched
    outcome = orch.finish()
    assert (outcome.data_status, outcome.reason) == ("INVALID", "RECORDER_NOT_CAPTURING_BEFORE_TEACHER_START")


def test_a_recorder_that_never_listens_costs_the_ready_timeout_and_the_data_is_invalid_not_the_teacher(tmp_path):
    orch, tree, clock = orchestrator(tmp_path, ready_after_polls=None, result=result_document())
    orch.start_before_teacher()
    waited = clock.now - 100.0
    assert POLICY["ready_timeout_s"] <= waited < POLICY["ready_timeout_s"] + 1.0, "the wait is bounded by the frozen policy"
    assert orch.ready is False and orch.ready_reason == "RECORDER_NOT_READY_BEFORE_TEACHER_START"
    orch.teacher_started_now()          # the Teacher starts regardless
    outcome = orch.finish()
    assert (outcome.data_status, outcome.reason) == ("INVALID", "RECORDER_NOT_READY_BEFORE_TEACHER_START"), (
        "a Recorder that reports VALID after being late is still INVALID: it was not listening at the Teacher's start")


def test_a_recorder_that_exits_before_it_listens_does_not_cost_the_timeout(tmp_path):
    orch, tree, clock = orchestrator(tmp_path, ready_after_polls=None, exit_code=2, dies_on_start=True)
    orch.start_before_teacher()
    assert clock.now - 100.0 < 1.0 and orch.ready_reason == "RECORDER_EXITED_BEFORE_READY"
    orch.teacher_started_now()
    assert orch.finish().data_status == "INVALID"


def test_a_recorder_that_cannot_be_started_is_invalid_data_and_never_an_exception(tmp_path):
    orch, tree, clock = orchestrator(tmp_path, start_error="fork failed")
    orch.start_before_teacher()
    orch.teacher_started_now()
    outcome = orch.finish()
    assert outcome.data_status == "INVALID" and outcome.reason.startswith("RECORDER_START_FAILED: fork failed")


def test_the_orchestrator_never_waits_after_the_teachers_start_until_the_teacher_ended(tmp_path):
    """The Teacher never waits on data after its own start: neither a poll, a sleep nor a wait runs in that window."""
    for fault in ("none", "recorder_late", "recorder_absent"):
        orch, tree, clock = orchestrator(tmp_path / fault, fault=fault, ready_after_polls=2, result=result_document())
        clock.forbidden_while = lambda: orch.teacher_started and not orch.teacher_ended
        original_wait, original_poll = tree.wait_exit, tree.exit_code
        tree.wait_exit = lambda *a, **k: (_ for _ in ()).throw(AssertionError("waited for the Recorder while the Teacher ran")
                                                                ) if orch.teacher_started and not orch.teacher_ended \
            else original_wait(*a, **k)
        tree.exit_code = lambda *a, **k: (_ for _ in ()).throw(AssertionError("polled the Recorder while the Teacher ran")
                                                                 ) if orch.teacher_started and not orch.teacher_ended \
            else original_poll(*a, **k)
        orch.start_before_teacher()
        orch.teacher_started_now()
        if fault == "recorder_late":
            assert orch.start_late() is True        # started beside the running Teacher, never waited for
        orch.finish()
        assert orch.teacher_ended is True


# ---- every fault is INVALID data and nothing else ------------------------------------------------------------------

def test_recorder_absent_starts_nothing_and_is_invalid(tmp_path):
    orch, tree, clock = orchestrator(tmp_path, fault="recorder_absent")
    orch.start_before_teacher()
    orch.teacher_started_now()
    assert tree.events == [] and clock.sleeps == []
    outcome = orch.finish()
    assert (outcome.data_status, outcome.reason) == ("INVALID", "RECORDER_ABSENT")


def test_recorder_late_starts_the_recorder_only_after_the_teacher_and_it_is_invalid(tmp_path):
    orch, tree, clock = orchestrator(tmp_path, fault="recorder_late", result=result_document("INVALID"), exit_code=3)
    orch.start_before_teacher()
    assert tree.events == [] and orch.identity is None, "nothing starts before the Teacher"
    orch.teacher_started_now()
    assert orch.start_late() is True and tree.events == ["start"]
    assert orch.start_late() is False, "started once"
    outcome = orch.finish()
    assert (outcome.data_status, outcome.reason) == ("INVALID", "RECORDER_STARTED_AFTER_TEACHER")


@pytest.mark.parametrize("fault", RECORDER_PROCESS_FAULTS)
def test_recorder_side_faults_are_the_recorders_own_invalid_verdict(tmp_path, fault):
    orch, tree, clock = orchestrator(tmp_path, fault=fault, ready_after_polls=0, exit_code=3,
                                     result=result_document("INVALID"))
    orch.start_before_teacher()
    orch.teacher_started_now()
    outcome = orch.finish()
    assert outcome.data_status == "INVALID" and outcome.reason.startswith("RECORDER_RESULT_INVALID: ")
    assert "TEACHER_EVENT_SEQUENCE_GAP" in outcome.reason and outcome.facts["recorder_rc"] == 3


def test_a_recorder_that_outlives_the_exit_wait_is_sigtermed_and_the_data_is_invalid(tmp_path):
    orch, tree, clock = orchestrator(tmp_path, ready_after_polls=0, exits=False, result=result_document())
    orch.start_before_teacher()
    orch.teacher_started_now()
    outcome = orch.finish()
    assert (outcome.data_status, outcome.reason) == ("INVALID", "RECORDER_EXIT_WAIT_EXPIRED")
    assert tree.events == ["start", ("wait_exit", POLICY["exit_wait_s"]), ("terminate", POLICY["term_grace_s"]), "stop"]
    assert outcome.facts["terminated"] is True and outcome.facts["returncode"] == -15


@pytest.mark.parametrize("fault, expected", [
    ("missing", "RECORDER_RESULT_MISSING"), ("unreadable", "RECORDER_RESULT_UNREADABLE"),
    ("schema", "RECORDER_RESULT_SCHEMA_INVALID"), ("identity", "RECORDER_RESULT_IDENTITY_MISMATCH"),
    ("status", "RECORDER_RESULT_STATUS_INVALID"), ("valid_without_seal", "RECORDER_RESULT_VALID_WITHOUT_SEAL")])
def test_a_result_that_cannot_be_trusted_is_invalid_with_its_reason(tmp_path, fault, expected):
    document = {"missing": None, "unreadable": "{", "schema": result_document(schema="OTHER"),
                "identity": result_document(identity={**IDENTITY, "attempt_id": "foreign"}),
                "status": result_document(status="MAYBE"),
                "valid_without_seal": result_document(seal=None)}[fault]
    orch, tree, clock = orchestrator(tmp_path, ready_after_polls=0)
    orch.start_before_teacher()
    orch.teacher_started_now()
    if document is not None:
        launch = orch._launch
        launch.result_file.parent.mkdir(parents=True, exist_ok=True)
        launch.result_file.write_text(document if isinstance(document, str) else json.dumps(document))
    outcome = orch.finish()
    assert (outcome.data_status, outcome.reason) == ("INVALID", expected)


def test_a_valid_result_whose_process_exit_disagrees_is_invalid(tmp_path):
    orch, tree, clock = orchestrator(tmp_path, ready_after_polls=0, exit_code=3, result=result_document())
    orch.start_before_teacher()
    orch.teacher_started_now()
    outcome = orch.finish()
    assert outcome.data_status == "INVALID" and "rc=3" in outcome.reason


# ---- the request is validated before anything starts ---------------------------------------------------------------

def test_the_collection_request_is_validated_before_any_teacher_start(tmp_path):
    run = tmp_path / "run"
    assert validate_collection_request("on", "none", run_mode="formal", run_root=run) == CollectionOptions("on", "none", None)
    assert validate_collection_request("off", "none", run_mode="formal", run_root=run).enabled is False
    diagnostic = "preselected_target_diagnostic"
    options = validate_collection_request("on", "source_gap", run_mode=diagnostic, run_root=run)
    assert options.sandbox_root == run / "fault-sandbox" and options.fault == "source_gap"
    for collection, fault, mode, code in (
            ("on", "source_gap", "formal", "COLLECTION_FAULT_REQUIRES_DIAGNOSTIC_MODE"),
            ("off", "source_gap", diagnostic, "COLLECTION_FAULT_REQUIRES_COLLECTION_ON"),
            ("maybe", "none", diagnostic, "COLLECTION_MODE_UNKNOWN"), ("on", "chaos", diagnostic, "COLLECTION_FAULT_UNKNOWN")):
        with pytest.raises(CollectionRefused, match=code):
            validate_collection_request(collection, fault, run_mode=mode, run_root=run)


def test_every_fault_is_refused_in_the_formal_mode(tmp_path):
    for fault in COLLECTION_FAULTS:
        if fault == "none":
            continue
        with pytest.raises(CollectionRefused, match="REQUIRES_DIAGNOSTIC_MODE"):
            validate_collection_request("on", fault, run_mode="formal", run_root=tmp_path)


def test_a_fault_output_outside_the_sandbox_is_refused(tmp_path):
    sandbox = tmp_path / "run" / "fault-sandbox"
    inside = sandbox / "attempt-1" / "episode"
    require_under_sandbox(sandbox, inside, sandbox / "attempt-1" / "recorder-result.json")
    outside = tmp_path / "run" / "attempts" / "episode"
    for bad in (outside, sandbox / ".." / "episode", tmp_path / "fault-sandbox-evil" / "episode"):
        with pytest.raises(CollectionRefused, match="COLLECTION_FAULT_OUTSIDE_SANDBOX"):
            require_under_sandbox(sandbox, inside, bad)
    with pytest.raises(CollectionRefused, match="COLLECTION_FAULT_OUTSIDE_SANDBOX"):
        require_under_sandbox(tmp_path / "run" / "not-a-sandbox", tmp_path / "run" / "not-a-sandbox" / "x")
    with pytest.raises(CollectionRefused, match="COLLECTION_FAULT_SANDBOX_REQUIRED"):
        require_under_sandbox(None, inside)
    link = tmp_path / "run" / "fault-sandbox" / "escape"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    with pytest.raises(CollectionRefused, match="COLLECTION_FAULT_OUTSIDE_SANDBOX"):
        require_under_sandbox(sandbox, link / "episode")


def test_the_worker_specification_round_trips_and_a_forged_one_is_refused(tmp_path):
    options = validate_collection_request("on", "queue_overflow", run_mode="preselected_target_diagnostic",
                                          run_root=tmp_path / "run")
    assert collection_from_document(options.document()) == options
    plain = CollectionOptions("off", "none", None)
    assert collection_from_document(plain.document()) == plain
    for forged in ({**options.document(), "sandbox_root": str(tmp_path / "run")},
                   {**options.document(), "sandbox_root": None}, {**options.document(), "mode": "off"},
                   {**options.document(), "fault": "chaos"}, {"mode": "on"},
                   {**plain.document(), "sandbox_root": str(tmp_path / "fault-sandbox")}):
        with pytest.raises(CollectionRefused):
            collection_from_document(forged)


# ---- the Worker runtime: Recorder first, Teacher regardless, refusal before any start ------------------------------

class TreeGroup(_ProcessGroup):
    """The Worker runtime's process group with the Recorder surface, scripted from the Recorder's launch paths."""

    def __init__(self, events, *, ready=True, result=None, exits=True, clock=None, ready_state="CAPTURING"):
        super().__init__(events)
        self.ready, self.result, self.exits, self.clock = ready, result, exits, clock
        self.ready_state, self.ready_file, self.state_at_teacher_start = ready_state, None, None
        self.recorder_argv = None
        self.terminated = []

    def start(self, spec, *, environment=None, pass_fds=()):
        identity = super().start(spec, environment=environment, pass_fds=pass_fds)
        if spec.role == RECORDER_ROLE:
            self.recorder_argv = spec.argv
            self.ready_file = Path(spec.argv[spec.argv.index("--ready-file") + 1])
            if self.ready:
                self.ready_file.parent.mkdir(parents=True, exist_ok=True)
                self.ready_file.write_text(json.dumps(ready_document(state=self.ready_state)))
        elif spec.role == "dynamic-consumer" and self.ready_file is not None:
            # what the Recorder's ready file said at the instant the Teacher was started
            try:
                self.state_at_teacher_start = json.loads(self.ready_file.read_text())["state"]
            except (OSError, ValueError, KeyError):
                self.state_at_teacher_start = None
        return identity

    def exit_code(self, identity):
        return None

    def wait_exit(self, identity, timeout_s):
        self.events.append(("wait_exit", identity.role))
        if not self.exits:
            return None
        if self.result is not None:
            path = Path(self.recorder_argv[self.recorder_argv.index("--result-file") + 1])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.result))
        return 0 if self.result is not None and self.result["status"] == "VALID" else 3

    def terminate(self, identity, grace_s):
        self.terminated.append((identity.role, grace_s))
        return -15


def worker_runtime(tmp_path, collection, *, events=None, group=None, qc=None, **extra):
    events = [] if events is None else events
    resources = _resources(tmp_path, "worker-1", 0, 181)
    group = group or TreeGroup(events)
    clock = Clock()

    def capture(path, boundary):
        events.append(("capture", path.name))
        return _write_capture(path, boundary + 1.0)

    runtime = build_worker_runtime(
        resources, RunMode.EXECUTE, process_group=group, station_config=lambda _resources_: SimpleNamespace(processes=()),
        episode_scope_path=str(tmp_path / "scope.json"), episode_inputs_manifest=str(tmp_path / "inputs/inputs-manifest.json"),
        collection=collection, recorder_policy=POLICY, qc_runner=qc, recorder_clock=clock, recorder_sleep=clock.sleep,
        reset_point=lambda _lease: SimpleNamespace(reset_epoch="reset-7", reset_completed_monotonic_s=10.0),
        initial_gate=lambda _lease, receipt: receipt, capture_rgb=capture,
        consumer_ready=lambda child: events.append(("ready", child.role)) or True,
        pause_physics=lambda _lease, _reset: events.append(("pause",)) or True, **extra)
    return runtime, group, events, clock, resources














def _teacher_decision(**changes):
    values = dict(status=AttemptStatus.PASSED, reason="OK", physical_action_proven_absent=False,
                  teacher_execution_status="COMPLETED", teacher_task_result="PASS", act_data_status="DISABLED")
    values.update(changes)
    return RuntimeDecision(**values)


def _teacher_fields(decision):
    return (decision.status, decision.reason, decision.teacher_execution_status, decision.teacher_task_result)


def finished(tmp_path, fault, *, group=None, qc=None):
    events = []
    options = CollectionOptions("on", "none", None) if fault == "none" else CollectionOptions(
        "on", fault, tmp_path / "run" / "fault-sandbox")
    runtime, group, events, clock, resources = worker_runtime(
        tmp_path, options, events=events, group=group or TreeGroup(events), qc=qc)
    runtime.start_physical_runtime()
    lease = _lease()
    runtime.reset_and_validate_point(lease)
    if fault == "recorder_late":
        next(iter(runtime._recorders.values())).start_late()
    baseline = _teacher_decision()
    return runtime, lease, baseline, runtime._finish_collection(lease, baseline), group












def _exit_code(sealed, monkeypatch):
    """What `act_first_episode run` returns for this committed result (the verified completion gate's mapping)."""
    from so101_demo.act import result_store
    from so101_demo.cli import act_first_episode
    proof = dict(result_status=sealed["status"], teacher_task_result="PASS", act_data_status=sealed["act_data_status"],
                 act_data_qc=sealed["act_data_qc"], export_eligible=sealed["export_eligible"])
    monkeypatch.setattr(result_store, "resolve_native_run", lambda root: dict(
        coordinator_root="c", location="l", scope="s", inputs_manifest="i"))
    monkeypatch.setattr(result_store, "verify_coordinator_commit", lambda *a, **k: proof)
    monkeypatch.setattr(result_store, "verify_coordinator_cleanup", lambda *a, **k: dict(cleanup_proof_path="cleanup"))
    monkeypatch.setattr(result_store, "write_commit_proof", lambda proof, path: "digest")
    return act_first_episode._verified_run_completion("/nonexistent-run")[0]


def test_seal_attempt_hands_the_independent_qc_report_to_the_store(tmp_path, monkeypatch):
    from test_act_result_schema3 import setup_result
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    captured = {}
    store.seal = lambda path, *, teacher, qc_report_path=None: captured.update(
        path=path, teacher=teacher, qc=qc_report_path) or "sealed"
    decision = SimpleNamespace(status=AttemptStatus.PASSED, teacher_execution_status="COMPLETED",
                               teacher_task_result="PASS", act_data_status="VALID", act_data_reason=None,
                               episode_seal_path=seal, qc_report_path=store.working / "qc-report.json")
    assert store.seal_attempt(store.lease, decision) == "sealed"
    assert captured["qc"] == store.working / "qc-report.json" and captured["teacher"]["data_status"] == "VALID"
    # a decision without a report (the Teacher-only path) hands the store nothing and the store grades in process
    del decision.qc_report_path
    store.seal_attempt(store.lease, decision)
    assert captured["qc"] is None


# ---- the Teacher's argv is identical with collection on and under every fault ----------------------------------------







# ---- the raw pilot is an explicit run option (CP-3428), carried like --collection --------------------------------------



class PilotGroup(TreeGroup):
    """TreeGroup that also scripts the record-only process: ready (or not) and its stop statistics."""

    def __init__(self, events, *, pilot_ready=True, pilot_start_error=None, **kwargs):
        super().__init__(events, **kwargs)
        self.pilot_ready, self.pilot_start_error, self.pilot_argv = pilot_ready, pilot_start_error, None

    def start(self, spec, *, environment=None, pass_fds=()):
        if spec.role == "act-raw-pilot":
            if self.pilot_start_error:
                raise RuntimeError(self.pilot_start_error)
            self.pilot_argv = spec.argv
            root = Path(spec.argv[spec.argv.index("--ready-file") + 1]).parent
            if self.pilot_ready:
                root.mkdir(parents=True, exist_ok=True)
                (root / "ready.json").write_text(json.dumps({"schema": "SO101_RAW_RECORDER_READY_V1", "state": "RECORDING"}))
        return super().start(spec, environment=environment, pass_fds=pass_fds)

    def stop(self, identity):
        return None

    def terminate(self, identity, grace_s):
        if identity.role == "act-raw-pilot":
            root = Path(self.pilot_argv[self.pilot_argv.index("--stats-file") + 1])
            root.write_text(json.dumps({"closed": True}))
            return 0
        return super().terminate(identity, grace_s)


def pilot_finished(tmp_path, *, raw_pilot, **group_options):
    events = []
    options = CollectionOptions("on", "none", None, raw_pilot)
    group = PilotGroup(events, result=result_document(), **group_options)

    def qc(*, episode_root, scope, inputs, output):
        Path(output).write_text("{}")
        return {"returncode": 0, "stderr_tail": ""}

    runtime, group, events, clock, resources = worker_runtime(tmp_path, options, events=events, group=group, qc=qc)
    runtime.start_physical_runtime()
    lease = _lease()
    runtime.reset_and_validate_point(lease)
    decision = runtime._finish_collection(lease, _teacher_decision())
    record = json.loads((runtime._point_root(lease)[1] / "recorder-orchestration.json").read_bytes())
    return group, decision, record








