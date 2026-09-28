"""Task 8P4 RED: qualification is derived from complete live evidence, never asserted."""

import hashlib
import json
from pathlib import Path

import pytest


def _summary(**overrides):
    digests = [f"{index:064d}" for index in range(1, 15)]
    summary = {"status": "PASSED", "prefix_count": 9, "consecutive_full_count": 5,
               "case_journal_sha256": digests}
    summary.update(overrides)
    return summary


def _sample(tmp_path, name="release.json"):
    path = tmp_path / name
    path.write_text('{"sample": true}')
    return {"sample_path": str(path),
            "sample_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_campaign_summary_requires_passed_complete_and_consecutive():
    from so101_demo.act.task8_live_qualification import validate_campaign_summary

    assert validate_campaign_summary(_summary())["status"] == "PASSED"
    for broken, code in ((_summary(status="FAILED"), "TASK8_QUALIFICATION_NOT_PASSED"),
                         (_summary(prefix_count=8), "TASK8_QUALIFICATION_CASE_COUNT_INVALID"),
                         (_summary(consecutive_full_count=4),
                          "TASK8_QUALIFICATION_FULLS_NOT_CONSECUTIVE"),
                         (_summary(case_journal_sha256=["a" * 64] * 14),
                          "TASK8_QUALIFICATION_JOURNAL_DUPLICATE"),
                         (_summary(case_journal_sha256=["nope"] + [f"{i:064d}"
                                                                   for i in range(2, 15)]),
                          "TASK8_QUALIFICATION_JOURNAL_HASH_INVALID"),
                         (_summary(extra=1), "TASK8_QUALIFICATION_SUMMARY_INVALID")):
        with pytest.raises(ValueError, match=code):
            validate_campaign_summary(broken)


def test_release_sample_requires_support_then_contact_loss_and_a_real_file(tmp_path):
    from so101_demo.act.task8_live_qualification import validate_release_sample

    sample = dict(_sample(tmp_path), supported_before_open=True, contact_lost_after_open=True,
                  stable_window_s=0.5)
    assert validate_release_sample(sample)["stable_window_s"] == 0.5
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_RELEASE_INVALID"):
        validate_release_sample(dict(sample, supported_before_open=False))
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_RELEASE_INVALID"):
        validate_release_sample(dict(sample, contact_lost_after_open=False))
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_SAMPLE_HASH_INVALID"):
        validate_release_sample(dict(sample, sample_sha256="0" * 64))
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_SAMPLE_MISSING"):
        validate_release_sample(dict(sample, sample_path=str(tmp_path / "absent.json")))


def test_retreat_sample_requires_distance_stability_and_the_deadline(tmp_path):
    from so101_demo.act.task8_live_qualification import validate_retreat_sample

    sample = dict(_sample(tmp_path, "retreat.json"), retreat_distance_m=0.06, target_stable=True,
                  completed_s=12.5)
    assert validate_retreat_sample(sample)["retreat_distance_m"] == 0.06
    for broken in (dict(sample, target_stable=False), dict(sample, retreat_distance_m=0.0),
                   dict(sample, completed_s=121.0), dict(sample, completed_s=-1.0)):
        with pytest.raises(ValueError, match="TASK8_QUALIFICATION_RETREAT_INVALID"):
            validate_retreat_sample(broken)


def _manifest():
    return {"prefix_cases": [{"case_id": f"prefix-{index:02d}"} for index in range(1, 10)],
            "full_cases": [{"case_id": f"full-{index:02d}"} for index in range(1, 6)]}


def _row(case_id, identity, manifest_document_sha256):
    prefix = case_id.startswith("prefix-")
    row = {"case_id": case_id, "mode": "phase_prefix" if prefix else "full", "status": "PASSED",
           "live_evidence_path": "" if prefix else f"/run/{case_id}-live.json",
           "live_evidence_sha256": "0" * 64 if prefix else "b" * 64,
           "child_retirement_receipt_path": f"/run/{case_id}-child.json",
           "child_retirement_receipt_sha256": "c" * 64,
           "stack_retirement_receipt_path": f"/run/{case_id}-stack.json",
           "stack_retirement_receipt_sha256": "d" * 64,
           "source_provenance_sha256": identity["source_provenance_sha256"],
           "runtime_config_sha256": identity["runtime_config_sha256"],
           "contact_policy_fingerprint": identity["contact_policy_fingerprint"],
           "manifest_document_sha256": manifest_document_sha256}
    return row


def _write_journals(root, identity, manifest_document_sha256, *, skip=None, mutate=None):
    cases = root / "task8-live" / "cases"
    cases.mkdir(parents=True)
    for case in [*_manifest()["prefix_cases"], *_manifest()["full_cases"]]:
        case_id = case["case_id"]
        if case_id == skip:
            continue
        row = _row(case_id, identity, manifest_document_sha256)
        if mutate is not None and case_id == mutate[0]:
            row.update(mutate[1])
        (cases / f"{case_id}.json").write_text(json.dumps(row))


def test_all_fourteen_journals_must_exist_and_match_the_bundle(tmp_path):
    from so101_demo.act.task8_live_qualification import validate_case_journals

    identity = {"source_provenance_sha256": "e" * 64, "runtime_config_sha256": "f" * 64,
                "contact_policy_fingerprint": "a" * 64}
    root = tmp_path / "run"
    root.mkdir()
    _write_journals(root, identity, "9" * 64)
    rows = validate_case_journals(root, _manifest(), identities=identity,
                                  manifest_document_sha256="9" * 64)
    assert [row["case_id"] for row in rows] == [f"prefix-{i:02d}" for i in range(1, 10)] + \
        [f"full-{i:02d}" for i in range(1, 6)]


@pytest.mark.parametrize("skip,mutate,code", [
    ("full-05", None, "TASK8_QUALIFICATION_JOURNAL_MISSING"),   # the last of the five fulls
    (None, ("full-01", {"source_provenance_sha256": "7" * 64}),
     "TASK8_JOURNAL_IDENTITY_MISMATCH"),
    (None, ("prefix-01", {"live_evidence_sha256": "b" * 64}), "TASK8_PREFIX_EVIDENCE_FORBIDDEN"),
    (None, ("full-01", {"stack_retirement_receipt_sha256": "nope"}), "TASK8_JOURNAL_HASH_INVALID"),
])
def test_incomplete_or_foreign_journals_refuse_qualification(tmp_path, skip, mutate, code):
    from so101_demo.act.task8_live_qualification import validate_case_journals

    identity = {"source_provenance_sha256": "e" * 64, "runtime_config_sha256": "f" * 64,
                "contact_policy_fingerprint": "a" * 64}
    root = tmp_path / "run"
    root.mkdir()
    _write_journals(root, identity, "9" * 64, skip=skip, mutate=mutate)
    with pytest.raises(ValueError, match=code):
        validate_case_journals(root, _manifest(), identities=identity,
                               manifest_document_sha256="9" * 64)
