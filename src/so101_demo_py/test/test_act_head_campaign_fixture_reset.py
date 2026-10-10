"""The existing native ResetWorld covers all declared bodies before Head motion."""
import copy
import json
from types import SimpleNamespace

import mujoco
import pytest

from test_act_head_search_campaign_scene import _baseline, _case, _module


def _prepared(tmp_path):
    from so101_demo.adapters.act.head_execution_scene import load_scene_safety
    baseline=_baseline(tmp_path)
    prepared=_module().prepare_case_fixture(_case(4),baseline,tmp_path/'variant')
    inputs=SimpleNamespace(refs={**baseline['refs'],**prepared['refs']},
        document={**baseline,'development_pose':prepared['development_pose']},run=baseline['run'])
    return inputs,prepared,load_scene_safety(inputs)


def test_optional_fixture_ref_is_verified_by_the_existing_input_parser(tmp_path):
    from test_act_head_execution_inputs import input_tree, write, inputs_module
    path,document=input_tree(tmp_path)
    fixture=tmp_path/'fixture.json'
    digest=write(fixture,{'sealed_test_fixture':True})
    document['refs']['scenario_fixture']={'path':str(fixture),'sha256':digest}
    write(path,document)
    parsed=inputs_module().HeadExecutionInputs.parse(path)
    assert parsed.refs['scenario_fixture']==document['refs']['scenario_fixture']
    fixture.write_text('{}')
    with pytest.raises(inputs_module().HeadExecutionInputsRefused):
        inputs_module().HeadExecutionInputs.parse(path)


def test_same_native_reset_request_contains_all_fixture_body_poses(tmp_path):
    from mujoco_ros2_control_msgs.srv import ResetWorld
    from so101_demo.adapters.act.head_execution_reset import HeadSceneServices
    _,prepared,_=_prepared(tmp_path)
    services=HeadSceneServices.__new__(HeadSceneServices)
    services.types={'reset':ResetWorld}
    requests=[]
    def call(name,request,**kwargs):
        requests.append((name,request,kwargs))
        return SimpleNamespace(success=True)
    services._call=call
    assert services.reset_pose(prepared['development_pose'],fixture=prepared['fixture'],deadline=123.)
    assert len(requests)==1 and requests[0][0]=='reset' and requests[0][2]=={'deadline':123.}
    request=requests[0][1]
    assert request.keyframe==''
    assert request.state_overrides.joint_states.name==['1','2','3','4','5','6','neck_yaw_joint']
    rows={row.name:row for row in request.state_overrides.free_joints}
    assert set(rows)=={'plastic_cup','plastic_cup_b','orange_bottle'}
    for name,expected in prepared['fixture']['reset_free_bodies'].items():
        row=rows[name]
        assert [row.pose.pose.position.x,row.pose.pose.position.y,row.pose.pose.position.z]==expected['xyz']
        assert [row.pose.pose.orientation.w,row.pose.pose.orientation.x,
                row.pose.pose.orientation.y,row.pose.pose.orientation.z]==expected['quat_wxyz']
        assert row.twist.twist.linear.x==row.twist.twist.angular.x==0.


@pytest.mark.parametrize('damage',[None,'second_position','second_rotation','bottle_position',
                                 'velocity','session','epoch','paused','step'])
def test_original_full_state_readback_checks_every_fixture_object_and_reset_identity(tmp_path,damage):
    from so101_demo.adapters.act.head_execution_reset import OwnedHeadScene
    from test_act_head_execution_reset import Node
    inputs,prepared,safety=_prepared(tmp_path)
    scene=OwnedHeadScene(node=Node(),inputs=inputs,safety=safety,max_age_s=.25,
        services=SimpleNamespace(close=lambda:{'closed':True}))
    try:
        data=mujoco.MjData(safety.checker.model)
        pose=prepared['development_pose']
        for name,value in zip(('1','2','3','4','5','6','neck_yaw_joint'),
                (*pose['arm_rad'],pose['neck_rad']),strict=True):
            data.qpos[safety.joint_map[name]['qpos']]=value
        for name,row in prepared['fixture']['reset_free_bodies'].items():
            address=safety.free_body_map[name]['qpos']
            data.qpos[address:address+7]=(*row['xyz'],*row['quat_wxyz'])
        scene._expected_epoch=1
        frame=dict(qpos=data.qpos.tolist(),qvel=data.qvel.tolist(),paused=True,simulation_step=0,
            reset_epoch=1,simulation_session_id=inputs.run['session_id'],
            model_sha256=safety.checker.model_sha256)
        if damage=='second_position':frame['qpos'][safety.free_body_map['plastic_cup_b']['qpos']]+=.01
        elif damage=='second_rotation':frame['qpos'][safety.free_body_map['plastic_cup_b']['qpos']+3]=.99
        elif damage=='bottle_position':frame['qpos'][safety.free_body_map['orange_bottle']['qpos']]+=.01
        elif damage=='velocity':frame['qvel'][safety.free_body_map['orange_bottle']['qvel']]=.1
        elif damage=='session':frame['simulation_session_id']='foreign'
        elif damage=='epoch':frame['reset_epoch']=2
        elif damage=='paused':frame['paused']=False
        elif damage=='step':frame['simulation_step']=1
        if damage:
            with pytest.raises((ValueError,PermissionError)):
                scene._verify_pose(frame)
        else:
            scene._verify_pose(frame)
    finally:
        assert scene.close()['closed']


@pytest.mark.parametrize('damage',['missing_body','extra_body','quat','primary','model','scene','schema'])
def test_fixture_mismatch_refuses_before_reset(tmp_path,damage):
    inputs,prepared,safety=_prepared(tmp_path)
    fixture=copy.deepcopy(prepared['fixture'])
    if damage=='missing_body':fixture['reset_free_bodies'].pop('orange_bottle')
    elif damage=='extra_body':fixture['reset_free_bodies']['unsealed']=fixture['reset_free_bodies']['plastic_cup']
    elif damage=='quat':fixture['reset_free_bodies']['plastic_cup_b']['quat_wxyz']=[0.,0.,0.,0.]
    elif damage=='primary':fixture['reset_free_bodies']['plastic_cup']['xyz'][0]+=.01
    elif damage=='model':fixture['truth_manifest']['model_sha256']='a'*64
    elif damage=='scene':fixture['scene_sha256']='a'*64
    else:fixture['unsafe_callable']='anything'
    with pytest.raises(ValueError):
        _module().validate_case_fixture(fixture,safety=safety,
            scene_sha256=inputs.refs['scene']['sha256'],development_pose=prepared['development_pose'])
