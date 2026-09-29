"""Task 8P3 / Boundary IV item 2: the measurement entry consumes the descriptor from its context, and refuses one
whose CUDA policy the approved design forbids.

Approved preparation design section 4.2 and section 6: the runtime config is parsed once at the entry, and internal
components receive identity, generation, deadline and audit hashes - they do not go back to the preparation directory.
So the descriptor travels as a parsed document in the context, and the entry is where a wrong one is refused.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_act_task8_calibration_aggregator import TEMPLATE_V2, _cli_identities   # noqa: E402


def _descriptor(cpu_fallback: bool = False, device: str = "cuda"):
    return {"schema_version": 1, "head_search": {
        "schema_version": 1,
        "detector": {"backend": "yolo_seg", "weights_path": "/weights/best.pt", "weights_sha256": "a" * 64,
                     "model_id": "plastic-cup", "image_size_px": 640, "requested_device": device,
                     "allow_cpu_fallback": cpu_fallback, "torch_threads": 4, "torch_interop_threads": 2,
                     "torch_version": "2.0", "ultralytics_version": "8.0"},
        "camera": {"frame_id": "head_camera_frame", "ray_origin_frame_id": "head_camera_frame",
                   "width_px": 640, "height_px": 480},
        "motion": {"goal_tolerance_rad": 0.02, "settle_velocity_rad_s": 0.01, "neck_goal_duration_s": 0.5}}}


def _context_document(tmp_path, descriptor):
    return {
        "generation": "gen-descriptor-red", "measurement_plan_sha256": "a" * 64, "safe_interval_rad": [0.0, 0.1],
        "candidate_sha256": "b" * 64, "policy_sha256": "c" * 64, "driver_source_sha256": "d" * 64,
        "controller_generation": "ctrl-1", "broker_generation": "broker-1", "evidence_root": str(tmp_path / "ev"),
        "resource_binding": {"bound_at_entry": True, "cpu_cores": 8, "gpu_device": "cuda:0"},
        "runtime_descriptor": descriptor,
    }


def _invoke(tmp_path, context):
    from so101_demo.act.task8_measurement_contract import bind_measurement_contract
    from so101_demo.cli import act_measure_task8_calibration as measure

    bound = bind_measurement_contract(TEMPLATE_V2, _cli_identities(), tmp_path / "bound-v2.json")

    identities = tmp_path / "identities.json"
    identities.write_text(json.dumps(_cli_identities()))
    context_path = tmp_path / "context.json"
    context_path.write_text(json.dumps(context))
    driver = tmp_path / "descriptor_driver.py"
    driver.write_text("def fill(contract, root):\n"
                      "    import json, pathlib\n"
                      "    root = pathlib.Path(root)\n"
                      "    root.mkdir(parents=True, exist_ok=True)\n"
                      "    (root / 'execution.json').write_text(json.dumps({}))\n")
    sys.path.insert(0, str(tmp_path))
    return measure.main(["--contract", str(bound),
                         "--identities", str(identities), "--batch-root", str(tmp_path / "batch"),
                         "--ledger", str(tmp_path / "ledger.md"), "--driver", "descriptor_driver:fill",
                         "--context", str(context_path)])


def test_a_context_descriptor_allowing_cpu_fallback_is_refused_before_measuring(tmp_path):
    """Section 4.2: the descriptor must request CUDA with no CPU fallback; the entry is where that is enforced."""

    with pytest.raises(ValueError, match="TASK8_PREPARATION_CUDA_REQUIRED|RUNTIME_DESCRIPTOR"):
        _invoke(tmp_path, _context_document(tmp_path, _descriptor(cpu_fallback=True)))


def test_a_context_carrying_only_a_digest_is_refused(tmp_path):
    """Item 3: an opaque digest cannot prove which configuration was measured, so the entry refuses it."""

    document = _context_document(tmp_path, _descriptor())
    del document["runtime_descriptor"]
    document["runtime_config_sha256"] = "f" * 64          # provenance without a descriptor
    with pytest.raises(ValueError, match="MEASUREMENT_RUNTIME_DESCRIPTOR_REQUIRED"):
        _invoke(tmp_path, document)
