"""Task 8P4 RED: qualification is derived from complete live evidence, never asserted."""

import hashlib
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
