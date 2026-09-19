"""Camera optical rays expressed in base axes, without range or object truth."""

import math

from .contracts import finite, vector


def bearing(ray_base):
    x, y, _ = vector(ray_base, 3)
    if math.hypot(x, y) < 1e-9:
        raise ValueError("BEARING_INVALID")
    return (math.atan2(y, x) + math.pi) % (2 * math.pi) - math.pi


def optical_ray_base(pixel, k, distortion, rotation_optical_to_base):
    import numpy as np
    import cv2

    xy = vector(pixel, 2)
    matrix = np.asarray(vector(k, 9)).reshape(3, 3)
    if (matrix[0, 0] <= 0 or matrix[1, 1] <= 0
            or not np.allclose(matrix[2], (0, 0, 1), atol=1e-9)):
        raise ValueError("CAMERA_INTRINSICS_INVALID")
    distortion = tuple(finite(value) for value in distortion)
    if len(distortion) not in (4, 5, 8, 12, 14):
        raise ValueError("CAMERA_DISTORTION_INVALID")
    rotation = np.asarray(rotation_optical_to_base, dtype=float)
    if (rotation.shape != (3, 3) or not np.isfinite(rotation).all()
            or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6)
            or not math.isclose(float(np.linalg.det(rotation)), 1., abs_tol=1e-6)):
        raise ValueError("CAMERA_ROTATION_INVALID")
    point = cv2.undistortPoints(np.array([[xy]], dtype=float), matrix,
                              np.asarray(distortion))[0, 0]
    ray = rotation @ np.array((point[0], point[1], 1.))
    return tuple(float(value) for value in ray / np.linalg.norm(ray))
