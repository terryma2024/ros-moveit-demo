"""Directed tests for the strict, closed stage-one execution inputs.

The parser is the only authority a stage-one run may start from: it must accept
exactly one closed document with a development scope, a fresh run root and every
controlled input sealed by SHA-256, and refuse anything else without side effects.
"""

import hashlib
import json
import os
from pathlib import Path

import pytest

def inputs_module():
    """Lazy access so a missing module is a testcase-body failure, not a collection error."""
    import importlib
    return importlib.import_module('so101_demo.act.head_execution_inputs')


REF_NAMES = ('weights', 'frozen_c', 'camera_geometry', 'development_config', 'local_policy',
             'controller_config', 'mujoco_plugin', 'scene', 'urdf', 'safety_inputs')


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload if type(payload) is bytes else json.dumps(payload).encode())
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_tree(tmp_path, **overrides):
    root = tmp_path / 'evidence'
    root.mkdir(exist_ok=True)
    refs = {}
    for name in REF_NAMES:
        digest = write(tmp_path / 'frozen' / ('%s.bin' % name), b'%s-bytes' % name.encode())
        refs[name] = {'path': str(tmp_path / 'frozen' / ('%s.bin' % name)), 'sha256': digest}
    freeze_path = tmp_path / 'freeze.json'
    freeze_sha = write(freeze_path, {'freeze': 'receipt'})
    document = dict(
        schema_version=1, kind='head_execution_inputs', operation='HEAD_FILE_STAGE1_DEVELOPMENT',
        execution_scope='MUJOCO_DEVELOPMENT_UNQUALIFIED',
        run=dict(run_id='run-001', session_id='session-001', epoch='epoch-001', generation=7),
        evidence_root=str(root), run_root=str(root / 'run-001'),
        freeze_receipt={'path': str(freeze_path), 'sha256': freeze_sha}, refs=refs,
        development_pose=dict(arm_rad=[-0.25, 0.0, 0.6, 0.8, 0.0, 0.8], neck_rad=0.1,
                              cup_xyz=[0.02, -0.28, 0.165]),
        resources=dict(cuda_device='cuda:0', allow_cpu_fallback=False, cpu_allocation=8),
        ros=dict(domain_id=42, environment={'ROS_DOMAIN_ID': '42', 'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp'}))
    document.update(overrides)
    path = tmp_path / 'execution-inputs.json'
    write(path, document)
    return path, document


def test_valid_closed_document_parses_with_full_readback(tmp_path):
    path, document = input_tree(tmp_path)
    inputs = inputs_module().HeadExecutionInputs.parse(path)
    readback = inputs.readback()
    assert readback['execution_scope'] == 'MUJOCO_DEVELOPMENT_UNQUALIFIED'
    assert readback['run'] == document['run']
    assert readback['document_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert readback['document_path'] == str(path)
    assert sorted(readback['refs']) == sorted(REF_NAMES)
    assert readback['refs']['weights'] == document['refs']['weights']
    assert readback['freeze_receipt'] == document['freeze_receipt']
    assert readback['development_pose']['arm_rad'] == [-0.25, 0.0, 0.6, 0.8, 0.0, 0.8]
    assert readback['resources'] == document['resources']
    assert inputs.execution_scope == 'MUJOCO_DEVELOPMENT_UNQUALIFIED'
    assert inputs.run_root == Path(document['run_root'])
    assert inputs.run_root.exists() is False
    assert inputs.evidence_root == Path(document['evidence_root'])


@pytest.mark.parametrize('damage', ['missing_field', 'extra_field', 'unknown_field_phase'])
def test_closed_schema_refuses_missing_unknown_and_legacy_fields(tmp_path, damage):
    path, document = input_tree(tmp_path)
    if damage == 'missing_field':
        document.pop('resources')
    elif damage == 'extra_field':
        document['legacy_phases'] = ['phase1']
    else:
        document['phase'] = 'input_validation'
    write(path, document)
    with pytest.raises(inputs_module().HeadExecutionInputsRefused) as refusal:
        inputs_module().HeadExecutionInputs.parse(path)
    assert refusal.value.code == 'EXECUTION_INPUTS_REFUSED'


@pytest.mark.parametrize('scope', ['HEAD_SEARCH_QUALIFIED', 'PROMOTED', 'mujoco_development_unqualified',
                                   None])
def test_only_the_explicit_development_scope_is_accepted(tmp_path, scope):
    path, document = input_tree(tmp_path)
    document['execution_scope'] = scope
    write(path, document)
    with pytest.raises(inputs_module().HeadExecutionInputsRefused) as refusal:
        inputs_module().HeadExecutionInputs.parse(path)
    assert refusal.value.code in ('EXECUTION_SCOPE_REFUSED', 'EXECUTION_INPUTS_REFUSED')


@pytest.mark.parametrize('damage', ['rewritten_ref', 'rewritten_freeze', 'symlinked_ref',
                                    'relative_path', 'escaped_path', 'missing_ref_file'])
def test_every_sealed_input_is_verified_by_bytes(tmp_path, damage):
    path, document = input_tree(tmp_path)
    if damage == 'rewritten_ref':
        Path(document['refs']['scene']['path']).write_bytes(b'rewritten')
    elif damage == 'rewritten_freeze':
        Path(document['freeze_receipt']['path']).write_bytes(b'rewritten')
    elif damage == 'symlinked_ref':
        target = Path(document['refs']['weights']['path'])
        link = tmp_path / 'frozen' / 'weights-link.bin'
        os.symlink(target, link)
        document['refs']['weights'] = {'path': str(link), 'sha256': document['refs']['weights']['sha256']}
    elif damage == 'relative_path':
        document['refs']['urdf']['path'] = 'frozen/urdf.bin'
    elif damage == 'escaped_path':
        document['refs']['urdf']['path'] = str(tmp_path / 'frozen' / '..' / 'frozen' / 'urdf.bin')
    else:
        Path(document['refs']['safety_inputs']['path']).unlink()
    write(path, document)
    with pytest.raises(inputs_module().HeadExecutionInputsRefused) as refusal:
        inputs_module().HeadExecutionInputs.parse(path)
    assert refusal.value.code == 'EXECUTION_INPUTS_UNSEALED'


@pytest.mark.parametrize('damage', ['existing_run_root', 'run_root_outside_evidence',
                                    'missing_evidence', 'run_root_symlink'])
def test_run_and_evidence_roots_are_fresh_and_contained(tmp_path, damage):
    path, document = input_tree(tmp_path)
    if damage == 'existing_run_root':
        Path(document['run_root']).mkdir()
    elif damage == 'run_root_outside_evidence':
        document['run_root'] = str(tmp_path / 'outside-run')
    elif damage == 'missing_evidence':
        Path(document['evidence_root']).rmdir()
    else:
        outside = tmp_path / 'outside'
        outside.mkdir()
        os.symlink(outside, Path(document['run_root']))
    write(path, document)
    with pytest.raises(inputs_module().HeadExecutionInputsRefused) as refusal:
        inputs_module().HeadExecutionInputs.parse(path)
    assert refusal.value.code in ('EXECUTION_RUN_ROOT_REFUSED', 'EXECUTION_INPUTS_UNSEALED')


@pytest.mark.parametrize('damage', ['arm_length', 'arm_nonfinite', 'neck_missing', 'cup_length'])
def test_development_pose_shape_is_enforced(tmp_path, damage):
    path, document = input_tree(tmp_path)
    pose = document['development_pose']
    if damage == 'arm_length':
        pose['arm_rad'] = pose['arm_rad'][:5]
    elif damage == 'arm_nonfinite':
        pose['arm_rad'] = [float('nan')] + pose['arm_rad'][1:]
    elif damage == 'neck_missing':
        pose.pop('neck_rad')
    else:
        pose['cup_xyz'] = [0.02, -0.28]
    write(path, document)
    with pytest.raises(inputs_module().HeadExecutionInputsRefused) as refusal:
        inputs_module().HeadExecutionInputs.parse(path)
    assert refusal.value.code in ('EXECUTION_INPUTS_REFUSED', 'EXECUTION_INPUTS_UNSEALED')


@pytest.mark.parametrize('device,cpu_fallback', [('cuda', False), ('cpu', False), ('cuda:1', False),
                                                 ('cuda:0', True), ('cuda:0', None)])
def test_cuda_device_and_no_cpu_fallback_are_mandatory(tmp_path, device, cpu_fallback):
    path, document = input_tree(tmp_path)
    document['resources']['cuda_device'] = device
    document['resources']['allow_cpu_fallback'] = cpu_fallback
    write(path, document)
    with pytest.raises(inputs_module().HeadExecutionInputsRefused) as refusal:
        inputs_module().HeadExecutionInputs.parse(path)
    assert refusal.value.code == 'EXECUTION_INPUTS_REFUSED'


@pytest.mark.parametrize('damage', ['domain_range', 'domain_bool', 'empty_environment',
                                    'environment_nonstring', 'ros_extra'])
def test_ros_domain_and_environment_are_declared_exactly(tmp_path, damage):
    path, document = input_tree(tmp_path)
    if damage == 'domain_range':
        document['ros']['domain_id'] = 233
    elif damage == 'domain_bool':
        document['ros']['domain_id'] = True
    elif damage == 'empty_environment':
        document['ros']['environment'] = {}
    elif damage == 'environment_nonstring':
        document['ros']['environment'] = {'ROS_DOMAIN_ID': 42}
    else:
        document['ros']['domain_id_override'] = 7
    write(path, document)
    with pytest.raises(inputs_module().HeadExecutionInputsRefused) as refusal:
        inputs_module().HeadExecutionInputs.parse(path)
    assert refusal.value.code == 'EXECUTION_INPUTS_REFUSED'


def test_run_identity_is_strict(tmp_path):
    for damage in ('run_id', 'session', 'epoch', 'generation'):
        path, document = input_tree(tmp_path)
        if damage == 'run_id':
            document['run']['run_id'] = 'bad id!'
        elif damage == 'session':
            document['run']['session_id'] = ''
        elif damage == 'epoch':
            document['run']['epoch'] = 'x' * 65
        else:
            document['run']['generation'] = 0
        write(path, document)
        with pytest.raises(inputs_module().HeadExecutionInputsRefused) as refusal:
            inputs_module().HeadExecutionInputs.parse(path)
        assert refusal.value.code == 'EXECUTION_INPUTS_REFUSED'


def test_parse_is_read_only_and_creates_no_run_root(tmp_path):
    path, document = input_tree(tmp_path)
    before = sorted(entry.name for entry in tmp_path.rglob('*'))
    inputs_module().HeadExecutionInputs.parse(path)
    after = sorted(entry.name for entry in tmp_path.rglob('*'))
    assert before == after
    assert not Path(document['run_root']).exists()
