"""The closed rollout wiring config (`config/act/rollout.yaml`) and the settings an episode takes from the frozen inputs.

Names and controller timing live in the config; every bound of the run is read from the frozen inputs manifest that the Teacher
and the Recorder read (`load_teacher_frozen_inputs`): nothing is defaulted here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from .rollout_episode import RolloutSettings

_KEYS = frozenset({"kind", "schema_version", "camera_topics", "joint_state_topic", "undeclared_bundle_cameras",
                   "controller_actions", "control", "no_motion_threshold_rad", "world_max_age_s",
                   "session_ready_wait_s"})
#: keys a config may omit; the behaviour without them is the behaviour before they existed
_OPTIONAL_KEYS = frozenset({"joint_limit_clamp_tolerance_rad"})
#: the largest clamp tolerance the loader accepts (rad): a clamp is for small overshoots of a limit, never a way around it
MAX_CLAMP_TOLERANCE_RAD = 0.1


def _topic(value) -> bool:
    return isinstance(value, str) and value.startswith("/") and " " not in value and len(value) > 1


def _positive(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and 0 < value < float("inf")


def load_rollout_config(path) -> dict:
    code = "ROLLOUT_CONFIG_INVALID"
    target = Path(path)
    if not target.is_file():
        raise ValueError("ROLLOUT_CONFIG_MISSING")
    try:
        document = yaml.safe_load(target.read_bytes())
    except yaml.YAMLError as error:
        raise ValueError(code) from error
    if (not isinstance(document, dict) or not _KEYS <= set(document) <= _KEYS | _OPTIONAL_KEYS or document["kind"] != "act_rollout"
            or document["schema_version"] != 1):
        raise ValueError(code)
    topics = document["camera_topics"]
    if (not isinstance(topics, dict) or not topics or not all(isinstance(name, str) and name and _topic(topic)
                                                              for name, topic in topics.items())
            or len(set(topics.values())) != len(topics)):
        raise ValueError(code)
    cameras = document["undeclared_bundle_cameras"]
    if not isinstance(cameras, list) or not cameras or len(set(cameras)) != len(cameras) or not set(cameras) <= set(topics):
        raise ValueError(code)
    actions = document["controller_actions"]
    control = document["control"]
    if (not _topic(document["joint_state_topic"]) or not isinstance(actions, dict) or set(actions) != {"arm", "gripper"}
            or not all(_topic(value) for value in actions.values())
            or not isinstance(control, dict) or set(control) != {"submit_lead_s", "accept_timeout_s"}
            or not all(_positive(value) for value in control.values())
            or not control["accept_timeout_s"] < control["submit_lead_s"] < 0.1
            or not _positive(document["no_motion_threshold_rad"]) or not _positive(document["world_max_age_s"])
            or not _positive(document["session_ready_wait_s"])):
        raise ValueError(code)
    if "joint_limit_clamp_tolerance_rad" in document:
        tolerance = document["joint_limit_clamp_tolerance_rad"]
        if not _positive(tolerance) or tolerance > MAX_CLAMP_TOLERANCE_RAD:
            raise ValueError(code)
    return document


def camera_topics_for(config: dict, cameras) -> dict:
    """The topic of each camera a bundle names, in the bundle's order; a camera with no mapped topic is refused."""

    topics = {}
    for name in cameras:
        topic = config["camera_topics"].get(name)
        if topic is None:
            raise ValueError("ROLLOUT_CAMERA_TOPIC_UNMAPPED: " + str(name))
        topics[name] = topic
    return topics


def controller_timing(frozen: dict, config: dict) -> dict:
    """The execution adapter and controller-port timing: the lead and accept bounds from the config, the stop wait, the stop
    velocity and the feedback age from the frozen Teacher execution policy."""

    execution = frozen["teacher_execution_policy"]["values"]
    return {"submit_lead_s": config["control"]["submit_lead_s"], "accept_timeout_s": config["control"]["accept_timeout_s"],
            "stop_timeout_s": execution["arm_stop_wait_s"], "stop_velocity_rad_s": execution["arm_stop_velocity_rad_s"],
            "max_age_s": execution["state_max_age_s"]}


def rollout_settings(frozen: dict, config: dict) -> RolloutSettings:
    """The episode settings from the frozen Teacher execution and endpoint policies, and the rollout config."""

    execution = frozen["teacher_execution_policy"]["values"]
    endpoint = frozen["teacher_endpoint"]["values"]
    return RolloutSettings(
        execution_deadline_s=execution["execution_deadline_s"],
        state_unavailable_stop_s=execution["state_unavailable_stop_s"],
        settle_s=endpoint["tolerances"]["settle_s"],
        no_motion_threshold_rad=config["no_motion_threshold_rad"],
        stop_wait_s=execution["arm_stop_wait_s"],
        ready_wait_s=config["session_ready_wait_s"],
        joint_limit_clamp_tolerance_rad=config.get("joint_limit_clamp_tolerance_rad"))


#: `control` (the lead and accept bounds) decides whether a reply is late, so it is the outcome-risk class: recorded, never bound.
#: Every other key of the file is logic.
OUTCOME_RISK_KEYS = ("control",)


def logic_document(config: dict) -> dict:
    """The parsed logic keys of a loaded rollout config: what the run identity binds (comments and the order of the file do
    not matter, and the outcome-risk keys are not in it)."""
    return {key: value for key, value in config.items() if key not in OUTCOME_RISK_KEYS}


def logic_sha256(config: dict) -> str:
    return hashlib.sha256(json.dumps(logic_document(config), sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def runtime_values(config: dict) -> dict:
    """The outcome-risk values the run used: recorded for audit, never compared."""
    return {key: config[key] for key in OUTCOME_RISK_KEYS}
