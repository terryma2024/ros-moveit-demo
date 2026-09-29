"""P1-3 (rereview 5): the matrix is built from SAMPLES taken at the model's own period, not from constants."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # noqa: E402

from so101_demo.act.task8_phase_camera_sampler import (  # noqa: E402
    MIN_SAMPLES_PER_ANCHOR, PhaseCameraSamplingError, build_phase_camera_matrix,
    sample_phase_camera_geometry,
)

ANCHORS = ("default", "left", "forward")


def _scene() -> Path:
    from ament_index_python.packages import get_package_share_directory

    return Path(get_package_share_directory("so101_demo_py")) / "assets/mujoco/act/scene.xml"


def test_the_sampler_takes_the_designs_minimum_consecutive_samples_per_anchor():
    sampled = sample_phase_camera_geometry(scene_path=_scene(), anchors=ANCHORS)
    assert sampled["period_s"] == pytest.approx(0.002), "the model's own period drives the cadence"
    for anchor in ANCHORS:
        record = sampled["anchors"][anchor]
        assert record["sample_count"] >= MIN_SAMPLES_PER_ANCHOR, anchor
        stamps = record["stamps_s"]
        assert all(b > a for a, b in zip(stamps, stamps[1:])), f"strictly increasing stamps for {anchor}"
        head = record["cameras"]["head_camera"]
        # the geometry is a real function of the model: the head camera's FOV follows from its declared fovy
        assert head["horizontal_fov_rad"] > 0.0
        assert head["width_px"] == 640 and head["height_px"] == 480
        assert len(head["position_m"]) == 3 and len(head["rpy_rad"]) == 3


def test_a_sample_count_below_the_designs_minimum_is_refused_by_name():
    with pytest.raises(PhaseCameraSamplingError) as error:
        sample_phase_camera_geometry(scene_path=_scene(), anchors=ANCHORS,
                                     samples_per_anchor=MIN_SAMPLES_PER_ANCHOR - 1)
    assert "SAMPLE_COUNT_TOO_LOW" in str(error.value)


def test_a_scene_without_the_named_camera_is_refused_by_name(tmp_path):
    scene = tmp_path / "scene.xml"
    scene.write_text("<mujoco><worldbody><body name='b'/></worldbody></mujoco>")
    with pytest.raises(PhaseCameraSamplingError) as error:
        sample_phase_camera_geometry(scene_path=scene, anchors=("default",))
    assert "CAMERA_MISSING" in str(error.value)


def test_the_matrix_builder_freezes_a_non_empty_phase_list_and_a_real_camera_block():
    document = build_phase_camera_matrix(scene_path=_scene(), anchors=ANCHORS,
                                         phases=("SEARCH", "APPROACH", "CLOSE", "RELEASE"))
    assert document["status"] == "FROZEN"
    assert document["phases"], "the scaffold's empty phase list is what this fixes"
    assert [entry["phase"] for entry in document["phases"]] == ["SEARCH", "APPROACH", "CLOSE", "RELEASE"]
    assert document["camera"]["width_px"] == 640
    assert document["camera"]["horizontal_fov_rad"] > 0.0
    assert set(document["anchor_geometry"]) == set(ANCHORS)
    assert all(count >= MIN_SAMPLES_PER_ANCHOR for count in document["sample_counts"].values())
    assert len(document["occluders"]) == 5, "the admitted occluder set travels with it"
