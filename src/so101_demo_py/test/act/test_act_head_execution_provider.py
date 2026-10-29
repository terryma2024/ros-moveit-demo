"""Directed tests for the installed resource provider.

Resolution must name every constructor explicitly and refuse a tree that lacks
one, assembly must construct and bind in the documented order and tear down on
any failure, and the provider must refuse a run whose closed-loop runner is not
installed instead of constructing resources it cannot drive.
"""

import json
from types import SimpleNamespace

import pytest

from test_act_head_execution_composition import build_inputs as composition_inputs
from test_act_head_execution_composition import local_stack

pytestmark = pytest.mark.usefixtures("isolated_ros_domain")      # real nodes: a ROS domain of this test's own (not the gate's 203)


def build_inputs(tmp_path, **kwargs):
    inputs, policy = composition_inputs(tmp_path, **kwargs)
    inputs.document['stop_declaration'] = dict(trigger='OPERATOR_STOP', teardown_timeout_s=1.)
    return inputs, policy


def test_resource_plan_requires_declared_teardown_before_resolving_resources(monkeypatch, tmp_path):
    inputs, _ = composition_inputs(tmp_path)
    provider = provider_module()
    monkeypatch.setattr(provider, '_resolve', lambda *args, **kwargs: pytest.fail('resolved before admission'))
    with pytest.raises(provider.HeadExecutionProviderRefused, match='teardown timeout'):
        provider.resource_plan(inputs)


def provider_module():
    import importlib
    return importlib.import_module('so101_demo.adapters.act.head_execution_provider')


def test_file_provider_batches_controller_startup_without_changing_inputs(tmp_path):
    inputs, _ = build_inputs(tmp_path)
    before = json.dumps(inputs.document, sort_keys=True)
    plan = provider_module().resource_plan(inputs)
    assert plan['constructors']['stack']['keywords']['batch_spawners'] is True
    assert json.dumps(inputs.document, sort_keys=True) == before


def composition_module():
    import importlib
    return importlib.import_module('so101_demo.adapters.act.head_execution_composition')


class FakeStack:
    def identity_snapshot(self, role="arm"):
        """The ACK-confirmed generation/incarnation/boot triple the provider records (CP-HFP-436)."""

        return (1, "incarnation-%s" % role, "boot-%s" % role)

    def __init__(self, node, port):
        self.node, self.port = node, port
        self.closed = 0

    def close(self):
        self.closed += 1


class FakeDetector:
    def __init__(self, *, device='cuda:0', fail=False):
        if fail:
            raise RuntimeError('the model refused to load')
        self.runtime_device = device
        self.closed = 0

    def close(self):
        self.closed += 1


class FakeNeckOwner:
    """The provider only builds and retires the neck owner; the runner drives it."""

    def __init__(self, **keywords):
        self.keywords, self.closed = keywords, 0

    def close(self):
        self.closed += 1
        return dict(monitor_alive=False, window=dict(thread_alive=False), helper_killed=True)


def plan_for(monkeypatch, composition, inputs, *, detector_fail=False, owner_fail=False,
             device='cuda:0', runner=None):
    stack = local_stack(monkeypatch, composition.policy, epoch=inputs.run['epoch'],
                        session=inputs.run['session_id'], generation=inputs.run['generation'])
    built = {}

    def fake_anchor(**keywords):
        """A stand-in for run_anchor_restart: the receipt the provider reads the triple from."""

        built['anchor_keywords'] = keywords
        return {"observations": {"reservation": {"controller_identity":
                {"generation": 1, "incarnation": "inc-1", "boot": "boot-1"}}}}

    def make_stack(**keywords):
        built['stack'] = FakeStack(stack.node, stack.port)
        built['stack_keywords'] = keywords
        return built['stack']

    def make_detector(**keywords):
        built['detector_keywords'] = keywords
        det = FakeDetector(device=device, fail=detector_fail)
        built['detector'] = det
        return det

    def make_owner(**keywords):
        built['owner_keywords'] = keywords
        if owner_fail:
            raise RuntimeError('the neck owner refused to build')
        owner = FakeNeckOwner(**keywords)
        built['owner'] = owner
        return owner

    plan = {
        'run': inputs.run, 'scope': inputs.execution_scope, 'refs': dict(inputs.refs),
        'ros': dict(inputs.document['ros']), 'resources': dict(inputs.document['resources']),
        'pose': inputs.document['development_pose'],
        'constructors': {
            'stack': {'callable': make_stack, 'keywords': {'controller_config_path': 'x'}},
            'detector': {'callable': make_detector, 'keywords': {'weights': 'w'}},
            'owner': {'callable': make_owner, 'keywords': {}}},
        'runner': runner,
    }
    plan['anchor'] = fake_anchor
    return plan, built, stack


def test_resource_plan_resolves_the_installed_constructors(monkeypatch, tmp_path):
    inputs, policy = build_inputs(tmp_path)
    plan = provider_module().resource_plan(inputs)
    assert plan['scope'] == 'MUJOCO_DEVELOPMENT_UNQUALIFIED'
    for stage in ('stack', 'detector', 'owner'):
        assert callable(plan['constructors'][stage]['callable'])
    assert plan['constructors']['stack']['keywords']['controller_config_path'] == \
        inputs.refs['controller_config']['path']
    assert plan['constructors']['stack']['keywords']['session_id'] == inputs.run['session_id']
    assert plan['constructors']['detector']['keywords']['cuda_device'] == 'cuda:0'
    assert plan['constructors']['detector']['keywords']['allow_cpu_fallback'] is False
    assert plan['constructors']['detector']['keywords']['weights_sha256'] == \
        inputs.refs['weights']['sha256']
    assert plan['run'] == inputs.run
    # The closed-loop runner is not installed yet, and the plan says so instead of inventing one.
    assert plan['runner'] is not None  # the installed runner resolves now


def test_resource_plan_refuses_a_foreign_object_and_a_promoted_scope(tmp_path):
    inputs, _ = build_inputs(tmp_path)
    with pytest.raises(provider_module().HeadExecutionProviderRefused) as refusal:
        provider_module().resource_plan(object())
    assert refusal.value.code == 'EXECUTION_PROVIDER_REFUSED'
    inputs.document['execution_scope'] = 'HEAD_SEARCH_QUALIFIED'
    with pytest.raises(provider_module().HeadExecutionProviderRefused) as refusal:
        provider_module().resource_plan(inputs)
    assert refusal.value.code == 'EXECUTION_PROVIDER_SCOPE_REFUSED'


def test_resource_plan_refuses_a_missing_installed_constructor(tmp_path):
    inputs, _ = build_inputs(tmp_path)
    broken = dict(provider_module().RESOURCE_MODULES)
    broken['stack'] = ('so101_demo.act.head_search.restarts', 'NoSuchStack')
    with pytest.raises(provider_module().HeadExecutionProviderRefused) as refusal:
        provider_module().resource_plan(inputs, modules=broken)
    assert refusal.value.code == 'EXECUTION_PROVIDER_RESOURCE_ABSENT'
    assert 'NoSuchStack' in refusal.value.detail


def test_assemble_binds_every_resource_and_returns_the_handle(monkeypatch, tmp_path):
    inputs, policy = build_inputs(tmp_path)
    composition = composition_module().HeadExecutionComposition.open(inputs)
    plan, built, stack = plan_for(monkeypatch, composition, inputs)
    handle = provider_module().assemble(composition, inputs, plan=plan)
    assert composition.bound_stages == ('ros',)
    assert handle['built'] == ('neck_owner', 'stack')
    assert handle['run'] == inputs.run and handle['scope'] == 'MUJOCO_DEVELOPMENT_UNQUALIFIED'
    assert handle['stack'] is built['stack']
    assert handle['neck_owner'] is built['owner']
    assert built['owner_keywords']['node'] is stack.node and built['owner_keywords']['inputs'] is inputs
    assert built['owner_keywords']['policy'] is composition.policy
    assert set(handle) >= {'detector_entry'} and 'native_entry' not in handle and 'revoker_entry' not in handle
    assert built['stack_keywords'] == {'controller_config_path': 'x'}
    stack.runtime.close(timeout_s=1.)










def test_assemble_binds_ros_with_an_inprocess_stack_and_binding_refs(monkeypatch, tmp_path):
    """The provider must bind the ros stage with the stack, which has no node and no port (CP-HFP-194)."""

    inputs, policy = build_inputs(tmp_path)
    # the run's own local set reads its search values from the binding reference (CP-HFP-225/229), and the
    # composition wants the snapshot root declared on the same path, so the fixture provides both
    import hashlib as _h
    root = tmp_path / 'launcher-refs'
    root.mkdir(exist_ok=True)
    # one shared set for both documents, because the validator compares them field by field: the three
    # identity fields at TOP level, the context fields, one motion block carrying the neck duration, an explicit
    # CUDA prohibition and one device (CP-HFP-259)
    fixture_values = {name: 0.05 for name in ["center_deadband_px", "coarse_step_rad", "horizontal_fov_rad", "lock_valid_neck_rad", "max_age_s", "max_fine_corrections", "max_fine_total_rad", "max_skew_s", "min_area_px2", "min_bbox_aspect", "min_confidence", "search_timeout_s", "stop_latency_s", "stop_velocity_rad_s", "submit_lead_s", "tracking_iou", "vertical_bounds_px"]}
    fixture_values.update({'submit_lead_s': .01, 'stop_latency_s': .05, 'stop_velocity_rad_s': .05,
                           'max_age_s': .05})
    fixture_shared = {
        'values': fixture_values,
        'motion': {'goal_tolerance_rad': .05, 'settle_velocity_rad_s': .05, 'neck_goal_duration_s': .5},
        'weight_sha256': 'a' * 64, 'candidate_identity_sha256': 'b' * 64, 'runtime_id': 'fixture-runtime',
        'weight_path': 'fixture-weights.pt', 'camera': {'frame_id': 'fixture-frame'},
        'tracker': {'name': 'bytetrack'}, 'controlled_dependencies': {'fixture': '1'},
        'allow_cpu_fallback': False, 'cuda_device': 'cuda:0',
    }
    root = tmp_path / 'launcher-refs'
    root.mkdir(exist_ok=True)
    binding_payload = json.dumps(fixture_shared).encode()
    (root / 'binding.json').write_bytes(binding_payload)
    inputs.refs['binding'] = {'path': str(root / 'binding.json'),
                             'sha256': _h.sha256(binding_payload).hexdigest()}
    bundle_payload = json.dumps({'kind': 'head_search_calibration_bundle',
                                 'parameters': {name: {'value': value, 'unit': 's'}
                                                for name, value in fixture_values.items()}}).encode()
    (root / 'bundle.json').write_bytes(bundle_payload)
    report_payload = json.dumps({**fixture_shared}).encode()
    (root / 'report.json').write_bytes(report_payload)
    inputs.refs['report'] = {'path': str(root / 'report.json'),
                            'sha256': _h.sha256(report_payload).hexdigest()}
    dev_config = {**fixture_shared, 'execution_scope': 'MUJOCO_DEVELOPMENT_UNQUALIFIED',
                  'values': {**fixture_values, 'search_timeout_s': 30.0, 'stop_latency_s': 1.0,
                             'max_age_s': 0.15}}
    dev_payload = json.dumps(dev_config).encode()
    (root / 'development-config.json').write_bytes(dev_payload)
    inputs.refs['development_config'] = {'path': str(root / 'development-config.json'),
                                         'sha256': _h.sha256(dev_payload).hexdigest()}
    inputs.document['snapshot_root'] = str(root)
    composition = composition_module().HeadExecutionComposition.open(inputs)
    plan, built, stack = plan_for(monkeypatch, composition, inputs)
    handle = provider_module().assemble(composition, inputs, plan=plan)
    assert composition.bound_stages == ('ros',)
    assert handle['built'] == ('neck_owner', 'stack')
    assert handle['run'] == inputs.run and handle['scope'] == 'MUJOCO_DEVELOPMENT_UNQUALIFIED'
    assert handle['stack'] is built['stack']
    assert handle['neck_owner'] is built['owner']
    assert built['owner_keywords']['node'] is stack.node and built['owner_keywords']['inputs'] is inputs
    assert built['owner_keywords']['policy'] is composition.policy
    assert set(handle) >= {'detector_entry'} and 'native_entry' not in handle and 'revoker_entry' not in handle
    assert built['stack_keywords'] == {'controller_config_path': 'x'}
    stack.runtime.close(timeout_s=1.)


def test_teardown_reports_a_failing_close_and_still_closes_the_rest():
    class Half:
        def __init__(self, fail):
            self.fail, self.closed = fail, 0

        def close(self):
            self.closed += 1
            if self.fail:
                raise RuntimeError('close failed')

    first, second = Half(False), Half(True)
    failures = provider_module().teardown([('stack', first), ('detector', second)])
    assert first.closed == 1 and second.closed == 1
    assert failures == [('detector', 'close', 'RuntimeError')]


def test_provide_refuses_a_bare_run_before_constructing_anything(monkeypatch, tmp_path):
    """Without the sealed binding material the provider refuses before building any resource."""

    inputs, policy = build_inputs(tmp_path)
    composition = composition_module().HeadExecutionComposition.open(inputs)
    with pytest.raises(provider_module().HeadExecutionProviderRefused) as refusal:
        provider_module().provide(composition, inputs)
    assert refusal.value.code == 'EXECUTION_PROVIDER_ADMISSION_ABSENT'
    assert composition.bound_stages == ()


def test_provide_runs_the_plan_runner_and_tears_down_afterwards(monkeypatch, tmp_path):
    inputs, policy = build_inputs(tmp_path)
    composition = composition_module().HeadExecutionComposition.open(inputs)
    seen = {}

    def runner(comp, handle, **keywords):
        seen['stages'] = comp.bound_stages
        seen['handle'] = sorted(handle)
        return 0

    plan, built, stack = plan_for(monkeypatch, composition, inputs, runner={'callable': runner})
    assert provider_module().provide(composition, inputs, plan=plan) == 0
    assert seen['stages'] == ('ros',)
    assert built['stack'].closed == 1
    stack.runtime.close(timeout_s=1.)

def test_the_admission_check_names_the_sealed_binding_material(tmp_path):
    """A bare run may only construct a model when the sealed inputs name the real binding material."""

    import hashlib

    inputs, policy = build_inputs(tmp_path)
    provider = provider_module()
    assert provider._admission_material(inputs) is False
    root = tmp_path / 'sealed-binding'
    root.mkdir(exist_ok=True)
    for name in ('binding', 'report'):
        payload = json.dumps({'name': name}).encode()
        path = root / ('%s.bin' % name)
        path.write_bytes(payload)
        inputs.refs[name] = {'path': str(path), 'sha256': hashlib.sha256(payload).hexdigest()}
    # snapshot_root is a declared top-level directory field (CP-HFP-099) and can never be a ref, so the
    # predicate must read it from the document: faking it as a third ref is what let the defect hide
    inputs.document['snapshot_root'] = str(root)
    assert provider._admission_material(inputs) is True

def test_the_stack_keywords_carry_the_four_real_arguments(monkeypatch, tmp_path):
    """The real transport needs urdf_path, scene_path, plugin_config_path and workspace (CP-HFP-188)."""

    inputs, policy = build_inputs(tmp_path)
    plan = provider_module().resource_plan(inputs)
    keywords = plan['constructors']['stack']['keywords']
    for name in ('urdf_path', 'scene_path', 'plugin_config_path', 'workspace'):
        assert name in keywords, f'the stack keywords must carry {name} for the real transport'
    assert keywords['urdf_path'] == inputs.refs['urdf']['path']
    assert keywords['scene_path'] == inputs.refs['scene']['path']
    assert keywords['plugin_config_path'] == inputs.refs['mujoco_plugin']['path']

def test_assemble_binds_ros_with_the_launcher_stack(monkeypatch, tmp_path):
    """The provider must bind the ros stage with the stack, which has no node and no port (CP-HFP-194)."""

    inputs, policy = build_inputs(tmp_path)
    # the run's own local set reads its search values from the binding reference (CP-HFP-225/229), and the
    # composition wants the snapshot root declared on the same path, so the fixture provides both
    import hashlib as _h
    root = tmp_path / 'launcher-refs'
    root.mkdir(exist_ok=True)
    # one source of truth for the fixture's numbers, so the binding and the calibration bundle cannot
    # disagree — the validator refuses inconsistent documents, which is how green-132 failed (CP-HFP-256)
    # the validator wants exactly the seventeen declared values (CP-HFP-257); a fixture may copy the shape
    # because the real documents stay sealed and the run never sees this data
    fixture_values = {name: 0.05 for name in ["center_deadband_px", "coarse_step_rad", "horizontal_fov_rad", "lock_valid_neck_rad", "max_age_s", "max_fine_corrections", "max_fine_total_rad", "max_skew_s", "min_area_px2", "min_bbox_aspect", "min_confidence", "search_timeout_s", "stop_latency_s", "stop_velocity_rad_s", "submit_lead_s", "tracking_iou", "vertical_bounds_px"]}
    fixture_values.update({'submit_lead_s': .01, 'stop_latency_s': .05, 'stop_velocity_rad_s': .05,
                           'max_age_s': .05})
    fixture_identity = {'weight_sha256': 'a' * 64, 'candidate_identity_sha256': 'b' * 64,
                        'runtime_id': 'fixture-runtime'}
    # the same shared set as the other launcher case, because the validator compares the two documents field
    # by field and a second, thinner copy is what kept this case refusing (CP-HFP-261)
    fixture_shared = {
        'values': fixture_values,
        'motion': {'goal_tolerance_rad': .05, 'settle_velocity_rad_s': .05, 'neck_goal_duration_s': .5},
        **fixture_identity,
        'weight_path': 'fixture-weights.pt', 'camera': {'frame_id': 'fixture-frame'},
        'tracker': {'name': 'bytetrack'}, 'controlled_dependencies': {'fixture': '1'},
        'allow_cpu_fallback': False, 'cuda_device': 'cuda:0',
    }
    binding_document = json.dumps(fixture_shared).encode()
    (root / 'binding.json').write_bytes(binding_document)
    inputs.refs['binding'] = {'path': str(root / 'binding.json'),
                             'sha256': _h.sha256(binding_document).hexdigest()}
    # the receipt names the calibration bundle the local set reads its measured values from (CP-HFP-252)
    bundle_payload = json.dumps({'kind': 'head_search_calibration_bundle',
                                 'parameters': {name: {'value': value, 'unit': 's'}
                                                for name, value in fixture_values.items()},
                                 **fixture_identity}).encode()
    (root / 'bundle.json').write_bytes(bundle_payload)
    for name in ('report',):
        payload = json.dumps({**fixture_shared}).encode()
        (root / f'{name}.json').write_bytes(payload)
        inputs.refs[name] = {'path': str(root / f'{name}.json'), 'sha256': _h.sha256(payload).hexdigest()}
    dev_config = {**fixture_shared, 'execution_scope': 'MUJOCO_DEVELOPMENT_UNQUALIFIED',
                  'values': {**fixture_values, 'search_timeout_s': 30.0, 'stop_latency_s': 1.0,
                             'max_age_s': 0.15}}
    dev_payload = json.dumps(dev_config).encode()
    (root / 'development-config.json').write_bytes(dev_payload)
    inputs.refs['development_config'] = {'path': str(root / 'development-config.json'),
                                         'sha256': _h.sha256(dev_payload).hexdigest()}
    inputs.document['snapshot_root'] = str(root)
    composition = composition_module().HeadExecutionComposition.open(inputs)
    plan = provider_module().resource_plan(inputs)

    class _Launcher:
        def __init__(self, **keywords):
            self.keywords = keywords
            self.controller_config_path = keywords.get('controller_config_path')
            self.environment = dict(keywords.get('environment') or {})

        def identity_snapshot(self, role="arm"):
            """The triple the provider records, so the launcher form answers like the real one."""

            return (1, "incarnation-%s" % role, "boot-%s" % role)

        def start(self):
            return {'started': True}

    plan['constructors']['stack']['callable'] = _Launcher
    plan['constructors']['owner'] = {'callable': FakeNeckOwner, 'keywords': {}}
    plan['owned_scene'] = False
    handle = provider_module().assemble(composition, inputs, plan=plan)
    assert handle['stack'] is not None
    for name in ('node', 'port', 'capture', 'neck', 'settlement'):
        assert handle.get(name) is not None, f'the handle must carry {name} for the runner'
    assert composition.bound_stages[:1] == ('ros',), composition.bound_stages
    assert handle['neck_owner'].keywords['node'] is handle['node']
    assert not provider_module().teardown([('local_ros', handle['local_ros']),
                                          ('stack', handle['stack']),
                                          ('neck_owner', handle['neck_owner'])])
    assert handle['neck_owner'].closed == 1
    composition.writer.finish({'execution': 'FAILED', 'reason': 'no-motion fixture cleanup'})

def test_the_run_node_name_is_legal_for_a_hyphenated_run_id():
    """ROS forbids anything but alphanumerics and underscores in a node name (CP-HFP-215)."""

    provider = provider_module()
    name = provider._run_node_name('item9-run-011')
    assert name == 'head_run_item9_run_011', name
    assert all(character.isalnum() or character == '_' for character in name), name


def test_the_run_node_name_keeps_a_clean_id_untouched():
    assert provider_module()._run_node_name('clean_id_1') == 'head_run_clean_id_1'


def test_failed_provider_retirement_overrides_success_and_blocks_seal(monkeypatch, tmp_path):
    inputs, _ = build_inputs(tmp_path)
    composition = composition_module().HeadExecutionComposition.open(inputs)
    plan, built, stack = plan_for(monkeypatch, composition, inputs,
                                  runner={'callable': lambda *a, **k: 0})
    monkeypatch.setattr(FakeStack, 'close', lambda self: {'retired': False})
    try:
        with pytest.raises(provider_module().HeadExecutionProviderRefused,
                           match='owned teardown failed'):
            provider_module().provide(composition, inputs, plan=plan)
        with pytest.raises(composition_module().HeadExecutionCompositionRefused,
                           match='EXECUTION_PRODUCERS_UNRETIRED'):
            composition.seal({'execution': 'FAILED'})
        assert not (inputs.run_root / 'completion.json').exists()
        assert not (inputs.run_root / 'seal.json').exists()
    finally:
        stack.runtime.close(timeout_s=1.)
        # This fixture created no live external producer; drain its test writer.
        composition.writer.finish({'execution': 'FAILED', 'reason': 'fixture cleanup'})


def test_the_plan_builds_the_neck_owner_and_has_no_native_provisioning(monkeypatch, tmp_path):
    inputs, _ = build_inputs(tmp_path)
    plan = provider_module().resource_plan(inputs)
    assert set(plan['constructors']) == {'stack', 'detector', 'owner'}
    assert plan['constructors']['owner']['keywords'] == {}
    assert plan['owned_scene'] is True and 'native_provisioning' not in plan
    assert callable(plan['constructors']['owner']['callable'])


def test_a_failing_owner_build_tears_the_stack_down_and_raises(monkeypatch, tmp_path):
    inputs, _ = build_inputs(tmp_path)
    composition = composition_module().HeadExecutionComposition.open(inputs)
    plan, built, stack = plan_for(monkeypatch, composition, inputs, owner_fail=True)
    try:
        with pytest.raises(RuntimeError, match='neck owner refused'):
            provider_module().assemble(composition, inputs, plan=plan)
        assert built['stack'].closed == 1
    finally:
        stack.runtime.close(timeout_s=1.)
        composition.writer.finish({'execution': 'FAILED', 'reason': 'fixture cleanup'})
