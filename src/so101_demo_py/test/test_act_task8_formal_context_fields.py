"""The FORMAL context must carry what the production controller path reads from it.

The composition contract test passes while the formal path cannot run, and this file is why: that test builds its context
with `type("Context", (), document)()` - a duck-typed namespace - so it never exercises `CalibrationMeasurementContext`,
the type the CLI actually constructs. The production controller builder reads four things from the context:

    context.calibration_report   -> PRODUCTION_CALIBRATION_REPORT_REQUIRED
    context.session_id           -> PRODUCTION_MEASUREMENT_IDENTITY_REQUIRED: session_id
    context.attempt_id           -> PRODUCTION_MEASUREMENT_IDENTITY_REQUIRED: attempt_id
    context.search_start_rad     -> PRODUCTION_MEASUREMENT_IDENTITY_REQUIRED: search_start_rad

and none of them is a field of that context, so on the formal path the composition fails at its first check. This test
therefore drives the REAL context type through the REAL controller builder, with no duck-typing, and requires the
controller to be admitted.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from so101_demo.act.task8_calibration_admission import CalibrationMeasurementContext  # noqa: E402


def _formal_context(**extra):
    """A context built the way the CLI builds it, plus whatever the production path requires of it."""

    fields = dict(
        generation="g1", contract_sha256="a" * 64, measurement_plan_sha256="b" * 64,
        safe_interval_rad=[-1.0, 1.0], candidate_sha256="c" * 64, policy_sha256="d" * 64,
        driver_source_sha256="e" * 64, controller_generation="ctrl-1", broker_generation="g1",
        evidence_root="/data/work/so101-evidence/act-data/run",
        resource_binding={"bound_at_entry": True, "cpu_cores": 8, "gpu_device": 0},
        # the complete production-shaped descriptor: the shared rule is closed over the detector block, so a stub is
        # refused by name (HEAD_SEARCH_CONFIG_INVALID) - the same completion the driver fixtures needed (CP-1578)
        runtime_descriptor={"schema_version": 1, "head_search": {
            "schema_version": 1,
            "detector": {"backend": "yolo_seg", "weights_path": "/weights/best.pt",
                         "weights_sha256": "a" * 64, "model_id": "plastic-cup",
                         "image_size_px": 640, "requested_device": "cuda", "allow_cpu_fallback": False,
                         "torch_threads": 4, "torch_interop_threads": 2, "torch_version": "2.0",
                         "ultralytics_version": "8.0"},
            "camera": {"frame_id": "head_camera_frame", "ray_origin_frame_id": "head_camera_frame",
                       "width_px": 640, "height_px": 480},
            "motion": {"goal_tolerance_rad": 0.02, "settle_velocity_rad_s": 0.01,
                       "neck_goal_duration_s": 0.5}}},
    )
    fields.update(extra)
    return CalibrationMeasurementContext(**fields)


@pytest.mark.parametrize("name", ["calibration_report", "session_id", "attempt_id", "search_start_rad"])
def test_the_formal_context_carries_every_field_the_controller_path_reads(name):
    """Each of the four is read by `_admitted_controller_config`; the context must be able to hold it."""

    value = {"schema_version": 1} if name == "calibration_report" else (
        "session-1" if name == "session_id" else ("attempt-1" if name == "attempt_id" else 0.0))
    context = _formal_context(**{name: value})
    assert getattr(context, name) == value, (
        f"the production controller path reads context.{name}; a context that cannot carry it makes the formal "
        "composition fail at its first check, which is the review's item 1")
