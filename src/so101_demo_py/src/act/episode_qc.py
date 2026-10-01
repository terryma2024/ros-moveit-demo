"""The shared QC recomputation for one episode's endpoints.

The division of labour is deliberate (CP-2574). This module is the **IO** half: it re-reads the sealed audit a fresh
process was pointed at, exactly as ``verify_audit_manifest`` listed it, and extracts the two endpoint poses from those
rows. ``evaluate_endpoint_pose`` (E1) is the **arithmetic** half and stays pure. So a QC verdict is recomputed evidence
plus a pure calculation, and nothing a run asserted about itself can enter the answer.

The two boundaries are the design's (CP-2569): the initial record is the pose evidence after the real reset and before
the arm-gripper dispatch, and the final record is the pose evidence after normal completion or a controller stop.
"""

from __future__ import annotations

import json
from pathlib import Path

from so101_demo.act.endpoint_pose_acceptance import evaluate_endpoint_pose

PHYSICS_STREAM = "physics.jsonl"
REFERENCE_STREAM = "references.jsonl"


def read_verified_rows(root: Path, stream: str) -> list[dict]:
    """The rows a fresh process re-reads from the sealed audit, in file order."""

    path = Path(root) / stream
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


#: a pose is seven finite reals - xyz plus an xyzw quaternion - as E1's own `_pose` states (CP-2591). The
#: registered live sample carries the model configuration; the MuJoCo summary rows carry only the cup's position,
#: which is not a pose and is never promoted to one.
POSE_KEYS = ("cup_pose_world", "cup_pose_m", "endpoint_pose", "cup_pose")
POSITION_KEYS = ("cup_position_m", "cup_position_world_m")


def observation_of(row) -> dict:
    observation = row.get("observation")
    return observation if isinstance(observation, dict) else {}


def endpoint_poses(physics_rows) -> list[list[float]]:
    """The **poses** the physics rows carry, in the order the rows were written. Positions are not poses."""

    poses = []
    for row in physics_rows:
        observation = observation_of(row)
        for key in POSE_KEYS:
            pose = observation.get(key)
            if isinstance(pose, (list, tuple)) and len(pose) == 7:
                poses.append([float(value) for value in pose])
                break
    return poses


def endpoint_positions(physics_rows) -> list[list[float]]:
    """The cup positions the physics rows carry, kept only so their absence can be told from a pose's."""

    positions = []
    for row in physics_rows:
        observation = observation_of(row)
        for key in POSITION_KEYS:
            position = observation.get(key)
            if isinstance(position, (list, tuple)) and len(position) >= 3:
                positions.append([float(value) for value in position])
                break
    return positions


def endpoint_records_from_audit(audit, inputs) -> dict:
    """Derive the endpoint records from the verified audit and the frozen inputs.

    ``audit`` is the pair ``{"manifest": <what verify_audit_manifest returned>, "root": <the directory it was verified
    against>}`` - the manifest's own ``files`` entries are relative, so the root has to travel with it (CP-2573).
    ``inputs`` carries the frozen targets and the endpoint policy. The verdict comes from E1's pure calculator, and a
    missing pose is reported as an absence rather than guessed at.
    """

    manifest = audit["manifest"]
    root = Path(audit["root"])
    listed = manifest.get("files") or {}
    if PHYSICS_STREAM not in listed:
        return {"status": "INCOMPLETE", "errors": ["ENDPOINT_PHYSICS_STREAM_ABSENT"], "passed": False}
    rows = read_verified_rows(root, PHYSICS_STREAM)
    poses = endpoint_poses(rows)
    if len(poses) < 2:
        # a source that publishes only the cup's position cannot answer an orientation question, so the absence is
        # named for what it is instead of a point being passed off as a pose (CP-2590/2591)
        positions = endpoint_positions(rows)
        reason = "ENDPOINT_POSE_NOT_DERIVABLE" if positions else "ENDPOINT_POSES_ABSENT"
        return {"status": "INCOMPLETE", "errors": [reason], "passed": False,
                "poses": len(poses), "positions": len(positions)}
    verdict = evaluate_endpoint_pose(poses[0], poses[-1], list(inputs["initial_target"]),
                                     list(inputs["final_target"]), inputs["endpoint_policy"])
    # E1 returns {"status": PASS|FAIL, "errors": {threshold: measured error}, "passed": {threshold: bool}} - both
    # maps, not a list and not a single boolean - so they are passed through unchanged (CP-2593)
    return {"status": verdict["status"], "errors": dict(verdict["errors"]), "passed": dict(verdict["passed"]),
            "endpoint_passed": all(verdict["passed"].values()),
            "initial_pose": poses[0], "final_pose": poses[-1], "source": "verified-raw-audit"}
