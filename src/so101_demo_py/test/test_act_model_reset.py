"""Name-based reset must preserve six-joint ordering and serialize overrides."""

import math
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from so101_demo.act.joints import ARM_JOINTS, ACT_JOINTS, ordered_positions
from so101_demo.backends.mujoco.client import JointResetOverride, joint_override_message


def test_named_mapping_preserves_arm_order():
    values = {name: index / 10 for index, name in enumerate(reversed(ACT_JOINTS))}
    assert ordered_positions(values, ARM_JOINTS) == tuple(values[name] for name in ARM_JOINTS)
    for names in (("missing",), ("1", "1")):
        with pytest.raises(ValueError):
            ordered_positions(values, names)
    with pytest.raises(ValueError):
        ordered_positions({"1": math.nan}, ("1",))


def test_overrides_serialize_positions_and_velocities():
    message = joint_override_message((JointResetOverride("1", .15),
                                      JointResetOverride("neck_yaw_joint", -1.2)))
    assert message.name == ["1", "neck_yaw_joint"]
    assert list(message.position) == [.15, -1.2]
    assert list(message.velocity) == [0., 0.]
    with pytest.raises(ValueError):
        joint_override_message((JointResetOverride("1", 0), JointResetOverride("1", 1)))


@pytest.mark.parametrize("name,position,velocity", [("unknown", 0, 0),
    ("cup_free_joint", 0, 0), ("1", math.nan, 0), ("6", 100, 0),
    ("1", 0, math.inf), ("1", True, 0)])
def test_invalid_joint_override(name, position, velocity):
    with pytest.raises(ValueError):
        JointResetOverride(name, position, velocity)


def test_act_model_joint_sets_and_named_keyframes():
    import mujoco
    assets = Path(__file__).parents[1] / "assets/mujoco/act"
    model = mujoco.MjModel.from_xml_path(str(assets / "scene.xml"))
    urdf = ET.parse(assets / "so101.urdf").getroot()
    assert {element.attrib["name"] for element in urdf.findall("ros2_control/joint")} == set(ACT_JOINTS)
    assert {element.attrib["name"] for element in urdf.findall("joint")
            if element.attrib["type"] != "fixed"} == set(ACT_JOINTS)
    for joint in ACT_JOINTS:
        identifier = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint)
        assert identifier >= 0
        assert model.jnt_type[identifier] == mujoco.mjtJoint.mjJNT_HINGE
    for camera in ("head_camera", "wrist_camera", "task_camera"):
        identifier = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, camera)
        assert tuple(model.cam_resolution[identifier]) == (640, 480)
    cup = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint")
    address = model.jnt_qposadr[cup]
    for index in range(model.nkey):
        assert model.key_qpos[index, address + 2] == .165
        for joint in ACT_JOINTS:
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint)
            assert model.key_qpos[index, model.jnt_qposadr[jid]] == 0.


def test_actual_physics_reset_feedback_and_full_request(monkeypatch):
    from types import SimpleNamespace
    from so101_mujoco_support.msg import ScalarJointEvidence
    from so101_demo.backends.mujoco.client import MujocoRosClient
    class Node:
        def create_client(self, kind, topic): return topic
        def create_subscription(self, kind, topic, callback, qos): return topic
    client=MujocoRosClient(Node(),Node())
    requests=[]
    monkeypatch.setattr(client,"_call",lambda port,request,operation:
                        (requests.append(request),SimpleNamespace(success=True))[1])
    q=(.1,.2,.3,.4,.5,.6,-.4)
    assert client.reset_world("task_start",joint_overrides=tuple(
        JointResetOverride(name,value) for name,value in zip(ACT_JOINTS,q,strict=True)))
    message=requests[-1].state_overrides.joint_states
    assert message.name==list(ACT_JOINTS)
    assert list(message.position)==list(q) and list(message.velocity)==[0.]*7
    actual=ScalarJointEvidence(joint_names=list(reversed(ACT_JOINTS)),
        positions_rad=list(reversed(q)),velocities_rad_s=[0.]*7,
        simulation_session_id="s",reset_epoch=3,simulation_step=0,paused=True)
    actual.header.stamp.sec=10
    client._scalar_joint_callback(actual)
    snapshot=client.reset_joint_snapshot(ACT_JOINTS)
    assert snapshot["positions"]==q and snapshot["velocities"]==(0.,)*7
    assert snapshot["sim_time_s"]==10. and snapshot["callback_count"]==1
    assert snapshot["reset_epoch"]==3 and snapshot["paused"] and snapshot["simulation_session_id"]=="s"


def test_act_launcher_checks_complete_broker_path_before_constructing_stack(monkeypatch):
    from launch import LaunchContext
    from launch.utilities import perform_substitutions
    from launch.actions import DeclareLaunchArgument,OpaqueFunction
    from so101_demo.runtime import launch_composition as launch
    description=launch.build_task_station_launch_description(act_profile=True)
    context=LaunchContext()
    for argument in description.entities:
        if isinstance(argument,DeclareLaunchArgument):
            context.launch_configurations[argument.name]=perform_substitutions(context,argument.default_value)
    context.launch_configurations.update(task_evidence_root='/data/work/so101-evidence/act-data/0917a/r/test',
        act_broker_socket='/'+'a'*107,act_stop_velocity_rad_s='.002',act_max_age_s='1.5')
    constructed=[]
    monkeypatch.setattr(launch,'_mujoco_stack_actions',lambda *args:(constructed.append(True),None)[1])
    opaque=next(a for a in description.entities if isinstance(a,OpaqueFunction))
    with pytest.raises(ValueError,match='SOCKET_PATH_TOO_LONG'):opaque.execute(context)
    assert constructed==[]


def test_act_reset_facade_routes_all_mutations_and_creates_only_readonly_clients(monkeypatch):
    from types import SimpleNamespace
    from so101_demo.backends.mujoco.client import MujocoRosClient
    from so101_demo.adapters.act import leased_action_client as remote
    endpoints=[];calls=[]
    context={'owner':'teacher','session_id':'s','attempt_id':'a','lease_token':'token','broker_socket':'/tmp/no-real-connect'}
    monkeypatch.setattr(remote,'context_from_environment',lambda:context)
    class Connection:
        def request(self,op,scope,**values):
            calls.append((op,values));return {('pause_result' if op=='pause' else 'switch_result' if op=='switch_controllers' else 'finish_result'):{'success':True,'ok':True}}
    monkeypatch.setattr(remote,'connection_for',lambda value:Connection())
    class Node:
        def create_client(self,kind,topic):endpoints.append(topic);return object()
        def create_subscription(self,*args):return None
    client=MujocoRosClient(Node(),Node())
    assert endpoints==['/controller_manager/list_controllers']
    monkeypatch.setattr(client,'_controller_states',lambda:{'arm_controller':'inactive','gripper_controller':'inactive','neck_controller':'inactive'})
    assert client.pause(True)
    assert client.switch_controllers(activate=(),deactivate=('arm_controller','gripper_controller','neck_controller'))
    assert client.finish_reset()
    assert [op for op,_ in calls]==['pause','switch_controllers','finish_reset']


def test_act_invalid_pair_timing_constructs_no_stack(monkeypatch):
    from launch import LaunchContext
    from launch.utilities import perform_substitutions
    from launch.actions import DeclareLaunchArgument,OpaqueFunction
    from so101_demo.runtime import launch_composition as launch
    description=launch.build_task_station_launch_description(act_profile=True);context=LaunchContext()
    for argument in description.entities:
        if isinstance(argument,DeclareLaunchArgument):context.launch_configurations[argument.name]=perform_substitutions(context,argument.default_value)
    context.launch_configurations.update(act_stop_velocity_rad_s='.002',act_max_age_s='1.5',
        act_submit_lead_s='.03',act_accept_timeout_s='.04',act_stop_timeout_s='1',act_permit_ttl_s='.1')
    constructed=[]
    monkeypatch.setattr(launch,'_mujoco_stack_actions',lambda *args:(constructed.append(True),None)[1])
    opaque=next(a for a in description.entities if isinstance(a,OpaqueFunction))
    with pytest.raises(ValueError,match='EXECUTION_TIMING_INVALID'):opaque.execute(context)
    assert constructed==[]
