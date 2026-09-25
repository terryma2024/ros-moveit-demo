"""Independent position-stage collision check for one SEARCH neck command."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import threading

import mujoco
import numpy as np

from so101_demo.act.contracts import finite, sha256, vector
from .physics import model_sha256


class MujocoNeckSweepChecker:
    """Replay every neck segment with the full observed qpos in private MjData."""

    def __init__(self, model_path: Path, *, expected_model_sha256: str,
                 protected_roots: tuple[str, ...],
                 allowed_pairs: tuple[tuple[str, str], ...],
                 path_step_s: float, path_clearance_m: float,
                 max_samples: int = 50000) -> None:
        expected_version = {"linux": "3.12.0", "darwin": "3.4.0"}.get(sys.platform)
        if expected_version is None or mujoco.mj_versionString() != expected_version:
            raise ValueError("NECK_SWEEP_MUJOCO_VERSION_INVALID")
        path = Path(model_path)
        if not path.is_absolute() or ".." in path.parts or not path.is_file():
            raise ValueError("NECK_SWEEP_MODEL_INVALID")
        sha256(expected_model_sha256)
        self.model = mujoco.MjModel.from_xml_path(str(path))
        self.model_sha256 = model_sha256(self.model)
        if self.model_sha256 != expected_model_sha256:
            raise ValueError("NECK_SWEEP_MODEL_MISMATCH")
        joint = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT,
                                  "neck_yaw_joint")
        if joint < 0 or self.model.jnt_type[joint] != mujoco.mjtJoint.mjJNT_HINGE:
            raise ValueError("NECK_SWEEP_JOINT_INVALID")
        self.neck_qpos = int(self.model.jnt_qposadr[joint])
        self.step_s = finite(path_step_s)
        self.clearance_m = finite(path_clearance_m)
        if (self.step_s <= 0 or self.clearance_m <= 0
                or type(max_samples) is not int or not 2 <= max_samples <= 50000):
            raise ValueError("NECK_SWEEP_CONFIG_INVALID")
        self.max_samples = max_samples
        roots = set()
        for name in protected_roots:
            if type(name) is not str or not name:
                raise ValueError("NECK_SWEEP_PROTECTED_ROOT_INVALID")
            body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, name)
            if body < 1:
                raise ValueError("NECK_SWEEP_PROTECTED_ROOT_INVALID")
            roots.add(body)
        if not roots:
            raise ValueError("NECK_SWEEP_PROTECTED_ROOT_INVALID")
        self.names = tuple(mujoco.mj_id2name(
            self.model, mujoco.mjtObj.mjOBJ_GEOM, index,
        ) for index in range(self.model.ngeom))
        known = {name for name in self.names if name is not None}
        if len(known) != self.model.ngeom:
            raise ValueError("NECK_SWEEP_CONTACT_CONFIG_INVALID")
        self.allowed = set()
        for pair in allowed_pairs:
            if (type(pair) is not tuple or len(pair) != 2
                    or any(type(name) is not str for name in pair)
                    or tuple(sorted(pair)) != pair
                    or not set(pair) <= known):
                raise ValueError("NECK_SWEEP_CONTACT_CONFIG_INVALID")
            self.allowed.add(pair)
        protected = set()
        for geom in range(self.model.ngeom):
            body = int(self.model.geom_bodyid[geom])
            while body > 0 and body not in roots:
                body = int(self.model.body_parentid[body])
            if body in roots:
                protected.add(geom)
        if not protected:
            raise ValueError("NECK_SWEEP_PROTECTED_ROOT_INVALID")
        self.protected = frozenset(protected)
        self.model.geom_margin[:] = np.maximum(self.model.geom_margin,
                                                self.clearance_m)
        self._data = mujoco.MjData(self.model)
        self._lock = threading.Lock()
        self.last_check: dict | None = None

    def _reject(self, reason: str, **details) -> bool:
        self.last_check = {"safe": False, "reason": reason, **details}
        return False

    def check(self, qpos, *, current_rad: float, target_rad: float,
              duration_s: float) -> bool:
        """Refuse invalid input or any protected contact along linear interpolation."""
        with self._lock:
            try:
                positions = vector(qpos, self.model.nq)
                current, target, duration = (
                    finite(value) for value in (current_rad, target_rad, duration_s)
                )
                if duration <= 0:
                    return self._reject("NECK_SWEEP_INPUT_INVALID")
                if abs(positions[self.neck_qpos] - current) > 0.002:
                    return self._reject("NECK_SWEEP_START_MISMATCH")
                intervals = math.ceil(duration / self.step_s)
                if intervals + 1 > self.max_samples:
                    return self._reject("NECK_SWEEP_SAMPLE_BUDGET")
                mujoco.mj_resetData(self.model, self._data)
                for index in range(intervals + 1):
                    self._data.qpos[:] = positions
                    self._data.qpos[self.neck_qpos] = current + (
                        target - current) * index / intervals
                    mujoco.mj_fwdPosition(self.model, self._data)
                    for contact in self._data.contact:
                        a, b = int(contact.geom1), int(contact.geom2)
                        if a not in self.protected and b not in self.protected:
                            continue
                        pair = tuple(sorted((self.names[a], self.names[b])))
                        distance = float(contact.dist)
                        if not math.isfinite(distance) or (
                            distance <= self.clearance_m and pair not in self.allowed
                        ):
                            return self._reject(
                                "NECK_SWEEP_CONTACT", contact_pair=pair,
                                signed_distance_m=distance,
                                sample_time_s=duration * index / intervals,
                            )
                self.last_check = {
                    "safe": True, "reason": None, "samples": intervals + 1,
                    "model_sha256": self.model_sha256,
                    "path_step_s": self.step_s,
                    "path_clearance_m": self.clearance_m,
                }
                return True
            except (IndexError, OverflowError, TypeError, ValueError) as error:
                return self._reject("NECK_SWEEP_INPUT_INVALID", error=repr(error))
