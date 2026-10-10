"""Directed tests for the sealed-document loaders.

The runner may not invent a search value: the policy and the eighteen-key
controller mapping must come from the sealed documents, the declared run
identity, the declared pose and the declared ROS environment, and a document
that declares other keys or out-of-range values must refuse the run.
"""

import hashlib
import json
from pathlib import Path

import pytest

from test_act_head_execution_composition import build_inputs
from test_act_head_execution_composition import REF_NAMES
from test_act_head_execution_composition import simulation_policy
from paths import PACKAGE_ROOT


def module():
    import importlib
    return importlib.import_module('so101_demo.act.head_execution_documents')


CONFIG = dict(horizontal_fov_rad=1.2, coarse_step_rad=.5, goal_tolerance_rad=.01,
              center_deadband_px=8., vertical_bounds_px=[100., 400.], min_area_px2=100.,
              min_confidence=.7, max_fine_corrections=3, max_fine_total_rad=.5, max_skew_s=.02,
              max_age_s=.15, settle_velocity_rad_s=.01)


def write_config(tmp_path, document):
    document = _with_development_blocks(document)
    path = tmp_path / 'frozen' / 'development_config.bin'
    payload = json.dumps(document).encode()
    path.write_bytes(payload)
    return {'path': str(path), 'sha256': hashlib.sha256(payload).hexdigest()}


def inputs_with_config(tmp_path, document):
    """A verified inputs document whose development config is the given mapping."""

    inputs, policy = build_inputs(tmp_path)
    inputs.document['refs']['development_config'] = write_config(tmp_path, document)
    inputs.refs['development_config'] = inputs.document['refs']['development_config']
    document_path = inputs.document_path
    document_path.write_bytes(json.dumps(inputs.document).encode())
    import importlib
    module_ = importlib.import_module('so101_demo.act.head_execution_inputs')
    return module_.HeadExecutionInputs.parse(document_path), policy


def test_loaders_read_the_sealed_documents(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    loaded = module().load_policy(inputs)
    assert loaded.readback() == policy.readback()
    assert module().load_development_config(inputs) == CONFIG
    config = module().load_search_config(inputs)
    assert config['attempt_id'] == inputs.run['epoch']
    assert config['session_id'] == inputs.run['session_id']
    assert config['search_start_rad'] == inputs.document['development_pose']['neck_rad']
    assert config['horizontal_fov_rad'] == 1.2
    assert config['vertical_bounds_px'] == (100., 400.)
    assert config['max_fine_corrections'] == 3
    assert config['search_timeout_s'] == loaded.search_timeout_s
    assert config['frame_id'] == 'head_camera_optical_frame'
    assert config['ray_origin_frame_id'] == config['frame_id']
    assert len(config) == 18


def test_sealed_reference_changed_after_input_parse_is_refused(tmp_path):
    inputs, _ = inputs_with_config(tmp_path, CONFIG)
    Path(inputs.refs['development_config']['path']).write_bytes(b'{"changed":true}')
    with pytest.raises(module().HeadExecutionDocumentRefused, match='DIGEST'):
        module().sealed_bytes(inputs, 'development_config')


def test_declared_bounded_domain_reaches_actual_search_config(tmp_path):
    document = _with_development_blocks(CONFIG)
    document['required_search_domain_rad'] = [-.17559216195018026,.08047101126546086]
    document['values']['lock_valid_neck_rad'] = [-6.283175307179587,6.283175307179587]
    inputs, _ = inputs_with_config(tmp_path, document)
    config = module().load_search_config(inputs)
    assert config['required_search_domain_rad'] == tuple(document['required_search_domain_rad'])
    assert config['lock_valid_neck_rad'] == tuple(document['values']['lock_valid_neck_rad'])


def test_default_development_search_needs_only_its_sealed_config(tmp_path):
    inputs, _ = inputs_with_config(tmp_path, CONFIG)
    result = module().resolve_run_search_config(inputs,
        session_id=inputs.run['session_id'],attempt_id=inputs.run['epoch'],
        search_start_rad=inputs.document['development_pose']['neck_rad'])
    assert result == module().load_search_config(inputs)


def test_development_detector_factory_uses_declared_snapshot_without_promoted_report(tmp_path):
    inputs, _ = inputs_with_config(tmp_path, CONFIG)
    snapshot=tmp_path/'snapshot';snapshot.mkdir()
    inputs.document['snapshot_root']=str(snapshot)
    calls=[]
    def builder(binding, *, snapshot_root):
        calls.append((binding,snapshot_root))
        return {'runtime':object()}
    factory=module().build_run_detector_factory(inputs,
        loader=module().development_detector_loader(inputs),builder=builder)
    assert calls==[]
    factory()
    assert len(calls)==1 and calls[0][1]==snapshot
    assert calls[0][0].detector['allow_cpu_fallback'] is False


@pytest.mark.parametrize('tensor_device,predictor_device',[
    ('cuda:0','cuda:0'),('cpu','cuda:0'),('cuda:1','cuda:1'),('cuda:0','cpu')])
def test_actual_cuda_readback_uses_model_parameters_and_predictor(tensor_device,predictor_device):
    from types import SimpleNamespace
    model=SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device=tensor_device)]))
    runtime=SimpleNamespace(detector=SimpleNamespace(_model=SimpleNamespace(
        model=model,predictor=SimpleNamespace(device=predictor_device))))
    if tensor_device==predictor_device=='cuda:0':
        assert module().read_detector_cuda_device(runtime,declared_device='cuda:0')=='cuda:0'
    else:
        with pytest.raises(PermissionError,match='DEVICE'):
            module().read_detector_cuda_device(runtime,declared_device='cuda:0')



def test_the_declared_camera_frame_is_used(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    inputs.document['ros']['environment']['SO101_HEAD_CAMERA_FRAME'] = 'declared_camera_frame'
    document_path = inputs.document_path
    document_path.write_bytes(json.dumps(inputs.document).encode())
    import importlib
    module_ = importlib.import_module('so101_demo.act.head_execution_inputs')
    reloaded = module_.HeadExecutionInputs.parse(document_path)
    config = module().load_search_config(reloaded)
    assert config['frame_id'] == 'declared_camera_frame'
    assert config['ray_origin_frame_id'] == 'declared_camera_frame'


@pytest.mark.parametrize('damage', ['missing_key', 'extra_key', 'wrong_type'])
def test_the_config_key_set_is_closed(tmp_path, damage):
    # the damages target the VALUES block, because that is where the controller fields live in a document of
    # the shape plan line 207 builds (CP-HFP-293); the case's protective purpose is unchanged
    document = _with_development_blocks(dict(CONFIG))
    document['values'] = dict(document['values'])
    if damage == 'missing_key':
        document['values'].pop('max_fine_total_rad')
    elif damage == 'extra_key':
        # extras are the plan's own semantics, so this parametrisation pins tolerance rather than refusal
        document['values']['max_fine_total_rad_invented'] = .5
    else:
        document['values']['coarse_step_rad'] = 'fast'
    inputs, policy = inputs_with_config(tmp_path, document)
    if damage == 'extra_key':
        module().load_search_config(inputs)
        return
    with pytest.raises(module().HeadExecutionDocumentRefused) as refusal:
        module().load_search_config(inputs)
    assert refusal.value.code in ('EXECUTION_SEARCH_CONFIG_REFUSED', 'EXECUTION_DOCUMENT_REFUSED')


@pytest.mark.parametrize('damage', ['zero_step', 'unordered_bounds', 'confidence_above_one', 'fov_zero',
                                    'negative_corrections', 'skew_above_ceiling', 'age_above_policy'])
def test_out_of_range_values_are_refused(tmp_path, damage):
    document = _with_development_blocks(dict(CONFIG))
    document['values'] = dict(document.get('values') or {})
    if damage == 'zero_step':
        document['values']['coarse_step_rad'] = 0.
    elif damage == 'unordered_bounds':
        document['values']['vertical_bounds_px'] = [400., 100.]
    elif damage == 'confidence_above_one':
        document['values']['min_confidence'] = 1.5
    elif damage == 'fov_zero':
        document['values']['horizontal_fov_rad'] = 0.
    elif damage == 'negative_corrections':
        document['values']['max_fine_corrections'] = -1
    elif damage == 'skew_above_ceiling':
        document['values']['max_skew_s'] = .2
    else:
        document['values']['max_age_s'] = 9.
    inputs, policy = inputs_with_config(tmp_path, document)
    with pytest.raises(module().HeadExecutionDocumentRefused) as refusal:
        module().load_search_config(inputs)
    assert refusal.value.code == 'EXECUTION_SEARCH_CONFIG_REFUSED'


def test_a_missing_reference_is_refused(tmp_path):
    inputs, policy = build_inputs(tmp_path)
    document_path = inputs.document_path
    inputs.document['refs'].pop('development_config')
    document_path.write_bytes(json.dumps(
        dict(inputs.document, refs=dict(inputs.document['refs'],
                                        development_config=inputs.refs['development_config']))).encode())
    with pytest.raises(module().HeadExecutionDocumentRefused):
        module().sealed_bytes(inputs, 'local_policy_absent')

def test_the_cross_check_accepts_an_agreeing_binding_config(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    docs = module()
    sealed = docs.load_search_config(inputs)
    assert docs.cross_check_search_config(inputs, dict(sealed)) == sealed


def test_the_cross_check_refuses_a_disagreement(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    docs = module()
    changed = docs.load_search_config(inputs)
    changed['coarse_step_rad'] = changed['coarse_step_rad'] + .25
    with pytest.raises(docs.HeadExecutionDocumentRefused) as refusal:
        docs.cross_check_search_config(inputs, changed)
    assert refusal.value.code == 'EXECUTION_SEARCH_CONFIG_MISMATCH'


def test_the_cross_check_refuses_a_missing_key(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    docs = module()
    partial = docs.load_search_config(inputs)
    partial.pop('max_fine_total_rad')
    with pytest.raises(docs.HeadExecutionDocumentRefused):
        docs.cross_check_search_config(inputs, partial)

def test_require_run_declarations_refuses_when_absent(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    docs = module()
    with pytest.raises(docs.HeadExecutionDocumentRefused) as refusal:
        docs.require_run_declarations(inputs)
    assert refusal.value.code == 'EXECUTION_RUN_DECLARATIONS_ABSENT'


def test_require_run_declarations_returns_the_declared_block(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    docs = module()
    import json as _json
    document = _json.loads(inputs.document_path.read_text())
    document['stop_declaration'] = {'trigger': 'OPERATOR_STOP', 'teardown_timeout_s': 1.}
    document['seal_expectation'] = {'completion': True, 'artifacts': ['completion.json']}
    document['log_capture'] = {'stdout': 'pytest.stdout', 'stderr': 'pytest.stderr'}
    document['fault_stop_probes'] = ['FAULT_PRIMARY']
    inputs.document_path.write_text(_json.dumps(document))
    inputs_module_ = __import__('importlib').import_module('so101_demo.act.head_execution_inputs')
    parsed = inputs_module_.HeadExecutionInputs.parse(inputs.document_path)
    declared = docs.require_run_declarations(parsed)
    assert declared['stop_declaration']['trigger'] == 'OPERATOR_STOP'
    assert declared['seal_expectation']['artifacts'] == ['completion.json']
    assert declared['fault_stop_probes'] == ['FAULT_PRIMARY']


def test_require_run_declarations_propagates_an_invalid_trigger(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    docs = module()
    import json as _json
    document = _json.loads(inputs.document_path.read_text())
    document['stop_declaration'] = {'trigger': 'SOMETHING_ELSE', 'teardown_timeout_s': 1.}
    inputs.document_path.write_text(_json.dumps(document))
    inputs_module_ = __import__('importlib').import_module('so101_demo.act.head_execution_inputs')
    with pytest.raises(Exception):
        docs.require_run_declarations(inputs_module_.HeadExecutionInputs.parse(inputs.document_path))

def test_the_schema_declares_snapshot_root_as_a_directory_field(tmp_path):
    inputs_module_ = __import__('importlib').import_module('so101_demo.act.head_execution_inputs')
    assert 'snapshot_root' in inputs_module_.TOP_LEVEL_FIELDS
    assert 'snapshot_root' in inputs_module_.DECLARATION_FIELDS
    assert 'snapshot_root' not in inputs_module_.REF_NAMES
    assert {'binding', 'report'} <= set(inputs_module_.REF_NAMES)


def test_the_run_declarations_have_their_own_trigger_set():
    inputs_module_ = __import__('importlib').import_module('so101_demo.act.head_execution_inputs')
    assert inputs_module_.RUN_DECLARATION_FIELDS == {'stop_declaration', 'seal_expectation',
                                                     'log_capture', 'fault_stop_probes'}
    assert 'snapshot_root' not in inputs_module_.RUN_DECLARATION_FIELDS


def test_require_binding_material_refuses_when_the_material_is_absent(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    docs = module()
    with pytest.raises(docs.HeadExecutionDocumentRefused) as refusal:
        docs.require_binding_material(inputs)
    assert refusal.value.code == 'EXECUTION_BINDING_MATERIAL_ABSENT'


def _sealed_material(tmp_path, inputs):
    import hashlib as _hashlib
    import json as _json
    document = _json.loads(inputs.document_path.read_text())
    root = tmp_path / 'sealed-binding'
    root.mkdir(exist_ok=True)
    # the report is the document the material parses for its calibration bundle (CP-HFP-319/343), so it is
    # written as real JSON rather than a placeholder; binding keeps the placeholder because only its path and
    # digest are read on this path
    bundle = root / 'calibration-bundle.json'
    bundle.write_bytes(_json.dumps({'kind': 'head_search_calibration_bundle',
                                    'parameters': {'submit_lead_s': {'value': 0.004, 'unit': 's'},
                                                   'stop_latency_s': {'value': 0.07, 'unit': 's'},
                                                   'stop_velocity_rad_s': {'value': 0.041, 'unit': 'rad/s'},
                                                   'max_age_s': {'value': 0.0147, 'unit': 's'}}}).encode())
    report_document = {
        'values': {name: 0.05 for name in
                   ('horizontal_fov_rad', 'coarse_step_rad', 'center_deadband_px', 'vertical_bounds_px',
                    'min_area_px2', 'min_confidence', 'max_fine_corrections', 'max_fine_total_rad',
                    'max_skew_s', 'max_age_s', 'search_timeout_s', 'stop_latency_s', 'stop_velocity_rad_s')},
        'motion': {'goal_tolerance_rad': 0.05, 'settle_velocity_rad_s': 0.05, 'neck_goal_duration_s': 0.5},
        'bundle': {'path': str(bundle)},
    }
    for name in ('binding', 'report'):
        payload = (_json.dumps(report_document) if name == 'report' else _json.dumps({'name': name})).encode()
        path = root / ('%s.json' % name)
        path.write_bytes(payload)
        document['refs'][name] = {'path': str(path), 'sha256': _hashlib.sha256(payload).hexdigest()}
    snapshot = root / 'snapshot'
    snapshot.mkdir(exist_ok=True)
    document['snapshot_root'] = str(snapshot)
    inputs.document_path.write_text(_json.dumps(document))
    inputs_module_ = __import__('importlib').import_module('so101_demo.act.head_execution_inputs')
    return inputs_module_.HeadExecutionInputs.parse(inputs.document_path), snapshot


def test_require_binding_material_returns_the_sealed_paths(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    parsed, snapshot = _sealed_material(tmp_path, inputs)
    material = module().require_binding_material(parsed)
    # the fixture's document declares execution_scope, so the material pairs the development config with
    # itself rather than with the promoted pair (CP-HFP-309/310)
    assert material['binding'].name == 'development_config.bin'
    # the report side is the calibration bundle the receipt names (CP-HFP-317/343)
    assert material['report'].name == 'calibration-bundle.json'
    assert material['snapshot_root'] == snapshot


def test_require_binding_material_refuses_a_snapshot_root_that_is_a_file(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    parsed, snapshot = _sealed_material(tmp_path, inputs)
    import json as _json
    document = _json.loads(inputs.document_path.read_text())
    marker = tmp_path / 'sealed-binding' / 'not-a-directory'
    marker.write_bytes(b'x')
    document['snapshot_root'] = str(marker)
    inputs.document_path.write_text(_json.dumps(document))
    inputs_module_ = __import__('importlib').import_module('so101_demo.act.head_execution_inputs')
    with pytest.raises(Exception):
        module().require_binding_material(inputs_module_.HeadExecutionInputs.parse(inputs.document_path))

def test_the_detector_factory_refuses_without_material(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    docs = module()
    with pytest.raises(docs.HeadExecutionDocumentRefused) as refusal:
        docs.build_run_detector_factory(inputs, loader=lambda *a: object(), builder=lambda *a, **k: object())
    assert refusal.value.code == 'EXECUTION_BINDING_MATERIAL_ABSENT'


def test_the_detector_factory_loads_once_and_builds_on_demand(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    parsed, snapshot = _sealed_material(tmp_path, inputs)
    docs = module()
    calls = {'load': 0, 'build': 0}

    def loader(binding_path, report_path):
        calls['load'] += 1
        assert (binding_path.name == 'development_config.bin'
                and report_path.name == 'calibration-bundle.json')
        return 'BINDING'

    def builder(binding, *, snapshot_root):
        calls['build'] += 1
        assert binding == 'BINDING' and snapshot_root == snapshot
        return {'runtime': 'DETECTOR', 'runtime_device': 'cuda:0'}

    factory = docs.build_run_detector_factory(parsed, loader=loader, builder=builder)
    assert calls == {'load': 1, 'build': 0}, 'the binding is loaded once and the model is not built yet'
    built = factory()
    assert built['runtime_device'] == 'cuda:0' and calls == {'load': 1, 'build': 1}


def test_the_detector_factory_propagates_a_builder_failure(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    parsed, snapshot = _sealed_material(tmp_path, inputs)
    docs = module()

    def builder(binding, *, snapshot_root):
        raise RuntimeError('the model refused to load')

    factory = docs.build_run_detector_factory(parsed, loader=lambda *a: 'B', builder=builder)
    with pytest.raises(RuntimeError, match='refused to load'):
        factory()

class _FakeBinding:
    def __init__(self, config):
        self.config = config
        self.calls = []

    def search_config(self, *, session_id, attempt_id, search_start_rad):
        self.calls.append((session_id, attempt_id, search_start_rad))
        return dict(self.config)


def test_resolve_run_search_config_uses_the_binding_and_cross_checks(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    parsed, snapshot = _sealed_material(tmp_path, inputs)
    docs = module()
    sealed = docs.load_search_config(parsed)
    binding = _FakeBinding(sealed)
    resolved = docs.resolve_run_search_config(parsed, session_id='session-x', attempt_id='attempt-y',
                                              search_start_rad=.25,
                                              binding_loader=lambda *a: binding)
    assert resolved == sealed
    assert binding.calls == [('session-x', 'attempt-y', .25)]


def test_resolve_run_search_config_refuses_a_divergence(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    parsed, snapshot = _sealed_material(tmp_path, inputs)
    docs = module()
    divergent = docs.load_search_config(parsed)
    divergent['coarse_step_rad'] = divergent['coarse_step_rad'] + .5
    with pytest.raises(docs.HeadExecutionDocumentRefused) as refusal:
        docs.resolve_run_search_config(parsed, session_id='s', attempt_id='a', search_start_rad=0.,
                                       binding_loader=lambda *a: _FakeBinding(divergent))
    assert refusal.value.code == 'EXECUTION_SEARCH_CONFIG_MISMATCH'


def test_resolve_run_search_config_refuses_without_material(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    docs = module()
    with pytest.raises(docs.HeadExecutionDocumentRefused) as refusal:
        docs.resolve_run_search_config(inputs, session_id='s', attempt_id='a', search_start_rad=0.,
                                       binding_loader=lambda *a: _FakeBinding({}))
    assert refusal.value.code == 'EXECUTION_BINDING_MATERIAL_ABSENT'

IDENTITY = {'generation': 7, 'incarnation': 'inc-1', 'boot': 'boot-1'}


def test_build_run_local_state_carries_the_sealed_run_identity(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    docs = module()
    state = docs.build_run_local_state(inputs, policy, dict(IDENTITY), now_s=1000.)
    assert state.scope['epoch'] == inputs.run['epoch']
    assert state.scope['session_id'] == inputs.run['session_id']
    assert state.scope['generation'] == inputs.run['generation']
    assert state.scope['controller_identity'] == IDENTITY
    from so101_demo.act.head_evidence_identity import digest
    assert state.scope['policy_sha256'] == digest(policy.readback())


def test_build_run_local_state_pairs_the_policy_with_the_sealed_bytes(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    docs = module()
    foreign = __import__('test_act_head_local_observer', fromlist=['simulation_policy']).simulation_policy(
        search_timeout_s=29.)
    with pytest.raises(docs.HeadExecutionDocumentRefused) as refusal:
        docs.build_run_local_state(inputs, foreign, dict(IDENTITY), now_s=1000.)
    assert refusal.value.code == 'EXECUTION_DOCUMENT_REFUSED'


def test_build_run_local_state_refuses_a_malformed_identity(tmp_path):
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    docs = module()
    for identity in ('not-a-mapping', {}, {'generation': 7, 'incarnation': '', 'boot': 'b'}):
        with pytest.raises(Exception):
            docs.build_run_local_state(inputs, policy, identity, now_s=1000.)

class _Closer:
    def __init__(self, fail=False):
        self.fail = fail
        self.closed = 0

    def close(self, *, timeout_s=1.):
        self.closed += 1
        if self.fail:
            raise RuntimeError('close failed')
        return {'closed': True}


class _Exposure:
    def __init__(self, fail=False):
        self.fail = fail
        self.frozen = 0

    def freeze_retirement(self):
        self.frozen += 1
        if self.fail:
            raise RuntimeError('retirement failed')
        return {'frozen': True}


def test_retire_run_resources_closes_every_stage_in_order():
    docs = module()
    runtime, exposure, owner = _Closer(), _Exposure(), _Closer()
    report = docs.retire_run_resources(runtime, exposure, owner)
    assert runtime.closed == 1 and exposure.frozen == 1 and owner.closed == 1
    assert report == {'runtime': None, 'exposure': None, 'owner': None}


def test_retire_run_resources_records_a_failure_and_still_closes_the_rest():
    docs = module()
    runtime, exposure, owner = _Closer(fail=True), _Exposure(), _Closer()
    events = []
    report = docs.retire_run_resources(runtime, exposure, owner,
                                       emit=lambda stage, error: events.append((stage, error)))
    assert runtime.closed == 1 and exposure.frozen == 1 and owner.closed == 1
    assert report['runtime'] == 'RuntimeError' and report['exposure'] is None and report['owner'] is None
    assert events == [('runtime', 'RuntimeError')]


def test_retire_run_resources_tolerates_absent_resources():
    docs = module()
    report = docs.retire_run_resources(None, None, None)
    assert report == {'runtime': None, 'exposure': None, 'owner': None}


def test_retirement_preserves_false_receipts_and_still_closes_other_resources():
    class Unretired:
        def close(self, **kwargs):
            return {'retired': False, 'unquiesced': ['watchdog']}

    owner, exposure = _Closer(), _Exposure()
    outcomes = {}
    report = module().retire_run_resources(Unretired(), exposure, owner, outcomes=outcomes)
    assert report['runtime'] == 'HEAD_RETIREMENT_UNCONFIRMED'
    assert outcomes['runtime'] == {'retired': False, 'unquiesced': ['watchdog']}
    assert outcomes['owner'] == {'closed': True}
    assert owner.closed == 1 and exposure.frozen == 1

def _with_development_blocks(document):
    """Lift the flat fixture document's own controller fields into the blocks the plan shape uses.

    The fixtures declare their values at the top level, and the cases assert that the sealed configuration
    returns exactly those numbers (CP-HFP-304), so the blocks are built from the document — never from a
    reference config — and nothing the document declares is overridden (CP-HFP-294).
    """

    import json as _json

    reference = PACKAGE_ROOT / 'config/mujoco/act/head_search_v2.json'
    names = list(_json.loads(reference.read_text())['values'])
    result = {key: value for key, value in document.items() if key not in names}
    values = {key: document[key] for key in names if key in document}
    if isinstance(document.get('values'), dict):
        values.update(document['values'])
    # no filling: the production code reads goal_tolerance_rad and settle_velocity_rad_s from the motion block,
    # so a key the document does not declare stays absent and the refusal cases can see it (CP-HFP-305)
    # the motion pair comes from the document's own flat fields first, then from a values block, and only then
    # from a default — otherwise a declared 0.01 is silently replaced by 0.05 (CP-HFP-305/306)
    motion = {}
    for key in ('goal_tolerance_rad', 'settle_velocity_rad_s'):
        if key in document:
            motion[key] = document[key]
        elif key in values:
            motion[key] = values[key]
        else:
            motion[key] = 0.05
    motion.update(document.get('motion') or {})
    result['values'] = values
    result['motion'] = motion
    return result


def _camera_shape_factory(monkeypatch, tmp_path, *, warm_error=None, damage=None):
    from types import SimpleNamespace
    import threading
    import numpy as np
    import torch
    from so101_demo.adapters.act import detector as detector_module
    inputs, _ = inputs_with_config(tmp_path, CONFIG)
    snapshot = tmp_path / 'camera-shape-snapshot'; snapshot.mkdir()
    inputs.document['snapshot_root'] = str(snapshot)
    camera_path = Path(inputs.refs['camera_geometry']['path'])
    geometry = dict(camera=dict(height=480, width=640))
    if damage == 'invalid_dimension': geometry['camera']['height'] = True
    raw = json.dumps(geometry).encode(); camera_path.write_bytes(raw)
    inputs.refs['camera_geometry']['sha256'] = hashlib.sha256(raw).hexdigest()
    if damage == 'digest_changed': camera_path.write_bytes(raw + b' ')
    calls = []; tracks = {'original': 'untouched'}
    def synchronize(*, device):
        assert device == 'cuda:0'
        assert calls[-1]['owner'] == threading.get_native_id()
        calls[-1]['synchronized'] = True
    monkeypatch.setattr(torch.cuda, 'synchronize', synchronize)
    def predict(pixels):
        calls.append(dict(shape=pixels.shape, dtype=str(pixels.dtype),
                          all_zero=not np.any(pixels), owner=threading.get_native_id()))
        if warm_error is not None: raise warm_error
        return [object()]
    tensor_model = SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device='cuda:0')]))
    model = SimpleNamespace(model=tensor_model, predictor=SimpleNamespace(device='cuda:0'))
    runtime = SimpleNamespace(detector=SimpleNamespace(_model=model, _predict=predict),
        weights_sha256='a'*64, model_id='camera-shape-model', tracks=tracks,
        reset=lambda: None, detect=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError('warmup must not be an admitted detection')))
    builds = []
    def builder(binding, *, snapshot_root):
        builds.append(threading.get_native_id())
        return SimpleNamespace(runtime=runtime, snapshot_path=snapshot_root/'best.pt')
    monkeypatch.setattr(detector_module, 'build_bound_head_detector', builder)
    factory = module().build_run_detector_factory(inputs,
        loader=module().development_detector_loader(inputs))
    return factory, calls, builds, tracks


def test_camera_shape_warmup_finishes_on_single_owner_before_ready(monkeypatch, tmp_path):
    import threading
    from so101_demo.adapters.act.head_inference_owner import HeadInferenceOwner
    factory, calls, builds, tracks = _camera_shape_factory(monkeypatch, tmp_path)
    assert calls == builds == []
    faults = []; owner = HeadInferenceOwner(factory=factory, fault_callback=faults.append)
    try:
        first = owner.configuration(timeout_s=1.)
        second = owner.configuration(timeout_s=1.)
        assert len(calls) == len(builds) == 1
        assert calls[0] == dict(shape=(480,640,3), dtype='uint8', all_zero=True,
                               owner=first['inference_owner']['native_id'], synchronized=True)
        assert builds == [first['inference_owner']['native_id']]
        assert builds[0] != threading.get_native_id()
        assert first['camera_shape_warmup'] == second['camera_shape_warmup']
        assert first['camera_shape_warmup']['shape'] == [480,640,3]
        assert first['camera_shape_warmup']['classification'] == 'STARTUP_ONLY_NOT_OBSERVATION'
        assert first['camera_shape_warmup']['elapsed_s'] >= 0
        assert tracks == {'original':'untouched'} and not faults
    finally:
        assert owner.close(timeout_s=1.)['retired']


@pytest.mark.parametrize('damage', ['digest_changed', 'invalid_dimension'])
def test_camera_shape_warmup_refuses_changed_or_invalid_seal_before_predict(monkeypatch, tmp_path, damage):
    factory, calls, _, _ = _camera_shape_factory(monkeypatch, tmp_path, damage=damage)
    with pytest.raises(module().HeadExecutionDocumentRefused): factory()
    assert not calls


def test_camera_shape_warmup_error_prevents_owner_ready(monkeypatch, tmp_path):
    from so101_demo.adapters.act.head_inference_owner import HeadInferenceOwner
    factory, calls, _, _ = _camera_shape_factory(monkeypatch, tmp_path,
        warm_error=RuntimeError('controlled startup CUDA failure'))
    faults = []; owner = HeadInferenceOwner(factory=factory, fault_callback=faults.append)
    try:
        with pytest.raises(PermissionError, match='HEAD_INFERENCE_READY_REFUSED'):
            owner.configuration(timeout_s=1.)
        assert len(calls) == 1 and faults
    finally:
        assert owner.close(timeout_s=1.)['retired']
