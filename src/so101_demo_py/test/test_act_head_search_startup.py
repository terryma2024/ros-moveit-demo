"""Production startup: exactly the promoted bundle, or a fail-closed refusal."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from so101_demo.act.head_search_binding import validate_head_search_binding
from paths import PACKAGE_ROOT

PACKAGE = PACKAGE_ROOT
V2 = PACKAGE / "config/mujoco/act/head_search_v2.json"

FIELDS = (
    "horizontal_fov_rad",
    "lock_valid_neck_rad",
    "coarse_step_rad",
    "search_timeout_s",
    "min_confidence",
    "tracking_iou",
    "min_bbox_aspect",
    "min_area_px2",
    "center_deadband_px",
    "vertical_bounds_px",
    "max_fine_corrections",
    "max_fine_total_rad",
    "max_age_s",
    "max_skew_s",
    "submit_lead_s",
    "stop_velocity_rad_s",
    "stop_latency_s",
)


def _config() -> dict:
    return json.loads(V2.read_text(encoding="utf-8"))


def test_the_shipped_config_declares_the_seventeen_values_and_its_identities() -> None:
    config = _config()

    assert set(config["values"]) == set(FIELDS)
    for key in ("weight_sha256", "candidate_identity_sha256", "camera", "tracker", "runtime_id"):
        assert config[key], key
    assert config["allow_cpu_fallback"] is False
    assert config["unused_values"] == [], (
        "the shipped config must not carry a value nobody consumes"
    )


def test_startup_rejects_one_field_of_bundle_drift() -> None:
    config = _config()
    report = copy.deepcopy(config)
    report["values"]["min_confidence"] = config["values"]["min_confidence"] + 0.01
    with pytest.raises(ValueError, match="HEAD_SEARCH_SAMPLE_MISMATCH"):
        validate_head_search_binding(config, report)


def test_startup_rejects_an_identity_or_dependency_drift() -> None:
    config = _config()
    for key in ("weight_sha256", "candidate_identity_sha256", "runtime_id"):
        report = copy.deepcopy(config)
        report[key] = "0" * 64 if key != "runtime_id" else "other-runtime"
        with pytest.raises(ValueError, match="HEAD_SEARCH_SAMPLE_MISMATCH"):
            validate_head_search_binding(config, report)


def test_startup_refuses_an_unconsumed_value() -> None:
    config = _config()
    config["unused_values"] = ["unused_extra"]
    with pytest.raises(ValueError, match="HEAD_SEARCH_UNUSED_VALUE"):
        validate_head_search_binding(config, copy.deepcopy(config))


def test_the_loader_validates_the_pair_before_anything_is_constructed(tmp_path: Path) -> None:
    from so101_demo.act.head_search_binding import load_promoted_head_search

    config = _config()
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    assert load_promoted_head_search(config_path) == config

    report = copy.deepcopy(config)
    report["values"]["tracking_iou"] = 0.9
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="HEAD_SEARCH_SAMPLE_MISMATCH"):
        load_promoted_head_search(config_path, report_path)


def test_startup_rejects_camera_tracker_device_and_dependency_drift() -> None:
    config = _config()

    for mutate in (
        lambda doc: doc["camera"].__setitem__("width", 1280),
        lambda doc: doc["tracker"].__setitem__("name", "ocsort"),
        lambda doc: doc.__setitem__("cuda_device", "cuda:1"),
        lambda doc: doc.__setitem__("controlled_dependencies", ["ultralytics"]),
        lambda doc: doc.__setitem__("weight_path", "models/other.pt"),
    ):
        report = copy.deepcopy(config)
        mutate(report)
        with pytest.raises(ValueError, match="HEAD_SEARCH_SAMPLE_MISMATCH"):
            validate_head_search_binding(config, report)


def test_startup_refuses_a_cpu_device_and_an_absent_identity() -> None:
    config = _config()
    cpu = copy.deepcopy(config)
    cpu["cuda_device"] = "cpu"
    with pytest.raises(ValueError, match="HEAD_SEARCH_CUDA_REQUIRED"):
        validate_head_search_binding(cpu, copy.deepcopy(cpu))

    missing = copy.deepcopy(config)
    missing["weight_sha256"] = ""
    with pytest.raises(ValueError, match="HEAD_SEARCH_SAMPLE_MISMATCH"):
        validate_head_search_binding(missing, copy.deepcopy(missing))


def test_startup_refuses_an_undeclared_key_and_binds_immutably() -> None:
    config = _config()
    extra = copy.deepcopy(config)
    extra["mystery"] = 1
    with pytest.raises(ValueError, match="HEAD_SEARCH_UNUSED_VALUE"):
        validate_head_search_binding(extra, copy.deepcopy(extra))

    binding = validate_head_search_binding(config, copy.deepcopy(config))
    with pytest.raises(TypeError):
        binding.search_values["min_confidence"] = 0.9
    with pytest.raises(TypeError):
        binding.camera["width"] = 1280
    assert isinstance(binding.search_values["vertical_bounds_px"], tuple)


def test_the_promoted_binding_can_build_a_search_config() -> None:
    """The reviewer's remaining defect: search_config() must not raise KeyError from a promoted binding."""

    config = _config()
    binding = validate_head_search_binding(config, copy.deepcopy(config))
    search = binding.search_config(session_id="session", attempt_id="attempt", search_start_rad=0.1)
    assert search["frame_id"] == config["camera"]["frame_id"]
    assert search["ray_origin_frame_id"] == config["camera"]["ray_origin_frame_id"]
    assert search["settle_velocity_rad_s"] == config["motion"]["settle_velocity_rad_s"]
    assert search["goal_tolerance_rad"] == config["motion"]["goal_tolerance_rad"]
    assert set(search) == {
        "horizontal_fov_rad",
        "coarse_step_rad",
        "search_timeout_s",
        "max_age_s",
        "max_skew_s",
        "center_deadband_px",
        "vertical_bounds_px",
        "min_area_px2",
        "min_confidence",
        "max_fine_corrections",
        "max_fine_total_rad",
        "session_id",
        "attempt_id",
        "search_start_rad",
        "settle_velocity_rad_s",
        "goal_tolerance_rad",
        "frame_id",
        "ray_origin_frame_id",
    }


def test_startup_rejects_a_drifted_motion_block() -> None:
    config = _config()
    report = copy.deepcopy(config)
    report["motion"]["goal_tolerance_rad"] = 0.5
    with pytest.raises(ValueError, match="HEAD_SEARCH_SAMPLE_MISMATCH"):
        validate_head_search_binding(config, report)

    report = copy.deepcopy(config)
    report["motion"]["settle_velocity_rad_s"] = 0.9
    with pytest.raises(ValueError, match="HEAD_SEARCH_SAMPLE_MISMATCH"):
        validate_head_search_binding(config, report)


def test_the_readiness_path_verifies_the_promoted_pair(tmp_path: Path) -> None:
    """The Task 8 call-site wiring, exercised where it can be verified."""

    from so101_demo.cli.act_stack_ready import verify_head_search_startup

    config = _config()
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(config), encoding="utf-8")

    assert verify_head_search_startup(environment={}) is None, "no config means no head search here"
    verified = verify_head_search_startup(
        environment={
            "SO101_HEAD_SEARCH_CONFIG": str(config_path),
            "SO101_HEAD_SEARCH_REPORT": str(report_path),
        }
    )
    assert verified == config

    drifted = copy.deepcopy(config)
    drifted["values"]["min_confidence"] = 0.99
    report_path.write_text(json.dumps(drifted), encoding="utf-8")
    with pytest.raises(ValueError, match="HEAD_SEARCH_SAMPLE_MISMATCH"):
        verify_head_search_startup(
            environment={
                "SO101_HEAD_SEARCH_CONFIG": str(config_path),
                "SO101_HEAD_SEARCH_REPORT": str(report_path),
            }
        )
