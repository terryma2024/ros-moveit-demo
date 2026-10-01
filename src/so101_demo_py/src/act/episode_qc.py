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


def endpoint_poses(physics_rows) -> list[list[float]]:
    """The cup poses the physics rows carry, in the order the rows were written."""

    poses = []
    for row in physics_rows:
        observation = row.get("observation")
        pose = observation.get("cup_position_m") if isinstance(observation, dict) else None
        if isinstance(pose, (list, tuple)) and len(pose) >= 3:
            poses.append([float(value) for value in pose])
    return poses


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
    poses = endpoint_poses(read_verified_rows(root, PHYSICS_STREAM))
    if len(poses) < 2:
        return {"status": "INCOMPLETE", "errors": ["ENDPOINT_POSES_ABSENT"], "passed": False, "poses": len(poses)}
    verdict = evaluate_endpoint_pose(poses[0], poses[-1], list(inputs["initial_target"]),
                                     list(inputs["final_target"]), inputs["endpoint_policy"])
    return {"status": verdict["status"], "errors": list(verdict["errors"]), "passed": verdict["passed"],
            "initial_pose": poses[0], "final_pose": poses[-1], "source": "verified-raw-audit"}
