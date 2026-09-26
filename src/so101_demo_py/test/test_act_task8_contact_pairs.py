"""Task 8 contact exceptions must come from one activated physical model."""

import hashlib
import json
import copy
from pathlib import Path
import time
from types import SimpleNamespace

import mujoco
import pytest
from ament_index_python.packages import get_package_share_directory

from so101_demo.act.contact_calibration import CONTROLS, REGIMES, make_activation_receipt
from so101_demo.act.contact_policy import policy_fingerprint
from so101_demo.adapters.act.physics import model_sha256
from so101_demo.adapters.act.phase_contact_allowlist import PhaseContactAllowlist


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
    return PhaseContactAllowlist(
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
        PhaseContactAllowlist(model=model, scene_path=scene, proposal_path=proposal,
                          receipt_path=receipt, expected_fingerprint=fingerprint)


def test_child_compiles_only_installed_act_scene_before_using_policy(tmp_path):
    from so101_demo.adapters.act.phase_contact_allowlist import load_installed_phase_contact_allowlist

    expected_model, scene, proposal, receipt, fingerprint = artifacts(tmp_path)
    model, pairs = load_installed_phase_contact_allowlist(
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
        load_installed_phase_contact_allowlist(
            proposal_path=wrong_proposal, receipt_path=wrong_receipt,
            expected_fingerprint=wrong_fingerprint,
        )


def test_act_child_retains_compiled_phase_pairs_before_ros_init(tmp_path, monkeypatch):
    from so101_teleop.unified.act_artifacts import ActArtifactBinding
    from so101_teleop.unified.ros_child import RclpyActionDriver
    from so101_demo.act import head_search_binding

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
    # This test isolates compiled contact pairs; the separate binding suite
    # exercises the required calibrated head-search configuration.
    monkeypatch.setattr(head_search_binding, "validate_head_search_binding",
                        lambda runtime, report: object())
    monkeypatch.setattr(RclpyActionDriver, "_start_ros_broker", lambda self: object())

    driver = RclpyActionDriver()
    assert model_sha256(driver._act_model) == model_sha256(expected_model)
    assert driver._act_contact_pairs.for_phase("SEARCH") != driver._act_contact_pairs.for_phase("CLOSE")


def test_ros_sources_arm_only_from_reset_and_enqueue_phase_contact_hazard(tmp_path):
    from so101_demo.adapters.act.task8_sources import Task8RosEvidence
    from so101_mujoco_support.msg import RobotContactEvidence
    from so101_mujoco_support.msg import SimulationEvidence as RosSimulationEvidence

    model, scene, proposal, receipt, fingerprint = artifacts(tmp_path)
    pairs = PhaseContactAllowlist(model=model, scene_path=scene, proposal_path=proposal,
                              receipt_path=receipt, expected_fingerprint=fingerprint)

    class Node:
        def __init__(self):
            self.topics = []

        def create_subscription(self, _kind, topic, _callback, _qos):
            self.topics.append(topic)
            return SimpleNamespace(get_publisher_count=lambda: 1)

    node = Node()
    sources = Task8RosEvidence(
        node, object(), model=model, contact_pairs=pairs, session_id="s",
        max_wall_age_s=0.2, max_source_skew_s=0.005, max_sim_gap_s=0.003,
        joint_tolerance_rad=0.001, cup_pose_tolerance_m=0.001,
        cup_orientation_tolerance=0.001,
    )
    assert {"/so101/simulation/evidence", "/so101/simulation/scene_state",
            "/so101/simulation/robot_contacts", "/head_camera/color",
            "/wrist_camera/color", "/joint_states"} <= set(node.topics)
    with pytest.raises(ValueError, match="TASK8_RESET_UNAVAILABLE"):
        sources.arm("SEARCH")
    reset = RosSimulationEvidence()
    reset.header.frame_id = "world"
    reset.publisher_sequence = 1
    reset.simulation_step = 0
    reset.reset_epoch = 1
    reset.simulation_session_id = "s"
    reset.paused = True
    reset.object_body_id = 1
    reset.object_body = "cup"
    reset.object_pose_world.position.x = 0.1
    reset.object_pose_world.position.y = -0.2
    reset.object_pose_world.position.z = 0.15
    reset.object_pose_world.orientation.w = 1.0
    sources.world.accept(reset, received_at_s=time.monotonic())
    assert sources.arm("SEARCH") == 1
    sources.contact_adapter.accept_message(RobotContactEvidence(
        simulation_session_id="s", reset_epoch=1, physics_step=1,
        simulation_time_s=0.002, geom_a=["bottom_collision"],
        geom_b=["table_collision"], signed_distance_m=[-0.001],
        normal_force_n=[1.0], truncated=False, evidence_loss=False,
    ))
    assert sources.contacts.safe()
    sources.set_phase("TRANSPORT")
    assert sources.take_hazard() == "ROBOT_CONTACT_HAZARD"
    assert sources.take_hazard() is None
    truncated = copy.deepcopy(reset)
    truncated.publisher_sequence = 2
    truncated.simulation_step = 1
    truncated.paused = False
    truncated.truncated = True
    sources.world._callback(truncated)
    assert "truncated" in sources.take_hazard()
    next_reset = copy.deepcopy(reset)
    next_reset.publisher_sequence = 3
    next_reset.reset_epoch = 2
    sources.world._callback(next_reset)
    gap = copy.deepcopy(next_reset)
    gap.publisher_sequence = 5
    sources.world._callback(gap)
    assert "sequence gap" in sources.take_hazard()
    with pytest.raises(ValueError, match="TASK8_RESET_UNAVAILABLE"):
        sources.arm("SEARCH")
