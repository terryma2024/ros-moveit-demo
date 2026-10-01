"""E2: the shared endpoint QC recomputes from the verified audit and asks for no quality fields."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from so101_demo.act.endpoint_pose_acceptance import load_endpoint_policy
from so101_demo.act.episode_audit import verify_audit_manifest
from so101_demo.act.episode_qc import endpoint_qc_document, endpoint_records_from_audit
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
        {"kind": "support", "sim_time_s": 1.3, "release_epoch": 1,
         "observation": {"simulation_time_s": 1.3, "simulation_step": 13, "cup_pose_world": pose}}),
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


def test_the_verdict_follows_the_frozen_targets_not_the_rows(tmp_path):
    """The plan's "target rewritten afterwards": the QC reads the frozen inputs, so rewriting the audit changes nothing
    that the endpoint verdict depends on."""

    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    audit = {"manifest": verify_audit_manifest(path), "root": path.parent}
    physics = audit["root"] / "physics.jsonl"
    pose = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    rows = physics.read_text().splitlines()
    physics.write_text("\n".join(rows + [__import__("json").dumps(
        {"kind": "support", "sim_time_s": 1.0, "release_epoch": 1,
         "observation": {"simulation_time_s": 1.0, "simulation_step": 10, "cup_pose_world": pose}}),
        __import__("json").dumps(
        {"kind": "retract", "sim_time_s": 1.4, "release_epoch": 1,
         "observation": {"simulation_time_s": 1.4, "simulation_step": 14, "cup_pose_world": pose}})]) + "\n")
    policy = load_endpoint_policy(POLICY)
    far = [9.0, 9.0, 9.0, 0.0, 0.0, 0.0, 1.0]
    accepted = endpoint_records_from_audit(audit, {"initial_target": pose, "final_target": pose,
                                                   "endpoint_policy": policy})
    refused = endpoint_records_from_audit(audit, {"initial_target": far, "final_target": far,
                                                  "endpoint_policy": policy})
    print("QC5 frozen-match:", accepted["status"], "| frozen-mismatch:", refused["status"])
    assert accepted["status"] == "PASS" and accepted["endpoint_passed"] is True
    assert refused["status"] == "FAIL" and refused["endpoint_passed"] is False
    assert accepted["initial_pose"] == refused["initial_pose"] == pose


def test_the_independent_document_keeps_the_claim_and_the_verdict_apart(tmp_path):
    """The seal's own qc_passed is a claim; the fresh-process endpoint verdict sits beside it, not instead of it."""

    writer, window = complete_audit(tmp_path)
    position = [0.0, 0.0, 0.0]
    orientation = [0.0, 0.0, 0.0, 1.0]
    pose = position + orientation
    # the rows go in through the writer, in the shape the audit's own schema admits: the MuJoCo summary fields,
    # of which cup_position_world_m and cup_orientation_world_xyzw together are a pose (CP-2635)
    # `pose` and `retract` are the two kinds whose required summary fields are exactly the ones a pose needs:
    # simulation_time_s, simulation_step and cup_position_world_m (CP-2638)
    for step, (kind, stamp) in enumerate((("pose", 1.3), ("retract", 1.4)), start=13):
        writer.append_source("physics", {
            "kind": kind, "sim_time_s": stamp, "release_epoch": 1,
            "observation": {"simulation_time_s": stamp, "simulation_step": step,
                            "cup_position_world_m": position, "cup_orientation_world_xyzw": orientation}})
    # and only then the seal, because a sealed manifest is verified by recomputation
    path = writer.seal(window)
    document = endpoint_qc_document(path.parent, {"initial_target": pose, "final_target": pose,
                                                 "endpoint_policy": load_endpoint_policy(POLICY)})
    print("QCDOC", {k: v for k, v in document.items() if k != "endpoint"})
    # the design's prescribed shape (CP-2673/2687): the top-level common schema, the versioned rule, and the
    # endpoint answer as one named check whose keys are the ones the design lists
    assert document["rule_version"] == "endpoint_pose_v1"
    assert set(document) >= {"rule_version", "status", "checked_monotonic_s", "cleanup_state", "checks"}
    assert document["status"] == "PASS"
    check = document["checks"]["endpoint_pose"]
    assert set(check) == {"status", "policy_sha256", "initial_sequence", "final_sequence",
                          "initial_pose", "final_pose", "initial_target", "final_target"}
    assert check["status"] == "PASS"
    assert check["initial_sequence"] is not None and check["final_sequence"] is not None
    assert check["initial_pose"] == pose and check["final_pose"] == pose
    assert len(check["policy_sha256"]) == 64
    assert check["initial_target"] == pose and check["final_target"] == pose
    # and the seal's own claim stays where it belongs: in the episode this report names, not in the report (CP-2645)
    assert "qc_passed" not in document and "claim" not in document


def test_the_final_endpoint_is_the_last_pose_not_the_best_one(tmp_path):
    """E2's negative list: "best frame before termination" cannot displace where the episode actually ended."""

    writer, window = complete_audit(tmp_path)
    target = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    # a row that would look perfect, early, and a later row that is where the run actually finished
    rows = ((("pose", 1.3), target), (("retract", 1.4), [0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]))
    for step, ((kind, stamp), pose) in enumerate(rows, start=13):
        writer.append_source("physics", {
            "kind": kind, "sim_time_s": stamp, "release_epoch": 1,
            "observation": {"simulation_time_s": stamp, "simulation_step": step,
                            "cup_position_world_m": pose[:3], "cup_orientation_world_xyzw": pose[3:]}})
    path = writer.seal(window)
    verdict = endpoint_records_from_audit(
        {"manifest": verify_audit_manifest(path), "root": path.parent},
        {"initial_target": target, "final_target": target, "endpoint_policy": load_endpoint_policy(POLICY)})
    print("BESTFRAME final_pose:", verdict.get("final_pose"), "| status:", verdict.get("status"))
    assert verdict["final_pose"] == rows[-1][1]          # the last pose, not the matching earlier one
    assert verdict["status"] == "FAIL"                   # and the verdict says so rather than flattering the run
