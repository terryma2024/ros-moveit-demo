"""Task 8P3 / Boundary IV: the immutable runtime config is parsed, not merely digested.

Approved preparation design §4.2: preparation accepts only content the production validator can parse; Task 8 live's
head-search config and parallel_batch_v3.yaml must both request CUDA with allow_cpu_fallback=false, and a disagreement is
refused rather than auto-recovered on CPU. The bundle is where that file is bound, so it is where the refusal belongs.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_act_task8_artifact_bundle import _inputs, _write          # noqa: E402


def _runtime_document(cpu_fallback: bool, device: str = "cuda"):
    """A runtime config shaped the way the production validator inspects it."""

    return {
        "schema_version": 1,
        "head_search": {
            "schema_version": 1,
            "detector": {
                "backend": "yolo_seg", "weights_path": "/nonexistent/best.pt", "weights_sha256": "a" * 64,
                "model_id": "plastic-cup", "image_size_px": 640, "requested_device": device,
                "allow_cpu_fallback": cpu_fallback, "torch_threads": 4, "torch_interop_threads": 2,
                "torch_version": "2.0", "ultralytics_version": "8.0",
            },
            "camera": {"frame_id": "head_camera_frame", "ray_origin_frame_id": "head_camera_frame",
                       "width_px": 640, "height_px": 480},
            "motion": {"goal_tolerance_rad": 0.02, "settle_velocity_rad_s": 0.01,
                       "neck_goal_duration_s": 0.5},
        },
    }


def test_a_runtime_config_that_allows_cpu_fallback_is_refused(tmp_path):
    """§4.2: allow_cpu_fallback must be false; resource shortage is a human decision, never a CPU recovery."""

    from so101_demo.act.task8_artifact_bundle import prepare_task8_bundle

    inputs = _inputs(tmp_path)
    _write(Path(inputs.runtime_config), _runtime_document(cpu_fallback=True))
    with pytest.raises(ValueError, match="TASK8_PREPARATION_CUDA_REQUIRED"):
        prepare_task8_bundle(inputs, tmp_path / "bundle")
