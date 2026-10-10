"""Inventory must bind complete decoded goals and the original raw digest."""

import hashlib
import json
import math
import time
import base64
import uuid

from control_msgs.action import FollowJointTrajectory
from control_msgs.msg import JointTolerance, JointComponentTolerance
from rclpy.serialization import serialize_message
from rosidl_runtime_py.convert import message_to_ordereddict
from trajectory_msgs.msg import JointTrajectoryPoint
import pytest

from so101_demo.adapters.act.head_goal_binding import validate_goal_inventory


def goal():
    message=FollowJointTrajectory.Goal()
    message.trajectory.joint_names=['neck_yaw_joint']
    message.trajectory.header.stamp.sec=20
    message.trajectory.header.frame_id='head-frame'
    point=JointTrajectoryPoint(positions=[.3],velocities=[.02],accelerations=[.04],effort=[.05])
    point.time_from_start.nanosec=100_000_000
    message.trajectory.points=[point]
    message.path_tolerance=[JointTolerance(name='neck_yaw_joint',position=.01,velocity=.02,acceleration=.03)]
    message.goal_tolerance=[JointTolerance(name='neck_yaw_joint',position=.04,velocity=.05,acceleration=.06)]
    message.component_path_tolerance=[JointComponentTolerance(joint_name='neck_yaw_joint',component=1,
        position=.01,velocity=.02,acceleration=.03)]
    message.component_goal_tolerance=[JointComponentTolerance(joint_name='neck_yaw_joint',component=2,
        position=.04,velocity=.05,acceleration=.06)]
    message.goal_time_tolerance.nanosec=20_000_000
    return message


def packet(message=None):
    message=goal() if message is None else message
    payload=serialize_message(message)
    # Match the ordinary JSON containers received from the authenticated wire.
    record=dict(typed_goal=json.loads(json.dumps(message_to_ordereddict(message))),
                payload_sha256=hashlib.sha256(payload).hexdigest())
    return record,payload




def test_every_ros_goal_field_is_owned_and_digest_bound():
    record,payload=packet()
    binding=validate_goal_inventory(record,payload)
    record['typed_goal']['trajectory']['points'][0]['positions'][0]=9.
    assert binding['typed_goal']['trajectory']['points'][0]['positions']==[.3]
    assert binding['payload_sha256']==hashlib.sha256(payload).hexdigest()
    assert 'multi_dof_trajectory' in binding['typed_goal']
    assert 'component_goal_tolerance' in binding['typed_goal']


@pytest.mark.parametrize('field',['header_stamp','header_frame','names','positions','velocities',
    'accelerations','effort','point_time','multi_dof','path','goal','component_path','component_goal','goal_time'])
def test_declared_goal_cannot_omit_or_change_any_decoded_field(field):
    record,payload=packet();description=record['typed_goal']
    if field=='header_stamp':description['trajectory']['header']['stamp']['sec']+=1
    elif field=='header_frame':description['trajectory']['header']['frame_id']='other'
    elif field=='names':description['trajectory']['joint_names']=['other_joint']
    elif field in ('positions','velocities','accelerations','effort'):
        description['trajectory']['points'][0][field][0]+=.1
    elif field=='point_time':description['trajectory']['points'][0]['time_from_start']['nanosec']+=1
    elif field=='multi_dof':description['multi_dof_trajectory']['header']['frame_id']='other'
    elif field in ('path','goal'):description[field+'_tolerance'][0]['position']+=.1
    elif field in ('component_path','component_goal'):description[field+'_tolerance'][0]['component']+=1
    else:description['goal_time_tolerance']['nanosec']+=1
    with pytest.raises(ValueError):validate_goal_inventory(record,payload)


def test_valid_changed_cdr_with_old_digest_is_refused():
    record,_=packet()
    changed=goal();changed.trajectory.points[0].positions=[.4]
    with pytest.raises(ValueError):
        validate_goal_inventory(record,serialize_message(changed))


def test_valid_changed_cdr_with_new_digest_but_old_description_is_refused():
    record,_=packet()
    changed=goal();changed.goal_tolerance[0].acceleration=.07
    payload=serialize_message(changed)
    record['payload_sha256']=hashlib.sha256(payload).hexdigest()
    with pytest.raises(ValueError):validate_goal_inventory(record,payload)


def test_padding_changes_original_digest_even_when_ros_decodes_same_goal():
    record,payload=packet()
    with pytest.raises(ValueError):validate_goal_inventory(record,payload+b'\0'*28)


@pytest.mark.parametrize('field',['velocity','acceleration'])
def test_nonfinite_tolerance_cannot_have_a_matching_binding(field):
    changed=goal();setattr(changed.goal_tolerance[0],field,math.inf)
    record,payload=packet(changed)
    with pytest.raises(ValueError):validate_goal_inventory(record,payload)


def test_expired_deadline_prevents_decoding(monkeypatch):
    from so101_demo.adapters.act import head_goal_binding as module
    def forbidden(*args):raise AssertionError('expired request decoded')
    monkeypatch.setattr(module,'deserialize_message',forbidden)
    record,payload=packet()
    with pytest.raises(TimeoutError):
        validate_goal_inventory(record,payload,deadline=time.monotonic()-1)


def test_decode_crossing_deadline_cannot_return_inventory_binding(monkeypatch):
    from so101_demo.adapters.act import head_goal_binding as module
    original=module.deserialize_message
    def delayed(*args):
        result=original(*args);time.sleep(.02);return result
    monkeypatch.setattr(module,'deserialize_message',delayed)
    record,payload=packet()
    with pytest.raises(TimeoutError):
        validate_goal_inventory(record,payload,deadline=time.monotonic()+.01)


def test_final_copy_crossing_deadline_cannot_return_inventory_binding(monkeypatch):
    from so101_demo.adapters.act import head_goal_binding as module
    record,payload=packet()
    original=module.json.loads
    def delayed(*args):
        result=original(*args);time.sleep(.02);return result
    monkeypatch.setattr(module.json,'loads',delayed)
    with pytest.raises(TimeoutError):
        validate_goal_inventory(record,payload,deadline=time.monotonic()+.01)


@pytest.mark.parametrize('damage',['digest','malformed_cdr','thin_description','non_neck','nonfinite',
    'bool_for_int','nonbytes','oversize'])
def test_invalid_raw_goal_has_no_inventory_binding(damage):
    record,payload=packet()
    if damage=='digest':record['payload_sha256']='0'*64
    elif damage=='malformed_cdr':
        payload=b'bad cdr';record['payload_sha256']=hashlib.sha256(payload).hexdigest()
    elif damage=='thin_description':record['typed_goal']={'trajectory':{'joint_names':['neck_yaw_joint']}}
    elif damage=='non_neck':
        message=goal();message.trajectory.joint_names=['shoulder_pan_joint'];record,payload=packet(message)
    elif damage=='nonfinite':
        message=goal();message.trajectory.points[0].positions=[math.nan];record,payload=packet(message)
    elif damage=='bool_for_int':record['typed_goal']['goal_time_tolerance']['sec']=False
    elif damage=='nonbytes':payload=bytearray(payload)
    else:payload=b'x'*1_048_577
    with pytest.raises(ValueError):validate_goal_inventory(record,payload)


def test_warm_codec_exercises_complete_bind_without_inventory_or_motion(monkeypatch):
    import so101_demo.adapters.act.head_goal_binding as module
    calls=[];actual=module.validate_goal_inventory
    def inspect(record,payload,**kw):
        calls.append((json.loads(json.dumps(record)),payload))
        return actual(record,payload,**kw)
    monkeypatch.setattr(module,'validate_goal_inventory',inspect)
    warm=getattr(module,'warm_goal_binding',lambda:dict(payload_bytes=0))
    receipt=warm()
    assert len(calls)==1 and receipt['native_arm_count']==receipt['sdk_send_count']==0
    record,payload=calls[0]
    assert receipt['payload_bytes']==len(payload)>0
    assert receipt['payload_sha256']==hashlib.sha256(payload).hexdigest()
    assert record['typed_goal']['trajectory']['joint_names']==['neck_yaw_joint']
    assert len(record['typed_goal']['trajectory']['points'])==2
    assert all(row['positions']==[0.] for row in record['typed_goal']['trajectory']['points'])
    assert set(record)=={'typed_goal','payload_sha256'}  # no UUID/generation/native inventory
