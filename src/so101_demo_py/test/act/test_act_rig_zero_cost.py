"""Components that read the rig: a rig without a head or a neck never subscribes to, reads, checks or reports either."""

from collections import deque
import threading
from types import SimpleNamespace

import mujoco
import pytest
from paths import PACKAGE_ROOT

from so101_demo.act.deadline import Deadline
from so101_demo.act.joints import ACT_JOINTS, ARM_JOINTS, act_joints_for
from so101_demo.act.rig_files import rig_model_files
from so101_demo.act.rig_profile import HEAD_WRIST_RIG, SIDE_WRIST_RIG
from so101_demo.act.supervisor import ActSupervisor, evidence_sources, snapshot_keys, validate_snapshot
from so101_demo.adapters.act.pick_place_readback import compiled_qpos_mapping
from so101_demo.adapters.act.physics import model_sha256
from test_act_supervisor import Pair, Physics, prefix, snapshot as head_snapshot


def _side_snapshot(**updates):
    value = head_snapshot()
    value.pop("neck_yaw_rad")
    value["source_times_s"] = {key: 1.0 for key in ("joints", "cup", "contacts", "side", "wrist")}
    value["received_wall_s"] = {key: 10.0 for key in ("joints", "cup", "contacts", "side", "wrist")}
    value.update(updates)
    return value


def test_the_joints_of_an_act_station_are_the_arm_and_only_a_neck_rig_adds_the_neck():
    assert act_joints_for(HEAD_WRIST_RIG) == ACT_JOINTS and act_joints_for(SIDE_WRIST_RIG) == ARM_JOINTS


def test_the_supervisor_of_a_neckless_rig_has_no_neck_yaw_no_neck_drift_and_no_head_source():
    assert "neck_yaw_rad" in snapshot_keys(HEAD_WRIST_RIG) and "neck_yaw_rad" not in snapshot_keys(SIDE_WRIST_RIG)
    assert evidence_sources(HEAD_WRIST_RIG) == {"joints", "cup", "contacts", "head", "wrist"}
    assert evidence_sources(SIDE_WRIST_RIG) == {"joints", "cup", "contacts", "side", "wrist"}
    assert validate_snapshot(_side_snapshot(), SIDE_WRIST_RIG)
    with pytest.raises(ValueError):
        validate_snapshot(head_snapshot(), SIDE_WRIST_RIG)          # a head+wrist snapshot is not a side+wrist one
    with pytest.raises(ValueError):
        validate_snapshot(_side_snapshot(neck_yaw_rad=0.2), SIDE_WRIST_RIG)
    with pytest.raises(ValueError):
        validate_snapshot(_side_snapshot())                         # nor is a side+wrist snapshot a head+wrist one
    pair, physics = Pair(), Physics()
    common = dict(deadline=Deadline(10.0), max_age_s=0.15, max_skew_s=0.12, visibility_occlusion_s=0.5,
                  opening_delta_rad=0.02, monotonic=lambda: 10.0, permit_port=lambda *_: {"approved": True})
    port = ActSupervisor(pair, physics, initial_snapshot=_side_snapshot(), rig=SIDE_WRIST_RIG, **common)
    assert port.neck is None and port.max_drift is None
    assert port.tick(_side_snapshot(), 10.0) == "EMPTY" and pair.reasons == []
    # a neck drift limit has no meaning without a neck, and a neck rig cannot do without one
    with pytest.raises(ValueError, match="SUPERVISOR_CONFIG_INVALID"):
        ActSupervisor(Pair(), Physics(), initial_snapshot=_side_snapshot(), rig=SIDE_WRIST_RIG, max_neck_drift_rad=0.02, **common)
    with pytest.raises(ValueError, match="SUPERVISOR_CONFIG_INVALID"):
        ActSupervisor(Pair(), Physics(), initial_snapshot=head_snapshot(), **common)


def test_the_physical_readback_resolves_the_joints_of_its_rigs_compiled_model():
    version = mujoco.mj_versionString()
    for rig, joints, cup_start in ((HEAD_WRIST_RIG, 7, 7), (SIDE_WRIST_RIG, 6, 6)):
        model = mujoco.MjModel.from_xml_path(str(PACKAGE_ROOT / rig_model_files(rig).scene))
        mapped, cup = compiled_qpos_mapping(model, expected_model_sha256=model_sha256(model), expected_mujoco_version=version,
                                            rig=rig)
        assert len(mapped) == joints and mapped == tuple(range(joints)) and cup == tuple(range(cup_start, cup_start + 7))
    side = mujoco.MjModel.from_xml_path(str(PACKAGE_ROOT / rig_model_files(SIDE_WRIST_RIG).scene))
    with pytest.raises(ValueError, match="PICK_PLACE_VALIDATION_MODEL_JOINT_INVALID"):
        compiled_qpos_mapping(side, expected_model_sha256=model_sha256(side), expected_mujoco_version=version)


class _Node:
    def __init__(self):
        self.topics = []

    def get_clock(self):
        return SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=5_000_000_000))

    def create_subscription(self, _kind, topic, _callback, _qos):
        self.topics.append(topic)
        return topic

    def destroy_subscription(self, _subscription):
        pass


def test_the_controller_reference_port_subscribes_to_the_controllers_of_its_rig():
    from so101_demo.act.offline.sources import ControllerReferencePort, controller_kinds_for

    assert controller_kinds_for(HEAD_WRIST_RIG) == ("arm", "gripper", "neck") and controller_kinds_for(SIDE_WRIST_RIG) == ("arm", "gripper")
    for rig, expected in ((HEAD_WRIST_RIG, ["arm", "gripper", "neck"]), (SIDE_WRIST_RIG, ["arm", "gripper"])):
        node = _Node()
        port = ControllerReferencePort(node, session_id="s", reset_epoch=1, kinds=controller_kinds_for(rig))
        assert node.topics == [f"/{kind}_controller/controller_state" for kind in expected]
        assert list(port.continuity_report()["kinds"]) == expected
    # a port made without naming a rig is the head+wrist one it always was
    node = _Node()
    ControllerReferencePort(node, session_id="s", reset_epoch=1)
    assert len(node.topics) == 3


def test_the_offline_joint_state_record_needs_only_the_joints_of_the_rig():
    from sensor_msgs.msg import JointState
    from so101_demo.act.offline.sources import OfflineRosSources

    def message(names):
        value = JointState(name=list(names), position=[0.1] * len(names), velocity=[0.0] * len(names))
        value.header.stamp.sec = 3
        return value

    def sources(rig):
        item = OfflineRosSources.__new__(OfflineRosSources)
        item.rig, item._counts = rig, {"joint_states": 0}
        item._controller_lock, item._controller_history, item._joint_generation = threading.Lock(), deque(maxlen=8), 0
        return item

    side, head = sources(SIDE_WRIST_RIG), sources(HEAD_WRIST_RIG)
    side._on_joint_state(message(ARM_JOINTS))
    head._on_joint_state(message(ARM_JOINTS))               # no neck in the message: not a row source for a rig with a neck
    assert len(side._controller_history) == 1 and len(head._controller_history) == 0
    head._on_joint_state(message(ACT_JOINTS))
    assert len(head._controller_history) == 1
    assert "neck_yaw_joint" not in side._controller_history[0]["positions"]


def test_native_qc_continuity_counts_neck_gaps_only_for_a_report_that_observed_a_neck():
    from so101_demo.act.episode_qc import verify_reference_continuity
    from so101_demo.adapters.act.controller_reference_observer import ControllerReferenceObserver

    identity, window = {"session_id": "s", "reset_epoch": 1}, {"collection_start_s": 0.0, "label_cutoff_s": 0.3}
    for kinds, expected in ((("arm", "gripper"), False), (("arm", "gripper", "neck"), True)):
        observer = ControllerReferenceObserver(max_frames=100, kinds=kinds)
        observer.reset("s", 1, source_floor_ns=0)
        result = verify_reference_continuity(observer.gap_report(), identity=identity, window=window)
        assert ("neck_gaps" in result) is expected and result["gaps_in_window"] == 0
