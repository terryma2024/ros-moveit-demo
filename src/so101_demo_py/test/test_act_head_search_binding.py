"""The admitted head detector must be the one measured by Task 6."""

import hashlib
import json

import pytest

from so101_demo.act.head_search_binding import validate_head_search_binding


def _inputs(tmp_path):
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"local test weights")
    descriptor = {
        "schema_version": 1,
        "detector": {
            "backend": "yolo_seg", "weights_path": str(weights),
            "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
            "model_id": "plastic-cup-test", "image_size_px": 640,
            "requested_device": "cuda", "allow_cpu_fallback": False,
            "torch_threads": 4, "torch_interop_threads": 2,
            "torch_version": "2.0-test", "ultralytics_version": "8.0-test",
        },
        "camera": {"frame_id": "head_camera_frame", "ray_origin_frame_id": "head_camera_frame",
                   "width_px": 640, "height_px": 480},
        "motion": {"goal_tolerance_rad": 0.02, "settle_velocity_rad_s": 0.01,
                   "neck_goal_duration_s": 0.5},
    }
    values = {"horizontal_fov_rad": 1.0, "coarse_step_rad": 0.2,
              "search_timeout_s": 15.0, "max_fine_corrections": 3,
              "max_fine_total_rad": 0.5, "min_confidence": 0.5,
              "tracking_iou": 0.5, "min_bbox_aspect": 0.2,
              "center_deadband_px": 15.0, "vertical_bounds_px": [100, 380],
              "min_area_px2": 100.0, "max_age_s": 0.5, "max_skew_s": 0.1,
              "lock_valid_neck_rad": [-3.14, 3.14], "submit_lead_s": 0.05,
              "stop_velocity_rad_s": 0.01, "stop_latency_s": 0.5}
    camera_values = {"head_intrinsics_px": [400.0, 400.0, 320.0, 240.0],
                     "head_translation_m": [0.0, 0.0, 0.1],
                     "head_rpy_rad": [0.0, 0.0, 0.0],
                     "yaw_zero_bearing_rad": 0.0}
    source_commit, config_sha256 = "a" * 40, "b" * 64
    sample = tmp_path / "head-search-sample.json"
    sample.write_text(json.dumps({"schema_version": 1, "kind": "head_search_qualification",
                                  "status": "PASS", "head_search": descriptor,
                                  "observed_lock_frames": 3, "measurements": values,
                                  "camera_measurements": camera_values,
                                  "source_commit": source_commit,
                                  "config_sha256": config_sha256}))
    digest = hashlib.sha256(sample.read_bytes()).hexdigest()
    report = {"status": "TASK8_READY", "source_commit": source_commit,
              "config_sha256": config_sha256, "measurements": {
        key: {"value": value, "sample_path": str(sample), "sample_sha256": digest}
        for key, value in {**values, **camera_values}.items()}}
    return {"schema_version": 1, "head_search": descriptor}, report, weights, sample


def test_head_search_binding_uses_measured_values_and_matching_sample(tmp_path):
    runtime, report, _, _ = _inputs(tmp_path)
    bound = validate_head_search_binding(runtime, report)
    assert bound.search_values["coarse_step_rad"] == 0.2
    assert bound.search_values["tracking_iou"] == 0.5
    assert bound.detector["model_id"] == "plastic-cup-test"


def test_head_search_binding_builds_attempt_config_from_reset_neck(tmp_path):
    runtime, report, _, _ = _inputs(tmp_path)
    bound = validate_head_search_binding(runtime, report)
    config = bound.search_config(session_id="sim-1", attempt_id="try-1",
                                 search_start_rad=0.1)
    assert config["search_start_rad"] == 0.1
    assert config["coarse_step_rad"] == 0.2
    assert config["goal_tolerance_rad"] == 0.02
    assert config["frame_id"] == "head_camera_frame"
    assert config["attempt_id"] == "try-1"


def test_head_search_detector_builder_uses_bound_model_and_thread_count(tmp_path):
    from so101_demo.adapters.act.detector import build_bound_head_detector

    runtime, report, weights, _ = _inputs(tmp_path)
    bound = validate_head_search_binding(runtime, report)
    observed = {}
    effective = {"threads": 1, "interop": 1}

    class TorchRuntime:
        __version__ = "2.0-test"

        def set_num_threads(self, count):
            effective["threads"] = count

        def get_num_threads(self):
            return effective["threads"]

        def set_num_interop_threads(self, count):
            effective["interop"] = count

        def get_num_interop_threads(self):
            return effective["interop"]

    class LocalDetector:
        cold_start_latency_ms = 1.0
        runtime_device = "cuda"

        def __init__(self, **kwargs):
            observed.update(kwargs)
            observed["loaded_bytes"] = kwargs["weights_path"].read_bytes()
            weights.write_bytes(b"replaced during model load")
            weights.write_bytes(b"local test weights")

    built = build_bound_head_detector(
        bound, snapshot_root=tmp_path, yolo_detector_factory=LocalDetector,
        torch_api=TorchRuntime(), ultralytics_version="8.0-test")
    assert built.runtime.model_id == "plastic-cup-test"
    assert built.runtime.weights_sha256 == runtime["head_search"]["detector"]["weights_sha256"]
    assert observed["requested_device"] == "cuda"
    assert observed["allow_cpu_fallback"] is False
    assert observed["imgsz"] == 640
    assert effective == {"threads": 4, "interop": 2}
    assert observed["weights_path"] == built.snapshot_path
    assert built.snapshot_path != tmp_path / "best.pt"
    assert built.snapshot_path.read_bytes() == b"local test weights"
    assert observed["loaded_bytes"] == b"local test weights"


def test_head_search_detector_builder_refuses_thread_drift_after_warmup(tmp_path):
    from so101_demo.adapters.act.detector import build_bound_head_detector

    runtime, report, _, _ = _inputs(tmp_path)
    bound = validate_head_search_binding(runtime, report)

    class TorchRuntime:
        __version__ = "2.0-test"

        def set_num_threads(self, count):
            self.threads = count

        def get_num_threads(self):
            return self.threads

        def set_num_interop_threads(self, count):
            self.interop = count

        def get_num_interop_threads(self):
            return self.interop

    runtime_api = TorchRuntime()

    class DriftingDetector:
        cold_start_latency_ms = 1.0
        runtime_device = "cuda"

        def __init__(self, **kwargs):
            runtime_api.threads = 1

    with pytest.raises(ValueError, match="HEAD_SEARCH_THREAD_DRIFT"):
        build_bound_head_detector(
            bound, snapshot_root=tmp_path, yolo_detector_factory=DriftingDetector,
            torch_api=runtime_api, ultralytics_version="8.0-test")


def test_head_search_binding_refuses_missing_descriptor(tmp_path):
    _, report, _, _ = _inputs(tmp_path)
    with pytest.raises(ValueError, match="HEAD_SEARCH_CONFIG_INVALID"):
        validate_head_search_binding({"schema_version": 1}, report)


def test_head_search_binding_refuses_sample_from_other_detector(tmp_path):
    runtime, report, _, sample = _inputs(tmp_path)
    document = json.loads(sample.read_text())
    document["head_search"]["detector"]["model_id"] = "other-model"
    sample.write_text(json.dumps(document))
    digest = hashlib.sha256(sample.read_bytes()).hexdigest()
    for item in report["measurements"].values():
        item["sample_sha256"] = digest
    with pytest.raises(ValueError, match="HEAD_SEARCH_SAMPLE_MISMATCH"):
        validate_head_search_binding(runtime, report)


def test_head_search_binding_refuses_measurement_changed_after_sample(tmp_path):
    runtime, report, _, _ = _inputs(tmp_path)
    report["measurements"]["coarse_step_rad"]["value"] = 0.3
    with pytest.raises(ValueError, match="HEAD_SEARCH_SAMPLE_MISMATCH"):
        validate_head_search_binding(runtime, report)


def test_head_search_binding_refuses_other_source_camera_profile(tmp_path):
    runtime, report, _, _ = _inputs(tmp_path)
    report["config_sha256"] = "c" * 64
    with pytest.raises(ValueError, match="HEAD_SEARCH_SAMPLE_MISMATCH"):
        validate_head_search_binding(runtime, report)


def test_head_search_binding_refuses_other_camera_intrinsics(tmp_path):
    runtime, report, _, _ = _inputs(tmp_path)
    report["measurements"]["head_intrinsics_px"]["value"] = [401.0, 400.0, 320.0, 240.0]
    with pytest.raises(ValueError, match="HEAD_SEARCH_SAMPLE_MISMATCH"):
        validate_head_search_binding(runtime, report)


def test_head_search_binding_accepts_fast_stop_latency_independent_of_submit_lead(tmp_path):
    runtime, report, _, sample_path = _inputs(tmp_path)
    document = json.loads(sample_path.read_text())
    document["measurements"]["stop_latency_s"] = 0.01
    sample_path.write_text(json.dumps(document))
    digest = hashlib.sha256(sample_path.read_bytes()).hexdigest()
    for item in report["measurements"].values():
        item["sample_sha256"] = digest
    report["measurements"]["stop_latency_s"]["value"] = 0.01
    assert validate_head_search_binding(runtime, report).search_values["stop_latency_s"] == 0.01


@pytest.mark.parametrize("mutation", ("replace", "symlink"))
def test_head_search_binding_refuses_unverified_weights(tmp_path, mutation):
    runtime, report, weights, _ = _inputs(tmp_path)
    if mutation == "replace":
        weights.write_bytes(b"different model")
    else:
        target = tmp_path / "target.pt"
        weights.rename(target)
        weights.symlink_to(target)
    with pytest.raises(ValueError, match="HEAD_SEARCH_WEIGHTS_INVALID"):
        validate_head_search_binding(runtime, report)
