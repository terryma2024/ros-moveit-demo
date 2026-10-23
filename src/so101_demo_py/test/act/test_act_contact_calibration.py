"""Synthetic contract tests; these samples never qualify a live contact policy."""

import copy
import hashlib
import json

import pytest

from so101_demo.act.contact_calibration import (
    analyze_evidence, analyze_manifests, seal_cohort, verify_disabled_proposal,
    make_activation_receipt, _classify, _validated_sample,
)
from so101_demo.act.contact_policy import policy_fingerprint, verify_activation


REGIMES = (
    "no_contact", "bilateral_touch", "over_compression", "micro_lift_slip", "stable_hold"
)
CONTROLS = ("table_only", "post_release", "left_only", "right_only")


def _sample(regime, source, index):
    has_left = regime not in {"no_contact", "table_only", "post_release", "right_only"}
    has_right = regime not in {"no_contact", "table_only", "post_release", "left_only"}
    force = 5.0 if regime == "over_compression" else 0.5
    distance = -0.003 if regime == "over_compression" else -0.0005
    speed = 0.1 if regime == "micro_lift_slip" else 0.001
    count = 4 if regime == "stable_hold" else 2
    frames = []
    for step in range(count):
        sim_time = 10.0 + step * 0.1
        frames.append({
            "physics_step": 100 + step,
            "simulation_time_s": sim_time,
            "ros_time_s": sim_time,
            "received_monotonic_s": 1000.0 + step * 0.1,
            "left_contacts": [{"robot_geom": "left_pad", "object_body": "cup",
                               "normal_force_n": force, "signed_distance_m": distance}] if has_left else [],
            "right_contacts": [{"robot_geom": "right_pad", "object_body": "cup",
                                "normal_force_n": force, "signed_distance_m": distance}] if has_right else [],
            "other_contacts": [{"robot_geom": "table_collision", "object_body": "cup",
                                "normal_force_n": 0.2, "signed_distance_m": -0.0001}]
            if regime in {"no_contact", "table_only", "post_release", "bilateral_touch", "over_compression"} else [],
            "cup_position_m": [0.0, 0.0, 0.16],
            "cup_velocity_m_s": [speed, 0.0, 0.0],
            "model_qpos": [0.0, 0.0, 0.0],
            "model_qvel": [0.0, 0.0, 0.0],
            "table_supported": regime in {"no_contact", "table_only", "post_release", "bilateral_touch", "over_compression"},
            "released": regime == "post_release",
        })
    scenario = {"regime": regime, "seed": index, "cup_start_m": [0.0, 0.0, 0.16],
                "gripper_close_q6": 0.1, "window_first_step": 100,
                "window_last_step": 100 + count - 1}
    peak_force = max(sum(c["normal_force_n"] for key in
                         ("left_contacts", "right_contacts", "other_contacts")
                         for c in frame[key]) for frame in frames)
    metadata = _metadata()
    return {
        "sample_id": f"{source}-{regime}-{index:03d}",
        "source": source,
        "regime": regime,
        "simulation_session_id": f"{source}-{regime}-{index:03d}",
        "reset_epoch": 1,
        "scenario": scenario,
        "scenario_sha256": hashlib.sha256(json.dumps(scenario, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest(),
        "model_sha256": metadata["model_sha256"],
        "scene_sha256": metadata["scene_sha256"],
        "motion_policy_sha256": metadata["motion_policy_sha256"],
        "collector_sha256": metadata[
            "collector_sha256" if source == "offline" else "live_collector_sha256"],
        "config_sha256": metadata["config_sha256"],
        "clock_origin": "mujoco_simulated_ros" if source == "offline" else "ros_clock",
        "diagnostic_result": {"status": "PASS", "peak_force_n": peak_force,
                              "peak_displacement_m": 0.0},
        "frames": frames,
        "collected_monotonic_s": frames[-1]["received_monotonic_s"],
    }


def _cohorts():
    return (
        {"source": "offline", "samples": [_sample(r, "offline", i) for r in REGIMES for i in range(20)]
         + [_sample(r, "offline", 0) for r in CONTROLS]},
        {"source": "live", "samples": [_sample(r, "live", i) for r in REGIMES for i in range(5)]
         + [_sample(r, "live", 0) for r in CONTROLS]},
    )


def _metadata():
    return {
        "mujoco_version": "3.4.0",
        "model_sha256": "a" * 64,
        "scene_sha256": "b" * 64,
        "motion_policy_sha256": "c" * 64,
        "collector_sha256": "d" * 64,
        "live_collector_sha256": "1" * 64,
        "analyzer_sha256": "e" * 64,
        "config_sha256": "f" * 64,
        "policy_id": "so101-act-contact",
        "allowed_other_contact_bodies": ["table_collision"],
        "evaluation": {"maximum_observation_age_s": 0.2, "minimum_consecutive_samples": 2},
        "diagnostic_limits": {"maximum_force_n": 11.6, "maximum_displacement_m": 0.03,
                              "maximum_ros_skew_s": 0.02, "maximum_receipt_age_s": 0.2},
    }


def test_20_offline_and_independent_5_live_produce_disabled_proposal():
    offline, live = _cohorts()
    result = analyze_evidence(offline, live, _metadata())
    assert result["status"] == "DISABLED"
    assert result["counts"] == {regime: {"offline": 20, "live": 5} for regime in REGIMES}
    assert result["false_positive_rate"] == 0
    assert result["false_negative_rate"] == 0
    assert result["confusion_matrix"]["stable_hold"]["stable_hold"] == 5
    assert result["policy_fingerprint"] == policy_fingerprint(result["payload"])
    assert result["proposal_sha256"] != result["policy_fingerprint"]
    assert result["payload"]["live_collector_sha256"] == _metadata()["live_collector_sha256"]


def test_table_supported_bilateral_touch_precedes_off_table_slip_speed():
    sample = _sample("bilateral_touch", "offline", 0)
    for frame in sample["frames"]:
        frame["cup_velocity_m_s"] = [0.0146, 0.0, 0.0]
    observed = _validated_sample(sample, "offline", _metadata()["diagnostic_limits"], _metadata())
    thresholds = {
        "maximum_compression_distance_m": 0.001,
        "maximum_safe_force_n": 3.21,
        "maximum_hold_linear_speed_m_s": 0.0038,
        "minimum_stable_hold_duration_s": 0.011,
    }
    assert observed["table_supported"] is True
    assert _classify(observed, thresholds) == "bilateral_touch"


def test_live_collector_provenance_cannot_impersonate_offline_source():
    offline, live = _cohorts()
    live["samples"][0]["collector_sha256"] = _metadata()["collector_sha256"]
    with pytest.raises(ValueError, match="collector_sha256"):
        analyze_evidence(offline, live, _metadata())


def test_missing_live_sample_or_negative_control_fails_closed():
    offline, live = _cohorts()
    live["samples"].pop(0)
    with pytest.raises(ValueError):
        analyze_evidence(offline, live, _metadata())
    offline, live = _cohorts()
    live["samples"] = [s for s in live["samples"] if s["regime"] != "post_release"]
    with pytest.raises(ValueError):
        analyze_evidence(offline, live, _metadata())


@pytest.mark.parametrize("damage", ["stale", "force", "displacement", "wrong_side", "reset"])
def test_physical_or_timeline_damage_aborts_analysis(damage):
    offline, live = _cohorts()
    sample = live["samples"][0]
    if damage == "stale":
        sample["frames"][1]["ros_time_s"] -= 1
    elif damage == "force":
        sample["frames"][1]["other_contacts"] = [
            {"robot_geom": "table", "object_body": "cup", "normal_force_n": 12.0,
             "signed_distance_m": -0.001}]
    elif damage == "displacement":
        sample["frames"][1]["cup_position_m"][0] = 0.1
    elif damage == "wrong_side":
        target = next(s for s in live["samples"] if s["regime"] == "left_only")
        target["frames"][1]["right_contacts"] = copy.deepcopy(target["frames"][1]["left_contacts"])
    elif damage == "reset":
        sample["frames"][1]["physics_step"] = 0
    with pytest.raises(ValueError):
        analyze_evidence(offline, live, _metadata())


def test_table_support_requires_raw_table_contact():
    offline, live = _cohorts()
    live["samples"][0]["frames"][-1]["other_contacts"] = []
    with pytest.raises(ValueError, match="table support"):
        analyze_evidence(offline, live, _metadata())


def test_total_contact_force_obeys_diagnostic_hard_limit():
    offline, live = _cohorts()
    frame = live["samples"][0]["frames"][-1]
    frame["other_contacts"] *= 2
    frame["other_contacts"][0]["normal_force_n"] = 7.0
    frame["other_contacts"][1]["normal_force_n"] = 7.0
    with pytest.raises(ValueError, match="force limit"):
        analyze_evidence(offline, live, _metadata())


def test_over_compression_can_occur_after_lift():
    offline, live = _cohorts()
    for cohort in (offline, live):
        for sample in cohort["samples"]:
            if sample["regime"] == "over_compression":
                for frame in sample["frames"]:
                    frame["other_contacts"] = []
                    frame["table_supported"] = False
                sample["diagnostic_result"]["peak_force_n"] = 10.0
    assert analyze_evidence(offline, live, _metadata())["confusion_matrix"]["over_compression"]["over_compression"] == 5


def test_sample_without_scenario_and_source_provenance_is_rejected():
    offline, live = _cohorts()
    del offline["samples"][0]["scenario"]
    with pytest.raises(ValueError, match="provenance|scenario"):
        analyze_evidence(offline, live, _metadata())


def test_offline_and_live_must_not_share_sample_identity():
    offline, live = _cohorts()
    live["samples"][0]["sample_id"] = offline["samples"][0]["sample_id"]
    with pytest.raises(ValueError):
        analyze_evidence(offline, live, _metadata())


def test_sealed_raw_cohorts_are_hash_bound_and_never_overwritten(tmp_path):
    offline, live = _cohorts()
    offline_manifest = seal_cohort(tmp_path / "offline", offline)
    live_manifest = seal_cohort(tmp_path / "live", live)
    result = analyze_manifests(offline_manifest, live_manifest, _metadata())
    assert result["counts"]["stable_hold"] == {"offline": 20, "live": 5}
    with pytest.raises(FileExistsError):
        seal_cohort(tmp_path / "offline", offline)
    raw = tmp_path / "live" / "raw.json"
    raw.write_bytes(raw.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash"):
        analyze_manifests(offline_manifest, live_manifest, _metadata())


def test_proposal_envelope_tamper_is_rejected_separately_from_payload():
    proposal = analyze_evidence(*_cohorts(), _metadata())
    verify_disabled_proposal(proposal)
    altered = copy.deepcopy(proposal)
    altered["counts"]["stable_hold"]["live"] = 4
    with pytest.raises(ValueError, match="proposal"):
        verify_disabled_proposal(altered)


def test_activation_receipt_requires_exact_reviewed_fingerprint(tmp_path):
    proposal = analyze_evidence(*_cohorts(), _metadata())
    with pytest.raises(ValueError, match="fingerprint"):
        make_activation_receipt(
            proposal, "0" * 64, approved_by="user",
            approval_reference="dispatch-30a80149", evidence_root=tmp_path,
            approved_at="2026-09-25T00:00:00+00:00",
        )
    receipt = make_activation_receipt(
        proposal, proposal["policy_fingerprint"], approved_by="user",
        approval_reference="dispatch-30a80149", evidence_root=tmp_path,
        approved_at="2026-09-25T00:00:00+00:00",
    )
    verify_activation(proposal["payload"], receipt)
    assert proposal["status"] == "DISABLED"


def test_analyze_and_activate_cli_replay_sealed_evidence(tmp_path):
    from so101_demo.cli.act_analyze_contact_calibration import main as analyze_main
    from so101_demo.cli.act_activate_contact_policy import main as activate_main

    offline, live = _cohorts()
    offline_manifest = seal_cohort(tmp_path / "offline", offline)
    live_manifest = seal_cohort(tmp_path / "live", live)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(_metadata()), encoding="utf-8")
    proposal_path = tmp_path / "proposal.json"
    assert analyze_main(["--offline", str(offline_manifest), "--live", str(live_manifest),
                         "--metadata", str(metadata_path), "--proposal", str(proposal_path)]) == 0
    proposal = json.loads(proposal_path.read_text())
    assert proposal["status"] == "DISABLED"
    receipt_path = tmp_path / "activation-receipt.json"
    common = ["--proposal", str(proposal_path), "--offline", str(offline_manifest),
              "--live", str(live_manifest), "--metadata", str(metadata_path),
              "--approved-by", "user", "--approval-reference", "dispatch-30a80149",
              "--evidence-root", str(tmp_path), "--receipt", str(receipt_path)]
    with pytest.raises(ValueError, match="fingerprint"):
        activate_main(common + ["--policy-fingerprint", proposal["proposal_sha256"]])
    assert not receipt_path.exists()
    assert activate_main(common + ["--policy-fingerprint", proposal["policy_fingerprint"]]) == 0
    verify_activation(proposal["payload"], json.loads(receipt_path.read_text()))
