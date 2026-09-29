"""P1-2: ONE complete head-search validator, and both entries must refuse the same documents.

Astra re-review #3, finding 2: `validate_head_search_shape` checked that the required fields were *present* but not
that the document was a closed, correctly typed, correctly valued structure - so the measurement entry accepted
descriptors the production binding would have refused (missing thread/version fields, extra fields, wrong camera
sizes, negative or stringly-typed motion). These tests assert the two entries agree, document by document.

Report pairing stays a separate concern: the calibration report's sample/digest checks belong to the binding and
are deliberately NOT part of the shared shape rule, so the binding's own pairing tests keep their meaning.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_act_head_search_binding import _inputs  # noqa: E402


def _mutations():
    """Each entry is (name, mutate) and every one must be refused by BOTH entries."""

    def missing_thread_field(runtime):
        del runtime["head_search"]["detector"]["torch_threads"]

    def missing_software_version(runtime):
        del runtime["head_search"]["detector"]["ultralytics_version"]

    def extra_detector_field(runtime):
        runtime["head_search"]["detector"]["torch_dtype"] = "float16"

    def extra_camera_field(runtime):
        runtime["head_search"]["camera"]["distortion_model"] = "plumb_bob"

    def extra_motion_field(runtime):
        runtime["head_search"]["motion"]["accel_limit_rad_s2"] = 1.0

    def wrong_camera_size(runtime):
        runtime["head_search"]["camera"]["width_px"] = 320
        runtime["head_search"]["camera"]["height_px"] = 240

    def negative_motion(runtime):
        runtime["head_search"]["motion"]["goal_tolerance_rad"] = -0.02

    def string_motion(runtime):
        runtime["head_search"]["motion"]["settle_velocity_rad_s"] = "0.01"

    def zero_threads(runtime):
        runtime["head_search"]["detector"]["torch_threads"] = 0

    return [
        ("missing_thread_field", missing_thread_field),
        ("missing_software_version", missing_software_version),
        ("extra_detector_field", extra_detector_field),
        ("extra_camera_field", extra_camera_field),
        ("extra_motion_field", extra_motion_field),
        ("wrong_camera_size", wrong_camera_size),
        ("negative_motion", negative_motion),
        ("string_motion", string_motion),
        ("zero_threads", zero_threads),
    ]


@pytest.mark.parametrize("name,mutate", _mutations(), ids=[name for name, _ in _mutations()])
def test_the_measurement_entry_refuses_a_descriptor_the_binding_would_refuse(tmp_path, name, mutate):
    """The measurement entry consumes the parsed context document, so it is the one that must be complete."""

    from so101_demo.act.task8_artifact_bundle import require_runtime_descriptor

    runtime, _calibration, _weights, _sample = _inputs(tmp_path)
    mutated = copy.deepcopy(runtime)
    mutate(mutated)

    with pytest.raises(ValueError, match="HEAD_SEARCH_CONFIG_INVALID"):
        require_runtime_descriptor(mutated)


@pytest.mark.parametrize("name,mutate", _mutations(), ids=[name for name, _ in _mutations()])
def test_the_binding_entry_refuses_the_same_descriptor(tmp_path, name, mutate):
    """And the production binding refuses it too - the same rule, not a second opinion."""

    from so101_demo.act.head_search_binding import validate_head_search_binding

    runtime, calibration, _weights, _sample = _inputs(tmp_path)
    mutated = copy.deepcopy(runtime)
    mutate(mutated)

    with pytest.raises(ValueError, match="HEAD_SEARCH_CONFIG_INVALID"):
        validate_head_search_binding(mutated, calibration)
