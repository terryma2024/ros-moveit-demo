"""`verify_processing`: the combined per-scene proof of both phases, from the processing journal, summary and processed results.

Every fixture is built here (`processed_fixture`): phase-1 sealed attempts, processed output directories, a journal written by the
real `ProcessingJournal` and a summary in the scheduler's shape. Nothing depends on host files.
"""

import json
from pathlib import Path

import pytest

from processed_fixture import Processed, echo_reader
from so101_demo.runtime.container_campaign.processing_scheduler import ProcessingJournal
from so101_demo.runtime.container_campaign.processing_verifier import (
    build_campaign_result, verify_processing)
from so101_demo.runtime.container_campaign.result_verifier import build_frozen_index
from so101_demo.runtime.container_campaign.service_owner import _write


class Run:
    """The run root with a journal and a summary the way the phase-2 scheduler leaves them."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.scenes = {}
        self.root = tmp_path / "run"
        (self.root / "host").mkdir(parents=True, exist_ok=True)
        self.journal = ProcessingJournal(self.root / "host/processing-journal.jsonl")
        self.summary = []

    def scene(self, name, **kwargs):
        self.scenes[name] = Processed(self.tmp, name, **kwargs)
        return self.scenes[name]

    def final(self, name, *, attempts=1, outcome="VALID", first_failures=()):
        """Journal and summary entry of a scene that ended with a final result on attempt `attempts`."""
        scene = self.scenes[name]
        for number in range(1, attempts + 1):
            self.journal.append("dispatch", scene_id=name, task_id=f"{name}-proc-{number}", proc_attempt=number,
                                processor_id="p00", launch_generation=1,
                                output_dir=str(scene.output.parent / f"{scene.lease['attempt_id']}-proc-{number}"))
            if number < attempts:
                self.journal.append("result", scene_id=name, task_id=f"{name}-proc-{number}", proc_attempt=number,
                                    outcome="INFRASTRUCTURE_FAILURE", retryable=True, reason="OFFLINE_PROCESSOR_FAILED: rc=4",
                                    processor_rc=4)
                self.journal.append("retry", scene_id=name, next_attempt=number + 1, reason="OFFLINE_PROCESSOR_FAILED: rc=4")
            else:
                self.journal.append("result", scene_id=name, task_id=f"{name}-proc-{number}", proc_attempt=number,
                                    outcome=outcome, retryable=False, reason=None, processor_rc=0)
        self.summary.append(dict(scene_id=name, status="FINAL", outcome=outcome, reason=None, attempts=attempts,
                                 output_dir=str(scene.output),
                                 processed_result=dict(path="processed-result.json", sha256="x" * 64)))

    def fault(self, name, fault="PROCESSING_REFUSED", reason="PHASE1_RECORD_REFUSED"):
        self.journal.append("dispatch", scene_id=name, task_id=f"{name}-proc-1", proc_attempt=1, processor_id="p00",
                            launch_generation=1, output_dir=str(self.root / "processing" / name / "x-proc-1"))
        self.journal.append("result", scene_id=name, task_id=f"{name}-proc-1", proc_attempt=1, outcome="REFUSED",
                            retryable=False, reason=reason, processor_rc=None)
        self.journal.append("scene_fault", scene_id=name, fault=fault, reason=reason)
        self.summary.append(dict(scene_id=name, status="FAULT", fault=fault, reason=reason, attempts=1))

    def missing(self, name, reason="PROCESSING_DEADLINE"):
        self.journal.append("scene_missing", scene_id=name, reason=reason)
        self.summary.append(dict(scene_id=name, status="MISSING", reason=reason, attempts=0))

    def write_summary(self):
        _write(self.root / "host/processing-result.json", dict(schema_version=1, kind="act_collection_processing_summary",
                                                               scenes=self.summary, processors_stopped=True))

    def waves(self, *names, pending=True):
        rows = [self.scenes[name].row(pending=pending) for name in names]
        return [dict(wave_index=0, scene_count=len(rows), coordinator_root="x", case_results=rows)]

    def verify(self, waves, ids):
        self.write_summary()
        return verify_processing(self.root, waves, ids, readback_workers=1, processed_reader=echo_reader)


def by_scene(combined):
    return {item["scene_id"]: item for item in combined["scenes"]}


def test_a_processed_scene_joins_the_phase_1_proof_the_phase_2_proof_and_every_attempt(tmp_path):
    run = Run(tmp_path)
    run.scene("scene-01", number=2)
    run.final("scene-01", attempts=2)
    combined = run.verify(run.waves("scene-01"), ["scene-01"])
    item = by_scene(combined)["scene-01"]
    assert item["state"] == "PROCESSED" and item["reason"] is None
    assert item["phase1"]["result_sha256"] == run.scenes["scene-01"].result_sha256
    assert item["phase2"]["status"] == "PASS" and item["phase2"]["proc_attempt"] == 2
    assert item["phase2"]["processed_result"]["sha256"] != "x" * 64, "the readback hash, not the summary's claim"
    assert [(a["proc_attempt"], a["outcome"]) for a in item["attempts"]] == [(1, "INFRASTRUCTURE_FAILURE"), (2, "VALID")]
    assert item["verdict"] == dict(status="PASSED", teacher_execution_status="COMPLETED", teacher_task_result="PASS",
                                   act_data_status="VALID", act_data_reason=None, act_data_qc="PASS", export_eligible=True)
    assert combined["counts"]["PROCESSED"] == 1 and combined["missing_evidence"] == []


def test_a_pre_motion_unreachable_teacher_failure_keeps_its_final_verdict_and_needs_no_processing(tmp_path):
    run = Run(tmp_path)
    run.scene("scene-01", status="FAILED")
    waves = run.waves("scene-01", pending=False)
    combined = run.verify(waves, ["scene-01"])
    item = by_scene(combined)["scene-01"]
    assert item["state"] == "FINAL_AT_PHASE1" and item["phase2"] is None and item["attempts"] == []
    assert item["verdict"]["act_data_status"] == "INVALID" and item["verdict"]["act_data_reason"] == "DYNAMIC_TARGET_UNREACHABLE"
    assert item["verdict"]["status"] == "FAILED" and item["verdict"]["export_eligible"] is False


def test_faults_missing_scenes_and_unrecorded_scenes_are_explicit_entries_never_dropped(tmp_path):
    run = Run(tmp_path)
    for name in ("a", "b", "c", "d"):
        run.scene(name)
    run.final("a")
    run.fault("b")
    run.missing("c")
    # "d" has a phase-1 record and no processing entry at all; "e" was never recorded
    combined = run.verify(run.waves("a", "b", "c", "d"), ["a", "b", "c", "d", "e"])
    items = by_scene(combined)
    assert [item["scene_id"] for item in combined["scenes"]] == ["a", "b", "c", "d", "e"]
    assert [items[name]["state"] for name in "abcde"] == ["PROCESSED", "FAULT", "MISSING", "MISSING", "MISSING"]
    assert items["b"]["reason"].startswith("PROCESSING_REFUSED") and items["c"]["reason"] == "PROCESSING_DEADLINE"
    assert items["d"]["reason"] == "PROCESSING_NOT_QUEUED" and items["e"]["reason"] == "PHASE1_NOT_RECORDED"
    assert items["e"]["phase1"] is None and items["e"]["verdict"]["act_data_status"] == "PROCESSING_MISSING"
    assert items["b"]["verdict"]["act_data_status"] == "PROCESSING_FAULT" and items["b"]["verdict"]["export_eligible"] is False
    assert items["b"]["verdict"]["teacher_task_result"] == "PASS", "the Teacher half is still the phase-1 fact"
    assert combined["missing_evidence"] == ["e"]
    assert combined["counts"] == dict(PROCESSED=1, FINAL_AT_PHASE1=0, FAULT=1, MISSING=3)


def test_a_processed_result_that_fails_its_readback_is_a_fault_with_the_reason(tmp_path):
    run = Run(tmp_path)
    scene = run.scene("scene-01")
    run.final("scene-01")
    scene.write(phase1_result_sha256="0" * 64)
    item = by_scene(run.verify(run.waves("scene-01"), ["scene-01"]))["scene-01"]
    assert item["state"] == "FAULT" and item["reason"].startswith("PROCESSED_RESULT_INVALID") and item["phase2"] is None
    assert [a["outcome"] for a in item["attempts"]] == ["VALID"], "the attempt stays on the list"


def test_a_summary_that_disagrees_with_the_journal_is_a_fault(tmp_path):
    run = Run(tmp_path)
    run.scene("scene-01")
    run.final("scene-01")
    run.summary[0]["output_dir"] = str(run.root / "processing/scene-01/elsewhere-proc-1")
    item = by_scene(run.verify(run.waves("scene-01"), ["scene-01"]))["scene-01"]
    assert item["state"] == "FAULT" and item["reason"] == "PROCESSING_RECORD_MISMATCH"


def test_a_campaign_whose_processing_never_ran_has_every_pending_scene_missing(tmp_path):
    run = Run(tmp_path)
    run.scene("scene-01")
    combined = verify_processing(run.root, run.waves("scene-01"), ["scene-01"], readback_workers=1, processed_reader=echo_reader)
    item = by_scene(combined)["scene-01"]
    assert item["state"] == "MISSING" and item["reason"] == "PROCESSING_NOT_RUN"


def test_a_broken_journal_is_refused(tmp_path):
    run = Run(tmp_path)
    run.scene("scene-01")
    run.final("scene-01")
    path = run.root / "host/processing-journal.jsonl"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(reversed(lines)) + "\n")
    with pytest.raises(ValueError, match="PROCESSING_JOURNAL_INVALID"):
        run.verify(run.waves("scene-01"), ["scene-01"])


def _combined(tmp_path):
    run = Run(tmp_path)
    for name in ("a", "b", "c"):
        run.scene(name)
    run.scene("u", status="FAILED")
    run.final("a")
    run.final("b", outcome="INVALID")
    run.scenes["b"].write(act_data_status="INVALID", act_data_qc="NOT_RUN", act_data_reason="OFFLINE_PROCESSOR_INVALID: rc=3",
                          export_eligible=False, qc_report_path=None, qc_report_sha256=None, inputs_sha256=None,
                          scope_sha256=None, audit_manifest_sha256=None, collection_mode=None)
    run.missing("c")
    rows = [run.scenes[n].row(pending=n != "u") for n in ("a", "b", "c", "u")]
    waves = [dict(wave_index=0, scene_count=4, coordinator_root="x", case_results=rows)]
    return run, waves, run.verify(waves, ["a", "b", "c", "u", "z"])


def test_the_campaign_result_lists_every_scene_with_the_processing_files_it_was_built_from(tmp_path):
    run, waves, combined = _combined(tmp_path)
    result = build_campaign_result("camp", 5, combined)
    assert result["kind"] == "act_collection_campaign_result" and result["schema_version"] == 2
    assert [item["scene_id"] for item in result["scenes"]] == ["a", "b", "c", "u", "z"]
    assert result["processing"]["summary"]["sha256"] and result["processing"]["journal"]["sha256"]
    assert result["missing_evidence"] == ["z"] and result["counts"]["PROCESSED"] == 2


def test_the_frozen_index_exports_only_a_processed_pass_and_lists_the_scenes_without_evidence(tmp_path):
    run, waves, combined = _combined(tmp_path)
    index = build_frozen_index(campaign_id="camp", qualification=False, scene_count=5, combined=combined)
    tasks = {item["scene_id"]: item for item in index["collected_tasks"]}
    assert set(tasks) == {"a", "b", "c", "u"}
    assert tasks["a"]["act_data_status"] == "VALID" and tasks["b"]["act_data_status"] == "INVALID"
    assert tasks["c"]["act_data_status"] == "PROCESSING_MISSING" and tasks["u"]["act_data_status"] == "INVALID"
    committed, = index["committed_episodes"]
    scene = run.scenes["a"]
    assert committed["scene_id"] == "a" and committed["schema_version"] == 4
    assert committed["verifier_sha256"] == scene.result_sha256
    assert committed["processed_result_sha256"] == by_scene(combined)["a"]["phase2"]["processed_result"]["sha256"]
    assert committed["collection_evidence"]["processing_output"] == str(scene.output)
    assert committed["collection_evidence"]["result_location"] == str(scene.sealed)
    assert [item["scene_id"] for item in index["scenes_without_evidence"]] == ["c", "z"]
    qualification = build_frozen_index(campaign_id="camp", qualification=True, scene_count=5, combined=combined)
    assert qualification["committed_episodes"] == [], "a qualification campaign never lists committed episodes"


def test_the_readback_pool_worker_reads_a_processed_job_as_well_as_a_registration(tmp_path):
    from so101_demo.runtime.container_campaign import readback_pool

    scene = Processed(tmp_path, valid=False)
    result = tmp_path / "answer.json"
    job = dict(scene_id=scene.scene, registration="unused", scope=str(scene.scope), inputs_manifest=str(scene.inputs),
               processing=dict(output_dir=str(scene.output), sealed=str(scene.sealed), scene_id=scene.scene,
                               result_sha256=scene.result_sha256, receipt_sha256=scene.receipt_sha256))
    request = dict(identity=readback_pool.import_identity(), result_path=str(result), job=job)
    assert readback_pool.worker_main(request) == 0
    body = json.loads(result.read_text())
    assert body["ok"] is True and body["proof"]["act_data_status"] == "INVALID" and body["proof"]["scene_id"] == scene.scene
    job["processing"]["result_sha256"] = "0" * 64
    assert readback_pool.worker_main(dict(request, job=job)) == 0
    assert json.loads(result.read_text())["ok"] is False


def test_the_legacy_index_still_refuses_a_pending_proof(tmp_path):
    run = Run(tmp_path)
    run.scene("a")
    with pytest.raises(ValueError, match="PROCESSING_PENDING"):
        build_frozen_index(campaign_id="camp", qualification=False, scene_count=1, waves=run.waves("a"))
