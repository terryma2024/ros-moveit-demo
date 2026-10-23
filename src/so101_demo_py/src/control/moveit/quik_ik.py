"""Weighted QuIK CPU adapter with canonical project FK and acceptance gates."""

from __future__ import annotations

import ctypes
import hashlib
import math
import threading
import weakref
from pathlib import Path

import numpy as np

from ...ports.evidence import PoseEvidence
from .underactuated_ik import UnderactuatedIkError, UnderactuatedPoseIk, _quaternion_matrix

UPSTREAM_COMMIT = "a9ebd1f21dfd3c9f0869140dfb0a4ae5a538cccc"
ORIENTATION_WEIGHT = 0.08

def dh_matrix(row):
    a, alpha, d, theta = row
    ct, st, ca, sa = math.cos(theta), math.sin(theta), math.cos(alpha), math.sin(alpha)
    return np.array([[ct,-st*ca,st*sa,a*ct],[st,ct*ca,-ct*sa,a*st],
                     [0,sa,ca,d],[0,0,0,1]], dtype=float)

def normalized(v):
    return v / np.linalg.norm(v)

def frame(o,z,x):
    x = normalized(x - np.dot(x,z)*z)
    result = np.eye(4)
    result[:3,:3] = np.column_stack((x,np.cross(z,x),z))
    result[:3,3] = o
    return result

def derive_dh(ref):
    t = np.eye(4)
    axes = []
    names = []
    for joint in ref._chain:
        t = t @ joint.origin
        if joint.kind != 'fixed':
            if joint.kind != 'revolute':
                raise UnderactuatedIkError('QUIK_CHAIN_UNSUPPORTED')
            axes.append((t[:3,3].copy(), normalized(t[:3,:3] @ np.asarray(joint.axis))))
            names.append(joint.name)
    if tuple(names) != ref._joint_names or len(axes) != 5:
        raise UnderactuatedIkError('QUIK_CHAIN_UNSUPPORTED')
    frames = []
    for index in range(1,5):
        op,zp = axes[index-1]
        on,zn = axes[index]
        # URDF axes 2/3/4 are parallel to roundoff (~1e-15). Do not
        # amplify the discarded singular direction into 1e13 m offsets.
        s,u = np.linalg.lstsq(np.column_stack((zp,-zn)),on-op,rcond=1e-12)[0]
        cp,cn = op+s*zp,on+u*zn
        cross = np.cross(zp,zn)
        # For nonparallel axes use the analytic common-normal direction;
        # subtracting almost intersecting points loses direction precision.
        x = cross if np.linalg.norm(cross)>1e-12 else cn-cp
        if np.linalg.norm(x) < 1e-12:
            x = frames[-1][:3,0] if frames else np.eye(3)[np.argmin(np.abs(zn))]
        frames.append(frame(cn,zn,x))
    frames.insert(0, frame(axes[0][0],axes[0][1],frames[0][:3,0]))
    frames.append(frames[-1].copy())
    rows,errors = [],[]
    for a,b in zip(frames[:-1],frames[1:]):
        d = np.linalg.inv(a) @ b
        theta = math.atan2(d[1,0],d[0,0])
        alpha = math.atan2(d[2,1],d[2,2])
        row = [d[0,3]*math.cos(theta)+d[1,3]*math.sin(theta),alpha,d[2,3],theta]
        errors.append(float(np.max(np.abs(d-dh_matrix(row)))))
        rows.append(row)
    if max(errors) >= 1e-12:
        raise UnderactuatedIkError('QUIK_CHAIN_UNSUPPORTED')
    return {'DH':rows,'Tbase':frames[0].tolist(),'Ttool':(np.linalg.inv(frames[-1])@t).tolist(),
            'row_reconstruction_max_abs':max(errors), 'joint_names':names,
            'Qsign':[1]*5,'convention':'Spong standard DH Rz(theta+q) Tz(d) Tx(a) Rx(alpha)'}


class QuikPoseIk:
    """Project pose IK API backed by one serialized, weighted QuIK context."""

    def __init__(self, reference: UnderactuatedPoseIk) -> None:
        try:
            from so101_quik import load_native_library

            self._library, self._artifact = load_native_library()
        except (ImportError, OSError) as error:
            raise UnderactuatedIkError(
                "QUIK_BACKEND_UNAVAILABLE: build and source the so101_quik package"
            ) from error
        self._reference = reference
        geometry = derive_dh(reference)
        dh, base, tool = (np.ascontiguousarray(geometry[key], dtype=float)
                          for key in ("DH", "Tbase", "Ttool"))
        self._context = self._library.quik_create(
            self._pointer(dh), self._pointer(base), self._pointer(tool), 0
        )
        if not self._context:
            raise UnderactuatedIkError("QUIK_BACKEND_INITIALIZATION_FAILED")
        self._finalizer = weakref.finalize(self, self._library.quik_destroy, self._context)
        self._lock = threading.Lock()

    @staticmethod
    def _pointer(array):
        return array.ctypes.data_as(ctypes.POINTER(ctypes.c_double))

    @classmethod
    def from_urdf(cls, urdf_path, joint_names, root_link, tip_link):
        return cls(UnderactuatedPoseIk.from_urdf(urdf_path, joint_names, root_link, tip_link))

    @property
    def joint_limits(self):
        return self._reference.joint_limits

    def forward(self, positions):
        return self._reference.forward(positions)

    def forward_positions(self, vectors):
        return self._reference.forward_positions(vectors)

    orientation_error_rad = staticmethod(UnderactuatedPoseIk.orientation_error_rad)

    def _normalize(self, positions, seed):
        if not np.all(np.isfinite(positions)):
            return positions
        result = positions.copy()
        for index, value in enumerate(positions):
            lower = self._reference._solve_lower[index]
            upper = self._reference._solve_upper[index]
            first = math.ceil((lower - value) / (2 * math.pi))
            last = math.floor((upper - value) / (2 * math.pi))
            if first <= last:
                turn = min(last, max(first, round((seed[index] - value) / (2 * math.pi))))
                result[index] = value + turn * 2 * math.pi
        return result

    def solve(
        self, target: PoseEvidence, seed: tuple[float, ...], *,
        position_tolerance_m: float = 0.002, orientation_tolerance_rad: float = 0.10,
    ) -> tuple[float, ...]:
        if len(seed) != len(self._reference._joint_names):
            raise UnderactuatedIkError("DYNAMIC_IK_SEED_INVALID")
        positions = np.clip(np.asarray(seed, dtype=float),
                            self._reference._solve_lower, self._reference._solve_upper)
        # Canonical FK also preserves the project's malformed/nonfinite input errors.
        # No valid request is passed to the native IK solver as a fallback.
        actual = self.forward(positions)
        rotation = _quaternion_matrix(target.orientation_xyzw)

        def accepted(pose):
            return (math.dist(pose.position_m, target.position_m) <= position_tolerance_m
                    and self.orientation_error_rad(pose, target) <= orientation_tolerance_rad)

        if accepted(actual):
            return tuple(float(value) for value in positions)
        matrix = np.eye(4)
        matrix[:3, :3] = rotation
        matrix[:3, 3] = target.position_m
        output, residual = np.empty(5), np.empty(6)
        iterations, reason = ctypes.c_int(), ctypes.c_int()
        with self._lock:
            code = self._library.quik_solve(
                self._context, self._pointer(matrix), self._pointer(positions),
                self._pointer(output), self._pointer(residual),
                ctypes.byref(iterations), ctypes.byref(reason),
            )
        if code != 0:
            raise UnderactuatedIkError("QUIK_BACKEND_SOLVE_FAILED")
        output = self._normalize(output, positions)
        finite = np.all(np.isfinite(output))
        actual = self.forward(output) if finite else None
        within_limits = (np.all(output >= self._reference._solve_lower)
                         and np.all(output <= self._reference._solve_upper))
        if finite and within_limits and accepted(actual):
            return tuple(float(value) for value in output)
        raise UnderactuatedIkError(
            "DYNAMIC_IK_RESIDUAL_EXCEEDED: "
            f"position_m={math.dist(actual.position_m, target.position_m) if actual else math.inf:.6f} "
            f"orientation_rad={self.orientation_error_rad(actual, target) if actual else math.inf:.6f}"
        )

    def provenance(self):
        return {"backend": "quik", "upstream_commit": UPSTREAM_COMMIT,
                "orientation_weight": ORIENTATION_WEIGHT, "eigen_version": "3.4.0",
                "artifacts": {"kernel": {"path": str(self._artifact.resolve()),
                    "sha256": hashlib.sha256(self._artifact.read_bytes()).hexdigest()}}}
