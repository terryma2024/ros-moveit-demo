"""P1-1: the PRODUCTION low-level client, exercised against the real scene.

Every other implementation of this surface lives in a test file; this one is the production client the default
composition reaches when nothing is set in the environment, so the assertions here are about real values travelling
through it rather than about keys existing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("MUJOCO_GL", "egl")


def _scene() -> Path:
    from ament_index_python.packages import get_package_share_directory

    return Path(get_package_share_directory("so101_demo_py")) / "assets/mujoco/act/scene.xml"


@pytest.fixture()
def client():
    from so101_demo.act.task8_measurement_client import MujocoMeasurementClient

    instance = MujocoMeasurementClient(scene_path=_scene(), session_id="session-p1-1", attempt_id="attempt-p1-1")
    yield instance
    instance.cleanup("anchor-a", "generation-p1-1")


def test_readback_is_the_runs_own_identity_and_moves_with_launch(client):
    with pytest.raises(Exception):
        client.readback("anchor-a")                      # nothing is open before launch
    first = client.launch("anchor-a")
    assert first["session_id"] == "session-p1-1" and first["attempt_id"] == "attempt-p1-1"
    assert isinstance(first["reset_epoch"], int) and first["reset_epoch"] >= 1
    second = client.launch("anchor-a")
    assert second["reset_epoch"] == first["reset_epoch"] + 1, "a launch is a new reset epoch"
    report = client.readback("anchor-a")
    assert set(report) >= {"session_id", "reset_epoch", "attempt_id"}
    assert report["session_id"] == "session-p1-1" and report["physics_step"] >= 0


def test_run_search_sweeps_the_real_neck_and_reports_measured_iterations(client):
    client.launch("anchor-a")
    result = client.run_search("anchor-a", {"sweep_rad": 0.05})
    assert isinstance(result["iterations"], list) and result["iterations"], "the driver requires iterations"
    for row in result["iterations"]:
        assert set(row) >= {"index", "neck_yaw_rad", "bearing_rad", "confidence", "visible", "physics_step"}
        assert 0.0 <= row["confidence"] <= 1.0
    assert len({round(row["neck_yaw_rad"], 9) for row in result["iterations"]}) > 1, "the sweep must actually move"
    assert isinstance(result["found"], bool)


def test_camera_info_declares_its_provenance_and_positive_intrinsics(client):
    client.launch("anchor-a")
    info = client.camera_info("anchor-a")
    assert info["intrinsics_provenance"] == "model_cam_fovy", "P1-3: a model-derived value must say so"
    assert info["width_px"] > 0 and info["height_px"] > 0
    assert info["fx_px"] > 0 and info["fy_px"] > 0
    assert info["cx_px"] == info["width_px"] / 2.0


def test_tf_reports_the_real_camera_pose(client):
    client.launch("anchor-a")
    transforms = client.tf("anchor-a")
    key = f"base_link->{client.camera}"
    assert key in transforms, sorted(transforms)
    translation = transforms[key]["translation_m"]
    assert len(translation) == 3 and any(abs(value) > 0.0 for value in translation), translation
    assert transforms["provenance"].startswith("mj_forward")


def test_probe_reports_the_contacts_mujoco_found(client):
    client.launch("anchor-a")
    report = client.probe("anchor-a", {"status": "PROBE", "joint_targets_rad": [0.0] * 6})
    assert isinstance(report["contacts"], list), "the driver requires a contacts list"
    assert report["contact_count"] == len(report["contacts"])
    assert report["physics_step"] >= 0


def test_cleanup_is_generation_scoped_and_confirms(client):
    client.launch("anchor-a")
    with pytest.raises(Exception):
        client.cleanup("anchor-a", "")                    # a cleanup without a generation is refused
    receipt = client.cleanup("anchor-a", "generation-p1-1")
    assert receipt["status"] == "CONFIRMED" and receipt["generation"] == "generation-p1-1"
    assert receipt["session_id"] == "session-p1-1"


def test_frame_neck_feedback_and_command_are_real_and_consistent(client):
    client.launch("anchor-a")
    frame = client.frame("anchor-a")
    feedback = client.neck_feedback("anchor-a")
    assert frame["frame_id"] == client.camera and frame["sim_time_s"] >= 0.0
    assert frame["sim_time_s"] == pytest.approx(feedback["sim_time_s"]), "one model, one clock"
    assert isinstance(feedback["safe_observe"], bool)
    receipt = client.command("anchor-a", {"status": "HOLD", "joint_targets_rad": [0.0] * 6})
    assert receipt["accepted"] is True
    assert client.frame("anchor-a")["sim_time_s"] >= frame["sim_time_s"], "a command advances the model"
