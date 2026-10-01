"""E2: the shared endpoint QC recomputes from the verified audit and asks for no quality fields."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from so101_demo.act.endpoint_pose_acceptance import load_endpoint_policy
from so101_demo.act.episode_audit import verify_audit_manifest
from so101_demo.act.episode_qc import endpoint_records_from_audit
from test_act_episode_audit import complete_audit

POLICY = Path(__file__).resolve().parents[1] / "config" / "act" / "endpoint_pose_acceptance_v1.yaml"


def test_a_legal_endpoint_episode_without_quality_fields_is_not_refused(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    audit = {"manifest": verify_audit_manifest(path), "root": path.parent}
    inputs = {"initial_target": [-0.07, -0.23, 0.165, 0.0, 0.0, 0.0, 1.0],
              "final_target": [-0.07, -0.23, 0.165, 0.0, 0.0, 0.0, 1.0],
              "endpoint_policy": load_endpoint_policy(POLICY)}
    verdict = endpoint_records_from_audit(audit, inputs)
    print("QC", {k: v for k, v in verdict.items() if k != "initial_pose"})
    # the sealed rows carry the cup's position but no orientation, and the endpoint rule asks about poses, so the
    # honest answer is a named absence rather than a point promoted into a pose (CP-2590/2591)
    assert verdict["errors"] == ["ENDPOINT_POSE_NOT_DERIVABLE"]
    assert verdict["passed"] is False
    assert verdict["positions"] >= 2 and verdict["poses"] == 0
    assert "quality" not in verdict


def test_a_sealed_episode_with_full_poses_yields_a_real_endpoint_verdict(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    audit = {"manifest": verify_audit_manifest(path), "root": path.parent}
    target = [-0.07, -0.23, 0.165, 0.0, 0.0, 0.0, 1.0]
    inputs = {"initial_target": target, "final_target": target,
              "endpoint_policy": load_endpoint_policy(POLICY)}
    # the same rows, with a full xyz_xyzw pose appended the way a live sample publishes one
    physics = audit["root"] / "physics.jsonl"
    rows = physics.read_text().splitlines()
    pose = [-0.07, -0.23, 0.165, 0.0, 0.0, 0.0, 1.0]
    appended = [__import__("json").dumps(
        {"kind": "support", "sim_time_s": 1.0, "release_epoch": 1,
         "observation": {"simulation_time_s": 1.0, "simulation_step": 10, "cup_pose_world": pose}}),
        __import__("json").dumps(
        {"kind": "retract", "sim_time_s": 1.3, "release_epoch": 1,
         "observation": {"simulation_time_s": 1.3, "simulation_step": 13, "cup_pose_world": pose}})]
    physics.write_text("\n".join(rows + appended) + "\n")
    verdict = endpoint_records_from_audit(audit, inputs)
    print("QC2", {k: v for k, v in verdict.items() if k not in ("initial_pose", "final_pose")})
    # E1's `passed` is a per-threshold map; the single boolean this module adds is `endpoint_passed`
    assert verdict["status"] == "PASS" and verdict["endpoint_passed"] is True, verdict
    assert set(verdict["passed"]) == set(verdict["errors"])


def test_a_sealed_audit_without_the_physics_stream_is_a_named_absence(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    manifest = verify_audit_manifest(path)
    manifest["files"] = {name: entry for name, entry in manifest["files"].items() if name != "physics.jsonl"}
    verdict = endpoint_records_from_audit({"manifest": manifest, "root": path.parent},
                                          {"initial_target": [0.0] * 7, "final_target": [0.0] * 7,
                                           "endpoint_policy": load_endpoint_policy(POLICY)})
    print("QC3", verdict)
    assert verdict["errors"] == ["ENDPOINT_PHYSICS_STREAM_ABSENT"] and verdict["passed"] is False


def test_a_single_pose_is_not_enough_for_two_endpoints(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    audit = {"manifest": verify_audit_manifest(path), "root": path.parent}
    physics = audit["root"] / "physics.jsonl"
    pose = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    physics.write_text(physics.read_text() + __import__("json").dumps(
        {"kind": "retract", "sim_time_s": 1.4, "release_epoch": 1,
         "observation": {"simulation_time_s": 1.4, "simulation_step": 14, "cup_pose_world": pose}}) + "\n")
    verdict = endpoint_records_from_audit(audit, {"initial_target": pose, "final_target": pose,
                                                  "endpoint_policy": load_endpoint_policy(POLICY)})
    print("QC4", verdict)
    assert verdict["errors"] == ["ENDPOINT_POSE_NOT_DERIVABLE"] and verdict["poses"] == 1
