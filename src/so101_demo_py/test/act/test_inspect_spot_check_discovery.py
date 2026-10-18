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


# ---- the opt-in: `--spot-check-receipt <path>` lists one named candidate receipt, and only it --------------------------------------


def _candidate_world(tmp_path, monkeypatch, name="candidate-receipt.json"):
    proposal = _proposal(monkeypatch, _identity(), spot_check=True)
    candidate = _receipt(proposal, tmp_path / "evidence", kind="spot_check_candidate", by="plan:test")
    evidence, ledger, proposal_path, receipt_path = _world(tmp_path, proposal, candidate, receipt_name=name)
    return proposal, evidence, ledger, proposal_path, receipt_path


def test_the_opt_in_lists_the_named_candidate_receipt_with_its_own_approval_kind(tmp_path, monkeypatch):
    _, _, ledger, proposal_path, receipt_path = _candidate_world(tmp_path, monkeypatch)
    roles = inspect_inputs(REPOSITORY, ledger, spot_check_receipt=receipt_path)["roles"]
    assert [c["path"] for c in roles["contact_proposal"]["candidates"]] == [str(proposal_path)]
    activation = roles["contact_activation"]
    assert activation["status"] == "READY" and activation["blocker"] is None
    assert [(c["path"], c["approval"], c["approved"]) for c in activation["candidates"]] == [
        (str(receipt_path), "spot_check_candidate", True)]
    assert activation["selected"] == activation["candidates"][0]
    # without the opt-in the same ledger still offers nothing (the formal default is unchanged)
    assert inspect_inputs(REPOSITORY, ledger)["roles"]["contact_activation"]["candidates"] == []


def test_the_opt_in_replaces_the_activation_candidates_so_the_freeze_sees_exactly_one(tmp_path, monkeypatch):
    proposal, evidence, ledger, _, receipt_path = _candidate_world(tmp_path, monkeypatch)
    user = evidence / "calibration" / "activation-receipt.json"
    user.write_text(json.dumps(_receipt(proposal, evidence)))
    ledger.write_text(ledger.read_text() + f"also {user}\n")
    default = inspect_inputs(REPOSITORY, ledger)["roles"]["contact_activation"]
    assert [c["approval"] for c in default["candidates"]] == ["user_activation"]
    opted = inspect_inputs(REPOSITORY, ledger, spot_check_receipt=receipt_path)["roles"]["contact_activation"]
    assert [c["approval"] for c in opted["candidates"]] == ["spot_check_candidate"]


def test_the_opt_in_refuses_a_receipt_that_is_not_a_candidate_for_the_proposal(tmp_path, monkeypatch):
    import pytest

    proposal, evidence, ledger, _, receipt_path = _candidate_world(tmp_path, monkeypatch)
    # a normal (user) receipt is not a spot-check candidate
    user = evidence / "calibration" / "activation-receipt.json"
    user.write_text(json.dumps(_receipt(proposal, evidence)))
    with pytest.raises(ValueError, match="INPUT_SPOT_CHECK_RECEIPT_INVALID"):
        inspect_inputs(REPOSITORY, ledger, spot_check_receipt=user)
    # a candidate whose fingerprint is another policy's
    forged = json.loads(receipt_path.read_text())
    forged["policy_fingerprint"] = "f" * 64
    other = evidence / "calibration" / "forged-receipt.json"
    other.write_text(json.dumps(forged))
    with pytest.raises(ValueError, match="INPUT_SPOT_CHECK_RECEIPT_INVALID"):
        inspect_inputs(REPOSITORY, ledger, spot_check_receipt=other)
    # a candidate outside the registered evidence root, a missing file and a directory
    outside = tmp_path / "outside-receipt.json"
    outside.write_text(receipt_path.read_text())
    for bad in (outside, evidence / "calibration" / "absent.json", evidence / "calibration"):
        with pytest.raises(ValueError, match="INPUT_SPOT_CHECK_RECEIPT_INVALID"):
            inspect_inputs(REPOSITORY, ledger, spot_check_receipt=bad)


def test_the_opt_in_needs_exactly_one_proposal_for_this_scene(tmp_path, monkeypatch):
    import pytest

    proposal, evidence, ledger, proposal_path, receipt_path = _candidate_world(tmp_path, monkeypatch)
    proposal_path.write_text(json.dumps(dict(proposal, false_positive_rate=0.5)))   # tampered: no proposal remains
    with pytest.raises(ValueError, match="INPUT_SPOT_CHECK_RECEIPT_INVALID"):
        inspect_inputs(REPOSITORY, ledger, spot_check_receipt=receipt_path)


def test_the_cli_opt_in_is_a_flag_of_inspect_and_not_a_subcommand(tmp_path, monkeypatch, capsys):
    from so101_demo.cli import act_diagnostic_episode as cli

    parser = cli.build_parser()
    commands = next(action for action in parser._actions if getattr(action, "choices", None)).choices
    assert set(commands) == {"inspect", "prepare", "preflight", "qc", "verify-commit", "check-export", "readback"}
    assert "--spot-check-receipt" in commands["inspect"].format_help()
    assert "--spot-check-receipt" not in commands["prepare"].format_help()
    _, _, ledger, _, receipt_path = _candidate_world(tmp_path, monkeypatch)
    output = tmp_path / "candidates.json"
    base = ["inspect", "--source-root", str(REPOSITORY), "--ledger", str(ledger), "--output", str(output)]
    assert cli.main(base) == 0
    assert json.loads(output.read_text())["roles"]["contact_activation"]["candidates"] == []
    output.unlink()
    assert cli.main(base + ["--spot-check-receipt", str(receipt_path)]) == 0
    listed = json.loads(output.read_text())["roles"]["contact_activation"]["candidates"]
    assert [item["approval"] for item in listed] == ["spot_check_candidate"]
    output.unlink()
    assert cli.main(base + ["--spot-check-receipt", str(tmp_path / "nope.json")]) == 2
    assert "INPUT_SPOT_CHECK_RECEIPT_INVALID" in capsys.readouterr().err and not output.exists()
