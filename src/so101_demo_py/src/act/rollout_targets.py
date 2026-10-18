"""Start and end targets of a closed-loop rollout episode, from the frozen execution snapshot.

The Teacher freezes its targets before the first motion (``Teacher._teacher_targets``): the start target is the input cup pose, and
the end target is the XY and attitude of the expected place pose at the input cup's own resting height (the snapshot's final target
is a TCP-derived pose, not a table-resting height). A rollout has no perceived input pose, so it makes one substitution, recorded
with the episode: the start target is the scene's COMMANDED reset pose (the cup position given to the reset, upright as the
``task_start`` keyframe), not a perceived one. The end target is computed from the snapshot exactly as the Teacher computes it.
Nothing is read from the live world and no tolerance lives here: the judgement is `evaluate_teacher_endpoint` with the frozen
endpoint policy.
"""

from __future__ import annotations

import math

from .teacher_endpoint import evaluate_teacher_endpoint

TARGETS_KIND = "ACT_ENDPOINT_TARGETS"


def _pose_values(value, size: int):
    if not isinstance(value, (list, tuple)) or len(value) != size or any(
            isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in value):
        raise ValueError("ROLLOUT_TARGETS_INVALID")
    return tuple(float(item) for item in value)


def _pose_document(position, quaternion_xyzw) -> dict:
    """The Teacher's pose document (`_teacher_pose_document`): the quaternion normalised, a zero norm left as it is."""

    x, y, z, w = quaternion_xyzw
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if not norm > 0.0:
        norm = 1.0
    return {"position": list(position), "orientation": {"x": x / norm, "y": y / norm, "z": z / norm, "w": w / norm}}


def rollout_targets(snapshot_targets: dict, *, cup_position_world_m) -> tuple:
    """(start_target, end_target) of one episode.

    ``snapshot_targets`` is the ``targets`` block of the verified execution snapshot (``ACT_ENDPOINT_TARGETS``);
    ``cup_position_world_m`` is the xyz the reset is commanded to place the cup at.
    """

    if (not isinstance(snapshot_targets, dict) or snapshot_targets.get("kind") != TARGETS_KIND
            or snapshot_targets.get("frame_id") != "world"):
        raise ValueError("ROLLOUT_TARGETS_INVALID")
    initial = _pose_values(snapshot_targets.get("initial_target"), 7)
    final = _pose_values(snapshot_targets.get("final_target"), 7)
    start_position = _pose_values(cup_position_world_m, 3)
    start = _pose_document(start_position, initial[3:7])
    end = _pose_document((final[0], final[1], start_position[2]), final[3:7])
    return start, end


def evaluate_rollout_endpoint(policy: dict, *, start_target: dict, end_target: dict, start_observation,
                              end_observation) -> dict:
    """The frozen Teacher endpoint rule over a rollout's start and end observations (no new threshold, no best-of-history)."""

    return evaluate_teacher_endpoint(policy, start_target=start_target, end_target=end_target,
                                     start_observation=start_observation, end_observation=end_observation)
