"""Audit builders and helpers shared by the episode audit tests."""

from __future__ import annotations

import hashlib
import json

import numpy as np

from so101_demo.act.acquisition import AcquisitionMinter
from so101_demo.act.episode_audit.writer import EpisodeAuditWriter

ZERO = np.zeros((480, 640, 3), dtype=np.uint8)


def identity():
    return {"session_id": "s", "attempt_id": "attempt-1", "reset_epoch": 1, "release_epoch": 1,
            "scene_id": "default", "seed": 0, "mode": "preselected_target_diagnostic"}


def scope():
    return {"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1,
            "mode": "preselected_target_diagnostic", "scene_id": "default", "seed": 0,
            "inputs_sha256": "a" * 64}


def complete_audit(tmp_path):
    """Every closed field and file this task writes, with real files and real hashes."""

    writer = EpisodeAuditWriter(tmp_path / "episode", scope(), identity(),
                                {"inputs_sha256": "a" * 64})
    minter = AcquisitionMinter()
    # one frame per camera per instant: a row binds the head frame to the head slot and the wrist frame
    # to the wrist slot, which is exactly the relationship the review's counterexample violated
    frames = {}
    for camera in ("head", "wrist"):
        for stamp in (1.0, 1.1, 1.2):
            frame = minter.mint(camera, session_id="s", reset_epoch=1, stamp_s=stamp,
                                received_monotonic_ns=int(stamp * 1e9) + 1, pixels=ZERO)
            writer.append_acquisition(frame)
            frames[(camera, stamp)] = frame
    writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
                                        "accepted": True})
    writer.append_source("events", {"kind": "phase_complete", "identity": identity(),
                                    "sim_time_s": 1.0, "monotonic_ns": 1000,
                                    "payload": {"phase": "SEARCH", "physics_step": 1}})
    # the raw block follows what the MuJoCo source actually publishes, plus the verified support flag
    writer.append_source("physics", {
        "kind": "support", "sim_time_s": 1.1, "release_epoch": 1,
        "observation": {"simulation_time_s": 1.1, "simulation_step": 11, "left_contact_count": 2,
                        "right_contact_count": 2, "table_contact": True, "supported": True,
                        "maximum_normal_force_n": 0.4, "cup_position_world_m": [0.02, -0.28, 0.165]}})
    writer.append_source("physics", {
        "kind": "retract", "sim_time_s": 1.2, "release_epoch": 1,
        "observation": {"simulation_time_s": 1.2, "simulation_step": 12, "left_contact_count": 0,
                        "right_contact_count": 0, "table_contact": True,
                        "maximum_normal_force_n": 0.0, "cup_position_world_m": [0.02, -0.28, 0.165]}})
    writer.bind_row(0, 1.0, frames[("head", 1.0)].acquisition_id,
                    frames[("wrist", 1.0)].acquisition_id, 1)
    window = {"start_s": 1.0, "end_s": 1.2, "label_cutoff_s": 1.0}
    return writer, window


def _resign(writer, manifest_path, name, payload):
    """Rewrite one stream and make the manifest agree, so only semantics can catch it."""

    (manifest_path.parent / name).write_bytes(payload)
    document = json.loads(manifest_path.read_bytes())
    document["files"][name] = {"path": name, "size": len(payload),
                               "sha256": hashlib.sha256(payload).hexdigest()}
    manifest_path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    return manifest_path


def _lease(**overrides):
    lease = {"batch_id": "batch-1", "coordinator_epoch": 1, "worker_id": "worker-1",
             "worker_generation": 1, "point_id": "point-1", "attempt_id": "attempt-1",
             "lease_generation": 1, "lease_issued_monotonic_s": 100.0,
             "lease_deadline_monotonic_s": 200.0}
    lease.update(overrides)
    return lease


def _window(**overrides):
    window = {"source_schedule": {"head": [1.0, 1.1, 1.2], "wrist": [1.0, 1.1, 1.2]},
              "streams_required": ["head", "wrist"], "cadence_s": 0.1, "permitted_gaps_s": [],
              "collection_start_s": 1.0, "collection_end_s": 1.2, "first_command_s": 1.1,
              "physics_end_s": 1.2, "label_cutoff_s": 1.0, "outcome": "complete"}
    window.update(overrides)
    return window


def _formal_writer(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return EpisodeAuditWriter(tmp_path / "formal", dict(scope(), mode="formal"),
                               {**identity(), "lease": _lease()}, {"inputs_sha256": "a" * 64})


def _arm_evaluation():
    return {"requested_sim_time_s": 1.1, "basis": "interval", "goal_id": "goal-1",
            "accepted_sim_s": 1.0, "revoked_sim_s": None}


def _ratified_reference():
    """The ratified A.1 shape: immutable publication beside the evaluated value per kind."""

    arm = {"joint_names": ["1", "2", "3", "4", "5"],
           "published_positions": [0.1, 0.2, 0.3, 0.4, 0.5], "published_velocities": [0.0] * 5,
           "evaluated_positions": [0.1, 0.2, 0.3, 0.4, 0.5], "evaluated_velocities": [0.0] * 5,
           "evaluation": _arm_evaluation(),
           "sim_stamp_ns": 1100000000, "received_monotonic_ns": 900000, "observer_sequence": 7}
    gripper = {"joint_names": ["6"], "published_positions": [0.6],
               "published_velocities": [0.0], "evaluated_positions": [0.6],
               "evaluated_velocities": [0.0], "evaluation": _arm_evaluation(),
               "sim_stamp_ns": 1100000000, "received_monotonic_ns": 900100, "observer_sequence": 7}
    return {"frames": {"arm": arm, "gripper": gripper},
            "projected_positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
            "projection_map": [["arm", 0], ["arm", 1], ["arm", 2], ["arm", 3], ["arm", 4],
                               ["gripper", 0]]}
