"""The explicit offline_fit_teacher_spot_check validation mode, bound into the fingerprinted payload.

The default mode still demands the live cohort. The mode is the user's recorded rule deviation, so it lives in
the payload (`live_collector_sha256` = sha256 of the canonical descriptor), which the activation fingerprint covers, and the
envelope merely repeats it. Synthetic cohorts come from test_act_contact_calibration; nothing here qualifies a policy."""
import copy
import hashlib
import json

import pytest

import test_act_contact_calibration as base
from so101_demo.act import contact_calibration as cal
from so101_demo.act.contact_calibration import analyze_evidence, analyze_manifests, seal_cohort, verify_disabled_proposal

MODE = "offline_fit_teacher_spot_check"
DESCRIPTOR = hashlib.sha256(json.dumps({"validation_mode": MODE, "decision": "owner_deviation_offline_cohort"}, sort_keys=True,
                                       separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


ORIGINAL_METADATA = base._metadata


def offline_metadata():
    return dict(ORIGINAL_METADATA(), live_collector_sha256=DESCRIPTOR)


def offline_only(monkeypatch):
    monkeypatch.setattr(base, "_metadata", offline_metadata)
    return base._cohorts()[0]


def rehash(proposal):
    body = {key: value for key, value in proposal.items() if key != "proposal_sha256"}
    return dict(body, proposal_sha256=hashlib.sha256(cal._canonical(body)).hexdigest())


def test_a_default_mode_proposal_without_a_live_cohort_is_refused():
    offline, _ = base._cohorts()
    with pytest.raises(ValueError, match="live cohort"):
        analyze_evidence(offline, None, ORIGINAL_METADATA())


def test_offline_mode_builds_a_disabled_proposal_bound_to_the_descriptor(monkeypatch):
    offline = offline_only(monkeypatch)
    proposal = analyze_evidence(offline, None, offline_metadata(), validation_mode=MODE)
    assert proposal["status"] == "DISABLED"
    assert proposal["payload"]["live_collector_sha256"] == DESCRIPTOR
    assert proposal["validation"] == {"mode": MODE, "decision": "owner_deviation_offline_cohort", "teacher_spot_check": "PENDING",
                                      "live_cohort": "NOT_COLLECTED"}
    assert proposal["counts"] == {regime: {"offline": 20, "live": 0} for regime in base.REGIMES}
    assert proposal["confusion_matrix"]["stable_hold"]["stable_hold"] == 20
    verify_disabled_proposal(proposal, validation_mode=MODE)
    verify_disabled_proposal(proposal, validation_mode=MODE)


def test_the_mode_is_in_the_fingerprint_so_a_default_payload_cannot_pass_as_offline(monkeypatch):
    offline, live = base._cohorts()
    default = analyze_evidence(offline, live, ORIGINAL_METADATA())
    offline_proposal = analyze_evidence(offline_only(monkeypatch), None, offline_metadata(), validation_mode=MODE)
    assert default["policy_fingerprint"] != offline_proposal["policy_fingerprint"]


def test_a_default_proposal_does_not_verify_in_offline_mode_and_the_reverse(monkeypatch):
    offline, live = base._cohorts()
    default = analyze_evidence(offline, live, ORIGINAL_METADATA())
    verify_disabled_proposal(default)
    with pytest.raises(ValueError, match="validation mode"):
        verify_disabled_proposal(default, validation_mode=MODE)
    offline_proposal = analyze_evidence(offline_only(monkeypatch), None, offline_metadata(), validation_mode=MODE)
    with pytest.raises(ValueError, match="validation mode"):
        verify_disabled_proposal(offline_proposal, validation_mode="unknown_mode")


def test_an_envelope_whose_mode_disagrees_with_its_payload_is_refused(monkeypatch):
    offline, live = base._cohorts()
    default = analyze_evidence(offline, live, ORIGINAL_METADATA())
    proposal = analyze_evidence(offline_only(monkeypatch), None, offline_metadata(), validation_mode=MODE)
    stripped = copy.deepcopy(proposal)
    del stripped["validation"]                      # payload says offline, envelope says default
    with pytest.raises(ValueError, match="validation mode"):
        verify_disabled_proposal(rehash(stripped))
    forged = copy.deepcopy(default)                 # payload says default, envelope claims the deviation
    forged["validation"] = proposal["validation"]
    with pytest.raises(ValueError, match="validation mode"):
        verify_disabled_proposal(rehash(forged))


def test_offline_mode_needs_its_descriptor_and_takes_no_live_cohort(monkeypatch):
    offline = offline_only(monkeypatch)
    with pytest.raises(ValueError, match="descriptor"):
        analyze_evidence(offline, None, ORIGINAL_METADATA(), validation_mode=MODE)
    _, live = base._cohorts()
    with pytest.raises(ValueError, match="live cohort"):
        analyze_evidence(offline, live, offline_metadata(), validation_mode=MODE)
    with pytest.raises(ValueError, match="validation mode"):
        analyze_evidence(offline, None, offline_metadata(), validation_mode="other")


def test_offline_mode_still_requires_every_control(monkeypatch):
    offline = offline_only(monkeypatch)
    offline["samples"] = [item for item in offline["samples"] if item["regime"] != "post_release"]
    with pytest.raises(ValueError, match="negative controls"):
        analyze_evidence(offline, None, offline_metadata(), validation_mode=MODE)


def test_offline_mode_self_classifies_the_offline_cohort(monkeypatch):
    offline = offline_only(monkeypatch)
    # a bilateral_touch sample that looks like an over-squeeze can no longer be separated: the fit itself refuses
    for item in offline["samples"]:
        if item["regime"] == "bilateral_touch" and item["sample_id"].endswith("003"):
            for frame in item["frames"]:
                for side in ("left_contacts", "right_contacts"):
                    frame[side][0]["normal_force_n"] = 6.0
            item["diagnostic_result"]["peak_force_n"] = 12.4
            item["diagnostic_result"]["peak_force_n"] = max(
                sum(c["normal_force_n"] for k in ("left_contacts", "right_contacts", "other_contacts")
                    for c in frame[k]) for frame in item["frames"])
    with pytest.raises(ValueError):
        analyze_evidence(offline, None, offline_metadata(), validation_mode=MODE)


def test_the_fit_formula_is_unchanged(monkeypatch):
    offline, live = base._cohorts()
    default = analyze_evidence(offline, live, ORIGINAL_METADATA())
    again = analyze_evidence(offline_only(monkeypatch), None, offline_metadata(), validation_mode=MODE)
    assert again["payload"]["thresholds"] == default["payload"]["thresholds"]
    # the D2 preview inputs: normal max (stable_hold) / over min give the same midpoints as the preview run
    assert cal._separating([9.821099586905134e-05], [0.0001403513383594888], "c") == pytest.approx(
        0.00011928116711427007, rel=0, abs=1e-18)
    assert cal._separating([1.547328152099317], [2.235932742595038], "f") == pytest.approx(
        1.8916304473471774, rel=0, abs=1e-15)


def test_analyze_manifests_and_the_analyze_cli_follow_the_same_rules(tmp_path, monkeypatch):
    from so101_demo.cli.act_analyze_contact_calibration import main as analyze_main

    offline = offline_only(monkeypatch)
    offline_manifest = seal_cohort(tmp_path / "offline", offline)
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(offline_metadata()))
    with pytest.raises(ValueError, match="live cohort"):
        analyze_manifests(offline_manifest, None, offline_metadata())
    out = tmp_path / "proposal.json"
    args = ["--offline", str(offline_manifest), "--metadata", str(metadata), "--proposal", str(out)]
    with pytest.raises((ValueError, SystemExit)):
        analyze_main(args)                       # no --live and no --validation-mode: refused
    assert not out.exists()
    assert analyze_main(args + ["--validation-mode", MODE]) == 0
    proposal = json.loads(out.read_text())
    assert proposal["validation"]["mode"] == MODE and proposal["payload"]["live_collector_sha256"] == DESCRIPTOR
    live_manifest = seal_cohort(tmp_path / "live", base._cohorts()[1])
    with pytest.raises((ValueError, SystemExit)):
        analyze_main(args[:-1] + [str(tmp_path / "p2.json"), "--live", str(live_manifest), "--validation-mode", MODE])
