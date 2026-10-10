"""V2 references are native initial-only originals, never rotating-frame masks."""
import json
import copy
import hashlib
from pathlib import Path

import mujoco
import numpy as np
import pytest
import yaml


@pytest.mark.parametrize('index,kind',[(0,'none'),(6,'normal_light'),(7,'amodal_cup')])
def test_fixture_seals_v2_reference_config_and_exact_light_baseline(tmp_path,index,kind):
    from test_act_head_search_campaign_scene import _baseline,_case
    from so101_demo.act.head_search_campaign_scene import prepare_case_fixture
    baseline=_baseline(tmp_path)
    prepared=prepare_case_fixture(_case(index),baseline,tmp_path/'variant')
    render=json.loads(Path(prepared['render_config_ref']['path']).read_text())
    assert render['truth_schema_version']==2
    assert render['initial_reference']['kind']==kind
    plugin=yaml.safe_load(Path(prepared['refs']['mujoco_plugin']['path']).read_text())
    camera=plugin['/**']['ros__parameters']['mujoco_plugins']['mujoco_camera_plugin']['head_camera']
    assert camera['truth_schema_version']==2 and camera['truth_reference_kind']==kind
    original=mujoco.MjModel.from_xml_path(baseline['refs']['scene']['path'])
    model=mujoco.MjModel.from_xml_path(prepared['refs']['scene']['path'])
    reference=render['initial_reference']
    if kind=='normal_light':
        assert camera['truth_baseline_diffuse']==original.light_diffuse.astype(float).ravel().tolist()
        assert camera['truth_baseline_specular']==original.light_specular.astype(float).ravel().tolist()
        assert reference['baseline_diffuse']==camera['truth_baseline_diffuse']
        assert reference['baseline_specular']==camera['truth_baseline_specular']
        np.testing.assert_array_equal(model.light_ambient,original.light_ambient)
    elif kind=='amodal_cup':
        body=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_BODY,'orange_bottle')
        declared=reference['hidden_geom_ids']
        assert declared and declared==camera['truth_hidden_geom_ids']
        assert all(model.geom_bodyid[geom]==body for geom in declared)
        options=mujoco.MjvOption()
        assert all(options.geomgroup[model.geom_group[geom]] and model.geom_rgba[geom,3]>0 for geom in declared)
    else:
        assert reference['baseline_diffuse']==reference['baseline_specular']==reference['hidden_geom_ids']==[]


def _native_envelope():
    from test_act_head_campaign_truth_collector import _frame
    from mujoco_ros2_control_msgs.msg import CameraTruthFrameV2
    from sensor_msgs.msg import Image
    frame=_frame()
    return CameraTruthFrameV2(schema_version=2,original=frame,reference_kind=1,
        reference=Image(header=copy.deepcopy(frame.rgb.header),width=frame.rgb.width,
            height=frame.rgb.height,encoding='rgb8',step=frame.rgb.step,
            data=bytes([100]*len(frame.rgb.data))),scene_light_model_ids=[-1,0],
        reference_light_diffuse=[.8,.8,.8],reference_light_specular=[.2,.2,.2],
        frozen_cameras=[0.]*32,scene_restored=True,initial_render_elapsed_ns=1000000)


def test_recorder_preserves_outer_v2_original_without_reserializing_v1(tmp_path):
    from test_act_head_campaign_truth_collector import _writer
    from so101_demo.adapters.act.head_campaign_truth_collector import FrameOriginalRecorder
    from rclpy.serialization import deserialize_message
    from mujoco_ros2_control_msgs.msg import CameraTruthFrameV2
    writer=_writer(tmp_path)
    try:
        recorder=FrameOriginalRecorder(writer=writer,capture_identity='capture',camera_name='head_camera',
            model_sha256='a'*64,render_config_sha256='b'*64,expected_schema_version=2)
        envelope=_native_envelope()
        saved=recorder.record_frame(envelope,received_utc_ns=1000,received_monotonic_ns=2000)
        assert saved['message_schema_version']==2
    finally:
        writer.finish({'execution':'TEST_ONLY'})
    raw=(tmp_path/'run'/saved['cdr_ref']['path']).read_bytes()
    assert deserialize_message(raw,CameraTruthFrameV2)==envelope
    assert hashlib.sha256(raw).hexdigest()==saved['cdr_ref']['sha256']


@pytest.mark.parametrize('damage',['empty','header','kind','restoration','camera_nan','repeat','late','final'])
def test_v2_reference_violation_is_sticky_and_keeps_rejected_outer_original(tmp_path,damage):
    from test_act_head_campaign_truth_collector import _writer
    from so101_demo.adapters.act.head_campaign_truth_collector import FrameOriginalRecorder
    writer=_writer(tmp_path)
    try:
        recorder=FrameOriginalRecorder(writer=writer,capture_identity='capture',camera_name='head_camera',
            model_sha256='a'*64,render_config_sha256='b'*64,expected_schema_version=2)
        envelope=_native_envelope()
        if damage=='empty':envelope.reference.data=[]
        elif damage=='header':envelope.reference.header.frame_id='other'
        elif damage=='kind':envelope.reference_kind=99
        elif damage=='restoration':envelope.scene_restored=False
        elif damage=='camera_nan':envelope.frozen_cameras[0]=float('nan')
        elif damage=='repeat':envelope.original.frame_sequence=2
        elif damage=='late':envelope.initial_render_elapsed_ns=100000000
        elif damage=='final':envelope.original.record_type=1
        with pytest.raises(ValueError):
            recorder.record_frame(envelope,received_utc_ns=1000,received_monotonic_ns=2000)
        assert recorder.failure
    finally:writer.finish({'execution':'TEST_ONLY'})
    assert json.loads((tmp_path/'run/seal.json').read_text())['artifact_count']==1


def _save(path,raw):
    path.write_bytes(raw)
    return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()}


def test_dynamic_truth_decodes_outer_v2_and_keeps_exact_physics_gate(tmp_path):
    from test_act_head_search_campaign_truth import _inputs
    from so101_demo.act.head_search_campaign_truth import build_frame_truth
    from rclpy.serialization import serialize_message,deserialize_message
    from mujoco_ros2_control_msgs.msg import CameraTruthFrame,CameraTruthFrameV2
    frame_ref,state_refs,fixture_ref=_inputs(tmp_path)
    doc=json.loads(Path(frame_ref['path']).read_text())
    original=deserialize_message(Path(doc['cdr']['path']).read_bytes(),CameraTruthFrame)
    envelope=CameraTruthFrameV2(schema_version=2,original=original)
    doc.update(schema_version=2,kind='paired_camera_truth_v2_original',
               cdr=_save(tmp_path/'v2.cdr',serialize_message(envelope)))
    frame_ref=_save(tmp_path/'v2-frame.json',json.dumps(doc).encode())
    result=build_frame_truth(frame_ref,state_refs,fixture_ref,tmp_path/'truth')
    assert result['status']=='PASS'
    assert result['original_message_schema_version']==2 and result['native_outer_cdr']==doc['cdr']
    with pytest.raises(ValueError):
        build_frame_truth(frame_ref,[],fixture_ref,tmp_path/'no-physics')
    assert not (tmp_path/'no-physics').exists()


def _initial_case(tmp_path,index):
    from test_act_head_search_campaign_scene import _baseline,_case
    from so101_demo.act.head_search_campaign_scene import prepare_case_fixture
    from so101_demo.adapters.act.head_execution_scene import load_scene_safety
    from types import SimpleNamespace
    from rclpy.serialization import serialize_message
    from mujoco_ros2_control_msgs.msg import CameraTruthFrame,CameraTruthFrameV2
    from sensor_msgs.msg import Image,CameraInfo
    from std_msgs.msg import Header
    from builtin_interfaces.msg import Time
    baseline=_baseline(tmp_path)
    prepared=prepare_case_fixture(_case(index),baseline,tmp_path/'variant')
    fixture=prepared['fixture'];truth=fixture['truth_manifest']
    render=json.loads(Path(prepared['render_config_ref']['path']).read_text())
    safety=load_scene_safety(SimpleNamespace(refs={**baseline['refs'],**prepared['refs']}))
    model=safety.checker.model
    qpos=model.qpos0.copy()
    for name,value in zip(('1','2','3','4','5','6','neck_yaw_joint'),
                         (*prepared['development_pose']['arm_rad'],prepared['development_pose']['neck_rad']),strict=True):
        qpos[safety.joint_map[name]['qpos']]=value
    header=Header(stamp=Time(sec=1),frame_id=truth['frame_id'])
    rgb=Image(header=header,width=640,height=480,encoding='rgb8',step=1920,data=bytes([20])*(640*480*3))
    info=CameraInfo(header=header,width=640,height=480)
    cup=next(row for row in truth['instances'] if row['instance_id']=='plastic_cup')['geom_ids'][0]
    visible=np.full((480*640,2),-1,dtype='<i4');visible[:2,:]=[cup,5]
    instances=Image(header=header,width=640,height=480,encoding='32SC2',step=5120,data=visible.tobytes())
    inner=CameraTruthFrame(schema_version=1,record_type=0,capture_identity=truth['capture_identity'],
        frame_sequence=1,camera_name=truth['camera_name'],model_sha256=truth['model_sha256'],
        render_config_sha256=truth['render_config_sha256'],render_phase=render['render_phase'],
        rgb=rgb,camera_info=info,instances=instances,segmentation_ids=list(range(model.ngeom)),
        object_ids=list(range(model.ngeom)),object_types=[5]*model.ngeom,
        generated_count=1,enqueued_count=1,last_enqueued_sequence=1)
    normal=index==6
    if normal:reference=Image(header=header,width=640,height=480,encoding='rgb8',step=1920,data=bytes([80])*(640*480*3))
    else:
        amodal=visible.copy();amodal[:3,:]=[cup,5]
        reference=Image(header=header,width=640,height=480,encoding='32SC2',step=5120,data=amodal.tobytes())
    declared=render['initial_reference']
    lights=[int(i) for i in range(model.nlight) if model.light_active[i]]
    if model.vis.headlight.active:lights.insert(0,-1)
    outer=CameraTruthFrameV2(schema_version=2,original=inner,reference_kind=1 if normal else 2,
        reference=reference,scene_light_model_ids=lights,hidden_geom_ids=declared['hidden_geom_ids'],
        reference_light_diffuse=declared['baseline_diffuse'],reference_light_specular=declared['baseline_specular'],
        frozen_cameras=[0.]*32,scene_restored=True,initial_render_elapsed_ns=1000000)
    reset=dict(paused=True,simulation_step=0,simulation_time_s=1.,reset_epoch=truth['reset_epoch'],
        simulation_session_id=truth['simulation_session_id'],model_sha256=truth['model_sha256'],
        qpos=qpos.tolist(),qvel=[0.]*model.nv)
    doc=dict(schema_version=2,kind='initial_paired_camera_truth_v2_original',
        cdr=_save(tmp_path/'initial.cdr',serialize_message(outer)),
        production_rgb=_save(tmp_path/'rgb.cdr',serialize_message(rgb)),
        production_info=_save(tmp_path/'info.cdr',serialize_message(info)),
        received_utc_ns=1000,received_monotonic_ns=2000,reset_original=reset)
    return prepared,outer,doc


@pytest.mark.parametrize('index',[6,7])
def test_initial_condition_uses_native_reference_and_never_supplies_dynamic_truth(tmp_path,index):
    from so101_demo.act import head_search_campaign_truth as truth
    prepared,outer,doc=_initial_case(tmp_path,index)
    initial=_save(tmp_path/'initial.json',json.dumps(doc).encode())
    result=truth.build_initial_condition_reference(initial,prepared['refs']['scenario_fixture'],tmp_path/'condition')
    assert result['status']=='PASS' and result['native_outer_cdr']==doc['cdr']
    assert result['campaign_admission'] is False and result['dynamic_truth'] is False
    if index==6:assert result['actual_mean_luminance']<result['reference_mean_luminance']
    else:assert result['visible_pixels']==2 and result['amodal_pixels']==3 and 0<result['occluded_fraction']<1


@pytest.mark.parametrize('damage',['moving','source','qvel','zero','full','not_subset','reference_kind'])
def test_initial_condition_conflicts_refuse_without_creating_output(tmp_path,damage):
    from so101_demo.act import head_search_campaign_truth as truth
    from rclpy.serialization import serialize_message
    prepared,outer,doc=_initial_case(tmp_path,7)
    if damage=='moving':doc['reset_original']['simulation_step']=1
    elif damage=='source':doc['reset_original']['simulation_time_s']=1.1
    elif damage=='qvel':doc['reset_original']['qvel'][0]=.01
    elif damage=='zero':outer.reference.data=outer.original.instances.data
    elif damage=='full':outer.original.instances.data=np.full((480*640,2),-1,dtype='<i4').tobytes()
    elif damage=='not_subset':outer.reference.data=np.full((480*640,2),-1,dtype='<i4').tobytes()
    elif damage=='reference_kind':outer.reference_kind=0
    doc['cdr']=_save(tmp_path/'changed.cdr',serialize_message(outer))
    initial=_save(tmp_path/'initial.json',json.dumps(doc).encode())
    with pytest.raises(ValueError):
        truth.build_initial_condition_reference(initial,prepared['refs']['scenario_fixture'],tmp_path/'condition')
    assert not (tmp_path/'condition').exists()
