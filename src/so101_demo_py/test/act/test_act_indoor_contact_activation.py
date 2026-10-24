"""Re-activation of the approved contact policy for the side-wrist-indoor rig, derived from the stripped-fingerprint equivalence.

The approved side-wrist receipt is keyed on the old scene and model files. The indoor scene has the same stripped physics
fingerprint, so the SAME calibration (thresholds, evidence, motion policy) is re-bound to the indoor scene and model pins in a new
proposal and a new receipt that says how it was derived. The old receipt and its pin are never touched.
"""

import hashlib
import json

import mujoco
import pytest
from paths import PACKAGE_ROOT

import test_act_contact_calibration as base
from so101_demo.act import contact_collector, contact_derivation as derivation
from so101_demo.act.contact_calibration import analyze_evidence, make_activation_receipt, verify_disabled_proposal
from so101_demo.act.contact_policy import DERIVED_BY, policy_fingerprint, verify_activation
from so101_demo.act.rollout_activation import contact_activation_substitution

ACT = PACKAGE_ROOT / "assets/mujoco/act"
SIDE_SCENE, INDOOR_SCENE = ACT / "scene_side_wrist.xml", ACT / "scene_side_wrist_indoor.xml"
OLD_PINS = ("b" * 64, "a" * 64)          # the fixture's scene and model pins
NEW_PINS = ("1" * 64, "2" * 64)
STRIPPED = "9" * 64


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _old(tmp_path):
    offline, live = base._cohorts()
    proposal = analyze_evidence(offline, live, base._metadata())
    receipt = make_activation_receipt(proposal, proposal["policy_fingerprint"], approved_by="user",
                                      approval_reference="the old activation", evidence_root=tmp_path,
                                      approved_at="2026-10-07T00:00:00+00:00")
    return proposal, receipt


def _derive(tmp_path, **changes):
    proposal, receipt = _old(tmp_path)
    arguments = dict(old_receipt_bytes=json.dumps(receipt).encode(), equivalence_bytes=b'{"equivalence": 1}',
                     stripped_fingerprint=STRIPPED, old_pins=OLD_PINS, new_pins=NEW_PINS, approved_by="user:test",
                     approval_reference="the indoor re-activation", evidence_root=tmp_path,
                     approved_at="2026-10-24T00:00:00+00:00")
    arguments.update(changes)
    return proposal, receipt, derivation.derive_activation(proposal, receipt, **arguments)


# ---- the derived proposal and receipt --------------------------------------------------------------------------------------------------


def test_the_derived_proposal_is_the_same_calibration_bound_to_the_new_scene_and_model(tmp_path):
    old, _receipt, (new, _new_receipt) = _derive(tmp_path)
    assert new["payload"]["scene_sha256"] == NEW_PINS[0] and new["payload"]["model_sha256"] == NEW_PINS[1]
    same = {key: value for key, value in new["payload"].items() if key not in ("scene_sha256", "model_sha256")}
    assert same == {key: value for key, value in old["payload"].items() if key not in ("scene_sha256", "model_sha256")}
    for key in ("source_evidence_sha256", "counts", "confusion_matrix", "negative_controls", "false_positive_rate",
                "false_negative_rate", "status"):
        assert new[key] == old[key], key
    assert new["policy_fingerprint"] == policy_fingerprint(new["payload"]) != old["policy_fingerprint"]
    assert new["proposal_sha256"] != old["proposal_sha256"]
    verify_disabled_proposal(new)


def test_the_derived_receipt_names_its_derivation_and_cites_three_sha256s(tmp_path):
    _old_proposal, old_receipt, (proposal, receipt) = _derive(tmp_path)
    assert receipt["derived_by"] == DERIVED_BY == "stripped_physics_fingerprint_equivalence"
    assert receipt["old_receipt_sha256"] == _sha(json.dumps(old_receipt).encode())
    assert receipt["equivalence_record_sha256"] == _sha(b'{"equivalence": 1}')
    assert receipt["stripped_fingerprint_sha256"] == STRIPPED
    assert receipt["policy_fingerprint"] == proposal["policy_fingerprint"]
    assert receipt["source_evidence_sha256"] == proposal["source_evidence_sha256"]
    assert receipt["approved_by"] == "user:test" and receipt["approval_reference"] == "the indoor re-activation"


def test_the_derived_pair_passes_the_rollout_verification_and_only_with_the_new_pins(tmp_path):
    _old_proposal, _old_receipt, (proposal, receipt) = _derive(tmp_path)
    (tmp_path / "p.json").write_text(json.dumps(proposal))
    (tmp_path / "r.json").write_text(json.dumps(receipt))
    block = contact_activation_substitution(tmp_path / "r.json", tmp_path / "p.json")
    assert block["policy_fingerprint"] == proposal["policy_fingerprint"]
    verify_activation(proposal["payload"], receipt, expected_scene_sha256=NEW_PINS[0], expected_model_sha256=NEW_PINS[1])
    for scene, model in ((OLD_PINS[0], NEW_PINS[1]), (NEW_PINS[0], OLD_PINS[1]), OLD_PINS):
        with pytest.raises(ValueError, match="POLICY_NOT_ACTIVATED"):
            verify_activation(proposal["payload"], receipt, expected_scene_sha256=scene, expected_model_sha256=model)


def test_the_old_receipt_is_untouched_and_the_two_pairs_do_not_cross(tmp_path):
    old_proposal, old_receipt, (proposal, receipt) = _derive(tmp_path)
    verify_activation(old_proposal["payload"], old_receipt, expected_scene_sha256=OLD_PINS[0], expected_model_sha256=OLD_PINS[1])
    assert "derived_by" not in old_receipt and old_receipt["policy_fingerprint"] == old_proposal["policy_fingerprint"]
    with pytest.raises(ValueError, match="POLICY_NOT_ACTIVATED"):
        verify_activation(old_proposal["payload"], receipt)
    with pytest.raises(ValueError, match="POLICY_NOT_ACTIVATED"):
        verify_activation(proposal["payload"], old_receipt)
    with pytest.raises(ValueError, match="POLICY_NOT_ACTIVATED"):
        verify_activation(old_proposal["payload"], old_receipt, expected_scene_sha256=NEW_PINS[0])


@pytest.mark.parametrize("edit", [
    lambda receipt: receipt.update(derived_by="something_else"),
    lambda receipt: receipt.update(old_receipt_sha256="x" * 64),
    lambda receipt: receipt.update(equivalence_record_sha256="short"),
    lambda receipt: receipt.update(stripped_fingerprint_sha256=5),
    lambda receipt: receipt.pop("old_receipt_sha256"),
    lambda receipt: receipt.pop("derived_by"),
    lambda receipt: receipt.update(extra="x"),
    lambda receipt: receipt.update(receipt_kind="spot_check_candidate"),
])
def test_a_malformed_derived_receipt_is_refused(tmp_path, edit):
    _old_proposal, _old_receipt, (proposal, receipt) = _derive(tmp_path)
    edit(receipt)
    with pytest.raises(ValueError, match="POLICY_NOT_ACTIVATED"):
        verify_activation(proposal["payload"], receipt)


def test_a_receipt_with_a_derived_key_but_a_wrong_fingerprint_is_refused(tmp_path):
    _old_proposal, _old_receipt, (proposal, receipt) = _derive(tmp_path)
    receipt["policy_fingerprint"] = "3" * 64
    with pytest.raises(ValueError, match="POLICY_NOT_ACTIVATED"):
        verify_activation(proposal["payload"], receipt)


# ---- what a derivation refuses ------------------------------------------------------------------------------------------------------


def test_a_derivation_needs_an_old_receipt_that_approves_the_old_proposal(tmp_path):
    proposal, receipt = _old(tmp_path)
    receipt["policy_fingerprint"] = "3" * 64
    with pytest.raises(ValueError, match="CONTACT_DERIVATION_OLD_RECEIPT_INVALID"):
        derivation.derive_activation(proposal, receipt, old_receipt_bytes=b"x", equivalence_bytes=b"y", stripped_fingerprint=STRIPPED,
                                     old_pins=OLD_PINS, new_pins=NEW_PINS, approved_by="u", approval_reference="r",
                                     evidence_root=tmp_path, approved_at="2026-10-24T00:00:00+00:00")


def test_a_derivation_needs_the_old_proposal_to_carry_the_old_pins(tmp_path):
    with pytest.raises(ValueError, match="CONTACT_DERIVATION_OLD_PINS_MISMATCH"):
        _derive(tmp_path, old_pins=("c" * 64, OLD_PINS[1]))
    with pytest.raises(ValueError, match="CONTACT_DERIVATION_OLD_PINS_MISMATCH"):
        _derive(tmp_path, old_pins=(OLD_PINS[0], "c" * 64))


def test_a_derivation_to_the_same_pins_or_a_malformed_input_is_refused(tmp_path):
    with pytest.raises(ValueError, match="CONTACT_DERIVATION_PINS_INVALID"):
        _derive(tmp_path, new_pins=OLD_PINS)
    with pytest.raises(ValueError, match="CONTACT_DERIVATION_PINS_INVALID"):
        _derive(tmp_path, new_pins=("short", NEW_PINS[1]))
    with pytest.raises(ValueError, match="CONTACT_DERIVATION_FINGERPRINT_INVALID"):
        _derive(tmp_path, stripped_fingerprint="nothex")


# ---- the equivalence record --------------------------------------------------------------------------------------------------------


def _record(**changes):
    scene = {"scene_sha256": "1" * 64, "v2": {"fingerprint_version": 2, "sha256": STRIPPED}}
    old = {"scene_sha256": "b" * 64, "v2": {"fingerprint_version": 2, "sha256": STRIPPED}}
    document = {"scenes": {"old_nominal_side_wrist": old, "new_nominal_side_wrist_indoor": scene},
                "conclusion": {"v2_old_nominal_equals_new_indoor_nominal": True, "all_stripped_arrays_identical": True}}
    document.update(changes)
    return json.dumps(document).encode()


def test_a_record_that_claims_the_equivalence_gives_the_stripped_fingerprint_it_cites():
    assert derivation.check_equivalence_record(_record(), old_scene_sha256="b" * 64, new_scene_sha256="1" * 64,
                                               fresh_old=STRIPPED, fresh_new=STRIPPED) == STRIPPED


@pytest.mark.parametrize("changes, arguments", [
    ({}, dict(old_scene_sha256="c" * 64)),
    ({}, dict(new_scene_sha256="c" * 64)),
    ({}, dict(fresh_new="8" * 64)),
    ({}, dict(fresh_old="8" * 64)),
    ({"conclusion": {"v2_old_nominal_equals_new_indoor_nominal": False, "all_stripped_arrays_identical": True}}, {}),
    ({"conclusion": {"v2_old_nominal_equals_new_indoor_nominal": True, "all_stripped_arrays_identical": False}}, {}),
    ({"scenes": {}}, {}),
])
def test_a_record_that_disagrees_with_the_files_or_with_itself_is_refused(changes, arguments):
    full = dict(old_scene_sha256="b" * 64, new_scene_sha256="1" * 64, fresh_old=STRIPPED, fresh_new=STRIPPED)
    full.update(arguments)
    with pytest.raises(ValueError, match="CONTACT_DERIVATION_EQUIVALENCE_INVALID"):
        derivation.check_equivalence_record(_record(**changes), **full)


def test_a_record_that_is_not_json_is_refused():
    with pytest.raises(ValueError, match="CONTACT_DERIVATION_EQUIVALENCE_INVALID"):
        derivation.check_equivalence_record(b"{", old_scene_sha256="b" * 64, new_scene_sha256="1" * 64, fresh_old=STRIPPED,
                                            fresh_new=STRIPPED)


# ---- the pins of the indoor rig -------------------------------------------------------------------------------------------------------


def test_the_indoor_rig_pins_are_the_recompiled_identity_and_the_side_wrist_pins_are_unchanged():
    from so101_demo.adapters.act.physics import model_sha256

    scene, model = contact_collector.rig_identity("side-wrist-indoor")
    assert scene == _sha(INDOOR_SCENE.read_bytes()) and model == model_sha256(mujoco.MjModel.from_xml_path(str(INDOOR_SCENE)))
    assert contact_collector.rig_identity("side-wrist") == (
        "611ed1e4645248d6fa3620ad95194993fd09915351fbe34fae30074ddf35c383",
        "9f16f382839c80fc2a0a26a59bf7723e6d920b730febd864f13a391d3179350c")
    assert (scene, model) != contact_collector.rig_identity("side-wrist")


def test_the_fresh_stripped_fingerprints_of_the_real_scenes_are_equal():
    fresh = derivation.fresh_stripped_fingerprints(SIDE_SCENE, INDOOR_SCENE)
    assert fresh[0] == fresh[1] and len(fresh[0]) == 64


# ---- the command ---------------------------------------------------------------------------------------------------------------------


def _world(tmp_path, monkeypatch):
    proposal, receipt = _old(tmp_path)
    paths = {"old_proposal": tmp_path / "old-proposal.json", "old_receipt": tmp_path / "old-receipt.json"}
    paths["old_proposal"].write_text(json.dumps(proposal))
    paths["old_receipt"].write_text(json.dumps(receipt))
    equivalence = tmp_path / "equivalence.json"
    sides = derivation.fresh_stripped_fingerprints(SIDE_SCENE, INDOOR_SCENE)
    old_sha, new_sha = _sha(SIDE_SCENE.read_bytes()), _sha(INDOOR_SCENE.read_bytes())
    scenes = {"old_nominal_side_wrist": {"scene_sha256": old_sha, "v2": {"fingerprint_version": 2, "sha256": sides[0]}},
              "new_nominal_side_wrist_indoor": {"scene_sha256": new_sha, "v2": {"fingerprint_version": 2, "sha256": sides[1]}}}
    equivalence.write_text(json.dumps({"scenes": scenes, "conclusion": {"v2_old_nominal_equals_new_indoor_nominal": True,
                                                                         "all_stripped_arrays_identical": True}}))
    # the fixture proposal carries fixture pins: stand them in for the side-wrist pins of the collector
    pins = dict(contact_collector.RIG_IDENTITIES)
    pins["side-wrist"] = OLD_PINS
    monkeypatch.setattr(contact_collector, "RIG_IDENTITIES", pins)
    return paths, equivalence


def _arguments(tmp_path, paths, equivalence, out):
    return ["--old-proposal", str(paths["old_proposal"]), "--old-receipt", str(paths["old_receipt"]),
            "--equivalence-record", str(equivalence), "--share", str(PACKAGE_ROOT), "--approved-by", "user:test",
            "--approval-reference", "the indoor re-activation", "--evidence-root", str(tmp_path),
            "--proposal-out", str(out / "proposal.json"), "--receipt-out", str(out / "activation-receipt.json")]


def test_the_command_writes_a_verified_proposal_and_receipt_and_refuses_to_overwrite(tmp_path, monkeypatch):
    from so101_demo.cli import act_derive_contact_activation as command

    paths, equivalence = _world(tmp_path, monkeypatch)
    out = tmp_path / "indoor"
    out.mkdir()
    assert command.main(_arguments(tmp_path, paths, equivalence, out)) == 0
    proposal = json.loads((out / "proposal.json").read_text())
    receipt = json.loads((out / "activation-receipt.json").read_text())
    new_scene, new_model = contact_collector.rig_identity("side-wrist-indoor")
    assert proposal["payload"]["scene_sha256"] == new_scene and proposal["payload"]["model_sha256"] == new_model
    assert receipt["old_receipt_sha256"] == _sha(paths["old_receipt"].read_bytes())
    assert receipt["equivalence_record_sha256"] == _sha(equivalence.read_bytes())
    assert len(receipt["stripped_fingerprint_sha256"]) == 64
    contact_activation_substitution(out / "activation-receipt.json", out / "proposal.json")
    before = (out / "activation-receipt.json").read_bytes()
    with pytest.raises((FileExistsError, ValueError)):
        command.main(_arguments(tmp_path, paths, equivalence, out))
    assert (out / "activation-receipt.json").read_bytes() == before
    # the inputs were not modified
    assert json.loads(paths["old_receipt"].read_text())["approval_reference"] == "the old activation"


def test_the_command_refuses_a_record_whose_scene_is_not_the_installed_indoor_scene(tmp_path, monkeypatch):
    from so101_demo.cli import act_derive_contact_activation as command

    paths, equivalence = _world(tmp_path, monkeypatch)
    document = json.loads(equivalence.read_text())
    document["scenes"]["new_nominal_side_wrist_indoor"]["scene_sha256"] = "7" * 64
    equivalence.write_text(json.dumps(document))
    out = tmp_path / "indoor"
    out.mkdir()
    with pytest.raises(ValueError, match="CONTACT_DERIVATION_EQUIVALENCE_INVALID"):
        command.main(_arguments(tmp_path, paths, equivalence, out))
    assert not (out / "activation-receipt.json").exists() and not (out / "proposal.json").exists()
