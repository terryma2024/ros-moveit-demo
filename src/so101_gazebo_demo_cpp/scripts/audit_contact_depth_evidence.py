#!/usr/bin/env python3
"""Utilities for time-aligned Bullet-contact versus exact-mesh evidence.

Gazebo's contact ``depth`` is a solver/manifold quantity.  It remains a useful
stable-window sanity signal, but it is not an exact geometric overlap.  Exact
penetration is derived independently from signed mesh clearance after poses
have been interpolated to the contact timestamp.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TimedPose:
    stamp: float
    position: np.ndarray
    orientation_xyzw: np.ndarray


def interpolate_pose(before: TimedPose, after: TimedPose, stamp: float) -> TimedPose:
    if not before.stamp <= stamp <= after.stamp or after.stamp <= before.stamp:
        raise ValueError('interpolation stamp must be bracketed by distinct samples')
    alpha = (stamp - before.stamp) / (after.stamp - before.stamp)
    q0 = np.asarray(before.orientation_xyzw, dtype=float)
    q1 = np.asarray(after.orientation_xyzw, dtype=float)
    q0 /= np.linalg.norm(q0)
    q1 /= np.linalg.norm(q1)
    dot = float(q0 @ q1)
    if dot < 0.0:
        q1 = -q1
        dot = -dot
    if dot > 0.9995:
        q = q0 + alpha * (q1 - q0)
        q /= np.linalg.norm(q)
    else:
        angle = np.arccos(np.clip(dot, -1.0, 1.0))
        q = (np.sin((1.0 - alpha) * angle) * q0 +
             np.sin(alpha * angle) * q1) / np.sin(angle)
    return TimedPose(
        stamp,
        np.asarray(before.position, dtype=float) + alpha * (
            np.asarray(after.position, dtype=float) - np.asarray(before.position, dtype=float)
        ),
        q,
    )


def depth_evidence(solver_reported_depth_m: float, signed_mesh_clearance_m: float) -> dict:
    """Return deliberately separate solver and exact-geometry measurements."""
    if not np.isfinite(solver_reported_depth_m) or solver_reported_depth_m < 0.0:
        raise ValueError('solver-reported depth must be finite and non-negative')
    if not np.isfinite(signed_mesh_clearance_m):
        raise ValueError('signed mesh clearance must be finite')
    return {
        'solver_reported_depth_m': float(solver_reported_depth_m),
        'signed_mesh_clearance_m': float(signed_mesh_clearance_m),
        'exact_mesh_penetration_m': float(max(0.0, -signed_mesh_clearance_m)),
    }
