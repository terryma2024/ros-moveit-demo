"""Phase 2: the processing task verifies the phase-1 record, runs the offline processor and writes `processed-result.json`.

Every fixture is built here: a phase-1 attempt (sealed `result.json` as `PENDING_QC`, a real recording receipt over fixture raw
files), a fake processor runner and a fake grader. Nothing depends on host files.
"""

import hashlib
import json
import os
from pathlib import Path
import threading
import time

import pytest

from so101_demo.act.offline.recording_receipt import write_recording_receipt
from so101_demo.runtime.act_processor import processing
from so101_demo.runtime.container_campaign.task_contracts import InputRef, TaskSpec

LEASE = dict(batch_id="b1", coordinator_epoch=1, worker_id="w00", worker_generation=1, point_id="scene-01",
             attempt_id="scene-01-lease-1", lease_generation=1, lease_issued_monotonic_s=10.0, lease_deadline_monotonic_s=900.0)
RESULT_LEASE = {name: LEASE[name] for name in ("batch_id", "coordinator_epoch", "worker_id", "worker_generation", "point_id",
                                                "attempt_id", "lease_generation")}
IDENTITY = dict(session_id="campaign-wave00-w00-g1", reset_epoch=1, attempt_id="scene-01-lease-1")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*")):
        digest.update(str(path.relative_to(root)).encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


class Fixture:
    def __init__(self, tmp_path, *, fault=None):
        self.run = tmp_path / "run"
        self.sealed = self.run / "wave-0/w00/g1/output/tasks/t1/attempts/scene-01/scene-01-lease-1/sealed"
        (self.sealed / "raw/bag").mkdir(parents=True)
        (self.sealed / "dynamic").mkdir()
        (self.sealed / "raw/bag/metadata.yaml").write_text("bag\n")
        (self.sealed / "raw/bag/data.mcap").write_bytes(b"mcap" * 10)
        (self.sealed / "raw/record-stats.json").write_text("{}\n")
        (self.sealed / "raw/lease.json").write_text(json.dumps(LEASE, sort_keys=True) + "\n")
        (self.sealed / "dynamic/dynamic-execute-manifest.json").write_text("{}\n")
        shared = self.run / "inputs"
        shared.mkdir()
        self.inputs = shared / "inputs-manifest.json"
        self.scope = shared / "scope.json"
        self.inputs.write_text('{"inputs": 1}\n')
        self.scope.write_text('{"scope": 1}\n')
        (self.sealed / "recorder-orchestration.json").write_text(
            json.dumps({} if fault is None else {"fault_deferred_to_processing": fault}))
        write_recording_receipt(self.sealed, lease_identity=LEASE, identity=IDENTITY, inputs_manifest=self.inputs, scope=self.scope)
        # the sealed result.json holds the seven-key lease identity of the result store; the receipt holds the whole lease
        self.result = dict(kind="ACT_COLLECTION_RESULT", schema_version=3, lease_identity=RESULT_LEASE, status="PASSED",
                           teacher_execution_status="COMPLETED", teacher_task_result="SUCCESS", act_data_status="PENDING_QC",
                           act_data_reason=None, act_data_qc="NOT_RUN", export_eligible=False, episode_seal_sha256=None,
                           completed_monotonic_s=20.0, qc_report_path=None, qc_report_sha256=None, inputs_sha256=None,
                           scope_sha256=None, audit_manifest_sha256=None, collection_mode=None)
        self.write_result(self.result)
        self.processing = self.run / "processing"
        self.owned = self.processing / "p00/g1"
        (self.owned / "task-inputs").mkdir(parents=True)
        self.output_dir = self.processing / "scene-01/scene-01-lease-1-proc-1"

    def write_result(self, result):
        (self.sealed / "result.json").write_bytes(json.dumps(result, sort_keys=True).encode() + b"\n")

    @property
    def result_sha256(self):
        return sha((self.sealed / "result.json").read_bytes())

    def task(self, *, number=1, **override):
        document = dict(schema_version=1, kind=processing.TASK_KIND, task_id="proc-scene-01-1", processor_id="p00",
                        launch_generation=1, scene_id="scene-01", proc_attempt=number, phase1_attempt=str(self.sealed),
                        phase1_result_sha256=self.result_sha256,
                        inputs_manifest=dict(path=str(self.inputs), sha256=sha(self.inputs.read_bytes())),
                        scope=dict(path=str(self.scope), sha256=sha(self.scope.read_bytes())),
                        output_dir=str(self.processing / "scene-01" / f"scene-01-lease-1-proc-{number}"))
        document.update(override)
        path = self.owned / "task-inputs" / (document["task_id"] + ".json")
        raw = json.dumps(document, sort_keys=True).encode()
        path.write_bytes(raw)
        return TaskSpec(task_id=document["task_id"], inputs_ref=InputRef(path=str(path), sha256=sha(raw)),
                        deadline_monotonic_s=time.monotonic() + 600)

    def load(self, spec):
        return processing.load_processing_task(spec, owned_root=self.owned, processing_root=self.processing,
                                               processor_id="p00", launch_generation=1)


class FakeRunner:
    """Stands in for the offline processor child: records its argv and writes the files the real one would."""

    def __init__(self, rc=0, *, write=True, raises=None, report=None, valid_result=True):
        self.rc, self.write, self.raises, self.calls = rc, write, raises, []
        self.report = report or {"verdict": "VALID" if rc == 0 else "INVALID", "rc": rc, "reasons": ["R1"], "qc": {"status": "PASS"}}
        self.valid_result = valid_result

    def run(self, argv, *, timeout_s, environment, stop):
        self.calls.append(dict(argv=list(argv), timeout_s=timeout_s))
        if self.raises is not None:
            raise self.raises
        if self.rc is None:
            return None
        out = Path(argv[argv.index("--out") + 1])
        qc = Path(argv[argv.index("--qc-output") + 1])
        if self.write:
            (out / "episode").mkdir()
            (out / "episode/seal.json").write_text("{}\n")
            (out / "offline-processor-report.json").write_text(json.dumps(self.report))
            if self.rc == 0 and self.valid_result:
                (out / "recorder-result.json").write_text(json.dumps(
                    {"schema": "SO101_RECORDER_RESULT", "identity": IDENTITY, "status": "VALID", "seal": {"sha256": "a" * 64}}))
                qc.write_text("{}\n")
        return self.rc

    def terminate(self):
        pass

    def alive(self):
        return False


def fake_grader(**kwargs):
    return dict(status="VALID", reason=None, qc="PASS", episode_sha256="e" * 64,
                binding=dict(qc_report_path="qc-report.json", qc_report_sha256="q" * 64, inputs_sha256="i" * 64,
                             scope_sha256="s" * 64, audit_manifest_sha256="a" * 64, collection_mode="formal"))


def execution(fixture, runner, *, number=1, grader=fake_grader, memo=lambda **kwargs: True, **load):
    task = fixture.load(fixture.task(number=number, **load))
    return processing.ProcessingExecution(task=task, python="/act/venv/bin/python", runner=runner, environment={}, grader=grader,
                                          memo_check=memo)


# ---- the assignment ---------------------------------------------------------------------------------------------------

def test_task_loads_when_every_binding_matches(tmp_path):
    fixture = Fixture(tmp_path)
    task = fixture.load(fixture.task())
    assert (task.sealed, task.scene_id, task.proc_attempt, task.output_dir) == (fixture.sealed, "scene-01", 1, fixture.output_dir)


@pytest.mark.parametrize("override", [
    dict(output_dir="/tmp/elsewhere"),                                        # outside <run>/processing/<scene>/<attempt>-proc-<n>
    dict(processor_id="p01"), dict(launch_generation=2), dict(proc_attempt=0), dict(scene_id="scene-02"),
    dict(phase1_attempt="/tmp/not-an-attempt/sealed"), dict(extra=1),
    dict(phase1_result_sha256="z" * 64),
])
def test_task_with_a_wrong_binding_is_refused(tmp_path, override):
    fixture = Fixture(tmp_path)
    with pytest.raises(processing.Refused):
        fixture.load(fixture.task(**override))


def test_task_input_with_a_changed_hash_is_refused(tmp_path):
    fixture = Fixture(tmp_path)
    spec = fixture.task()
    Path(spec.inputs_ref.path).write_bytes(b"{}")
    with pytest.raises(processing.Refused, match="PROCESSING_TASK_INPUT_INVALID"):
        fixture.load(spec)


# ---- the phase-1 record -------------------------------------------------------------------------------------------------

def test_phase1_record_binds_result_and_receipt(tmp_path):
    fixture = Fixture(tmp_path)
    phase1 = processing.verify_phase1(fixture.load(fixture.task()))
    assert phase1["result_sha256"] == fixture.result_sha256
    assert phase1["identity"] == IDENTITY and phase1["lease_identity"] == LEASE and phase1["fault"] == "none"
    assert phase1["receipt_sha256"] == sha((fixture.sealed / "raw/recording-receipt.json").read_bytes())


@pytest.mark.parametrize("tamper", ["raw_file", "unlisted_file", "missing_file", "not_pending", "result_changed", "foreign_scope",
                                    "unknown_fault", "fault_removed", "fault_injected"])
def test_phase1_record_is_refused_when_anything_disagrees(tmp_path, tamper):
    fixture = Fixture(tmp_path, fault="no_such_fault" if tamper == "unknown_fault"
                      else "source_gap" if tamper == "fault_removed" else None)
    spec = fixture.task()
    if tamper == "fault_removed":
        (fixture.sealed / "recorder-orchestration.json").write_text("{}")
    elif tamper == "fault_injected":
        (fixture.sealed / "recorder-orchestration.json").write_text('{"fault_deferred_to_processing": "source_gap"}')
    elif tamper == "raw_file":
        (fixture.sealed / "raw/bag/data.mcap").write_bytes(b"changed")
    elif tamper == "unlisted_file":
        (fixture.sealed / "raw/extra.bin").write_bytes(b"x")
    elif tamper == "missing_file":
        (fixture.sealed / "raw/record-stats.json").unlink()
    elif tamper == "not_pending":
        fixture.write_result({**fixture.result, "act_data_status": "VALID", "act_data_qc": "PASS"})
        spec = fixture.task()
    elif tamper == "result_changed":
        fixture.write_result({**fixture.result, "completed_monotonic_s": 21.0})
    elif tamper == "foreign_scope":
        fixture.scope.write_text('{"scope": 2}\n')
        spec = fixture.task()
    task = fixture.load(spec)
    with pytest.raises(processing.Refused, match="PHASE1_RECORD_REFUSED"):
        processing.verify_phase1(task)


def test_phase1_record_with_a_deferred_diagnostic_fault_is_read(tmp_path):
    fixture = Fixture(tmp_path, fault="source_gap")
    assert processing.verify_phase1(fixture.load(fixture.task()))["fault"] == "source_gap"


# ---- running the processor ------------------------------------------------------------------------------------------------

def test_valid_run_uses_the_inline_arguments_and_writes_the_processed_result(tmp_path):
    fixture = Fixture(tmp_path)
    runner = FakeRunner(0)
    before = tree_digest(fixture.sealed)
    result = execution(fixture, runner).run()
    sealed = fixture.sealed
    out = fixture.output_dir
    assert runner.calls[0]["argv"] == ["/act/venv/bin/python", "-m", "so101_demo.cli.act_offline_episode",
        "--bag", str(sealed / "raw/bag"), "--inputs", str(fixture.inputs), "--out", str(out),
        "--lease", str(sealed / "raw/lease.json"), "--scope", str(fixture.scope),
        "--record-stats", str(sealed / "raw/record-stats.json"),
        "--teacher-manifest", str(sealed / "dynamic/dynamic-execute-manifest.json"),
        "--qc-output", str(out / "qc-report.json")]
    assert (result["outcome"], result["retryable"], result["processor_rc"]) == ("VALID", False, 0)
    written = json.loads((out / "processed-result.json").read_bytes())
    assert result["processed_result"] == dict(path="processed-result.json", sha256=sha((out / "processed-result.json").read_bytes()))
    assert written["kind"] == "ACT_PROCESSED_RESULT" and written["schema_version"] == 1
    assert written["phase1_result_sha256"] == fixture.result_sha256
    assert written["receipt_sha256"] == sha((sealed / "raw/recording-receipt.json").read_bytes())
    assert written["lease_identity"] == LEASE and written["identity"] == IDENTITY and written["status"] == "PASSED"
    assert (written["act_data_status"], written["act_data_reason"], written["act_data_qc"]) == ("VALID", None, "PASS")
    assert written["episode_seal_sha256"] == "e" * 64 and written["export_eligible"] is True
    assert written["collection_mode"] == "formal" and written["qc_report_path"] == "qc-report.json"
    assert written["artifacts"]["recorder_result"]["sha256"] == sha((out / "recorder-result.json").read_bytes())
    assert not list(out.glob("*.tmp"))
    assert tree_digest(sealed) == before, "the phase-1 sealed directory is read only"


def test_a_failed_teacher_with_valid_data_is_not_exportable(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.write_result({**fixture.result, "status": "FAILED"})
    result = execution(fixture, FakeRunner(0)).run()
    written = json.loads((fixture.output_dir / "processed-result.json").read_bytes())
    assert result["outcome"] == "VALID" and written["status"] == "FAILED" and written["export_eligible"] is False


def test_rc3_is_a_final_invalid_data_verdict(tmp_path):
    fixture = Fixture(tmp_path)
    result = execution(fixture, FakeRunner(3)).run()
    written = json.loads((fixture.output_dir / "processed-result.json").read_bytes())
    assert (result["outcome"], result["retryable"], result["processor_rc"]) == ("INVALID", False, 3)
    assert written["act_data_status"] == "INVALID" and written["act_data_qc"] == "NOT_RUN" and written["export_eligible"] is False
    assert written["act_data_reason"] == "OFFLINE_PROCESSOR_INVALID: rc=3; R1" and written["qc_report_sha256"] is None


def test_rc2_is_a_refusal_that_is_not_retried_and_leaves_no_verdict(tmp_path):
    fixture = Fixture(tmp_path)
    result = execution(fixture, FakeRunner(2, write=False)).run()
    assert (result["outcome"], result["retryable"], result["processor_rc"]) == ("REFUSED", False, None)
    assert result["processed_result"] is None and not (fixture.output_dir / "processed-result.json").exists()


@pytest.mark.parametrize("runner", [FakeRunner(4, write=False), FakeRunner(None), FakeRunner(0, raises=OSError("spawn")),
                                    FakeRunner(0, valid_result=False), FakeRunner(137, write=False)])
def test_infrastructure_failures_are_retryable_and_leave_no_verdict(tmp_path, runner):
    fixture = Fixture(tmp_path)
    result = execution(fixture, runner).run()
    assert (result["outcome"], result["retryable"]) == ("INFRASTRUCTURE_FAILURE", True)
    assert result["processed_result"] is None and not (fixture.output_dir / "processed-result.json").exists()
    assert result["phase1"]["result_sha256"] == fixture.result_sha256


def test_an_output_that_cannot_be_written_is_an_infrastructure_failure(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.processing.chmod(0o555)
    try:
        if os.access(fixture.processing, os.W_OK):
            pytest.skip("directory permissions are not enforced for this user")
        result = execution(fixture, FakeRunner(0)).run()
    finally:
        fixture.processing.chmod(0o755)
    assert (result["outcome"], result["retryable"]) == ("INFRASTRUCTURE_FAILURE", True)


def test_a_retry_directory_that_exists_is_refused(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.output_dir.mkdir(parents=True)
    result = execution(fixture, FakeRunner(0)).run()
    assert (result["outcome"], result["retryable"]) == ("REFUSED", False)


def test_a_new_attempt_number_uses_a_new_directory(tmp_path):
    fixture = Fixture(tmp_path)
    first = execution(fixture, FakeRunner(4, write=False), number=1).run()
    second = execution(fixture, FakeRunner(0), number=2, task_id="proc-scene-01-2").run()
    assert first["output_dir"].endswith("scene-01-lease-1-proc-1") and second["output_dir"].endswith("scene-01-lease-1-proc-2")
    assert second["outcome"] == "VALID" and first["outcome"] == "INFRASTRUCTURE_FAILURE"


def test_a_refused_phase1_record_never_starts_the_processor(tmp_path):
    fixture = Fixture(tmp_path)
    spec = fixture.task()
    (fixture.sealed / "raw/bag/data.mcap").write_bytes(b"changed")
    runner = FakeRunner(0)
    result = execution(fixture, runner).run() if False else processing.ProcessingExecution(
        task=fixture.load(spec), python="/x", runner=runner, environment={}).run()
    assert result["outcome"] == "REFUSED" and runner.calls == [] and not fixture.output_dir.exists()


def test_data_that_fails_the_memo_or_the_grader_is_invalid(tmp_path):
    fixture = Fixture(tmp_path)
    result = execution(fixture, FakeRunner(0), memo=lambda **kwargs: False).run()
    assert result["outcome"] == "INVALID" and result["reason"] == "OFFLINE_QC_MEMO_NOT_VALID"
    other = Fixture(tmp_path / "other")
    graded = execution(other, FakeRunner(0), grader=lambda **kwargs: dict(
        status="INVALID", reason="RESULT_QC_NOT_RUN: x", qc="NOT_RUN", episode_sha256=None, binding=None)).run()
    written = json.loads((other.output_dir / "processed-result.json").read_bytes())
    assert graded["outcome"] == "INVALID" and written["act_data_reason"] == "RESULT_QC_NOT_RUN: x"


@pytest.mark.parametrize("fault", ["queue_overflow", "source_gap", "output_write_failure"])
def test_a_deferred_diagnostic_fault_is_applied_and_gives_invalid_data(tmp_path, monkeypatch, fault):
    fixture = Fixture(tmp_path, fault=fault)
    drops = []

    def fake_drop(source, destination, *, topic, count):
        drops.append((Path(source), Path(destination), topic, count))
        Path(destination).mkdir()
        return dict(topic=topic, dropped=count)
    monkeypatch.setattr(processing, "drop_bag_messages", fake_drop)
    runner = FakeRunner(4, write=False)
    result = execution(fixture, runner).run()
    argv = runner.calls[0]["argv"]
    base = fixture.output_dir
    if fault == "output_write_failure":
        assert drops == [] and argv[argv.index("--bag") + 1] == str(fixture.sealed / "raw/bag")
        assert argv[argv.index("--out") + 1] == str(base / "out")
    else:
        topic = processing.FAULT_TOPIC[fault]
        assert drops == [(fixture.sealed / "raw/bag", base / "fault-bag", topic, processing.FAULT_DROP_COUNT[fault])]
        assert argv[argv.index("--bag") + 1] == str(base / "fault-bag")
    assert argv[argv.index("--qc-output") + 1] == str(base / "out" / "offline-qc-report.json")
    written = json.loads((base / "processed-result.json").read_bytes())
    assert (result["outcome"], result["retryable"]) == ("INVALID", False)
    assert written["act_data_status"] == "INVALID" and written["diagnostic_fault"] == fault
    assert written["act_data_reason"] == "OFFLINE_PROCESSOR_FAILED: rc=4" and written["export_eligible"] is False
    if fault == "output_write_failure":
        assert os.stat(base / "out").st_mode & 0o222, "the read-only output is writable again"


def test_a_stop_request_ends_the_run_as_an_infrastructure_failure(tmp_path):
    fixture = Fixture(tmp_path)

    class Blocking(FakeRunner):
        def run(self, argv, *, timeout_s, environment, stop):
            self.entered = threading.Event()
            self.entered.set()
            assert stop.wait(5)
            return None
    runner = Blocking(0)
    run = execution(fixture, runner)
    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(run.run()))
    thread.start()
    time.sleep(0.05)
    run.request_stop()
    thread.join(5)
    assert outcome[0]["outcome"] == "INFRASTRUCTURE_FAILURE" and run.shutdown_owned() is True


# ---- the child process --------------------------------------------------------------------------------------------------------

def test_subprocess_runner_returns_the_exit_code_and_stops_a_hung_child():
    runner = processing.SubprocessRunner()
    stop = threading.Event()
    import sys
    assert runner.run([sys.executable, "-c", "raise SystemExit(3)"], timeout_s=10, environment={}, stop=stop) == 3
    began = time.monotonic()
    assert runner.run([sys.executable, "-c", "import time; time.sleep(60)"], timeout_s=1, environment={}, stop=stop) is None
    assert time.monotonic() - began < 20 and runner.alive() is False


# ---- the grader keeps the inline result store's rules ----------------------------------------------------------------------------

def test_export_rule_is_the_result_stores():
    from so101_demo.act.result_store import export_eligible
    assert export_eligible("PASSED", "PASS", "formal") is True
    assert export_eligible("PASSED", "PASS", "diagnostic") is False
    assert export_eligible("FAILED", "PASS", "formal") is False


# ---- the default grader: the result store's checks, wired to the processor's output ---------------------------------------------

def grader_inputs(tmp_path):
    out = tmp_path / "out"
    (out / "episode/audit").mkdir(parents=True)
    (out / "episode/seal.json").write_text("{}\n")
    (out / "qc-report.json").write_text("{}\n")
    return dict(out=out, qc_output=out / "qc-report.json", lease=LEASE, identity=IDENTITY, scope=tmp_path / "scope.json",
                inputs_manifest=tmp_path / "inputs.json", teacher_status="PASSED",
                teacher_manifest=tmp_path / "sealed/dynamic/dynamic-execute-manifest.json")


def patch_store(monkeypatch, *, seal=None, qc=None, audit=None):
    from so101_demo.act import result_store
    monkeypatch.setattr(result_store, "_seal_facts", lambda path: seal or dict(attempt_id=LEASE["attempt_id"],
        session_id=IDENTITY["session_id"], reset_epoch=IDENTITY["reset_epoch"]))
    monkeypatch.setattr(result_store, "_verify_audit_lease", audit or (lambda manifest, lease: None))
    seen = []

    def verify(path, **kwargs):
        seen.append(kwargs)
        if qc is not None:
            raise qc
        return dict(status="PASS", inputs_sha256="i" * 64, scope_sha256="s" * 64, audit_manifest_sha256="a" * 64), "d" * 64, "formal"
    monkeypatch.setattr(result_store, "_verify_result_qc", verify)
    # the Teacher-oracle rule has its own tests (test_processor_oracle_exclusion.py); the QC report here is a stub
    from so101_demo.act import teacher_process
    monkeypatch.setattr(teacher_process, "bound_teacher_oracle_exclusion", lambda report, manifest: None)
    return seen


def test_default_grader_binds_the_qc_and_trusts_the_fresh_memo(tmp_path, monkeypatch):
    seen = patch_store(monkeypatch)
    inputs = grader_inputs(tmp_path)
    graded = processing.grade_episode(**inputs)
    assert (graded["status"], graded["reason"], graded["qc"]) == ("VALID", None, "PASS")
    assert graded["episode_sha256"] == sha(b"{}\n")
    assert graded["binding"] == dict(qc_report_path="qc-report.json", qc_report_sha256="d" * 64, inputs_sha256="i" * 64,
                                     scope_sha256="s" * 64, audit_manifest_sha256="a" * 64, collection_mode="formal")
    assert seen[0]["trust_memo"] is True and seen[0]["audit_manifest"] == inputs["out"] / "episode/audit/audit-manifest.json"


def test_default_grader_marks_a_foreign_session_or_a_failed_qc_invalid(tmp_path, monkeypatch):
    patch_store(monkeypatch, seal=dict(attempt_id=LEASE["attempt_id"], session_id="other", reset_epoch=1))
    graded = processing.grade_episode(**grader_inputs(tmp_path))
    assert graded["status"] == "INVALID" and graded["reason"].startswith("RESULT_EPISODE_INVALID") and graded["qc"] == "NOT_RUN"
    patch_store(monkeypatch, qc=ValueError("RESULT_QC_READBACK_INVALID"))
    graded = processing.grade_episode(**grader_inputs(tmp_path / "again"))
    assert graded["status"] == "INVALID" and graded["reason"].startswith("RESULT_QC_NOT_RUN") and graded["binding"] is None
