"""Phase 1 of the two-phase collection: the attempt ends after the Teacher and the closed bag.

The data side seals PENDING_QC with a recording receipt (sha256 and size of every raw file and of the documents the offline
processor will need) and starts no processor. Everything runs with the fakes of `test_offline_recording_switch`.
"""

import hashlib
import json
from pathlib import Path

import pytest

from so101_demo.act.collection_orchestration import CollectionOptions
from so101_demo.act.offline import orchestration
from test_offline_recording_switch import (
    IDENTITY, LEASE, FakePilot, FakeProcesses, _decision, collection_for, pilot_factory, worker_runtime)
from parallel_worker_runtime_support import _lease


def _phase1_files(tmp_path, point):
    """The documents and extra raw files a finished recording leaves behind (the fake recorder only wrote metadata.yaml)."""
    (point / "raw" / "bag").mkdir(parents=True, exist_ok=True)
    (point / "raw" / "bag" / "bag_0.db3").write_bytes(b"bag-bytes" * 1000)
    (point / "raw" / "record-stats.json").write_text('{"rc": 0}\n')
    (point / "raw" / "scene-reads").mkdir(exist_ok=True)
    (point / "raw" / "scene-reads" / "read-1.json").write_text("{}\n")
    (point / "dynamic").mkdir(exist_ok=True)
    (point / "dynamic" / "dynamic-execute-manifest.json").write_text('{"teacher": true}\n')
    (tmp_path / "inputs").mkdir(exist_ok=True)
    (tmp_path / "inputs" / "inputs-manifest.json").write_text('{"inputs": 1}\n')
    (tmp_path / "scope.json").write_text('{"scope": 1}\n')


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_the_phase_one_finish_seals_pending_qc_without_starting_a_processor(tmp_path):
    processes = FakeProcesses()
    collection, point, clock = collection_for(tmp_path, processes=processes)
    collection.start_before_teacher()
    _phase1_files(tmp_path, point)
    collection.teacher_started_now()
    outcome = collection.finish(lease=LEASE)
    assert (outcome.data_status, outcome.reason) == ("PENDING_QC", None)
    assert processes.specs == [] and processes.events == [], "phase 1 starts no processor and waits for none"
    assert "processor" not in outcome.facts and "seal" not in outcome.facts and "qc_report_path" not in outcome.facts
    assert FakePilot.instances[0].finished, "the bag is closed before the receipt is written"
    receipt = json.loads((point / "raw" / "recording-receipt.json").read_text())
    assert receipt["kind"] == "ACT_RECORDING_RECEIPT" and receipt["schema_version"] == 1
    assert receipt["lease_identity"] == LEASE and receipt["identity"] == IDENTITY
    listed = {item["path"]: item for item in receipt["raw_files"]}
    on_disk = sorted(path.relative_to(point).as_posix() for path in (point / "raw").rglob("*")
                     if path.is_file() and path.name != "recording-receipt.json")
    assert sorted(listed) == on_disk and "raw/bag/bag_0.db3" in listed and "raw/lease.json" in listed
    for relative, item in listed.items():
        assert item["sha256"] == _sha(point / relative) and item["size"] == (point / relative).stat().st_size
    documents = receipt["documents"]
    assert set(documents) == {"teacher_manifest", "inputs_manifest", "scope", "lease", "recorder_orchestration"}
    assert documents["recorder_orchestration"]["path"] == "recorder-orchestration.json"
    assert documents["recorder_orchestration"]["sha256"] == _sha(point / "recorder-orchestration.json")
    assert documents["teacher_manifest"]["path"] == "dynamic/dynamic-execute-manifest.json"
    assert documents["teacher_manifest"]["sha256"] == _sha(point / "dynamic" / "dynamic-execute-manifest.json")
    assert documents["inputs_manifest"]["sha256"] == _sha(tmp_path / "inputs" / "inputs-manifest.json")
    assert documents["scope"]["sha256"] == _sha(tmp_path / "scope.json")
    assert documents["lease"] == dict(listed["raw/lease.json"])
    assert json.loads((point / "raw" / "lease.json").read_text()) == LEASE
    facts = outcome.facts["recording_receipt"]
    assert facts["sha256"] == _sha(point / "raw" / "recording-receipt.json") and facts["files"] == len(listed)
    assert facts["bytes"] == sum(item["size"] for item in listed.values())
    assert not list((point / "raw").glob("*.tmp")), "the receipt is written atomically"


def test_the_receipt_detects_a_changed_bag_byte(tmp_path):
    from so101_demo.act.offline.recording_receipt import verify_recording_receipt
    collection, point, _ = collection_for(tmp_path)
    collection.start_before_teacher()
    _phase1_files(tmp_path, point)
    collection.finish(lease=LEASE)
    proof = verify_recording_receipt(point)
    assert proof["sha256"] == _sha(point / "raw" / "recording-receipt.json") and proof["files"] >= 4
    (point / "raw" / "bag" / "bag_0.db3").write_bytes(b"bag-bytes" * 999 + b"X" * 9)
    with pytest.raises(ValueError, match="RECORDING_RECEIPT_FILE_CHANGED"):
        verify_recording_receipt(point)


def test_the_receipt_refuses_an_unlisted_raw_file_and_a_missing_one(tmp_path):
    from so101_demo.act.offline.recording_receipt import verify_recording_receipt
    collection, point, _ = collection_for(tmp_path)
    collection.start_before_teacher()
    _phase1_files(tmp_path, point)
    collection.finish(lease=LEASE)
    (point / "raw" / "extra.bin").write_bytes(b"x")
    with pytest.raises(ValueError, match="RECORDING_RECEIPT_UNLISTED_FILE"):
        verify_recording_receipt(point)
    (point / "raw" / "extra.bin").unlink()
    (point / "raw" / "record-stats.json").unlink()
    with pytest.raises(ValueError, match="RECORDING_RECEIPT_FILE_MISSING"):
        verify_recording_receipt(point)


def test_the_receipt_binds_the_expected_lease_and_external_documents(tmp_path):
    from so101_demo.act.offline.recording_receipt import verify_recording_receipt
    collection, point, _ = collection_for(tmp_path)
    collection.start_before_teacher()
    _phase1_files(tmp_path, point)
    collection.finish(lease=LEASE)
    verify_recording_receipt(point, lease_identity=LEASE, external={
        "scope": _sha(tmp_path / "scope.json"), "inputs_manifest": _sha(tmp_path / "inputs" / "inputs-manifest.json")})
    with pytest.raises(ValueError, match="RECORDING_RECEIPT_LEASE_MISMATCH"):
        verify_recording_receipt(point, lease_identity=dict(LEASE, attempt_id="attempt-2"))
    with pytest.raises(ValueError, match="RECORDING_RECEIPT_DOCUMENT_MISMATCH"):
        verify_recording_receipt(point, external={"scope": "0" * 64})


@pytest.mark.parametrize("what", ["teacher_manifest", "scope", "inputs_manifest"])
def test_a_missing_document_the_processor_needs_is_invalid_data_not_a_receipt(tmp_path, what):
    collection, point, _ = collection_for(tmp_path)
    collection.start_before_teacher()
    _phase1_files(tmp_path, point)
    {"teacher_manifest": point / "dynamic" / "dynamic-execute-manifest.json", "scope": tmp_path / "scope.json",
     "inputs_manifest": tmp_path / "inputs" / "inputs-manifest.json"}[what].unlink()
    outcome = collection.finish(lease=LEASE)
    assert outcome.data_status == "INVALID" and outcome.reason.startswith("RECORDER_ORCHESTRATION_FAILED")
    assert not (point / "raw" / "recording-receipt.json").exists()


@pytest.mark.parametrize("name,options,skip", [
    ("not_ready", dict(pilot=pilot_factory(ready=False, failure="RAW_PILOT_READY_TIMEOUT")), None),
    ("not_closed", dict(pilot=pilot_factory(facts={"closed": False})), None),
    ("verdict_made", dict(), "TERMINAL_CAPTURE_FAILED: x")])
def test_a_recorder_defect_or_a_made_verdict_stays_invalid_without_a_receipt(tmp_path, name, options, skip):
    collection, point, _ = collection_for(tmp_path / name, **options)
    collection.start_before_teacher()
    _phase1_files(tmp_path / name, point)
    outcome = collection.finish(lease=LEASE, skip_processing=skip)
    assert outcome.data_status == "INVALID" and not (point / "raw" / "recording-receipt.json").exists()


def test_a_missing_bag_is_still_invalid_in_phase_one(tmp_path):
    collection, point, _ = collection_for(tmp_path)
    collection.start_before_teacher()
    (point / "raw" / "bag" / "metadata.yaml").unlink()
    assert collection.finish(lease=LEASE).reason == "RAW_BAG_MISSING"


def test_the_runtime_finish_ends_in_pending_qc_with_the_teachers_fields_untouched_and_no_processor(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestration, "PilotRecording", pilot_factory())
    runtime, group, events, clock = worker_runtime(tmp_path, CollectionOptions("on"))
    runtime.start_physical_runtime()
    lease = _lease()
    runtime.reset_and_validate_point(lease)
    point = runtime._point_root(lease)[1]
    _phase1_files(tmp_path, point)
    baseline = _decision()
    decision = runtime._finish_collection(lease, baseline)
    assert (decision.act_data_status, decision.act_data_reason, decision.qc_report_path) == ("PENDING_QC", None, None)
    assert (decision.status, decision.reason, decision.teacher_execution_status, decision.teacher_task_result) == (
        baseline.status, baseline.reason, baseline.teacher_execution_status, baseline.teacher_task_result)
    assert not any(spec.role == "act-offline-processor" for spec in group.specs)
    record = json.loads((point / "recorder-orchestration.json").read_text())
    assert record["act_data_status"] == "PENDING_QC" and record["fault"] == "none"
    # the receipt hashes this very record, so the record cannot also name the receipt
    assert "recording_receipt" not in record
    receipt = json.loads((point / "raw" / "recording-receipt.json").read_text())
    assert receipt["documents"]["recorder_orchestration"]["sha256"] == _sha(point / "recorder-orchestration.json")
    assert (point / "raw" / "recording-receipt.json").is_file()


def test_the_receipt_binds_the_orchestration_record_that_carries_the_deferred_fault(tmp_path):
    from so101_demo.act.offline.recording_receipt import verify_recording_receipt
    collection, point, _ = collection_for(tmp_path)
    collection.start_before_teacher()
    _phase1_files(tmp_path, point)
    collection.finish(lease=LEASE)
    record = point / "recorder-orchestration.json"
    verify_recording_receipt(point)
    record.write_text(record.read_text().replace('"fault": "none"', '"fault": "none", "fault_deferred_to_processing": "x"'))
    with pytest.raises(ValueError, match="RECORDING_RECEIPT_FILE_CHANGED"):
        verify_recording_receipt(point)
    record.unlink()
    with pytest.raises(ValueError, match="RECORDING_RECEIPT_FILE_MISSING"):
        verify_recording_receipt(point)
