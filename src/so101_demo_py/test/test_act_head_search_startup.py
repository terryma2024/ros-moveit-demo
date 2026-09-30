"""Production startup: exactly the promoted bundle, or a fail-closed refusal."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from so101_demo.act.head_search_binding import validate_head_search_binding

PACKAGE = Path(__file__).parents[1]
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
