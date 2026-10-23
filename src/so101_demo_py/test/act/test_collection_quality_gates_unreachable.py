import hashlib
import json

from so101_demo.act.collection_quality_gates import QUALITY_ORDER, apply_rule, evaluate_scene


def _sealed_unreachable(tmp_path):
    """The sealed form of a pre-motion DYNAMIC_TARGET_UNREACHABLE Teacher failure: manifest present, no episode, no QC report."""
    sealed = tmp_path / "sealed"
    (sealed / "dynamic").mkdir(parents=True)
    (sealed / "dynamic" / "dynamic-execute-manifest.json").write_text(json.dumps({
        "teacher_execution_status": "FAILED", "teacher_task_result": {"result": "UNCONFIRMED"},
        "failure": "DYNAMIC_TARGET_UNREACHABLE"}))
    raw = json.dumps({
        "kind": "ACT_COLLECTION_RESULT", "schema_version": 3, "status": "FAILED",
        "teacher_execution_status": "FAILED", "teacher_task_result": "UNCONFIRMED",
        "act_data_status": "INVALID", "act_data_reason": "DYNAMIC_TARGET_UNREACHABLE", "act_data_qc": "NOT_RUN",
        "export_eligible": False, "episode_seal_sha256": None, "qc_report_sha256": None, "qc_report_path": None,
        "inputs_sha256": None, "scope_sha256": None, "audit_manifest_sha256": None, "collection_mode": None}).encode()
    (sealed / "result.json").write_bytes(raw)
    return dict(location=str(sealed), result_sha256=hashlib.sha256(raw).hexdigest())


def test_the_unreachable_teacher_failure_is_a_non_success_without_evidence_errors(tmp_path):
    verdicts, membership = evaluate_scene(_sealed_unreachable(tmp_path))
    assert set(verdicts) == set(QUALITY_ORDER)
    assert all(error is None for _outcome, _source, error in verdicts.values()), verdicts
    assert verdicts["teacher_physical_success_rate"][0] in ("NO_EVIDENCE", "FAIL")
    assert verdicts["recorder_lossless"][0] == "NO_EVIDENCE" and verdicts["frame_continuity"][0] == "NO_EVIDENCE"
    assert membership == (False, "NO_QC_EVIDENCE"), "excluded from the QC_VALID_EPISODES population with a reason"


def test_that_scene_stays_in_the_teacher_denominator_as_a_non_pass(tmp_path):
    verdicts, _ = evaluate_scene(_sealed_unreachable(tmp_path))
    outcome = verdicts["teacher_physical_success_rate"][0]
    rule = {"pass": {"kind": "EVERY"}}
    assert apply_rule(rule, [outcome]) == (0, "FAIL")
