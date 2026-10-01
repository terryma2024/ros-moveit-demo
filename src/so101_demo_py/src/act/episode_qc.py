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
from so101_demo.act.episode_audit import verify_audit_manifest

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


def endpoint_qc_document(episode_root, inputs, *, manifest_name: str = "audit-manifest.json") -> dict:
    """The independent endpoint verdict for a sealed episode, as a document.

    A fresh process is pointed at the sealed episode's root; this reads the manifest through the repository's own
    verifier - which re-reads every stream and recomputes the digests - and then recomputes the endpoint records from
    what it re-read. The verdict it returns is therefore evidence plus calculation, and it is deliberately **beside**
    the seal's own ``qc_passed`` claim rather than replacing it, so that "a legal seal" and "the endpoints were judged
    by a fresh process" stay distinguishable (the design's three states).
    """

    root = Path(episode_root)
    manifest_path = root / manifest_name
    manifest = verify_audit_manifest(manifest_path)
    verdict = endpoint_records_from_audit({"manifest": manifest, "root": manifest_path.parent}, inputs)
    return {"kind": "ACT_ENDPOINT_QC", "schema_version": 1,
            "episode_root": str(root), "episode_manifest_sha256": _manifest_digest(manifest_path),
            "claim": {"status": manifest.get("status"), "qc_passed": manifest.get("qc_passed")},
            "endpoint": verdict}


def _manifest_digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pose_from_configuration(scene_path, model_qpos, body_name) -> list[float]:
    """The `xyz_xyzw` pose of `body_name` at a recorded configuration, computed in this process.

    This is the geometry half of `adapters/act/held_cup_state.py`'s `_body_transform`, and deliberately not its public
    ``prove``: that one is a **live** proof whose freshness arguments include the wall clock at the moment of the call
    (`scene_received_monotonic_s`, `now_monotonic_s`), which a process reading a finished episode cannot supply
    honestly (CP-2632). Forward kinematics needs no live input at all, so a sealed audit can be judged from it.

    It performs no IO beyond loading the scene's model, touches no live port, and invents nothing: an unusable
    configuration or an unknown body is refused rather than defaulted.
    """

    import mujoco

    model = mujoco.MjModel.from_xml_path(str(scene_path))
    data = mujoco.MjData(model)
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, str(body_name))
    if body < 0:
        raise ValueError("ENDPOINT_QC_BODY_UNKNOWN: " + str(body_name))
    qpos = [float(value) for value in model_qpos]
    if len(qpos) != model.nq:
        raise ValueError("ENDPOINT_QC_QPOS_INVALID: expected %d, got %d" % (model.nq, len(qpos)))
    data.qpos[:] = qpos
    mujoco.mj_forward(model, data)
    position = [float(value) for value in data.xpos[body]]
    quaternion = [float(value) for value in data.xquat[body]]          # mujoco's xquat is (w, x, y, z)
    return position + [quaternion[1], quaternion[2], quaternion[3], quaternion[0]]
