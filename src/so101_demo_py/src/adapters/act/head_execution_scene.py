"""Explicit frozen scene safety and full-coordinate identity for Head file runs."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree

import mujoco

from so101_demo.act.head_execution_documents import sealed_bytes
from so101_demo.act.head_execution_inputs import _read_plain
from .physics import model_sha256
from .pick_place_neck_sweep import MujocoNeckSweepChecker


def scene_byte_closure(scene_path):
    """Hash each include and file asset actually referenced by this scene."""
    result, visiting = {}, set()

    def visit(path, *, xml=False):
        path = Path(path).resolve(strict=True)
        if path in visiting:
            raise ValueError('HEAD_SCENE_INCLUDE_CYCLE')
        if str(path) in result:
            return
        raw = _read_plain('scene closure', path)
        result[str(path)] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        if not xml:
            return
        visiting.add(path)
        tree = ElementTree.fromstring(raw)
        compiler = tree.find('compiler')
        attrs = {} if compiler is None else compiler.attrib
        for element in tree.iter():
            file = element.get('file')
            if file is None:
                continue
            if not file or Path(file).is_absolute():
                raise ValueError('HEAD_SCENE_ASSET_PATH_INVALID')
            if element.tag == 'include':
                visit(path.parent/file, xml=True)
            elif element.tag in ('mesh', 'texture', 'hfield'):
                key = 'meshdir' if element.tag == 'mesh' else 'texturedir'
                directory = attrs.get(key, attrs.get('assetdir', ''))
                visit(path.parent/directory/file)
            else:
                raise ValueError('HEAD_SCENE_ASSET_KIND_INVALID')
        visiting.remove(path)

    visit(scene_path, xml=True)
    return dict(sorted(result.items()))


def scene_coordinates(model):
    """Derive all scalar/free joint addresses from the pristine semantic model."""
    joints, bodies = {}, {}
    for index in range(model.njnt):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, index)
        body = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, int(model.jnt_bodyid[index]))
        if not name or not body or name in joints:
            raise ValueError('HEAD_SCENE_COORDINATES_INVALID')
        row = dict(qpos=int(model.jnt_qposadr[index]), qvel=int(model.jnt_dofadr[index]),
                   type=int(model.jnt_type[index]), body=body)
        joints[name] = row
        if row['type'] == int(mujoco.mjtJoint.mjJNT_FREE):
            if body in bodies:
                raise ValueError('HEAD_SCENE_COORDINATES_INVALID')
            bodies[body] = dict(joint=name, qpos=row['qpos'], qvel=row['qvel'])
    return joints, bodies


@dataclass(frozen=True)
class HeadSceneSafety:
    checker: MujocoNeckSweepChecker
    joint_map: dict
    free_body_map: dict
    source_sha256: str


def load_scene_safety(inputs):
    """Verify sealed bytes, exact fixed policy, closure and semantic mappings."""
    raw = sealed_bytes(inputs, 'safety_inputs')
    document = json.loads(raw)
    fixed = dict(schema_version=1, kind='head_file_stage1_safety_inputs',
        mujoco_version='3.12.0', path_step_s=.002, path_clearance_m=.001,
        max_samples=50000, protected_roots=['base'], allowed_pairs=[])
    keys = set(fixed) | {'expected_model_sha256', 'scene_sha256', 'urdf_sha256',
                        'byte_closure', 'joint_map', 'free_body_map'}
    if (type(document) is not dict or set(document) != keys
            or any(type(document[key]) is not type(value) or document[key] != value
                   for key, value in fixed.items())
            or mujoco.mj_versionString() != fixed['mujoco_version']):
        raise ValueError('HEAD_SCENE_SAFETY_POLICY_INVALID')
    for name in ('scene', 'urdf'):
        sealed_bytes(inputs, name)
        if document[name+'_sha256'] != inputs.refs[name]['sha256']:
            raise ValueError('HEAD_SCENE_SOURCE_DIGEST_INVALID')
    path = Path(inputs.refs['scene']['path'])
    closure = scene_byte_closure(path)
    if document['byte_closure'] != closure:
        raise ValueError('HEAD_SCENE_BYTE_CLOSURE_INVALID')
    model = mujoco.MjModel.from_xml_path(str(path))
    semantic = model_sha256(model)
    joints, bodies = scene_coordinates(model)
    if (semantic != document['expected_model_sha256']
            or document['joint_map'] != joints or document['free_body_map'] != bodies
            or any(name not in joints for name in ('1','2','3','4','5','6','neck_yaw_joint'))
            or 'plastic_cup' not in bodies):
        raise ValueError('HEAD_SCENE_SEMANTIC_OR_COORDINATE_INVALID')
    checker = MujocoNeckSweepChecker(path, expected_model_sha256=semantic,
        protected_roots=('base',), allowed_pairs=(), path_step_s=.002,
        path_clearance_m=.001, max_samples=50000)
    # An asset replacement between the pristine and checker loads refuses.
    if scene_byte_closure(path) != closure:
        raise ValueError('HEAD_SCENE_BYTE_CLOSURE_CHANGED')
    return HeadSceneSafety(checker=checker, joint_map=joints, free_body_map=bodies,
                           source_sha256=hashlib.sha256(raw).hexdigest())
