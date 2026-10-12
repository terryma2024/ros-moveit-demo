"""`inspect` verifies a contact proposal with the rule the freeze uses: the proposal's own validation mode.

The ledger-reference rule is unchanged (only JSON files the ledger names are candidates), and the approvals the formal freeze
accepts are unchanged (a spot_check_candidate receipt is never offered as a user activation). Every file is built here."""
import json

import test_act_contact_calibration as base
import test_contact_calibration_spot_check_mode as d3
from so101_demo.act.contact_calibration import analyze_evidence, make_activation_receipt
from so101_demo.act.diagnostic_episode_inputs import inspect_inputs
from so101_demo.act.diagnostic_episode_inspection import _compiled_model_identity
from paths import REPOSITORY

MODE = d3.MODE


def _proposal(monkeypatch, identity, *, spot_check):
    meta = dict(d3.offline_metadata() if spot_check else d3.ORIGINAL_METADATA(), **identity,
                allowed_other_contact_bodies=["table"])
    monkeypatch.setattr(base, "_metadata", lambda: meta)
    offline, live = base._cohorts()
    if spot_check:
        return analyze_evidence(offline, None, meta, validation_mode=MODE)
    return analyze_evidence(offline, live, meta)


def _receipt(proposal, root, *, kind=None, by="user-standing-authorization:test"):
    return make_activation_receipt(proposal, proposal["policy_fingerprint"], approved_by=by,
                                   approval_reference="test activation", evidence_root=root,
                                   approved_at="2026-10-07T00:00:00+00:00", receipt_kind=kind)


def _world(tmp_path, proposal, receipt, receipt_name="activation-receipt.json"):
    evidence = tmp_path / "evidence"
    calibration = evidence / "calibration"
    calibration.mkdir(parents=True)
    proposal_path = calibration / "proposal.json"
    receipt_path = calibration / receipt_name
    proposal_path.write_text(json.dumps(proposal))
    receipt_path.write_text(json.dumps(receipt))
    ledger = tmp_path / "ledger.md"
    ledger.write_text(f"---\nevidence_root: {evidence}\n---\nproposal {proposal_path}\nreceipt {receipt_path}\n")
    return evidence, ledger, proposal_path, receipt_path


def _identity():
    return _compiled_model_identity(REPOSITORY)


def test_a_spot_check_mode_proposal_and_its_receipt_are_listed_and_the_scene_is_ready(tmp_path, monkeypatch):
    identity = _identity()
    proposal = _proposal(monkeypatch, identity, spot_check=True)
    evidence, ledger, proposal_path, receipt_path = _world(tmp_path, proposal, _receipt(proposal, tmp_path / "evidence"))
    roles = inspect_inputs(REPOSITORY, ledger)["roles"]
    assert [c["path"] for c in roles["contact_proposal"]["candidates"]] == [str(proposal_path)]
    assert roles["contact_proposal"]["candidates"][0]["approval"] == "disabled_proposal"
    assert [c["path"] for c in roles["contact_activation"]["candidates"]] == [str(receipt_path)]
    assert roles["contact_activation"]["candidates"][0]["approval"] == "user_activation"
    assert roles["scene_model"]["status"] == "READY" and roles["scene_model"]["blocker"] is None


def test_a_default_mode_proposal_is_still_listed(tmp_path, monkeypatch):
    identity = _identity()
    proposal = _proposal(monkeypatch, identity, spot_check=False)
    _, ledger, proposal_path, _ = _world(tmp_path, proposal, _receipt(proposal, tmp_path / "evidence"))
    roles = inspect_inputs(REPOSITORY, ledger)["roles"]
    assert [c["path"] for c in roles["contact_proposal"]["candidates"]] == [str(proposal_path)]


def test_a_proposal_for_another_model_is_still_refused(tmp_path, monkeypatch):
    other = dict(_identity(), model_sha256="1" * 64)
    proposal = _proposal(monkeypatch, other, spot_check=True)
    _, ledger, _, _ = _world(tmp_path, proposal, _receipt(proposal, tmp_path / "evidence"))
    roles = inspect_inputs(REPOSITORY, ledger)["roles"]
    assert roles["contact_proposal"]["candidates"] == [] and roles["contact_proposal"]["status"] == "MISSING"
    assert roles["contact_activation"]["candidates"] == []
    assert roles["scene_model"]["status"] == "UNAPPROVED"


def test_a_spot_check_candidate_receipt_is_not_offered_as_a_user_activation(tmp_path, monkeypatch):
    proposal = _proposal(monkeypatch, _identity(), spot_check=True)
    candidate = _receipt(proposal, tmp_path / "evidence", kind="spot_check_candidate", by="plan:test")
    _, ledger, proposal_path, _ = _world(tmp_path, proposal, candidate, receipt_name="candidate-receipt.json")
    roles = inspect_inputs(REPOSITORY, ledger)["roles"]
    assert [c["path"] for c in roles["contact_proposal"]["candidates"]] == [str(proposal_path)]
    assert roles["contact_activation"]["candidates"] == []
    assert roles["contact_activation"]["status"] == "MISSING"


def test_a_tampered_proposal_is_refused(tmp_path, monkeypatch):
    proposal = _proposal(monkeypatch, _identity(), spot_check=True)
    receipt = _receipt(proposal, tmp_path / "evidence")
    proposal["false_positive_rate"] = 0.5
    _, ledger, _, _ = _world(tmp_path, proposal, receipt)
    assert inspect_inputs(REPOSITORY, ledger)["roles"]["contact_proposal"]["candidates"] == []


def test_a_file_the_ledger_does_not_name_is_not_discovered(tmp_path, monkeypatch):
    proposal = _proposal(monkeypatch, _identity(), spot_check=True)
    evidence, ledger, _, _ = _world(tmp_path, proposal, _receipt(proposal, tmp_path / "evidence"))
    ledger.write_text(f"---\nevidence_root: {evidence}\n---\nonly the directory {evidence / 'calibration'}\n")
    roles = inspect_inputs(REPOSITORY, ledger)["roles"]
    assert roles["contact_proposal"]["candidates"] == [] and roles["contact_activation"]["candidates"] == []


def test_discovery_and_freeze_share_one_proposal_rule():
    from so101_demo.act import diagnostic_episode_inputs as inputs
    from so101_demo.act import diagnostic_episode_inspection as inspection

    assert inspection.verify_proposal_in_own_mode is inputs.verify_proposal_in_own_mode
