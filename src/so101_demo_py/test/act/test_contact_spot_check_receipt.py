"""A spot_check_candidate receipt is refused everywhere by default and accepted only on the frozen-inputs
path of a preselected_target_diagnostic freeze. A run holding one can never be export eligible."""
import copy
import json
from pathlib import Path

import pytest

import test_act_contact_calibration as base
import test_contact_calibration_spot_check_mode as d3
from act_identity import ACT_MODEL_SHA256, ACT_SCENE_SHA256, PACKAGE
from so101_demo.act.contact_calibration import analyze_evidence, make_activation_receipt
from so101_demo.act.contact_policy import verify_activation

MODE = d3.MODE


@pytest.fixture
def proposal(monkeypatch):
    import mujoco
    meta = dict(d3.offline_metadata(), model_sha256=ACT_MODEL_SHA256, scene_sha256=ACT_SCENE_SHA256,
                mujoco_version=mujoco.mj_versionString(), allowed_other_contact_bodies=["table"])
    monkeypatch.setattr(base, "_metadata", lambda: meta)
    return analyze_evidence(base._cohorts()[0], None, meta, validation_mode=MODE)


def receipt(proposal, tmp_path, *, kind="spot_check_candidate", by="plan:R10-D4"):
    return make_activation_receipt(proposal, proposal["policy_fingerprint"], approved_by=by,
                                   approval_reference="CP-3389 plan R10 D4 candidate", evidence_root=tmp_path,
                                   approved_at="2026-10-07T00:00:00+00:00", receipt_kind=kind)


def test_a_candidate_receipt_is_refused_by_default_and_accepted_only_with_the_opt_in(proposal, tmp_path):
    candidate = receipt(proposal, tmp_path)
    assert candidate["receipt_kind"] == "spot_check_candidate"
    with pytest.raises(ValueError, match="POLICY_NOT_ACTIVATED"):
        verify_activation(proposal["payload"], candidate)
    verify_activation(proposal["payload"], candidate, allow_spot_check_candidate=True)


def test_a_normal_receipt_for_the_same_proposal_carries_no_kind_and_verifies_everywhere(proposal, tmp_path):
    normal = receipt(proposal, tmp_path, kind=None, by="user")
    assert "receipt_kind" not in normal
    verify_activation(proposal["payload"], normal)


@pytest.mark.parametrize("by", ["user", "zjumty", "zjumty@gmail.com", "terry", "", "planner", "plan:"])
def test_a_candidate_receipt_never_names_the_user(proposal, tmp_path, by):
    with pytest.raises(ValueError):
        receipt(proposal, tmp_path, by=by)


def test_an_unknown_kind_or_a_candidate_for_a_default_proposal_is_refused(proposal, tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        receipt(proposal, tmp_path, kind="other_kind")
    forged = copy.deepcopy(receipt(proposal, tmp_path))
    forged["receipt_kind"] = "other_kind"
    with pytest.raises(ValueError, match="POLICY_NOT_ACTIVATED"):
        verify_activation(proposal["payload"], forged, allow_spot_check_candidate=True)
    monkeypatch.setattr(base, "_metadata", d3.ORIGINAL_METADATA)
    offline, live = base._cohorts()
    default = analyze_evidence(offline, live, d3.ORIGINAL_METADATA())
    with pytest.raises(ValueError):
        make_activation_receipt(default, default["policy_fingerprint"], approved_by="plan:x", approval_reference="r",
                                evidence_root=tmp_path, approved_at="2026-10-07T00:00:00+00:00",
                                receipt_kind="spot_check_candidate")


@pytest.mark.parametrize("mode, accepted", [("formal", False), (None, False), ("anything", False),
                                            ("preselected_target_diagnostic", True)])
def test_the_frozen_inputs_path_opts_in_only_for_the_diagnostic_mode(proposal, tmp_path, mode, accepted):
    from so101_demo.act.diagnostic_episode_inputs import verify_contact_activation
    candidate = receipt(proposal, tmp_path)
    identity = {"model_sha256": ACT_MODEL_SHA256, "scene_sha256": ACT_SCENE_SHA256,
                "mujoco_version": proposal["payload"]["mujoco_version"]}
    if accepted:
        verify_contact_activation(proposal["payload"], candidate, identity, mode=mode)
    else:
        with pytest.raises(ValueError, match="INPUT_ACTIVATION_STALE"):
            verify_contact_activation(proposal["payload"], candidate, identity, mode=mode)
    verify_contact_activation(proposal["payload"], receipt(proposal, tmp_path, kind=None, by="user"), identity, mode=mode)


def write(tmp_path, proposal, candidate):
    (tmp_path / "proposal.json").write_text(json.dumps(proposal))
    (tmp_path / "receipt.json").write_text(json.dumps(candidate))
    return tmp_path / "proposal.json", tmp_path / "receipt.json"


def test_the_allowlist_refuses_the_candidate_unless_the_frozen_path_opts_in(proposal, tmp_path):
    import mujoco
    from so101_demo.adapters.act.phase_contact_allowlist import PhaseContactAllowlist
    scene = PACKAGE / "assets/mujoco/act/scene.xml"
    model = mujoco.MjModel.from_xml_path(str(scene))
    proposal_path, receipt_path = write(tmp_path, proposal, receipt(proposal, tmp_path))
    args = dict(model=model, scene_path=scene, proposal_path=proposal_path, receipt_path=receipt_path,
                expected_fingerprint=proposal["policy_fingerprint"])
    with pytest.raises(ValueError):
        PhaseContactAllowlist(**args)
    pairs = PhaseContactAllowlist(**args, allow_spot_check_candidate=True)
    assert pairs.thresholds["maximum_safe_force_n"] == proposal["payload"]["thresholds"]["maximum_safe_force_n"]


def test_the_installed_loader_never_accepts_the_candidate(proposal, tmp_path, monkeypatch):
    import inspect
    import ament_index_python.packages as packages
    from so101_demo.adapters.act import phase_contact_allowlist as module
    assert "allow_spot_check_candidate" not in inspect.signature(module.load_installed_phase_contact_allowlist).parameters
    monkeypatch.setattr(packages, "get_package_share_directory", lambda name: str(PACKAGE))
    proposal_path, receipt_path = write(tmp_path, proposal, receipt(proposal, tmp_path))
    with pytest.raises(ValueError, match="TASK8_CONTACT_POLICY_INVALID"):
        module.load_installed_phase_contact_allowlist(
            proposal_path=proposal_path, receipt_path=receipt_path, expected_fingerprint=proposal["policy_fingerprint"])
    normal = receipt(proposal, tmp_path, kind=None, by="user")
    (tmp_path / "receipt.json").write_text(json.dumps(normal))
    module.load_installed_phase_contact_allowlist(
        proposal_path=proposal_path, receipt_path=receipt_path, expected_fingerprint=proposal["policy_fingerprint"])


def test_the_bundle_refuses_a_diagnostic_episode_and_training_never_selects_it():
    from so101_demo.act.collection import TRAINABLE_COLLECTION_MODES, training_eligible
    assert "preselected_target_diagnostic" not in TRAINABLE_COLLECTION_MODES
    assert training_eligible({"collection_mode": "preselected_target_diagnostic"}) is False


@pytest.mark.parametrize("mode, expected", [("formal", True), ("preselected_target_diagnostic", False), (None, False)])
def test_export_eligible_needs_a_trainable_mode(mode, expected):
    from so101_demo.act.result_store import export_eligible
    assert export_eligible("PASSED", "PASS", mode) is expected
    assert export_eligible("FAILED", "PASS", mode) is False
    assert export_eligible("PASSED", "FAIL", mode) is False


def test_the_activation_cli_writes_a_candidate_receipt_only_for_a_plan_signer(tmp_path, monkeypatch):
    from so101_demo.act.contact_calibration import seal_cohort
    from so101_demo.cli.act_activate_contact_policy import main as activate_main
    from so101_demo.cli.act_analyze_contact_calibration import main as analyze_main

    meta = dict(d3.offline_metadata(), model_sha256=ACT_MODEL_SHA256, scene_sha256=ACT_SCENE_SHA256,
                mujoco_version=__import__("mujoco").mj_versionString(), allowed_other_contact_bodies=["table"])
    monkeypatch.setattr(base, "_metadata", lambda: meta)
    manifest = seal_cohort(tmp_path / "offline", base._cohorts()[0])
    (tmp_path / "metadata.json").write_text(json.dumps(meta))
    assert analyze_main(["--offline", str(manifest), "--metadata", str(tmp_path / "metadata.json"),
                         "--proposal", str(tmp_path / "proposal.json"), "--validation-mode", MODE]) == 0
    fingerprint = json.loads((tmp_path / "proposal.json").read_text())["policy_fingerprint"]
    common = ["--proposal", str(tmp_path / "proposal.json"), "--offline", str(manifest), "--metadata",
              str(tmp_path / "metadata.json"), "--validation-mode", MODE, "--policy-fingerprint", fingerprint,
              "--approval-reference", "CP-3389 plan R10 D4", "--evidence-root", str(tmp_path),
              "--receipt-kind", "spot_check_candidate"]
    with pytest.raises(ValueError):
        activate_main(common + ["--approved-by", "zjumty", "--receipt", str(tmp_path / "bad.json")])
    assert not (tmp_path / "bad.json").exists()
    assert activate_main(common + ["--approved-by", "plan:R10-D4", "--receipt", str(tmp_path / "ok.json")]) == 0
    document = json.loads((tmp_path / "ok.json").read_text())
    assert document["receipt_kind"] == "spot_check_candidate" and document["approved_by"] == "plan:R10-D4"
    proposal = json.loads((tmp_path / "proposal.json").read_text())
    verify_activation(proposal["payload"], document, allow_spot_check_candidate=True)
    with pytest.raises(ValueError, match="POLICY_NOT_ACTIVATED"):
        verify_activation(proposal["payload"], document)
