"""The rollout wiring config is closed, maps cameras to topics by name, and takes every run bound from the frozen inputs."""

import copy

import pytest
import yaml

from so101_demo.act.rollout_config import (
    camera_topics_for, controller_timing, load_rollout_config, rollout_settings)
from paths import PACKAGE_ROOT

CONFIG_PATH = PACKAGE_ROOT / "config/act/rollout.yaml"
FROZEN = {"teacher_execution_policy": {"values": {
              "execution_deadline_s": 180.0, "state_unavailable_stop_s": 1.0, "state_max_age_s": 0.5,
              "arm_stop_wait_s": 1.0, "arm_stop_velocity_rad_s": 0.002}},
          "teacher_endpoint": {"values": {"tolerances": {"settle_s": 0.5}}}}


def _write(tmp_path, edit):
    document = yaml.safe_load(CONFIG_PATH.read_text())
    edit(document)
    path = tmp_path / "rollout.yaml"
    path.write_text(yaml.safe_dump(document))
    return path


def test_the_shipped_config_loads_and_names_the_shipped_cameras():
    config = load_rollout_config(CONFIG_PATH)
    assert camera_topics_for(config, ("head", "wrist")) == {"head": "/head_camera/color", "wrist": "/wrist_camera/color"}
    assert set(config["undeclared_bundle_cameras"]) == {"head", "wrist"}
    # the rig-v2 camera is a mapping entry, not code
    assert camera_topics_for(config, ("side", "wrist"))["side"] == "/side_camera/color"


def test_a_camera_without_a_topic_is_refused():
    with pytest.raises(ValueError, match="ROLLOUT_CAMERA_TOPIC_UNMAPPED: elbow"):
        camera_topics_for(load_rollout_config(CONFIG_PATH), ("head", "elbow"))


def test_no_motion_means_what_the_training_view_means_by_idle():
    training = yaml.safe_load((PACKAGE_ROOT / "config/act/training-002.yaml").read_text())
    idle = training["training"]["sample_selection"]["idle_threshold_rad"]
    assert load_rollout_config(CONFIG_PATH)["no_motion_threshold_rad"] == idle


@pytest.mark.parametrize("edit", [
    lambda d: d.update(extra=1), lambda d: d.pop("control"), lambda d: d.update(kind="other"),
    lambda d: d["camera_topics"].update(head="head_camera"), lambda d: d["camera_topics"].update(side="/head_camera/color"),
    lambda d: d.update(undeclared_bundle_cameras=["front"]), lambda d: d["control"].update(accept_timeout_s=0.05),
    lambda d: d["control"].update(submit_lead_s=0.2), lambda d: d.update(no_motion_threshold_rad=0),
    lambda d: d["controller_actions"].pop("gripper"), lambda d: d.update(session_ready_wait_s=0),
    lambda d: d.pop("session_ready_wait_s")])
def test_a_damaged_config_is_refused(tmp_path, edit):
    with pytest.raises(ValueError, match="ROLLOUT_CONFIG_INVALID"):
        load_rollout_config(_write(tmp_path, edit))


def test_a_missing_config_is_refused(tmp_path):
    with pytest.raises(ValueError, match="ROLLOUT_CONFIG_MISSING"):
        load_rollout_config(tmp_path / "absent.yaml")


def test_run_bounds_come_from_the_frozen_inputs_and_the_config_only():
    config = load_rollout_config(CONFIG_PATH)
    settings = rollout_settings(FROZEN, config)
    assert (settings.execution_deadline_s, settings.state_unavailable_stop_s, settings.settle_s, settings.stop_wait_s) == (
        180.0, 1.0, 0.5, 1.0)
    assert settings.no_motion_threshold_rad == config["no_motion_threshold_rad"]
    assert settings.ready_wait_s == config["session_ready_wait_s"]
    timing = controller_timing(FROZEN, config)
    assert timing == {"submit_lead_s": config["control"]["submit_lead_s"],
                      "accept_timeout_s": config["control"]["accept_timeout_s"], "stop_timeout_s": 1.0,
                      "stop_velocity_rad_s": 0.002, "max_age_s": 0.5}
    broken = copy.deepcopy(FROZEN)
    del broken["teacher_execution_policy"]["values"]["execution_deadline_s"]
    with pytest.raises(KeyError):
        rollout_settings(broken, config)                      # nothing is defaulted


@pytest.mark.parametrize("profile_file", ["config/act/rig-v1.yaml", "config/act/rig-v2.yaml"])
def test_the_camera_topics_are_the_topics_each_rig_profile_publishes(profile_file):
    """The rollout topic map must agree with the rig the stack composes: a subscription to a topic the rig does not publish
    would leave the executor without observations (rig v2 publishes /side_camera/color, never a head topic)."""
    from so101_demo.act.rig_profile import validate_rig_profile

    profile = validate_rig_profile(yaml.safe_load((PACKAGE_ROOT / profile_file).read_text()))
    config = load_rollout_config(CONFIG_PATH)
    assert camera_topics_for(config, profile.camera_names) == {camera.name: camera.image_topic for camera in profile.cameras}


def test_a_side_wrist_bundle_names_a_rig_without_head_or_neck():
    from so101_demo.act.rig_profile import rig_from_observation

    rig = rig_from_observation(["side", "wrist"], 6)
    assert (rig.rig, rig.has_head, rig.has_neck, rig.state_dim) == ("side-wrist", False, False, 6)
    assert "head" not in rig.camera_names
    assert not any("head" in topic or "neck" in topic for topic in rig.camera_topics)
