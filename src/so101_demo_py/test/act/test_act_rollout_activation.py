"""The calibration substitution: the contact-policy activation receipt stands in for the never-produced QUALIFIED report."""

import hashlib
import json

import pytest

import test_act_contact_calibration as base
from so101_demo.act.contact_calibration import analyze_evidence, make_activation_receipt
from so101_demo.act.rollout_activation import RULING, contact_activation_substitution


def _world(tmp_path, *, edit_proposal=None, edit_receipt=None):
    offline, live = base._cohorts()
    proposal = analyze_evidence(offline, live, base._metadata())
    receipt = make_activation_receipt(proposal, proposal["policy_fingerprint"], approved_by="user",
                                      approval_reference="test activation", evidence_root=tmp_path,
                                      approved_at="2026-10-07T00:00:00+00:00")
    if edit_proposal is not None:
        edit_proposal(proposal)
    if edit_receipt is not None:
        edit_receipt(receipt)
    proposal_path, receipt_path = tmp_path / "proposal.json", tmp_path / "activation-receipt.json"
    proposal_path.write_text(json.dumps(proposal))
    receipt_path.write_text(json.dumps(receipt))
    return proposal_path, receipt_path, proposal


def test_a_verified_receipt_gives_the_substitution_block(tmp_path):
    proposal_path, receipt_path, proposal = _world(tmp_path)
    block = contact_activation_substitution(receipt_path, proposal_path)
    assert block["substituted_by"] == "contact_activation_receipt"
    assert block["path"] == str(receipt_path)
    assert block["sha256"] == hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    assert block["policy_fingerprint"] == proposal["policy_fingerprint"]
    assert block["ruling"] == RULING and "calibration" in RULING
    assert block["proposal"] == {"path": str(proposal_path), "sha256": hashlib.sha256(proposal_path.read_bytes()).hexdigest()}


@pytest.mark.parametrize("edit", [
    lambda receipt: receipt.update(policy_fingerprint="2" * 64),
    lambda receipt: receipt.update(approved_by=""),
    lambda receipt: receipt.update(evidence_root="relative/path")])
def test_a_receipt_that_does_not_approve_the_exact_proposal_is_refused(tmp_path, edit):
    proposal_path, receipt_path, _ = _world(tmp_path, edit_receipt=edit)
    with pytest.raises(ValueError, match="ROLLOUT_ACTIVATION_NOT_VERIFIED"):
        contact_activation_substitution(receipt_path, proposal_path)


def test_a_tampered_proposal_is_refused(tmp_path):
    proposal_path, receipt_path, _ = _world(tmp_path, edit_proposal=lambda p: p.update(false_positive_rate=0.5))
    with pytest.raises(ValueError, match="ROLLOUT_ACTIVATION_NOT_VERIFIED"):
        contact_activation_substitution(receipt_path, proposal_path)


def test_a_missing_or_symlinked_file_is_refused(tmp_path):
    proposal_path, receipt_path, _ = _world(tmp_path)
    with pytest.raises(ValueError, match="ROLLOUT_ACTIVATION_FILE_INVALID"):
        contact_activation_substitution(tmp_path / "absent.json", proposal_path)
    link = tmp_path / "link.json"
    link.symlink_to(receipt_path)
    with pytest.raises(ValueError, match="ROLLOUT_ACTIVATION_FILE_INVALID"):
        contact_activation_substitution(link, proposal_path)


def test_a_proposal_of_the_offline_spot_check_mode_is_verified_in_its_own_mode(tmp_path, monkeypatch):
    """The side-wrist activation (receipt 93bd5108) is of the offline_fit_teacher_spot_check mode: the verification must use the
    mode the proposal declares, as collection admission does (found when the first live rollout refused with
    ROLLOUT_ACTIVATION_NOT_VERIFIED)."""
    import test_contact_calibration_spot_check_mode as spot

    offline = spot.offline_only(monkeypatch)
    proposal = analyze_evidence(offline, None, spot.offline_metadata(), validation_mode=spot.MODE)
    receipt = make_activation_receipt(proposal, proposal["policy_fingerprint"], approved_by="user",
                                      approval_reference="test activation", evidence_root=tmp_path,
                                      approved_at="2026-10-07T00:00:00+00:00")
    proposal_path, receipt_path = tmp_path / "proposal.json", tmp_path / "activation-receipt.json"
    proposal_path.write_text(json.dumps(proposal))
    receipt_path.write_text(json.dumps(receipt))
    block = contact_activation_substitution(receipt_path, proposal_path)
    assert block["policy_fingerprint"] == proposal["policy_fingerprint"]
