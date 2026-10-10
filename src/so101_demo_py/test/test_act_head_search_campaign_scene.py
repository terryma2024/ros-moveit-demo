"""Scene conditions, closure and complete reset declarations use actual models."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import mujoco
import numpy as np
import pytest
from paths import PACKAGE_ROOT


def _module():
    return importlib.import_module('so101_demo.act.head_search_campaign_scene')


def _ref(path):
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def _baseline(tmp_path):
    from test_act_head_execution_scene import scene_inputs, register_safety
    inputs, _, safety=scene_inputs(tmp_path)
    register_safety(inputs,safety)
    root=PACKAGE_ROOT
    plugin=root/'config/mujoco/act/mujoco_plugins.yaml'
    inputs.refs['mujoco_plugin']=_ref(plugin)
    geometry={'schema_version':1,'camera_name':'head_camera','image_width':640,'image_height':480,
        'source_digests':{'scene_sha256':inputs.refs['scene']['sha256']},
        'lock_valid_neck_rad':[-6.283175307179587,6.283175307179587],
        'required_search_domain_rad':[-.17559216195018026,.08047101126546086],
        'camera':{'camera_name':'head_camera','width':640,'height':480},
        'in_frame_matrix':{
            'default':{'neck_start_rad':.1,'centre_angle_rad':.23109066719589708},
            'left':{'neck_start_rad':0.,'centre_angle_rad':-.05875582270999715},
            'forward':{'neck_start_rad':0.,'centre_angle_rad':.18822150530477078}},
        'workspace_matrix':{'key_samples':[{'kind':'anchor','anchor':name,'point_m':point}
            for name,point in [('default',[.02,-.28,.165]),('left',[-.08,-.28,.165]),
                               ('forward',[.02,-.36,.165])]]}}
    path=tmp_path/'geometry.json';path.write_text(json.dumps(geometry))
    inputs.refs['camera_geometry']=_ref(path)
    document=copy.deepcopy(inputs.document)
    document['refs']=copy.deepcopy(inputs.refs)
    document['ros']['environment']['SO101_HEAD_CAMERA_FRAME']='head_camera_frame'
    document['event_log_enabled']=True
    return document


def _case(index):
    from so101_demo.act.head_search_campaign import load_cases
    path=PACKAGE_ROOT/'config/act/head-search-scenario-partitions-v1.json'
    return load_cases(json.loads(path.read_text()))[index]


@pytest.mark.parametrize('index',range(10))
def test_fixture_applies_real_condition_and_preserves_camera_and_safety(tmp_path,index):
    from so101_demo.adapters.act.head_execution_scene import load_scene_safety, scene_byte_closure
    baseline=_baseline(tmp_path)
    case=_case(index)
    result=_module().prepare_case_fixture(case,baseline,tmp_path/'variant')
    fixture=result['fixture']
    assert set(fixture)=={'schema_version','case_id','seed','condition_class','anchor',
        'scene_sha256','reset_free_bodies','lighting','truth_manifest','injection'}
    assert fixture['anchor']==case['anchor'] and fixture['case_id']==case['case_id']
    refs={**baseline['refs'],**result['refs']}
    safety=load_scene_safety(SimpleNamespace(refs=refs))
    model=safety.checker.model
    original=mujoco.MjModel.from_xml_path(baseline['refs']['scene']['path'])
    for field in ('cam_pos','cam_quat','cam_bodyid','cam_fovy','cam_resolution'):
        np.testing.assert_array_equal(getattr(model,field),getattr(original,field))
    assert set(fixture['reset_free_bodies'])==set(safety.free_body_map)
    assert all(row['quat_wxyz']==[1.,0.,0.,0.] for row in fixture['reset_free_bodies'].values())
    assert safety.checker.clearance_m==.001 and safety.checker.allowed==set()
    assert json.loads(Path(refs['safety_inputs']['path']).read_text())['byte_closure']==scene_byte_closure(refs['scene']['path'])
    ratio=.35 if case['condition_class']=='low_light' else 1.
    np.testing.assert_allclose(model.light_diffuse,original.light_diffuse*ratio,rtol=1e-6)
    np.testing.assert_allclose(model.light_specular,original.light_specular*ratio,rtol=1e-6)
    np.testing.assert_array_equal(model.light_ambient,original.light_ambient)
    assert fixture['lighting']['scale']==ratio
    active=fixture['lighting']['active_bodies']
    if case['condition_class']=='two_cups':
        assert {'plastic_cup','plastic_cup_b'}<=set(active)
    elif case['condition_class']=='no_cup':
        assert not any(name.startswith('plastic_cup') for name in active)
    else:
        assert 'plastic_cup' in active and 'plastic_cup_b' not in active
    if case['condition_class'] in ('distractor_present','partial_occlusion'):
        assert 'orange_bottle' in active
    for name,row in fixture['reset_free_bodies'].items():
        if name not in active:
            assert row['xyz'][1]==2.
            support=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_GEOM,'campaign_parking_collision')
            assert support>=0 and row['xyz'][2]>.12
    assert fixture['truth_manifest']['model_sha256']==safety.checker.model_sha256
    assert fixture['truth_manifest']['simulation_session_id']==baseline['run']['session_id']
    assert fixture['truth_manifest']['qpos_count']==model.nq
    assert json.loads(Path(result['refs']['scenario_fixture']['path']).read_text())==fixture


def test_same_seed_is_deterministic_and_new_seed_changes_only_legal_appearance(tmp_path):
    baseline=_baseline(tmp_path)
    module=_module()
    a=module.prepare_case_fixture(_case(0),baseline,tmp_path/'a')
    b=module.prepare_case_fixture(_case(0),baseline,tmp_path/'b')
    assert Path(a['refs']['scene']['path']).read_bytes()==Path(b['refs']['scene']['path']).read_bytes()
    assert a['fixture']['reset_free_bodies']==b['fixture']['reset_free_bodies']
    assert a['fixture']['truth_manifest']==b['fixture']['truth_manifest']
    c=module.prepare_case_fixture(_case(30),baseline,tmp_path/'c')
    assert Path(c['refs']['scene']['path']).read_bytes()!=Path(a['refs']['scene']['path']).read_bytes()
    model=mujoco.MjModel.from_xml_path(c['refs']['scene']['path'])
    for name in ('cup_a_material','cup_b_material','bottle_material'):
        identifier=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_MATERIAL,name)
        assert np.all(model.mat_rgba[identifier,:3]>=.1) and np.all(model.mat_rgba[identifier,:3]<=1.)


@pytest.mark.parametrize('damage',['bad_seed','bad_class','bad_anchor','source_digest','closure','policy','camera'])
def test_refuse_unsealed_or_contradictory_baseline_before_creating_variant(tmp_path,damage):
    baseline=_baseline(tmp_path)
    case=_case(0)
    if damage=='bad_seed':case['seed']=True
    elif damage=='bad_class':case['condition_class']='low_light'
    elif damage=='bad_anchor':case['anchor']='guessed'
    elif damage=='source_digest':baseline['refs']['scene']['sha256']='a'*64
    elif damage in ('closure','policy'):
        path=Path(baseline['refs']['safety_inputs']['path'])
        document=json.loads(path.read_text())
        if damage=='closure':document['byte_closure'].pop(next(iter(document['byte_closure'])))
        else:document['allowed_pairs']=[['base','table']]
        path.write_text(json.dumps(document));baseline['refs']['safety_inputs']=_ref(path)
    else:
        path=Path(baseline['refs']['camera_geometry']['path'])
        document=json.loads(path.read_text());document['camera_name']='task_camera'
        path.write_text(json.dumps(document));baseline['refs']['camera_geometry']=_ref(path)
    root=tmp_path/'refused'
    with pytest.raises((ValueError,PermissionError)):
        _module().prepare_case_fixture(case,baseline,root)
    assert not root.exists()


def test_existing_variant_is_never_overwritten(tmp_path):
    baseline=_baseline(tmp_path)
    output=tmp_path/'existing';output.mkdir();(output/'keep').write_bytes(b'original')
    with pytest.raises(ValueError):
        _module().prepare_case_fixture(_case(0),baseline,output)
    assert (output/'keep').read_bytes()==b'original'


@pytest.mark.parametrize('index',[0,4,6])
def test_fixture_geometry_assembles_real_trajectory_guard(tmp_path,index):
    from so101_demo.adapters.act.head_execution_scene import load_scene_safety
    from so101_demo.adapters.act.head_trajectory_guard import HeadTrajectoryGuard
    baseline=_baseline(tmp_path)
    prepared=_module().prepare_case_fixture(_case(index),baseline,tmp_path/'variant',
                                            paired_truth_enabled=False)
    refs={**baseline['refs'],**prepared['refs']}
    safety=load_scene_safety(SimpleNamespace(refs=refs))
    guard=HeadTrajectoryGuard(checker=safety.checker,
        feedback_port=SimpleNamespace(feedback_snapshot=lambda:None),
        scene_observer=SimpleNamespace(model_sha256=safety.checker.model_sha256,
                                       snapshot_with_receipt=lambda:None),
        node=SimpleNamespace(get_clock=lambda:None),
        model_xml_path=refs['scene']['path'],geometry_path=refs['camera_geometry']['path'],
        geometry_sha256=refs['camera_geometry']['sha256'],
        simulation_session_id=baseline['run']['session_id'],reset_epoch=1)
    assert guard.geometry_scene_sha256==refs['scene']['sha256']
    assert guard.safe_interval==tuple(json.loads(Path(baseline['refs']['camera_geometry']['path']).read_text())['lock_valid_neck_rad'])


def test_fixture_refuses_geometry_bound_to_another_baseline(tmp_path):
    baseline=_baseline(tmp_path)
    path=Path(baseline['refs']['camera_geometry']['path'])
    document=json.loads(path.read_text())
    document['source_digests']['scene_sha256']='a'*64
    path.write_text(json.dumps(document))
    baseline['refs']['camera_geometry']=_ref(path)
    with pytest.raises(ValueError,match='GEOMETRY_SCENE'):
        _module().prepare_case_fixture(_case(0),baseline,tmp_path/'variant')
    assert not (tmp_path/'variant').exists()


def test_derived_fixture_geometry_keeps_valid_seal_and_historical_provenance(tmp_path):
    from test_act_head_trajectory_guard import GEOMETRY
    from so101_demo.perception_benchmark.contracts import canonical_sha256
    baseline=_baseline(tmp_path)
    baseline['refs']['camera_geometry']=_ref(GEOMETRY)
    prepared=_module().prepare_case_fixture(_case(6),baseline,tmp_path/'variant',
                                            paired_truth_enabled=False)
    document=json.loads(Path(prepared['refs']['camera_geometry']['path']).read_text())
    assert document['source_digests']['scene_sha256']==prepared['refs']['scene']['sha256']
    assert document['seal_sha256']==canonical_sha256({key:value for key,value in document.items()
                                                     if key!='seal_sha256'})
    assert document['fixture_binding']['baseline_geometry_ref']==baseline['refs']['camera_geometry']
    assert 'Historical baseline' in document['fixture_binding']['rendered_samples_scope']
    original=json.loads(GEOMETRY.read_text())
    for field in ('camera','lock_valid_neck_rad','required_search_domain_rad','workspace_matrix'):
        assert document[field]==original[field]


def test_fixture_does_not_rebind_geometry_when_camera_mount_changes(tmp_path,monkeypatch):
    from xml.etree import ElementTree
    baseline=_baseline(tmp_path)
    module=_module()
    copy_aliases=module._closure_aliases
    def changed_mount(*args,**kwargs):
        aliases=copy_aliases(*args,**kwargs)
        changed=False
        for path,raw in list(aliases.items()):
            if path.suffix!='.xml':
                continue
            tree=ElementTree.fromstring(raw)
            mount=tree.find(".//body[@name='head_mount']")
            if mount is not None:
                mount.set('pos','0.1 0 0')
                aliases[path]=ElementTree.tostring(tree)
                changed=True
        assert changed
        return aliases
    monkeypatch.setattr(module,'_closure_aliases',changed_mount)
    with pytest.raises(ValueError,match='CAMERA_MOUNT_CHANGED'):
        _module().prepare_case_fixture(_case(0),baseline,tmp_path/'variant')
    assert not (tmp_path/'variant'/'camera-geometry.json').exists()
