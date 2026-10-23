"""Start and end targets of a rollout episode, pinned to the targets one sealed Teacher manifest recorded."""

import math

import pytest

from so101_demo.act.rollout_targets import evaluate_rollout_endpoint, rollout_targets
from so101_demo.act.teacher_endpoint import load_teacher_endpoint_policy

# `targets` of the frozen execution snapshot of the sealed w8 campaign (execution-manifest.json), reduced to the fields that matter.
SNAPSHOT_TARGETS = {
    "kind": "ACT_ENDPOINT_TARGETS", "schema_version": 1, "object_id": "plastic_cup", "body_name": "plastic_cup",
    "frame_id": "world", "reset_keyframe": "task_start",
    "initial_target": [0.02, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0],
    "final_target": [-0.08030314585074438, -0.24678506444167467, 0.18115431756299882,
                     0.019395490544908408, -0.003818548106558014, -0.1929819197596565, 0.9810031662959899],
}
# `teacher_targets` that the Teacher sealed in dynamic-execute-manifest.json (wave-0-w00-qual-01) for the input cup pose below.
SEALED_INPUT_POSE = (0.0035445030627499242, -0.309159727074945, 0.16499999999999998)
SEALED_TEACHER_TARGETS = {
    "start_target": {"position": [0.0035445030627499242, -0.309159727074945, 0.16499999999999998],
                     "orientation": {"w": 1.0, "x": 0.0, "y": 0.0, "z": 0.0}},
    "end_target": {"position": [-0.08030314585074438, -0.24678506444167467, 0.16499999999999998],
                   "orientation": {"w": 0.98100316629599, "x": 0.01939549054490841,
                                   "y": -0.0038185481065580143, "z": -0.19298191975965653}},
}


def _policy():
    return load_teacher_endpoint_policy(b"""kind: ACT_TEACHER_ENDPOINT_POLICY
schema_version: 1
rule_version: teacher_endpoint
tolerances: {initial_position_m: 0.010, initial_axis_rad: 0.15, final_xy_m: 0.020, final_z_m: 0.010,
  final_axis_rad: 0.15, settle_s: 0.5}
""")


def _flat(target):
    quaternion = target["orientation"]
    return [*target["position"], quaternion["x"], quaternion["y"], quaternion["z"], quaternion["w"]]


def test_targets_equal_the_ones_a_sealed_teacher_manifest_recorded():
    start, end = rollout_targets(SNAPSHOT_TARGETS, cup_position_world_m=SEALED_INPUT_POSE)
    assert _flat(start) == pytest.approx(_flat(SEALED_TEACHER_TARGETS["start_target"]), abs=1e-12)
    assert _flat(end) == pytest.approx(_flat(SEALED_TEACHER_TARGETS["end_target"]), abs=1e-12)
    assert set(start) == set(end) == {"position", "orientation"}
    assert set(start["orientation"]) == {"x", "y", "z", "w"}


def test_the_start_is_the_commanded_reset_pose_and_the_end_keeps_its_height():
    start, end = rollout_targets(SNAPSHOT_TARGETS, cup_position_world_m=(0.07, -0.28, 0.165))
    assert start["position"] == [0.07, -0.28, 0.165] and start["orientation"] == {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    assert end["position"][2] == 0.165                      # not the TCP-derived height of the snapshot's final target
    assert end["position"][:2] == pytest.approx(SNAPSHOT_TARGETS["final_target"][:2])
    norm = math.sqrt(sum(value ** 2 for value in end["orientation"].values()))
    assert norm == pytest.approx(1.0, abs=1e-12)


def test_targets_are_refused_when_the_snapshot_or_the_pose_is_malformed():
    for bad in (None, {}, dict(SNAPSHOT_TARGETS, kind="OTHER"),
                dict(SNAPSHOT_TARGETS, initial_target=[0.0] * 6), dict(SNAPSHOT_TARGETS, final_target=[float("nan")] * 7),
                dict(SNAPSHOT_TARGETS, frame_id="map")):
        with pytest.raises(ValueError, match="ROLLOUT_TARGETS_INVALID"):
            rollout_targets(bad, cup_position_world_m=SEALED_INPUT_POSE)
    for pose in ((0.0, 0.0), (0.0, 0.0, float("nan")), "x", None):
        with pytest.raises(ValueError, match="ROLLOUT_TARGETS_INVALID"):
            rollout_targets(SNAPSHOT_TARGETS, cup_position_world_m=pose)


def _observation(position, quaternion, time_s):
    x, y, z, w = quaternion
    return {"position": list(position), "orientation": {"x": x, "y": y, "z": z, "w": w}, "simulation_time_s": time_s,
            "frame_id": "world", "object_id": "plastic_cup", "session_id": "s", "reset_epoch": 1}


def test_a_cup_placed_on_the_end_target_passes_and_one_left_at_the_start_fails():
    pose = (0.07, -0.28, 0.165)
    start, end = rollout_targets(SNAPSHOT_TARGETS, cup_position_world_m=pose)
    upright = (0.0, 0.0, 0.0, 1.0)
    start_obs = _observation(pose, upright, 1.0)
    placed = evaluate_rollout_endpoint(_policy(), start_target=start, end_target=end, start_observation=start_obs,
                                       end_observation=_observation(end["position"], upright, 100.0))
    assert placed["result"] == "PASS"
    stayed = evaluate_rollout_endpoint(_policy(), start_target=start, end_target=end, start_observation=start_obs,
                                       end_observation=_observation(pose, upright, 100.0))
    assert stayed["result"] == "FAIL" and "FINAL_XY_OUT_OF_TOLERANCE" in stayed["reasons"]
    assert stayed["measured"]["final_xy_error_m"] > 0.02
    missing = evaluate_rollout_endpoint(_policy(), start_target=start, end_target=end, start_observation=start_obs,
                                        end_observation=None)
    assert missing["result"] == "UNCONFIRMED"
