"""Task 8 contact exceptions must come from one activated physical model."""

import hashlib
import json
from pathlib import Path

import mujoco
import pytest
from ament_index_python.packages import get_package_share_directory

from so101_demo.act.contact_calibration import CONTROLS, REGIMES, make_activation_receipt
from so101_demo.act.contact_policy import policy_fingerprint
from so101_demo.adapters.act.physics import model_sha256
from so101_demo.adapters.act.task8_contact_pairs import Task8ContactPairs


def artifacts(tmp_path, *, change=None):
    scene = Path(get_package_share_directory("so101_demo_py")) / "assets/mujoco/act/scene.xml"
    model = mujoco.MjModel.from_xml_path(str(scene))
    payload = {
        "schema_version": 1, "policy_id": "test-act-contact", "mujoco_version": mujoco.mj_versionString(),
        "model_sha256": model_sha256(model), "scene_sha256": hashlib.sha256(scene.read_bytes()).hexdigest(),
        "motion_policy_sha256": "1" * 64, "source_evidence_sha256": "2" * 64,
        "collector_sha256": "3" * 64, "live_collector_sha256": "4" * 64,
        "analyzer_sha256": "5" * 64, "config_sha256": "6" * 64,
        "allowed_other_contact_bodies": ["table"],
        "thresholds": {
            "minimum_bilateral_force_n": 0.1, "maximum_compression_distance_m": 0.0001,
            "maximum_safe_force_n": 3.0, "maximum_hold_linear_speed_m_s": 0.004,
            "minimum_stable_hold_duration_s": 0.1,
        },
        "evaluation": {"maximum_observation_age_s": 0.1, "minimum_consecutive_samples": 5},
    }
    if change:
        change(payload)
    proposal = {
        "status": "DISABLED", "payload": payload,
        "policy_fingerprint": policy_fingerprint(payload),
        "source_evidence_sha256": payload["source_evidence_sha256"],
        "counts": {name: {"offline": 20, "live": 5} for name in REGIMES},
        "negative_controls": {name: [name if name in {"left_only", "right_only"} else "no_contact"]
                              for name in CONTROLS},
        "confusion_matrix": {name: {name: 5} for name in REGIMES},
        "false_positive_rate": 0.0, "false_negative_rate": 0.0,
    }
    raw = json.dumps(proposal, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    proposal["proposal_sha256"] = hashlib.sha256(raw).hexdigest()
    receipt = make_activation_receipt(
        proposal, proposal["policy_fingerprint"], approved_by="unit-test",
        approval_reference="synthetic-fixture", evidence_root=tmp_path,
        approved_at="2026-09-25T00:00:00+00:00",
    )
    proposal_path, receipt_path = tmp_path / "proposal.json", tmp_path / "receipt.json"
    proposal_path.write_text(json.dumps(proposal))
    receipt_path.write_text(json.dumps(receipt))
    return model, scene, proposal_path, receipt_path, proposal["policy_fingerprint"]


def bound(tmp_path, *, change=None, expected=None):
    model, scene, proposal, receipt, fingerprint = artifacts(tmp_path, change=change)
    return Task8ContactPairs(
        model=model, scene_path=scene, proposal_path=proposal, receipt_path=receipt,
        expected_fingerprint=fingerprint if expected is None else expected,
    )


def test_actual_model_pairs_are_exact_and_phase_scoped(tmp_path):
    pairs = bound(tmp_path)
    support = ("bottom_collision", "table_collision")
    finger = ("fixed_fingertip_pad_collision_000", "wall_near_collision")
    assert support in pairs.for_phase("SEARCH")
    assert finger not in pairs.for_phase("SEARCH")
    assert support in pairs.for_phase("CLOSE") and finger in pairs.for_phase("CLOSE")
    assert support not in pairs.for_phase("TRANSPORT") and finger in pairs.for_phase("TRANSPORT")
    assert support in pairs.for_phase("RADIAL_RETREAT") and finger not in pairs.for_phase("RADIAL_RETREAT")
    assert all(a.endswith("collision") or "contact_convex" in a or "collision_" in a
               for phase in pairs.PHASES for a, _ in pairs.for_phase(phase))
    assert pairs.for_phase("MICRO_LIFT") != pairs.for_phase("TRANSPORT")


def test_unknown_phase_or_wrong_admitted_fingerprint_is_refused(tmp_path):
    pairs = bound(tmp_path)
    with pytest.raises(ValueError, match="TASK8_CONTACT_PHASE_INVALID"):
        pairs.for_phase("UNKNOWN")
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(ValueError, match="TASK8_CONTACT_POLICY_INVALID"):
        bound(other, expected="a" * 64)


def test_model_scene_version_and_body_policy_drift_are_refused(tmp_path):
    for label, change in (
        ("model", lambda p: p.update(model_sha256="7" * 64)),
        ("scene", lambda p: p.update(scene_sha256="8" * 64)),
        ("version", lambda p: p.update(mujoco_version="0.0.0")),
        ("body", lambda p: p.update(allowed_other_contact_bodies=["wall"])),
    ):
        root = tmp_path / label
        root.mkdir()
        with pytest.raises(ValueError, match="TASK8_CONTACT_POLICY_INVALID"):
            bound(root, change=change)


def test_receipt_tamper_is_refused(tmp_path):
    model, scene, proposal, receipt, fingerprint = artifacts(tmp_path)
    value = json.loads(receipt.read_text())
    value["policy_fingerprint"] = "a" * 64
    receipt.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="TASK8_CONTACT_POLICY_INVALID"):
        Task8ContactPairs(model=model, scene_path=scene, proposal_path=proposal,
                          receipt_path=receipt, expected_fingerprint=fingerprint)


def test_child_compiles_only_installed_act_scene_before_using_policy(tmp_path):
    from so101_demo.adapters.act.task8_contact_pairs import load_installed_act_contact_pairs

    expected_model, scene, proposal, receipt, fingerprint = artifacts(tmp_path)
    model, pairs = load_installed_act_contact_pairs(
        proposal_path=proposal, receipt_path=receipt, expected_fingerprint=fingerprint,
    )
    assert model_sha256(model) == model_sha256(expected_model)
    assert pairs.scene_sha256 == hashlib.sha256(scene.read_bytes()).hexdigest()
    assert pairs.for_phase("SEARCH") != pairs.for_phase("CLOSE")

    wrong_root = tmp_path / "wrong-model"
    wrong_root.mkdir()
    _, _, wrong_proposal, wrong_receipt, wrong_fingerprint = artifacts(
        wrong_root, change=lambda payload: payload.update(model_sha256="a" * 64),
    )
    with pytest.raises(ValueError, match="TASK8_CONTACT_POLICY_INVALID"):
        load_installed_act_contact_pairs(
            proposal_path=wrong_proposal, receipt_path=wrong_receipt,
            expected_fingerprint=wrong_fingerprint,
        )


def test_act_child_retains_compiled_phase_pairs_before_ros_init(tmp_path, monkeypatch):
    from so101_teleop.unified.act_artifacts import ActArtifactBinding
    from so101_teleop.unified.ros_child import RclpyActionDriver

    expected_model, _, proposal, receipt, fingerprint = artifacts(tmp_path)
    names = ("source", "manifest", "runtime_config", "collection_config",
             "calibration_report")
    files = {}
    for name in names:
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps({"artifact": name}))
        files[name] = path
    binding = ActArtifactBinding(
        evidence_root=tmp_path,
        paths=tuple((name, files[name]) for name in names)
        + (("proposal", proposal), ("activation_receipt", receipt)),
        hashes=tuple((name, hashlib.sha256(files[name].read_bytes()).hexdigest())
                     for name in names),
        policy_fingerprint=fingerprint,
    )
    for name, value in binding.environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("SO101_ACT_CAMPAIGN_ID", "compiled-model-test")
    monkeypatch.setenv("SO101_ACT_WORKER_ID", "w00")
    monkeypatch.setenv("SO101_ACT_MANIFEST_SHA256", dict(binding.hashes)["manifest"])
    monkeypatch.setenv("SO101_ACT_RUNTIME_CONFIG_SHA256", dict(binding.hashes)["runtime_config"])
    monkeypatch.setenv("SO101_ACT_POLICY_FINGERPRINT", fingerprint)
    monkeypatch.setattr(RclpyActionDriver, "_start_ros_broker", lambda self: object())

    driver = RclpyActionDriver()
    assert model_sha256(driver._act_model) == model_sha256(expected_model)
    assert driver._act_contact_pairs.for_phase("SEARCH") != driver._act_contact_pairs.for_phase("CLOSE")
