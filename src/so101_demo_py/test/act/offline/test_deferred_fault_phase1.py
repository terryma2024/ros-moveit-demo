"""A diagnostic fault the processor applies later (queue_overflow, source_gap, output_write_failure) is recorded in phase 1 exactly as a
fault-free attempt is: the raw bag, the receipt and the orchestration record live in the point root the result store reads. The
fault is applied by the phase-2 processor to a copy under its own output directory. `recorder_absent` and `recorder_late` are phase-1
faults and keep their sandbox and their INVALID verdict."""

import pytest

from so101_demo.act.collection_orchestration import CollectionOptions
from so101_demo.act.offline import orchestration

from test_offline_recording_switch import FakePilot, FakeProcesses, ScriptedGroup, _decision, _lease, pilot_factory, worker_runtime


def finish(tmp_path, monkeypatch, fault):
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
    return runtime._finish_collection(lease, _decision()), point, tmp_path / "orch" / "run" / "fault-sandbox"


@pytest.mark.parametrize("fault", ["queue_overflow", "source_gap", "output_write_failure"])
def test_a_deferred_fault_is_recorded_in_the_point_root_where_the_decision_names_the_receipt(tmp_path, monkeypatch, fault):
    FakePilot.instances.clear()
    decision, point, sandbox = finish(tmp_path, monkeypatch, fault)
    assert decision.act_data_status == "PENDING_QC" and decision.act_data_reason is None
    assert decision.recording_receipt_path == point / "raw" / "recording-receipt.json"
    assert decision.recording_receipt_path.is_file(), "the receipt the decision names exists"
    assert FakePilot.instances[0].root == point / "raw"
    assert not sandbox.exists() or not any(sandbox.iterdir()), "nothing of a deferred fault is recorded in the sandbox"


@pytest.mark.parametrize("fault", ["recorder_absent", "recorder_late"])
def test_a_recorder_fault_keeps_its_phase_1_invalid_verdict(tmp_path, monkeypatch, fault):
    FakePilot.instances.clear()
    decision, point, sandbox = finish(tmp_path, monkeypatch, fault)
    assert decision.act_data_status == "INVALID" and decision.recording_receipt_path is None
    assert decision.act_data_reason in ("RECORDER_ABSENT", "RECORDER_STARTED_AFTER_TEACHER")
