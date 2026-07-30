import importlib.util
from pathlib import Path

import numpy as np
import pytest


SCRIPT = Path(__file__).parents[1] / 'scripts' / 'audit_contact_depth_evidence.py'
SPEC = importlib.util.spec_from_file_location('contact_depth_evidence', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_pose_interpolation_is_bracketed_and_normalized():
    before = MODULE.TimedPose(10.000, np.array([0.0, 1.0, 2.0]), np.array([0, 0, 0, 1]))
    after = MODULE.TimedPose(10.010, np.array([0.2, 1.2, 2.2]), np.array([0, 0, 0.1, 0.995]))
    sample = MODULE.interpolate_pose(before, after, 10.004)
    assert sample.position == pytest.approx([0.08, 1.08, 2.08])
    assert np.linalg.norm(sample.orientation_xyzw) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        MODULE.interpolate_pose(before, after, 10.011)


def test_recorded_bullet_peaks_remain_distinct_from_exact_mesh_penetration():
    # Fresh optimized-baseline peaks, synchronized to the high-rate pose/joint
    # streams.  Both exact meshes were separated at these historical transient
    # peaks; the positive Bullet values are speculative manifold metrics.
    fixed = MODULE.depth_evidence(0.00142276613042, 0.001006883858057861)
    moving = MODULE.depth_evidence(0.00121834897436, 0.001071523907928501)
    assert fixed['solver_reported_depth_m'] > 0.0008
    assert moving['solver_reported_depth_m'] > 0.0008
    assert fixed['exact_mesh_penetration_m'] == 0.0
    assert moving['exact_mesh_penetration_m'] == 0.0


def test_negative_signed_clearance_becomes_exact_penetration():
    evidence = MODULE.depth_evidence(0.0004, -0.00037)
    assert evidence['exact_mesh_penetration_m'] == pytest.approx(0.00037)
