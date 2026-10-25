"""The Teacher's cup pose from the simulator (`teacher_source: privileged_pose`, decision D2), and the camera-versus-truth check.

A randomised-appearance episode of the indoor rig is demonstrated from the simulator's own cup pose, so the demonstration's planning input
never depends on how well the detector reads that appearance. The shard still runs the whole camera chain first (the frame capture, the YOLO
inference, the localisation and their evidence are kept as for any episode); what changes is the pose the Teacher is given: the position the
simulator reports at the same paused instant, with the orientation the camera pose always carries (the identity), so the grasp yaw convention
is the camera Teacher's. The camera pose is kept beside it.

For a nominal episode (`camera_rgbd`) nothing is replaced: the same instant's truth is read and the camera pose is checked against it within
the Teacher endpoint's start tolerance (`initial_position_m`, the rule that already decides a nominal episode's start). The check is recorded
and never changes the pose; the Teacher's own start check is what fails an episode whose camera pose is off.

The record of every episode is written once by the caller (`record_directory`/`<task id>.json`).
"""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path

from so101_demo.act import appearance_plan as ap
from so101_demo.core.task_geometry import Pose7

class PrivilegedPoseRefused(RuntimeError):
    """The simulator's pose cannot be read for this episode; `args[0]` is the refusal code."""


def agreement(camera_xyz, truth_xyz, tolerance_m: float) -> dict:
    """The camera pose against the simulator's, as a record: the distances and whether the xy error is within `tolerance_m` (pure)."""

    if len(camera_xyz) != 3 or len(truth_xyz) != 3 or not tolerance_m > 0:
        raise ValueError("PRIVILEGED_POSE_AGREEMENT_INVALID")
    if not all(math.isfinite(value) for value in (*camera_xyz, *truth_xyz)):
        raise ValueError("PRIVILEGED_POSE_NON_FINITE")
    xy = math.hypot(camera_xyz[0] - truth_xyz[0], camera_xyz[1] - truth_xyz[1])
    return {"camera_position_m": [float(v) for v in camera_xyz], "truth_position_m": [float(v) for v in truth_xyz],
            "xy_error_m": xy, "z_error_m": float(camera_xyz[2] - truth_xyz[2]),
            "tolerance_m": float(tolerance_m), "within_tolerance": xy <= tolerance_m}


class PoseSource:
    """Applied between the camera chain and the pose admission of a task: `__call__(lease, chain)` returns the chain to admit."""

    def __init__(self, *, source: str, kind: str, rig, evidence, session_id: str, tolerance_m: float, record_directory=None,
                 task_id: str | None = None):
        if source not in ap.TEACHER_SOURCES or not ap.teacher_source_allowed(rig, source, kind):
            raise PrivilegedPoseRefused("TEACHER_SOURCE_NOT_ALLOWED: " + f"{source} on a {kind} episode of {getattr(rig, 'rig', rig)}")
        if not callable(evidence) or not tolerance_m > 0 or (record_directory is None) != (task_id is None):
            raise ValueError("PRIVILEGED_POSE_CONFIG_INVALID")
        self.source, self.kind, self.session_id = source, kind, session_id
        self.evidence, self.tolerance_m = evidence, float(tolerance_m)
        self.record_directory, self.task_id = record_directory, task_id
        self.record = None

    @property
    def privileged(self) -> bool:
        return self.source == ap.TEACHER_SOURCE_PRIVILEGED

    def __call__(self, lease, chain):
        observed = self.evidence(self.session_id)
        expected_epoch = int(str(chain.reset_epoch).removeprefix("reset-"))
        if (observed.simulation_session_id != self.session_id or observed.reset_epoch != expected_epoch or not observed.paused):
            raise PrivilegedPoseRefused("PRIVILEGED_POSE_EVIDENCE_NOT_THIS_EPISODE")
        truth = tuple(float(value) for value in observed.object_state.position_world)
        camera = tuple(float(value) for value in chain.pose_world.values[:3])
        record = {"teacher_source": self.source, "episode_kind": self.kind, "attempt_id": lease.attempt_id, "scene_id": lease.point_id,
                  "reset_epoch": observed.reset_epoch, "simulation_time_s": observed.simulation_time_s,
                  **agreement(camera, truth, self.tolerance_m)}
        if not self.privileged:
            self.record = {**record, "applied": False}
            self._write()
            return chain
        given = Pose7((*truth, 0.0, 0.0, 0.0, 1.0))
        self.record = {**record, "applied": True, "published_position_m": list(truth)}
        self._write()
        return dataclasses.replace(chain, pose_world=given)

    def _write(self):
        """The record of the episode, written once beside the task's appearance record (nothing when no directory was given)."""

        if self.record_directory is None:
            return
        import json
        import os

        directory = Path(self.record_directory)
        directory.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(directory / f"{self.task_id}.teacher-source.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write((json.dumps({"task_id": self.task_id, **self.record}, sort_keys=True, indent=1, allow_nan=False) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
