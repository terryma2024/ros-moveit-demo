"""The Host readback of `processed-result.json`: every binding to the phase-1 record is re-checked, a lie is refused."""

import pytest

from processed_fixture import Processed


def test_a_valid_processed_result_reads_back_with_its_bindings(tmp_path):
    scene = Processed(tmp_path)
    record = scene.verify()
    assert record["status"] == "PASS" and record["act_data_status"] == "VALID" and record["act_data_qc"] == "PASS"
    assert record["export_eligible"] is True and record["processed_result"]["path"] == "processed-result.json"
    assert record["phase1_result_sha256"] == scene.result_sha256 and record["receipt_sha256"] == scene.receipt_sha256
    assert record["data_dir"] == str(scene.output) and record["qc_report_sha256"] == "q" * 64


def test_an_invalid_data_verdict_reads_back_without_a_grading_and_is_not_exportable(tmp_path):
    scene = Processed(tmp_path, valid=False)

    def forbidden(**kwargs):
        raise AssertionError("an INVALID verdict is not graded again")
    record = scene.verify(regrade=forbidden)
    assert record["act_data_status"] == "INVALID" and record["export_eligible"] is False and record["qc_report_sha256"] is None


def test_a_deferred_fault_run_keeps_its_data_under_out(tmp_path):
    scene = Processed(tmp_path, valid=False, fault="topic_drop")
    assert scene.verify()["data_dir"] == str(scene.output / "out")


@pytest.mark.parametrize("edit", [
    dict(phase1_result_sha256="0" * 64),                        # bound to another phase-1 result
    dict(receipt_sha256="0" * 64),                              # bound to another receipt
    dict(scene_id="scene-02"),
    dict(identity=dict(session_id="other", reset_epoch=1, attempt_id="scene-01-lease-1")),
    dict(lease_identity=dict(point_id="scene-01")),
    dict(status="FAILED"),                                      # the Teacher status is phase 1's
    dict(proc_attempt=2),                                       # the directory and the task id say attempt 1
    dict(export_eligible=False),                                # not the rule's value
    dict(act_data_status="MAYBE"),
    dict(episode_seal_sha256="0" * 64),                         # not the seal on disk
    dict(extra=1),
])
def test_a_processed_result_that_contradicts_the_phase_1_record_is_refused(tmp_path, edit):
    scene = Processed(tmp_path)
    scene.write(**edit)
    with pytest.raises(ValueError, match="PROCESSED_RESULT_INVALID"):
        scene.verify()


def test_a_tampered_phase_1_result_is_refused(tmp_path):
    scene = Processed(tmp_path)
    (scene.sealed / "result.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="PROCESSED_RESULT_INVALID"):
        scene.verify()


def test_a_non_canonical_document_is_refused(tmp_path):
    scene = Processed(tmp_path)
    path = scene.output / "processed-result.json"
    path.write_text(" " + path.read_text())
    with pytest.raises(ValueError, match="PROCESSED_RESULT_INVALID"):
        scene.verify()


@pytest.mark.parametrize("override", [dict(status="INVALID"), dict(qc="FAIL"), dict(episode_sha256="0" * 64),
                                      dict(binding=dict(qc_report_path="qc-report.json", qc_report_sha256="x" * 64))])
def test_a_valid_verdict_the_files_do_not_support_is_refused(tmp_path, override):
    scene = Processed(tmp_path)
    with pytest.raises(ValueError, match="PROCESSED_RESULT_INVALID"):
        scene.verify(regrade=scene.grader(**override))


def test_an_invalid_verdict_may_not_carry_a_qc_binding(tmp_path):
    scene = Processed(tmp_path, valid=False)
    scene.write(qc_report_sha256="q" * 64)
    with pytest.raises(ValueError, match="PROCESSED_RESULT_INVALID"):
        scene.verify()


def test_a_missing_document_is_refused(tmp_path):
    scene = Processed(tmp_path)
    (scene.output / "processed-result.json").unlink()
    with pytest.raises(ValueError, match="PROCESSED_RESULT_INVALID"):
        scene.verify()


def test_the_regrade_reason_is_in_the_cause_chain_but_the_refusal_text_is_unchanged(tmp_path):
    scene = Processed(tmp_path)
    reason = "TEACHER_ORACLE_EXCLUDED: INCOMPLETE WORLD_SEQUENCE_GAP"
    with pytest.raises(ValueError) as refused:
        scene.verify(regrade=scene.grader(status="INVALID", reason=reason, qc="NOT_RUN"))
    assert str(refused.value) == "PROCESSED_RESULT_INVALID"
    assert reason in str(refused.value.__cause__)
