"""Frozen full-scene bytes, semantic identity and coordinate mapping gates."""

import hashlib
import json
from pathlib import Path

import mujoco
import pytest

from test_act_head_execution_composition import build_inputs
from so101_demo.adapters.act.physics import model_sha256


def scene_inputs(tmp_path):
    from so101_demo.adapters.act.head_execution_scene import scene_byte_closure, scene_coordinates
    inputs, policy = build_inputs(tmp_path)
    root = Path(__file__).resolve().parents[1] / 'assets/mujoco/act'
    for name, path in [('scene', root/'head_search_scene.xml'), ('urdf', root/'so101.urdf')]:
        inputs.refs[name] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    model = mujoco.MjModel.from_xml_path(inputs.refs['scene']['path'])
    joints, bodies = scene_coordinates(model)
    document = dict(schema_version=1, kind='head_file_stage1_safety_inputs', mujoco_version='3.12.0',
        expected_model_sha256=model_sha256(model), scene_sha256=inputs.refs['scene']['sha256'],
        urdf_sha256=inputs.refs['urdf']['sha256'], path_step_s=.002, path_clearance_m=.001,
        max_samples=50000, protected_roots=['base'], allowed_pairs=[],
        byte_closure=scene_byte_closure(root/'head_search_scene.xml'),
        joint_map=joints, free_body_map=bodies)
    return inputs, policy, document


def register_safety(inputs, document):
    path = inputs.document_path.parent/'frozen/safety_inputs.json'
    path.write_text(json.dumps(document))
    inputs.refs['safety_inputs'] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def test_scene_loader_checks_real_semantic_model_and_coordinate_maps(tmp_path):
    from so101_demo.adapters.act.head_execution_scene import load_scene_safety
    inputs, _, document = scene_inputs(tmp_path)
    register_safety(inputs, document)
    safety = load_scene_safety(inputs)
    assert safety.checker.model_sha256 == document['expected_model_sha256']
    assert safety.checker.clearance_m == .001 and safety.checker.allowed == set()
    assert safety.joint_map['neck_yaw_joint']['qpos'] == int(safety.checker.neck_qpos)
    assert 'plastic_cup' in safety.free_body_map


@pytest.mark.parametrize('damage', ['clearance', 'sample_step', 'allowed', 'root', 'semantic',
    'scene', 'urdf', 'joint', 'free_body', 'closure_missing', 'closure_digest', 'version'])
def test_frozen_scene_refuses_mismatched_safety_before_guard(tmp_path, damage):
    from so101_demo.adapters.act.head_execution_scene import load_scene_safety
    inputs, _, document = scene_inputs(tmp_path)
    if damage == 'clearance': document['path_clearance_m'] = .002
    elif damage == 'sample_step': document['path_step_s'] = .004
    elif damage == 'allowed': document['allowed_pairs'] = [['a','b']]
    elif damage == 'root': document['protected_roots'] = ['head_mount']
    elif damage == 'semantic': document['expected_model_sha256'] = inputs.refs['scene']['sha256']
    elif damage == 'scene': document['scene_sha256'] = 'a'*64
    elif damage == 'urdf': document['urdf_sha256'] = 'a'*64
    elif damage == 'joint': document['joint_map']['neck_yaw_joint']['qpos'] += 1
    elif damage == 'free_body': document['free_body_map'].pop('plastic_cup')
    elif damage == 'closure_missing': document['byte_closure'].pop(next(iter(document['byte_closure'])))
    elif damage == 'closure_digest': document['byte_closure'][next(iter(document['byte_closure']))]['sha256'] = 'a'*64
    else: document['mujoco_version'] = '3.4.0'
    register_safety(inputs, document)
    with pytest.raises((ValueError, PermissionError)):
        load_scene_safety(inputs)
