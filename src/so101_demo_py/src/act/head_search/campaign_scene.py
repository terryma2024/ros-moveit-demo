"""Freeze deterministic Head-only scene fixtures without starting a simulator."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

from .campaign import _case_valid
from .campaign_truth import _FIXTURE_FIELDS, _TRUTH_FIELDS, _read_ref, _write_new


def _require(condition, reason):
    if not condition:
        raise ValueError('HEAD_CAMPAIGN_FIXTURE_'+reason)


def _json_bytes(value):
    return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()


def _json_ref(reference):
    return json.loads(_read_ref(reference,maximum_bytes=1024*1024))


def _vector(value, length):
    return (type(value) is list and len(value)==length and
            all(type(item) in (int,float) and math.isfinite(item) for item in value))


def _closure_aliases(source, closure):
    """Copy sealed asset bytes to their MJCF lookup names, without output symlinks.

    Existing source assets may link to shared mesh bytes. The safety closure
    hashes their resolved files; MuJoCo still opens the declared lookup names.
    """
    aliases={}
    visited=set()
    def visit(path, *, xml):
        path=Path(os.path.normpath(path))
        resolved=str(path.resolve(strict=True))
        _require(resolved in closure,'CLOSURE_MISSING')
        raw=_read_ref({'path':resolved,'sha256':closure[resolved]['sha256']})
        aliases[path]=raw
        if not xml or path in visited:
            return
        visited.add(path)
        tree=ElementTree.fromstring(raw)
        compiler=tree.find('compiler')
        attrs={} if compiler is None else compiler.attrib
        for element in tree.iter():
            file=element.get('file')
            if file is None:
                continue
            _require(file and not Path(file).is_absolute(),'ASSET_PATH')
            if element.tag=='include':
                visit(path.parent/file,xml=True)
            else:
                _require(element.tag in ('mesh','texture','hfield'),'ASSET_KIND')
                key='meshdir' if element.tag=='mesh' else 'texturedir'
                visit(path.parent/attrs.get(key,attrs.get('assetdir',''))/file,xml=False)
    visit(source,xml=True)
    _require({str(path.resolve(strict=True)) for path in aliases}==set(closure),'CLOSURE_SET')
    return aliases


def validate_case_fixture(fixture, *, safety, scene_sha256, development_pose):
    """Reject omitted objects, promoted truth identities and mismatched reset poses."""
    _require(type(fixture) is dict and set(fixture)==_FIXTURE_FIELDS and
             type(fixture['schema_version']) is int and fixture['schema_version']==1,'SCHEMA')
    case={key:fixture[key] for key in ('case_id','seed','condition_class','anchor')}
    case['expected_attempt_count']=2 if case['condition_class'] in (
        'fast_interruption','reacquire_after_stop') else 1
    _require(_case_valid(case),'CASE')
    _require(fixture['scene_sha256']==scene_sha256,'SCENE')
    truth=fixture['truth_manifest']
    _require(type(truth) is dict and set(truth)==_TRUTH_FIELDS and
             truth['model_sha256']==safety.checker.model_sha256,'MODEL')
    _require(type(fixture['reset_free_bodies']) is dict and
             set(fixture['reset_free_bodies'])==set(safety.free_body_map),'FREE_BODY_SET')
    for row in fixture['reset_free_bodies'].values():
        _require(type(row) is dict and set(row)=={'xyz','quat_wxyz'} and
                 _vector(row['xyz'],3) and _vector(row['quat_wxyz'],4) and
                 abs(sum(v*v for v in row['quat_wxyz'])-1)<1e-12,'FREE_BODY_POSE')
    _require(fixture['reset_free_bodies']['plastic_cup']['xyz']==development_pose['cup_xyz'],
             'PRIMARY_POSE')
    _require(type(truth['reset_epoch']) is int and truth['reset_epoch']==1 and
             type(truth['simulation_session_id']) is str and truth['simulation_session_id'] and
             type(truth['qpos_count']) is int and truth['qpos_count']==safety.checker.model.nq and
             type(truth['qvel_count']) is int and truth['qvel_count']==safety.checker.model.nv,
             'NATIVE_IDENTITY')
    return copy.deepcopy(fixture)


def load_case_fixture(inputs, safety):
    """An absent optional ref preserves the original single-cup reset contract."""
    if 'scenario_fixture' not in inputs.refs:
        return None
    return validate_case_fixture(_json_ref(inputs.refs['scenario_fixture']),safety=safety,
        scene_sha256=inputs.refs['scene']['sha256'],development_pose=inputs.document['development_pose'])


def prepare_case_fixture(case, baseline_inputs, output_root, *, paired_truth_enabled=True):
    """Create a new copy of the sealed scene closure and fixed-policy safety inputs.

    The declared first-reset epoch is checked against the actual native reset
    receipt at runtime. It cannot stand in for that receipt or a frame state.
    """
    import mujoco
    import numpy as np
    import yaml
    from so101_demo.adapters.act.head_execution_scene import (
        load_scene_safety, scene_byte_closure, scene_coordinates)
    from so101_demo.adapters.act.physics import model_sha256

    _require(_case_valid(case),'CASE')
    _require(type(paired_truth_enabled) is bool,'TRUTH_MODE')
    root=Path(output_root)
    _require(root.is_absolute() and '..' not in root.parts and not root.exists() and
             not root.is_symlink() and not any(p.is_symlink() for p in root.parents),'OUTPUT_COLLISION')
    baseline=copy.deepcopy(baseline_inputs)
    refs=baseline['refs']
    for name in ('scene','urdf','safety_inputs','camera_geometry','mujoco_plugin'):
        _read_ref(refs[name])
    original_safety=load_scene_safety(SimpleNamespace(refs=refs))
    original=original_safety.checker.model
    _require(original.nmocap==0 and original.nflex==0 and original.nskin==0,'MODEL_RENDER_STATE')
    geometry=_json_ref(refs['camera_geometry'])
    _require(geometry.get('source_digests',{}).get('scene_sha256')==refs['scene']['sha256'],
             'GEOMETRY_SCENE')
    _require(geometry.get('camera_name')=='head_camera' and
             geometry.get('image_width')==640 and geometry.get('image_height')==480,'CAMERA')
    camera=mujoco.mj_name2id(original,mujoco.mjtObj.mjOBJ_CAMERA,'head_camera')
    _require(camera>=0 and list(original.cam_resolution[camera])==[640,480],'CAMERA')
    matrix=geometry.get('in_frame_matrix',{})
    samples=geometry.get('workspace_matrix',{}).get('key_samples',[])
    points=[row['point_m'] for row in samples if row.get('kind')=='anchor' and
            row.get('anchor')==case['anchor']]
    _require(len(points)==1 and _vector(points[0],3) and case['anchor'] in matrix,'ANCHOR')
    neck=matrix[case['anchor']].get('neck_start_rad')
    _require(type(neck) in (int,float) and math.isfinite(neck),'ANCHOR')
    pose=copy.deepcopy(baseline['development_pose'])
    pose['neck_rad']=neck
    pose['cup_xyz']=copy.deepcopy(points[0])
    _require(_vector(pose['arm_rad'],6),'ARM_POSE')
    source=Path(refs['scene']['path'])
    tree=ElementTree.fromstring(_read_ref(refs['scene']))
    world=tree.find('worldbody')
    _require(world is not None,'WORLD')
    random=np.random.default_rng(case['seed'])
    condition=case['condition_class']
    active=[] if condition=='no_cup' else ['plastic_cup']
    positions={'plastic_cup':[2.,2.,.165], 'plastic_cup_b':[2.2,2.,.165],
               'orange_bottle':[2.4,2.,.19]}
    if active:
        positions['plastic_cup']=copy.deepcopy(points[0])
    if condition=='two_cups':
        active.append('plastic_cup_b')
        offset=.11 if case['anchor']=='left' else -.11
        positions['plastic_cup_b']=[points[0][0]+offset+random.uniform(-.025,.025),
                                  points[0][1]+random.uniform(-.025,.025),.165]
    elif condition=='distractor_present':
        active.append('orange_bottle')
        positions['orange_bottle']=[points[0][0]+.075,points[0][1],.19]
    elif condition=='partial_occlusion':
        active.append('orange_bottle')
        cup=np.array(points[0],dtype=float)
        cup[:2]+=random.uniform(-.025,.025,size=2)
        positions['plastic_cup']=cup.tolist()
        pose['cup_xyz']=cup.tolist()
        data=mujoco.MjData(original)
        for name,value in zip(('1','2','3','4','5','6','neck_yaw_joint'),
                (*pose['arm_rad'],neck),strict=True):
            data.qpos[original_safety.joint_map[name]['qpos']]=value
        mujoco.mj_forward(original,data)
        toward=data.cam_xpos[camera,:2]-cup[:2]
        _require(np.linalg.norm(toward)>0,'OCCLUSION_DIRECTION')
        toward/=np.linalg.norm(toward)
        sideways=np.array([-toward[1],toward[0]])
        bottle=cup[:2]+toward*random.uniform(.055,.105)+sideways*random.uniform(-.025,.025)
        positions['orange_bottle']=[*bottle.tolist(),.19]
    for name,position in positions.items():
        body=world.find("body[@name='"+name+"']")
        _require(body is not None,'FREE_BODY')
        body.set('pos',' '.join(str(v) for v in position))
    pose['cup_xyz']=copy.deepcopy(positions['plastic_cup'])
    support=ElementTree.SubElement(world,'body',name='campaign_parking_support',pos='2.2 2 0.1')
    ElementTree.SubElement(support,'geom',name='campaign_parking_visual',type='box',
        size='0.6 0.12 0.02',group='0',contype='0',conaffinity='0',rgba='0.36 0.24 0.14 1')
    ElementTree.SubElement(support,'geom',name='campaign_parking_collision',type='box',
        size='0.6 0.12 0.02',group='2',contype='1',conaffinity='1',rgba='0 0 0 0')
    scale=.35 if condition=='low_light' else 1.
    lights=[]
    for light in world.iter('light'):
        identifier=mujoco.mj_name2id(original,mujoco.mjtObj.mjOBJ_LIGHT,light.get('name',''))
        _require(identifier>=0,'LIGHT')
        diffuse=(original.light_diffuse[identifier].astype(float)*scale).tolist()
        specular=(original.light_specular[identifier].astype(float)*scale).tolist()
        light.set('diffuse',' '.join(str(v) for v in diffuse))
        light.set('specular',' '.join(str(v) for v in specular))
        lights.append(dict(name=light.get('name'),diffuse=diffuse,specular=specular,
                           ambient=original.light_ambient[identifier].tolist()))
    for material in tree.findall('./asset/material'):
        if material.get('name') in ('cup_a_material','cup_b_material','bottle_material'):
            material.set('rgba',' '.join(str(v) for v in (*random.uniform(.1,1.,size=3),1.)))
    closure=scene_byte_closure(source)
    aliases=_closure_aliases(source,closure)
    common=Path(os.path.commonpath([str(p.parent) for p in aliases]))
    copied={path.relative_to(common):raw for path,raw in aliases.items()}
    # Capture every original byte before any output directory is created.
    copied[source.relative_to(common)]=ElementTree.tostring(tree,encoding='utf-8')+b'\n'
    root.mkdir(parents=True,exist_ok=False)
    for relative,raw in copied.items():
        path=root/'model'/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        _write_new(path,raw)
    scene=root/'model'/source.relative_to(common)
    scene_ref={'path':str(scene),'sha256':hashlib.sha256(scene.read_bytes()).hexdigest()}
    model=mujoco.MjModel.from_xml_path(str(scene))
    semantic=model_sha256(model)
    for field in ('cam_pos','cam_quat','cam_bodyid','cam_fovy','cam_resolution',
                  'cam_intrinsic','cam_sensorsize','cam_mode','cam_targetbodyid'):
        _require(np.array_equal(getattr(model,field),getattr(original,field)),'CAMERA_CHANGED')
    # A fixed local camera transform alone does not establish unchanged world
    # geometry. Check every mounting ancestor and its joint coordinates too.
    body=int(original.cam_bodyid[camera])
    while body:
        for field in ('body_parentid','body_pos','body_quat','body_jntadr','body_jntnum'):
            _require(np.array_equal(getattr(model,field)[body],getattr(original,field)[body]),
                     'CAMERA_MOUNT_CHANGED')
        start=int(original.body_jntadr[body])
        for joint in range(start,start+int(original.body_jntnum[body])):
            for field in ('jnt_type','jnt_pos','jnt_axis','jnt_range','jnt_qposadr'):
                _require(np.array_equal(getattr(model,field)[joint],getattr(original,field)[joint]),
                         'CAMERA_MOUNT_CHANGED')
        body=int(original.body_parentid[body])
    joints,bodies=scene_coordinates(model)
    _require(set(bodies)==set(positions),'FREE_BODY_SET')
    safety=_json_ref(refs['safety_inputs'])
    safety.update(expected_model_sha256=semantic,scene_sha256=scene_ref['sha256'],
        byte_closure=scene_byte_closure(scene),joint_map=joints,free_body_map=bodies)
    safety_ref=_write_new(root/'safety-inputs.json',_json_bytes(safety))
    geometry['source_digests']['scene_sha256']=scene_ref['sha256']
    geometry['fixture_binding']=dict(baseline_geometry_ref=copy.deepcopy(refs['camera_geometry']),
        baseline_scene_sha256=refs['scene']['sha256'],camera_mount_verified_unchanged=True,
        rendered_samples_scope='Historical baseline samples; not fixture pixel-level evidence')
    if 'seal_sha256' in geometry:
        from so101_demo.perception_benchmark.contracts import canonical_sha256
        geometry['seal_sha256']=canonical_sha256({key:value for key,value in geometry.items()
                                                  if key!='seal_sha256'})
    camera_ref=_write_new(root/'camera-geometry.json',_json_bytes(geometry))
    plugins=yaml.safe_load(_read_ref(refs['mujoco_plugin']))
    parameters=plugins['/**']['ros__parameters']
    camera_plugin=parameters['mujoco_plugins']['mujoco_camera_plugin']
    reference_kind={'low_light':'normal_light','partial_occlusion':'amodal_cup'}.get(condition,'none')
    hidden_geoms=[]
    if reference_kind=='amodal_cup':
        occluder=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_BODY,'orange_bottle')
        options=mujoco.MjvOption()
        hidden_geoms=[int(geom) for geom in np.flatnonzero(model.geom_bodyid==occluder)
            if options.geomgroup[model.geom_group[geom]] and model.geom_rgba[geom,3]>0]
        _require(hidden_geoms,'OCCLUDER_VISUALS')
    initial_reference=dict(kind=reference_kind,hidden_geom_ids=hidden_geoms,
        baseline_diffuse=original.light_diffuse.astype(float).ravel().tolist()
                         if reference_kind=='normal_light' else [],
        baseline_specular=original.light_specular.astype(float).ravel().tolist()
                          if reference_kind=='normal_light' else [])
    render_config=dict(schema_version=1,model_sha256=semantic,camera=geometry['camera'],
        camera_name='head_camera',width=640,height=480,
        frame_id=baseline['ros']['environment'].get('SO101_HEAD_CAMERA_FRAME','head_camera_frame'),
        rgb_plugin=camera_plugin,instance_encoding='32SC2',instance_byte_order='little',
        render_phase='frozen_mjv_scene_after_original_rgb',scene_capacity=2000,
        truth_schema_version=2,initial_reference=initial_reference,
        scene_sha256=scene_ref['sha256'],
        development_pose=copy.deepcopy(pose),
        baseline_light_ambient=original.light_ambient.astype(float).ravel().tolist(),
        baseline_headlight=dict(active=int(original.vis.headlight.active),
            ambient=original.vis.headlight.ambient.astype(float).tolist(),
            diffuse=original.vis.headlight.diffuse.astype(float).tolist(),
            specular=original.vis.headlight.specular.astype(float).tolist()),
        physics_step_buffer_capacity=parameters.get('physics_step_buffer_capacity',5000),
        physics_step_chunk_size=parameters.get('physics_step_chunk_size',5),
        physics_step_topic=parameters.get('physics_step_topic','/so101/simulation/physics_step_chunks'))
    render_ref=_write_new(root/'render-config.json',_json_bytes(render_config))
    capture=baseline['run']['run_id']
    _require(type(capture) is str and 0<len(capture)<=64,'CAPTURE_IDENTITY')
    if paired_truth_enabled:
        camera_plugin['head_camera'].update(truth_enabled=True,
            truth_topic='/head_campaign/paired_truth',truth_capture_identity=capture,
            truth_model_sha256=semantic,truth_render_config_sha256=render_ref['sha256'],
            truth_schema_version=2,truth_reference_kind=reference_kind,
            truth_baseline_diffuse=initial_reference['baseline_diffuse'],
            truth_baseline_specular=initial_reference['baseline_specular'],truth_hidden_geom_ids=hidden_geoms)
    else:
        # ROS YAML has no element type for an empty array. Disabled truth needs
        # no reference arrays or identity overrides; omit all unused parameters
        # before rclcpp parses them, even when the baseline enabled truth.
        for key in tuple(camera_plugin['head_camera']):
            if key.startswith('truth_'):
                camera_plugin['head_camera'].pop(key)
        camera_plugin['head_camera']['truth_enabled'] = False
    plugin_ref=_write_new(root/'mujoco-plugins.yaml',yaml.safe_dump(plugins,sort_keys=False).encode())
    instances=[]
    for name,kind in [('plastic_cup','cup'),('plastic_cup_b','cup'),
                      ('orange_bottle','occluder' if condition=='partial_occlusion' else 'distractor'),
                      ('table','support'),('campaign_parking_support','support')]:
        body=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_BODY,name)
        instances.append(dict(instance_id=name,kind=kind,
            geom_ids=np.flatnonzero(model.geom_bodyid==body).tolist()))
    truth=dict(model_sha256=semantic,render_config_sha256=render_ref['sha256'],camera_name='head_camera',
        capture_identity=capture,simulation_session_id=baseline['run']['session_id'],reset_epoch=1,
        width=640,height=480,frame_id=render_config['frame_id'],qpos_count=model.nq,qvel_count=model.nv,
        instances=instances)
    injection={'kind': {'fast_interruption':'camera_loss','reacquire_after_stop':'signal_stop'}.get(condition,'none')}
    fixture=dict(schema_version=1,case_id=case['case_id'],seed=case['seed'],condition_class=condition,
        anchor=case['anchor'],scene_sha256=scene_ref['sha256'],
        reset_free_bodies={name:dict(xyz=xyz,quat_wxyz=[1.,0.,0.,0.]) for name,xyz in positions.items()},
        lighting=dict(scale=scale,lights=lights,active_bodies=active,render_config_ref=render_ref,
            scene_safety_refs=dict(scene=scene_ref,safety_inputs=safety_ref,urdf=refs['urdf'])),
        truth_manifest=truth,injection=injection)
    prepared_refs={**refs,'scene':scene_ref,'camera_geometry':camera_ref,'safety_inputs':safety_ref,
                   'mujoco_plugin':plugin_ref}
    verified=load_scene_safety(SimpleNamespace(refs=prepared_refs))
    validate_case_fixture(fixture,safety=verified,scene_sha256=scene_ref['sha256'],development_pose=pose)
    fixture_ref=_write_new(root/'scenario-fixture.json',_json_bytes(fixture))
    for directory in sorted((p for p in root.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
        descriptor=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
    for directory in (root,root.parent):
        descriptor=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
    return dict(fixture=fixture,development_pose=pose,render_config_ref=render_ref,
        refs=dict(scene=scene_ref,camera_geometry=camera_ref,safety_inputs=safety_ref,
                  mujoco_plugin=plugin_ref,scenario_fixture=fixture_ref))
