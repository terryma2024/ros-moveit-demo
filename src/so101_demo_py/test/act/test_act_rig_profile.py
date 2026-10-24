"""The rig profile (`config/act/rig-v*.yaml`, `act/rig_profile.py`) and the components that read it.

Rig v1 is today's rig (head and wrist cameras, neck, 8-wide state) and every v1 value below is the literal the code carried before
profiles existed. Rig v2 (side and wrist cameras, no head, no neck, 6-wide state) must work through the same code paths.
"""

from __future__ import annotations

import copy
import hashlib
import json

import numpy as np
import pytest
import yaml

from paths import PACKAGE_ROOT
from so101_demo.act.rig_profile import (
    DEFAULT_RIG, HEAD_WRIST_RIG, SIDE_WRIST_INDOOR_RIG, SIDE_WRIST_RIG, dump_rig_profile, known_rig, load_rig_profile, load_rig_profile_bytes, rig_from_frame_keys,
    rig_from_frozen, rig_from_observation, stack_state, validate_rig_profile)

CONFIG = PACKAGE_ROOT / "config/act"
RIGS = [pytest.param(HEAD_WRIST_RIG, id="head-wrist"), pytest.param(SIDE_WRIST_RIG, id="side-wrist"),
        pytest.param(SIDE_WRIST_INDOOR_RIG, id="side-wrist-indoor")]


# ---- the profile documents -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("file, name, constant", [("rig-v1.yaml", "head-wrist", HEAD_WRIST_RIG),
                                                  ("rig-v2.yaml", "side-wrist", SIDE_WRIST_RIG),
                                                  ("rig-v3.yaml", "side-wrist-indoor", SIDE_WRIST_INDOOR_RIG)])
def test_the_yaml_files_are_the_constants_the_code_defaults_to(file, name, constant):
    loaded = load_rig_profile(CONFIG / file)
    assert loaded.document == constant.document and loaded.profile_sha256 == constant.profile_sha256
    assert loaded.rig == name and known_rig(name) is constant


def test_head_wrist_rig_is_exactly_the_rig_the_code_used_to_hard_code():
    assert DEFAULT_RIG is HEAD_WRIST_RIG
    assert HEAD_WRIST_RIG.camera_names == ("head", "wrist") and HEAD_WRIST_RIG.frame_keys == ("head_png", "wrist_png")
    assert HEAD_WRIST_RIG.camera_topics == ("/head_camera/color", "/head_camera/camera_info",
                                    "/wrist_camera/color", "/wrist_camera/camera_info")
    assert HEAD_WRIST_RIG.has_head and HEAD_WRIST_RIG.has_neck and HEAD_WRIST_RIG.state_dim == 8
    assert HEAD_WRIST_RIG.decode_table == (("head_png", "head"), ("wrist_png", "wrist"))


def test_side_wrist_rig_has_a_side_camera_and_neither_head_nor_neck():
    assert SIDE_WRIST_RIG.camera_names == ("side", "wrist") and SIDE_WRIST_RIG.frame_keys == ("side_png", "wrist_png")
    assert SIDE_WRIST_RIG.image_topics == ("/side_camera/color", "/wrist_camera/color")
    assert SIDE_WRIST_RIG.info_topics == ("/side_camera/camera_info", "/wrist_camera/camera_info")
    assert not SIDE_WRIST_RIG.has_head and not SIDE_WRIST_RIG.has_neck and SIDE_WRIST_RIG.state_dim == 6 and SIDE_WRIST_RIG.neck_features == ()
    assert HEAD_WRIST_RIG.profile_sha256 != SIDE_WRIST_RIG.profile_sha256


def test_the_side_topic_follows_the_plugin_config_naming_convention():
    plugins = yaml.safe_load((PACKAGE_ROOT / "config/mujoco/act/act_camera_plugins.yaml").read_text())
    cameras = plugins["/**"]["ros__parameters"]
    found = {}
    for key, value in _walk(cameras):
        if key in ("head_camera", "wrist_camera") and isinstance(value, dict):
            found[key] = (value["image_topic"], value["info_topic"], value["frame_name"])
    for camera in HEAD_WRIST_RIG.cameras:
        assert found[f"{camera.name}_camera"] == (camera.image_topic, camera.info_topic, f"{camera.name}_camera_frame")
    # the convention that makes `side` -> `/side_camera/color`
    assert SIDE_WRIST_RIG.camera("side").image_topic == "/side_camera/color"


def _walk(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from _walk(value)


def _mutate(rig, change):
    document = copy.deepcopy(rig.document)
    change(document)
    return document


@pytest.mark.parametrize("change", [
    lambda d: d.update(extra=1),
    lambda d: d.pop("has_neck"),
    lambda d: d.update(kind="other"),
    lambda d: d.update(schema_version=2),
    lambda d: d.update(cameras=[]),
    lambda d: d["cameras"][0].update(image_topic="/elsewhere/color"),
    lambda d: d["cameras"][0].update(frame_key="head.png"),
    lambda d: d["cameras"][0].update(extra="x"),
    lambda d: d["cameras"].append(copy.deepcopy(d["cameras"][0])),
    lambda d: d.update(has_head=False),                      # a head camera with has_head false
    lambda d: d.update(has_neck="yes"),
    lambda d: d["state"].update(state_dim=7),
    lambda d: d["state"].update(neck_features=["neck_sin"]),
    lambda d: d["state"].update(arm_joints=["1", "2"]),
])
def test_the_schema_is_closed(change):
    with pytest.raises(ValueError, match="RIG_PROFILE_INVALID"):
        validate_rig_profile(_mutate(HEAD_WRIST_RIG, change))


def test_a_neck_without_a_head_and_a_neck_feature_without_a_neck_are_refused():
    with pytest.raises(ValueError, match="RIG_PROFILE_INVALID"):
        validate_rig_profile(_mutate(SIDE_WRIST_RIG, lambda d: d.update(has_neck=True)))
    with pytest.raises(ValueError, match="RIG_PROFILE_INVALID"):
        validate_rig_profile(_mutate(SIDE_WRIST_RIG, lambda d: d["state"].update(neck_features=["neck_sin", "neck_cos"], state_dim=8)))


def test_unparsable_and_missing_files_are_refused(tmp_path):
    with pytest.raises(ValueError, match="RIG_PROFILE_INVALID"):
        load_rig_profile_bytes(b"{ not yaml")
    with pytest.raises(ValueError, match="RIG_PROFILE_MISSING"):
        load_rig_profile(tmp_path / "missing.yaml")


@pytest.mark.parametrize("rig", RIGS)
def test_a_profile_round_trips_through_its_bytes(rig):
    assert load_rig_profile_bytes(dump_rig_profile(rig)).document == rig.document


# ---- where the active profile comes from ---------------------------------------------------------------------------------------

def test_a_frozen_manifest_without_a_rig_binding_is_head_wrist_rig_and_one_with_a_binding_is_that_rig():
    assert rig_from_frozen({"roles": {}}) is DEFAULT_RIG
    from so101_demo.act.diagnostic_episode_inputs import rig_profile_binding
    binding = rig_profile_binding(dump_rig_profile(SIDE_WRIST_RIG))
    assert rig_from_frozen({"rig_profile": binding}).document == SIDE_WRIST_RIG.document
    assert binding["policy_sha256"] == SIDE_WRIST_RIG.profile_sha256 and binding["values"] == SIDE_WRIST_RIG.document


def test_a_bundle_observation_names_its_rig_and_an_unknown_set_is_refused():
    assert rig_from_observation(["head", "wrist"], 8) is HEAD_WRIST_RIG
    assert rig_from_observation(["side", "wrist"], 6) is SIDE_WRIST_RIG
    for cameras, width in ((["head", "wrist"], 6), (["side", "wrist"], 8), (["wrist", "head"], 8), (["top"], 6)):
        with pytest.raises(ValueError, match="RIG_PROFILE_UNKNOWN"):
            rig_from_observation(cameras, width)


def test_a_stored_observation_names_its_rig_by_its_frame_keys():
    assert rig_from_frame_keys({"sim_time_s": 0, "state": [], "head_png": "a", "wrist_png": "b"}) is HEAD_WRIST_RIG
    assert rig_from_frame_keys({"state": [], "side_png": "a", "wrist_png": "b"}) is SIDE_WRIST_RIG
    with pytest.raises(ValueError, match="RIG_PROFILE_UNKNOWN"):
        rig_from_frame_keys({"head_png": "a"})


def test_the_state_vector_carries_the_neck_only_when_the_rig_has_one():
    arm = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
    state = stack_state(HEAD_WRIST_RIG, arm, 0.5)
    assert len(state) == 8 and state[6] ** 2 + state[7] ** 2 == pytest.approx(1.0)
    assert stack_state(SIDE_WRIST_RIG, arm) == arm and stack_state(SIDE_WRIST_RIG, arm, 0.5) == arm
    with pytest.raises(ValueError, match="STATE_NECK_REQUIRED"):
        stack_state(HEAD_WRIST_RIG, arm)
    with pytest.raises(ValueError, match="STATE_ARM_WIDTH_INVALID"):
        stack_state(SIDE_WRIST_RIG, arm[:3])


# ---- the preprocessing hash ----------------------------------------------------------------------------------------------------

def test_the_head_wrist_preprocessing_hash_is_the_frozen_one_and_side_wrist_has_its_own():
    from so101_demo.adapters.act.lerobot import OBSERVATION_DECODE_TABLE, PREPROCESSING, preprocessing_for, preprocessing_sha256
    frozen = yaml.safe_load((CONFIG / "training-002.yaml").read_text())["frozen"]["preprocessing_sha256"]
    assert preprocessing_sha256() == frozen == preprocessing_sha256(HEAD_WRIST_RIG)
    assert OBSERVATION_DECODE_TABLE == (("head_png", "head"), ("wrist_png", "wrist"))
    assert PREPROCESSING["observation_decode"] == {"head_png": "head", "wrist_png": "wrist"} and PREPROCESSING["state_dim"] == 8
    v2 = preprocessing_for(SIDE_WRIST_RIG)
    assert v2["observation_decode"] == {"side_png": "side", "wrist_png": "wrist"} and v2["state_dim"] == 6
    assert preprocessing_sha256(SIDE_WRIST_RIG) != frozen
    assert preprocessing_sha256(SIDE_WRIST_RIG) == hashlib.sha256(json.dumps(v2, sort_keys=True, separators=(",", ":"),
                                                                     ensure_ascii=False).encode()).hexdigest()


# ---- the contracts, the synchronizer and the acquisition ------------------------------------------------------------------------

def _frame():
    return np.zeros((480, 640, 3), dtype=np.uint8)


def _observation(rig, state=None):
    state = state if state is not None else stack_state(rig, (0.0,) * 6, 0.0)
    return {"session_id": "s", "attempt_id": "a", "sim_time_s": 1.0, "state": state,
            **{camera: _frame() for camera in rig.camera_names}}


@pytest.mark.parametrize("rig", RIGS)
def test_validate_observation_takes_the_rigs_cameras_and_state_width(rig):
    from so101_demo.act.contracts import ContractError, validate_observation
    assert validate_observation(_observation(rig), rig=rig)["state"] == tuple(stack_state(rig, (0.0,) * 6, 0.0))
    other = SIDE_WRIST_RIG if rig is HEAD_WRIST_RIG else HEAD_WRIST_RIG
    with pytest.raises(ContractError):
        validate_observation(_observation(rig), rig=other)


def test_validate_observation_defaults_to_the_head_wrist_rig_and_still_checks_the_neck_encoding():
    from so101_demo.act.contracts import ContractError, validate_observation
    validate_observation(_observation(HEAD_WRIST_RIG))
    with pytest.raises(ContractError, match="NECK_ENCODING_INVALID"):
        validate_observation(_observation(HEAD_WRIST_RIG, state=(0.0,) * 6 + (1.0, 1.0)))
    with pytest.raises(ContractError):
        validate_observation(_observation(SIDE_WRIST_RIG))


@pytest.mark.parametrize("rig", RIGS)
def test_the_synchronizer_joins_the_rigs_streams(rig):
    from so101_demo.act.synchronizer import RgbObservationSynchronizer
    sync = RgbObservationSynchronizer(max_age_s=0.1, max_skew_s=0.1, rig=rig)
    assert sync.streams == (*rig.camera_names, "arm", *(("neck",) if rig.has_neck else ()))
    sync.reset("s")
    clock = lambda: 1.0                                                     # noqa: E731
    for camera in rig.camera_names:
        sync.push(camera, "s", 1.0, _frame(), received_monotonic_s=clock())
    sync.push("arm", "s", 1.0, [0.0] * 6, received_monotonic_s=clock())
    if rig.has_neck:
        sync.push("neck", "s", 1.0, 0.0, received_monotonic_s=clock())
    else:
        with pytest.raises(ValueError, match="INPUT_SESSION_INVALID"):      # a rig without a neck takes no neck stream
            sync.push("neck", "s", 1.0, 0.0, received_monotonic_s=clock())
    observation, audit = sync.sample_with_audit("s", "a", 1.0)
    assert set(observation) == {"session_id", "attempt_id", "sim_time_s", "state", *rig.camera_names}
    assert len(observation["state"]) == rig.state_dim
    assert set(audit["source_stamps"]) == set(sync.streams) and ("neck_yaw_rad" in audit) == rig.has_neck


def test_the_synchronizer_defaults_to_the_head_wrist_streams():
    from so101_demo.act.synchronizer import RgbObservationSynchronizer
    assert RgbObservationSynchronizer(max_age_s=0.1, max_skew_s=0.1).streams == ("head", "wrist", "arm", "neck")


def test_the_acquisition_minter_refuses_a_camera_the_rig_does_not_have():
    from so101_demo.act.acquisition import AcquisitionMinter
    minted = AcquisitionMinter(SIDE_WRIST_RIG).mint("side", session_id="s", reset_epoch=1, stamp_s=1.0,
                                            received_monotonic_ns=2, pixels=_frame())
    assert minted.camera == "side" and minted.acquisition_id == "s/1/side/1"
    with pytest.raises(ValueError, match="ACQUISITION_CAMERA_INVALID"):
        AcquisitionMinter(SIDE_WRIST_RIG).mint("head", session_id="s", reset_epoch=1, stamp_s=1.0, received_monotonic_ns=2, pixels=_frame())
    with pytest.raises(ValueError, match="ACQUISITION_CAMERA_INVALID"):
        AcquisitionMinter().mint("side", session_id="s", reset_epoch=1, stamp_s=1.0, received_monotonic_ns=2, pixels=_frame())


# ---- the raw recorder topic lists, the scan topics, the delivery and probe topics ------------------------------------------------

def test_the_head_wrist_topic_lists_are_the_literals_they_replaced():
    from so101_demo.act.offline import delivery_diag, probe_trace, raw_recorder, replay, scan
    head_wrist = ("/head_camera/color", "/head_camera/camera_info", "/wrist_camera/color", "/wrist_camera/camera_info")
    assert raw_recorder.CAMERA_TOPICS == head_wrist and delivery_diag.STALL_TOPICS == head_wrist
    assert probe_trace.TRACE_TOPICS == ("/clock", *head_wrist, *probe_trace.STATE_TOPICS, probe_trace.NECK_STATE_TOPIC)
    assert replay.CAMERA_TOPICS == ("/head_camera/color", "/wrist_camera/color")
    assert scan.CAMERA_INFO_TOPICS == ("/head_camera/camera_info", "/wrist_camera/camera_info")
    assert scan.COLOR_TOPICS == {"/head_camera/color": "/head_camera/camera_info", "/wrist_camera/color": "/wrist_camera/camera_info"}
    assert scan.CONTROLLER_STATE_TOPICS == ("/arm_controller/controller_state", "/gripper_controller/controller_state",
                                            "/neck_controller/controller_state")
    assert raw_recorder.TOPICS == (
        "/clock", *head_wrist, "/so101/simulation/evidence", "/so101/simulation/physics_step_chunks",
        "/so101/simulation/robot_contacts", "/so101/simulation/scene_state", "/so101/simulation/joints",
        "/so101/simulation/physics_hazard", "/joint_states", "/arm_controller/controller_state",
        "/gripper_controller/controller_state", "/neck_controller/controller_state", "/so101/teacher/events",
        "/so101/raw/planning_scene_reads")
    assert raw_recorder.CORE_TOPICS == (
        "/clock", "/head_camera/color", "/wrist_camera/color", "/so101/simulation/evidence",
        "/so101/simulation/physics_step_chunks", "/so101/simulation/scene_state", "/joint_states",
        "/arm_controller/controller_state", "/gripper_controller/controller_state",
        "/neck_controller/controller_state", "/head_camera/camera_info", "/wrist_camera/camera_info",
        "/so101/simulation/robot_contacts", "/so101/raw/planning_scene_reads")
    assert raw_recorder.DEEP_RELIABLE == {
        "/so101/simulation/physics_step_chunks": 1000, "/so101/simulation/robot_contacts": 10000,
        "/arm_controller/controller_state": 20000, "/gripper_controller/controller_state": 20000,
        "/neck_controller/controller_state": 20000, "/clock": 20000,
        "/head_camera/camera_info": 100, "/wrist_camera/camera_info": 100,
        "/head_camera/color": 50, "/wrist_camera/color": 50}


def test_a_side_wrist_rig_stack_records_no_head_and_no_neck_topic():
    from so101_demo.act.offline import raw_recorder, scan
    topics = raw_recorder.topics_for(SIDE_WRIST_RIG)
    core = raw_recorder.core_topics_for(SIDE_WRIST_RIG)
    deep = raw_recorder.deep_reliable_for(SIDE_WRIST_RIG)
    for listing in (topics, core, tuple(deep), scan.required_topics(SIDE_WRIST_RIG), scan.controller_state_topics_for(SIDE_WRIST_RIG),
                    scan._decoded_for(SIDE_WRIST_RIG)):
        assert not any("head" in topic or "neck" in topic for topic in listing), listing
    assert "/side_camera/color" in core and "/side_camera/camera_info" in topics and deep["/side_camera/color"] == 50
    assert scan.controller_state_topics_for(SIDE_WRIST_RIG) == ("/arm_controller/controller_state", "/gripper_controller/controller_state")
    assert set(topics) - set(raw_recorder.TOPICS) == {"/side_camera/color", "/side_camera/camera_info"}
    assert raw_recorder.qos_overrides_for(topics, SIDE_WRIST_RIG).keys() == deep.keys()


def test_the_raw_recorder_takes_the_rig_for_its_topics_its_probe_and_its_stall_report():
    from so101_demo.act.offline import probe_trace, raw_recorder
    recorder = raw_recorder.RawRecorder("/tmp/never-started", rig=SIDE_WRIST_RIG)
    assert recorder.topics == raw_recorder.topics_for(SIDE_WRIST_RIG) and recorder.core_topics == raw_recorder.core_topics_for(SIDE_WRIST_RIG)
    assert raw_recorder.RawRecorder("/tmp/never-started").topics == raw_recorder.TOPICS
    neck = (probe_trace.NECK_STATE_TOPIC,) if SIDE_WRIST_RIG.has_neck else ()
    assert probe_trace.trace_topics_for(SIDE_WRIST_RIG) == ("/clock", "/side_camera/color", "/side_camera/camera_info",
                                                    "/wrist_camera/color", "/wrist_camera/camera_info", *probe_trace.STATE_TOPICS, *neck)


def test_the_replay_camera_repair_touches_only_the_rigs_image_topics():
    from so101_demo.act.offline.replay import ReplayNode
    import inspect
    parameter = inspect.signature(ReplayNode.__init__).parameters["camera_topics"]
    assert tuple(parameter.default) == HEAD_WRIST_RIG.image_topics


# ---- the readiness probe -------------------------------------------------------------------------------------------------------

def _readiness(rig, **overrides):
    from so101_demo.cli.act_stack_ready import actions_for, controllers_for, evaluate_act_stack_readiness
    now = 100.0
    worlds = [{"session_id": "s", "reset_epoch": 1, "step": step, "sim_time_s": 10.0 + step * 0.002, "paused": False,
               "received_s": now - 0.1 + step * 0.01} for step in (1, 2)]
    width = 7 if rig.has_neck else 6
    joints = [{"stamp_s": 10.0 + i * 0.001, "received_s": now - 0.2 + i * 0.02, "velocity": (0.0,) * width} for i in range(8)]
    camera = {"width": 640, "height": 480, "encoding": "rgb8", "step": 1920, "byte_count": 640 * 480 * 3,
              "stamp_s": 10.004, "received_s": now - 0.05}
    arguments = dict(session_id="s", ros_domain_id=1, now_s=now, worlds=worlds, joints=joints,
                     rgb={name: dict(camera) for name in rig.camera_names},
                     controllers={name: "active" for name in controllers_for(rig)},
                     services={"/apply_planning_scene": True, "/get_planning_scene": True, "/plan_kinematic_path": True},
                     actions={name: True for name in actions_for(rig)}, rig=rig)
    arguments.update(overrides)
    return evaluate_act_stack_readiness(**arguments)


@pytest.mark.parametrize("rig", RIGS)
def test_readiness_has_one_rgb_check_per_camera_of_the_rig(rig):
    result = _readiness(rig)
    assert result.ready, result
    assert [name for name in result.checks if name.endswith("_rgb")] == [f"{camera}_rgb" for camera in rig.camera_names]
    assert ("neck_controller" in {*_controllers(rig)}) == rig.has_neck


def _controllers(rig):
    from so101_demo.cli.act_stack_ready import controllers_for
    return controllers_for(rig)


def test_readiness_names_the_stale_camera_of_the_rig():
    stale = {"width": 640, "height": 480, "encoding": "rgb8", "step": 1920, "byte_count": 640 * 480 * 3,
             "stamp_s": 1.0, "received_s": 1.0}
    assert _readiness(HEAD_WRIST_RIG, rgb={"head": stale, "wrist": stale}).failure_code == "ACT_STACK_HEAD_RGB_STALE"
    assert _readiness(SIDE_WRIST_RIG, rgb={"side": stale, "wrist": stale}).failure_code == "ACT_STACK_SIDE_RGB_STALE"
    assert _readiness(SIDE_WRIST_RIG, rgb={"side": {"width": 1}, "wrist": stale}).failure_code == "ACT_STACK_SIDE_RGB_INVALID"


def test_a_side_wrist_stack_does_not_wait_for_a_neck_controller_and_a_head_wrist_stack_does():
    assert _readiness(SIDE_WRIST_RIG, controllers={name: "active" for name in _controllers(SIDE_WRIST_RIG)}).ready
    assert _readiness(HEAD_WRIST_RIG, controllers={name: "active" for name in _controllers(SIDE_WRIST_RIG)}).failure_code \
        == "ACT_STACK_CONTROLLER_NOT_ACTIVE"


# ---- the training config and the bundle's observation ---------------------------------------------------------------------------

def _training_document(**observation):
    document = yaml.safe_load((CONFIG / "training-002.yaml").read_text())
    document["observation"].update(observation)
    return document


def test_the_training_config_accepts_each_known_rig_with_its_own_state_width(tmp_path):
    from so101_demo.act.training_config import load_training_config

    def load(document):
        path = tmp_path / "training.yaml"
        path.write_text(yaml.safe_dump(document))
        return load_training_config(path)

    assert load(_training_document())["observation"]["state_dim"] == 8
    assert load(_training_document(cameras=["side", "wrist"], state_dim=6))["observation"]["cameras"] == ["side", "wrist"]
    with pytest.raises(ValueError, match="TRAINING_DIMENSIONS_INVALID"):
        load(_training_document(cameras=["side", "wrist"], state_dim=8))
    with pytest.raises(ValueError, match="TRAINING_DIMENSIONS_INVALID"):
        load(_training_document(state_dim=6))
    with pytest.raises(ValueError, match="TRAINING_CAMERAS_INVALID"):
        load(_training_document(cameras=["top", "wrist"]))


def test_the_trainer_refuses_a_config_whose_frozen_preprocessing_is_another_rigs():
    from so101_demo.adapters.act.lerobot import _require_trainable_config, preprocessing_sha256
    v1 = _training_document()
    _require_trainable_config(v1, "e" * 64)
    v2 = _training_document(cameras=["side", "wrist"], state_dim=6)
    with pytest.raises(ValueError, match="TRAINING_PREPROCESSING_DRIFT"):
        _require_trainable_config(v2, "e" * 64)              # v2 observation with the v1 hash
    v2["frozen"]["preprocessing_sha256"] = preprocessing_sha256(SIDE_WRIST_RIG)
    _require_trainable_config(v2, "e" * 64)


def test_the_policy_runner_and_the_bundle_spec_default_to_the_head_wrist_set_and_read_a_declaration():
    from so101_demo.act.policy import observation_spec
    undeclared = {"normalization": {"state_mean": [0.0] * 8}}
    assert observation_spec(undeclared, legacy_cameras=DEFAULT_RIG.camera_names) == {"cameras": ("head", "wrist"), "state_dim": 8}
    declared = {"normalization": {"state_mean": [0.0] * 6, "observation": SIDE_WRIST_RIG.observation_spec() | {}}}
    declared["normalization"]["observation"] = {"cameras": ["side", "wrist"], "state_dim": 6}
    assert observation_spec(declared) == {"cameras": ("side", "wrist"), "state_dim": 6}


class _Node:
    """A node that only records its subscriptions."""

    def __init__(self):
        self.topics = []

    def create_subscription(self, _type, topic, callback, _qos):
        self.topics.append((topic, callback))
        return object()

    def destroy_subscription(self, _subscription):
        pass


def _adapter(rig):
    from so101_demo.adapters.act.ros_observation import RosObservationAdapter
    from so101_demo.act.synchronizer import RgbObservationSynchronizer
    node = _Node()
    sync = RgbObservationSynchronizer(max_age_s=0.1, max_skew_s=0.1, rig=rig)
    adapter = RosObservationAdapter(node, sync)
    adapter.reset("s", source_floor_s=0.0, reset_epoch=1)
    return adapter, node, sync


@pytest.mark.parametrize("rig", RIGS)
def test_the_observation_adapter_subscribes_to_the_rigs_cameras_and_reads_its_joints(rig):
    from types import SimpleNamespace

    from so101_demo.act.joints import ACT_JOINTS, ARM_JOINTS
    adapter, node, sync = _adapter(rig)
    assert [topic for topic, _ in node.topics] == [*rig.image_topics, "/joint_states"]
    assert adapter.cameras == rig.camera_names and adapter.acquisitions.rig is rig
    names = ACT_JOINTS if rig.has_neck else ARM_JOINTS
    message = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nanosec=0)), name=list(names),
                              position=[0.1] * len(names), velocity=[0.0] * len(names))
    adapter._joints_locked(message, received_monotonic_s=1.0)
    assert adapter.hazard is None and [stream for stream in sync.buffers if sync.buffers[stream]] == ["arm", *(["neck"] * rig.has_neck)]
    assert adapter.seed_pair_refusal(0.0) == "INPUT_COLLECTION_SEED_UNAVAILABLE"      # no camera frame has arrived yet


def test_the_observation_adapter_of_a_neckless_rig_accepts_a_six_joint_state_and_the_default_rig_refuses_it():
    from types import SimpleNamespace

    from so101_demo.act.joints import ARM_JOINTS
    message = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nanosec=0)), name=list(ARM_JOINTS),
                              position=[0.1] * 6, velocity=[0.0] * 6)
    adapter, _, _ = _adapter(SIDE_WRIST_RIG)
    adapter._joints_locked(message, received_monotonic_s=1.0)
    assert adapter.rejected == []
    adapter, _, _ = _adapter(HEAD_WRIST_RIG)
    adapter._joints_locked(message, received_monotonic_s=1.0)
    assert adapter.rejected == ["JOINT_MAPPING_INVALID"]


def test_the_offline_engine_requires_the_sources_of_its_rig():
    from so101_demo.act.offline.engine import REQUIRED_SOURCES, required_sources_for
    assert REQUIRED_SOURCES == ("head", "wrist", "physics", "scene_state", "world", "joint_states")
    assert required_sources_for(SIDE_WRIST_RIG) == ("side", "wrist", "physics", "scene_state", "world", "joint_states")


def test_the_offline_sources_count_the_rigs_cameras():
    from so101_demo.act.offline.sources import OfflineRosSources
    assert OfflineRosSources.rig is DEFAULT_RIG                      # a constructor-less instance (test doubles) is the default rig


def test_the_processor_reads_the_rig_from_the_frozen_inputs(tmp_path):
    from so101_demo.act.diagnostic_episode_inputs import rig_profile_binding
    from so101_demo.act.offline.processor import _inputs_rig
    assert _inputs_rig(tmp_path / "missing-manifest.json") is DEFAULT_RIG     # refused later by the policy load
    from so101_demo.act import frozen_runtime_inputs
    document = {"rig_profile": rig_profile_binding(dump_rig_profile(SIDE_WRIST_RIG))}
    import unittest.mock as mock
    with mock.patch("so101_demo.act.diagnostic_episode_inputs.read_inputs_manifest", return_value=document):
        assert frozen_runtime_inputs.load_frozen_rig(tmp_path / "any.json") == SIDE_WRIST_RIG
        assert _inputs_rig(tmp_path / "any.json") == SIDE_WRIST_RIG


def test_decode_observation_reads_each_rigs_frame_keys(tmp_path):
    from PIL import Image
    from so101_demo.adapters.act.lerobot import decode_observation
    for rig in (HEAD_WRIST_RIG, SIDE_WRIST_RIG):
        stored = {"sim_time_s": 0.0, "state": list(stack_state(rig, (0.0,) * 6, 0.0))}
        for camera in rig.camera_names:
            Image.new("RGB", (4, 3)).save(tmp_path / f"{camera}.png")
            stored[rig.frame_key(camera)] = f"{camera}.png"
        decoded = decode_observation(stored, tmp_path)
        assert set(decoded) == {"sim_time_s", "state", *rig.camera_names}
        assert decoded[rig.camera_names[0]].shape == (3, 4, 3)
        assert set(decode_observation(stored, tmp_path, rig=rig)) == set(decoded)
