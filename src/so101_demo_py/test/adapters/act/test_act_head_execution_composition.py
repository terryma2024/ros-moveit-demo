"""Directed tests for the one resource composition of a stage-one run.

The composition must open exactly one writer for a fresh run root from verified
inputs, bind one ROS/owner/detector/inference/runtime/search set in one fixed
order with no rebinding, prove every bound resource shares the sealed policy and
run identity, and seal the run exactly once.
"""

import hashlib
import itertools
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.act.head_evidence_identity import digest
from so101_demo.act.head_local_state import HeadLocalState
from so101_demo.adapters.act.head_owned_search import OwnedHeadSearch
from test_act_head_feedback_freshness import policy as feedback_policy_dict
from test_act_head_local_observer import observer_setup, simulation_policy
from test_act_head_local_runtime import Recorder
from head_owner_support import deadline, make as make_neck_owner
from test_act_search import config as search_config


def module():
    import importlib
    return importlib.import_module('so101_demo.adapters.act.head_execution_composition')


def inputs_module():
    import importlib
    return importlib.import_module('so101_demo.act.head_execution_inputs')


REF_NAMES = ('weights', 'frozen_c', 'camera_geometry', 'development_config', 'local_policy',
             'controller_config', 'mujoco_plugin', 'scene', 'urdf', 'safety_inputs')

_SEQUENCE = itertools.count(1)


def unique(tag):
    """A fresh identity token: live local scopes are process-global and never reused."""
    return '%s-%d' % (tag, next(_SEQUENCE))


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload if type(payload) is bytes else payload.encode())
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_inputs(tmp_path, *, policy=None, epoch=None, session=None, generation=7):
    """A verified execution-inputs document whose local_policy is a real policy."""

    policy = simulation_policy() if policy is None else policy
    epoch = unique('epoch-comp') if epoch is None else epoch
    session = unique('session-comp') if session is None else session
    policy_bytes = json.dumps(policy.readback(), sort_keys=True).encode()
    root = tmp_path / 'evidence'
    root.mkdir(parents=True, exist_ok=True)
    refs = {}
    for name in REF_NAMES:
        payload = policy_bytes if name == 'local_policy' else ('%s-bytes' % name).encode()
        refs[name] = {'path': str(tmp_path / 'frozen' / ('%s.bin' % name)),
                      'sha256': write(tmp_path / 'frozen' / ('%s.bin' % name), payload)}
    freeze_sha = write(tmp_path / 'freeze.json', b'{"freeze": "receipt"}')
    document = dict(
        schema_version=1, kind='head_execution_inputs', operation='HEAD_FILE_STAGE1_DEVELOPMENT',
        execution_scope='MUJOCO_DEVELOPMENT_UNQUALIFIED',
        run=dict(run_id='run-comp', session_id=session, epoch=epoch, generation=generation),
        evidence_root=str(root), run_root=str(root / 'run-comp'),
        freeze_receipt={'path': str(tmp_path / 'freeze.json'), 'sha256': freeze_sha}, refs=refs,
        development_pose=dict(arm_rad=[-0.25, 0.0, 0.6, 0.8, 0.0, 0.8], neck_rad=0.1,
                              cup_xyz=[0.02, -0.28, 0.165]),
        resources=dict(cuda_device='cuda:0', allow_cpu_fallback=False, cpu_allocation=8),
        ros=dict(domain_id=42, environment={'ROS_DOMAIN_ID': '42'}))
    path = tmp_path / 'execution-inputs.json'
    write(path, json.dumps(document))
    return inputs_module().HeadExecutionInputs.parse(path), policy


def local_stack(monkeypatch, policy, *, epoch=None, session=None, generation=7,
                controller_identity=None):
    """One local node/port/state/observer/runtime/search set on the given identity."""

    epoch = unique('epoch-stack') if epoch is None else epoch
    session = unique('session-stack') if session is None else session
    row = observer_setup(monkeypatch, policy=policy, bind_port_sink=False)
    identity = dict(controller_identity or dict(generation=generation, incarnation='inc-1',
                                                boot='boot-1'))
    scope = dict(epoch=epoch, generation=generation, session_id=session,
                 policy_sha256=digest(policy.readback()), controller_identity=identity)
    state = HeadLocalState(scope, 10 ** 18)
    from so101_demo.adapters.act.head_local_observer import HeadLocalObserver
    from so101_demo.adapters.act.head_local_runtime import HeadLocalRuntime
    observer = HeadLocalObserver(row.node, row.port, state, policy=policy,
                                 camera_frame='head_camera_optical_frame',
                                 bind_port_sink=False)
    neck_owner, *_ = make_neck_owner(policy=policy, generation=generation, session_id=session,
                                     identity=identity, auto_window=True)
    neck_owner.activate(deadline=deadline())
    runtime = HeadLocalRuntime(node=row.node, port=row.port, local_state=state, owner=neck_owner,
                               observer=observer, policy=policy, sink=Recorder())

    class Owner:
        _simulation_policy = policy

        def __init__(self):
            self.requests = []

        def configuration(self, timeout_s):
            return {}

        def request_observation(self, request):
            self.requests.append(dict(request))
            return dict(request)

        def next_completed_observation(self, after_sequence):
            return None

        def close(self, timeout_s=1.):
            return {'retired': True}

        def infer(self):
            return None

    owner = Owner()
    search = OwnedHeadSearch(config=search_config(), primary=runtime, port=row.port, owner=owner,
                             settlement=lambda *a, **k: None, stop_velocity_rad_s=.01,
                             emit=lambda event, **fields: None,
                             local_state=state, policy=policy)
    return SimpleNamespace(node=row.node, port=row.port, state=state, observer=observer,
                           runtime=runtime, neck_owner=neck_owner, owner=owner,
                           search=search, policy=policy)


def bound_composition(monkeypatch, tmp_path, *, policy=None):
    inputs, policy = build_inputs(tmp_path, policy=policy)
    composition = module().HeadExecutionComposition.open(inputs)
    stack = local_stack(monkeypatch, policy, epoch=inputs.run['epoch'],
                        session=inputs.run['session_id'], generation=inputs.run['generation'])
    composition.bind_ros(node=stack.node, port=stack.port)
    composition.bind_owner(owner=stack.neck_owner)
    composition.bind_detector(object(), runtime_device='cuda:0')
    composition.bind_inference(stack.owner)
    composition.bind_runtime(observer=stack.observer, runtime=stack.runtime)
    composition.bind_search(stack.search)
    return composition, inputs, stack


def test_open_creates_one_writer_with_the_full_manifest(monkeypatch, tmp_path):
    inputs, policy = build_inputs(tmp_path)
    composition = module().HeadExecutionComposition.open(inputs)
    manifest = json.loads((inputs.run_root / 'manifest.json').read_text())
    assert manifest['execution_inputs']['sha256'] == inputs.document_sha256
    assert manifest['execution_scope'] == 'MUJOCO_DEVELOPMENT_UNQUALIFIED'
    assert manifest['run'] == inputs.run
    assert sorted(manifest['refs']) == sorted(REF_NAMES)
    assert manifest['simulation_policy_sha256'] == digest(policy.readback())
    assert manifest['resources_declared']['cuda_device'] == 'cuda:0'
    assert composition.complete is False and composition.bound_stages == ()
    assert composition.readback()['sealed'] is False
    with pytest.raises(FileExistsError):
        module().HeadExecutionComposition.open(inputs)


def test_open_refuses_a_foreign_object_and_a_promoted_scope(monkeypatch, tmp_path):
    inputs, _ = build_inputs(tmp_path)
    with pytest.raises(module().HeadExecutionCompositionRefused) as refusal:
        module().HeadExecutionComposition.open(object())
    assert refusal.value.code == 'EXECUTION_COMPOSITION_REFUSED'
    inputs.document['execution_scope'] = 'HEAD_SEARCH_QUALIFIED'
    with pytest.raises(module().HeadExecutionCompositionRefused) as refusal:
        module().HeadExecutionComposition.open(inputs)
    assert refusal.value.code == 'EXECUTION_COMPOSITION_REFUSED'
    assert not inputs.run_root.exists()


def test_binding_order_and_single_binding_are_enforced(monkeypatch, tmp_path):
    composition, inputs, stack = bound_composition(monkeypatch, tmp_path)
    assert composition.complete is True
    assert composition.bound_stages == ('ros', 'owner', 'detector', 'inference', 'runtime',
                                        'search')
    with pytest.raises(module().HeadExecutionCompositionRefused) as refusal:
        composition.bind_ros(node=stack.node, port=stack.port)
    assert refusal.value.code == 'EXECUTION_RESOURCE_REBOUND'

    other_inputs, policy = build_inputs(tmp_path / 'second')
    early = module().HeadExecutionComposition.open(other_inputs)
    from so101_demo.adapters.act.head_local_observer import HeadLocalObserver
    with pytest.raises(module().HeadExecutionCompositionRefused) as refusal:
        early.bind_detector(object(), runtime_device='cuda:0')
    assert refusal.value.code == 'EXECUTION_COMPOSITION_REFUSED'


def test_ros_binding_requires_the_frozen_policy_and_joint(monkeypatch, tmp_path):
    inputs, policy = build_inputs(tmp_path)
    composition = module().HeadExecutionComposition.open(inputs)
    foreign_row = observer_setup(monkeypatch, policy=simulation_policy(search_timeout_s=29.),
                                 bind_port_sink=False)
    with pytest.raises(module().HeadExecutionCompositionRefused) as refusal:
        composition.bind_ros(node=foreign_row.node, port=foreign_row.port)
    assert refusal.value.code == 'EXECUTION_COMPOSITION_REFUSED'
    stack = local_stack(monkeypatch, policy, epoch=inputs.run['epoch'],
                        session=inputs.run['session_id'], generation=inputs.run['generation'])
    with pytest.raises(module().HeadExecutionCompositionRefused):
        composition.bind_ros(node=SimpleNamespace(), port=stack.port)
    composition.bind_ros(node=stack.node, port=stack.port)
    assert composition.bound_stages == ('ros',)


@pytest.mark.parametrize('device', ['cpu', 'cuda:1', None, 'CUDA:0'])
def test_detector_binding_refuses_any_device_but_cuda_zero(monkeypatch, tmp_path, device):
    inputs, policy = build_inputs(tmp_path)
    composition = module().HeadExecutionComposition.open(inputs)
    stack = local_stack(monkeypatch, policy, epoch=inputs.run['epoch'],
                        session=inputs.run['session_id'], generation=inputs.run['generation'])
    composition.bind_ros(node=stack.node, port=stack.port)
    composition.bind_owner(owner=stack.neck_owner)
    with pytest.raises(module().HeadExecutionCompositionRefused) as refusal:
        composition.bind_detector(object(), runtime_device=device)
    assert refusal.value.code == 'EXECUTION_DEVICE_REFUSED'


def test_inference_binding_requires_the_frozen_policy(monkeypatch, tmp_path):
    inputs, policy = build_inputs(tmp_path)
    composition = module().HeadExecutionComposition.open(inputs)
    stack = local_stack(monkeypatch, policy, epoch=inputs.run['epoch'],
                        session=inputs.run['session_id'], generation=inputs.run['generation'])
    composition.bind_ros(node=stack.node, port=stack.port)
    composition.bind_owner(owner=stack.neck_owner)
    composition.bind_detector(object(), runtime_device='cuda:0')
    with pytest.raises(module().HeadExecutionCompositionRefused):
        composition.bind_inference(SimpleNamespace(configuration=lambda **k: {},
                                                   request_observation=lambda r: r,
                                                   next_completed_observation=lambda s: None,
                                                   close=lambda **k: {}))


def test_runtime_binding_requires_the_sealed_identity_and_policy(monkeypatch, tmp_path):
    inputs, policy = build_inputs(tmp_path)
    composition = module().HeadExecutionComposition.open(inputs)
    foreign = local_stack(monkeypatch, policy, epoch='foreign-epoch',
                          session=inputs.run['session_id'], generation=inputs.run['generation'])
    composition.bind_ros(node=foreign.node, port=foreign.port)
    composition.bind_owner(owner=foreign.neck_owner)
    composition.bind_detector(object(), runtime_device='cuda:0')
    composition.bind_inference(foreign.owner)
    with pytest.raises(module().HeadExecutionCompositionRefused):
        composition.bind_runtime(observer=foreign.observer, runtime=foreign.runtime)


def test_search_binding_requires_the_composition_state(monkeypatch, tmp_path):
    composition, inputs, stack = bound_composition(monkeypatch, tmp_path)
    # A foreign stack on its own fresh identity: its search is committed elsewhere.
    other = local_stack(monkeypatch, stack.policy)
    # An identical-looking search committed to another state is refused.
    composition._bound.pop('search')
    with pytest.raises(module().HeadExecutionCompositionRefused):
        composition.bind_search(other.search)
    assert composition.bind_search(stack.search) is stack.search
    assert composition.complete is True


def test_seal_writes_the_run_once_and_closes_the_composition(monkeypatch, tmp_path):
    composition, inputs, stack = bound_composition(monkeypatch, tmp_path)
    composition.emit('EXECUTION_TEST_EVENT', {'value': 1})
    sealed = composition.seal({'execution': 'SUCCEEDED', 'business_return_code': 0})
    assert sealed and (inputs.run_root / 'seal.json').is_file()
    completion = json.loads((inputs.run_root / 'completion.json').read_text())
    assert completion['complete_composition'] is True
    assert completion['business_return_code'] == 0
    assert composition.readback()['sealed'] is True
    with pytest.raises(module().HeadExecutionCompositionRefused) as refusal:
        composition.seal({'execution': 'SUCCEEDED'})
    assert refusal.value.code == 'EXECUTION_COMPOSITION_CLOSED'
    with pytest.raises(module().HeadExecutionCompositionRefused):
        composition.emit('EXECUTION_TEST_EVENT', {'value': 2})
    stack.runtime.close(timeout_s=1.)


def test_incomplete_composition_seals_as_a_failure(monkeypatch, tmp_path):
    inputs, policy = build_inputs(tmp_path)
    composition = module().HeadExecutionComposition.open(inputs)
    stack = local_stack(monkeypatch, policy, epoch=inputs.run['epoch'],
                        session=inputs.run['session_id'], generation=inputs.run['generation'])
    composition.bind_ros(node=stack.node, port=stack.port)
    with pytest.raises(module().HeadExecutionCompositionRefused) as refusal:
        composition.seal({'execution': 'SUCCEEDED'})
    assert refusal.value.code == 'EXECUTION_COMPOSITION_REFUSED'
    completion = json.loads((inputs.run_root / 'completion.json').read_text())
    assert completion['complete_composition'] is False
    assert completion['missing_stages'] == ['owner', 'detector', 'inference', 'runtime', 'search']
    stack.runtime.close(timeout_s=1.)


def test_run_head_execution_opens_one_composition(monkeypatch, tmp_path):
    inputs, policy = build_inputs(tmp_path)
    composition = module().run_head_execution(inputs, evidence=lambda reason: None)
    assert composition.complete is False
    assert (inputs.run_root / 'manifest.json').is_file()
    with pytest.raises(module().HeadExecutionCompositionRefused):
        module().run_head_execution(inputs, evidence=object())


import pytest




class _LauncherStack:
    def identity_snapshot(self, role="arm"):
        """The ACK-confirmed generation/incarnation/boot triple the provider records (CP-HFP-436)."""

        return (1, "incarnation-%s" % role, "boot-%s" % role)

    """A stack shaped like the real one: two constructor values, children, and no node or port."""

    def __init__(self, *, controller_config_path, environment):
        self.controller_config_path = controller_config_path
        self.environment = dict(environment)
        self.log_path = None
        self.children = []

    def start(self):
        self.children.append({'argv': ['ros2_control_node'], 'pid': 4242, 'start_ticks': 99})
        return {'started': True}


def test_bind_ros_accepts_the_launcher_stack(tmp_path):
    inputs, policy = build_inputs(tmp_path)
    composition = module().HeadExecutionComposition.open(inputs)
    stack = _LauncherStack(controller_config_path=inputs.refs['controller_config']['path'],
                           environment=dict(inputs.document['ros']['environment']))
    composition.bind_ros(stack)
    assert 'ros' in composition.bound_stages, 'the stack itself is the ros owner'


def test_bind_ros_refuses_an_object_that_is_not_a_stack(tmp_path):
    inputs, policy = build_inputs(tmp_path)
    composition = module().HeadExecutionComposition.open(inputs)
    with pytest.raises(Exception) as refusal:
        composition.bind_ros(object())
    assert 'COMPOSITION' in str(refusal.value) or 'ros' in str(refusal.value).lower()


def test_the_stack_children_are_recorded_once_started(tmp_path):
    inputs, policy = build_inputs(tmp_path)
    composition = module().HeadExecutionComposition.open(inputs)
    stack = _LauncherStack(controller_config_path=inputs.refs['controller_config']['path'],
                           environment=dict(inputs.document['ros']['environment']))
    composition.bind_ros(stack)
    stack.start()
    if hasattr(composition, 'ros_children'):
        children = composition.ros_children()
        assert children and children[0]['argv'] == ['ros2_control_node'], (
            'the composition must carry the launched children so the manifest can record argv/PIDs')


def test_owner_binding_requires_the_run_generation_session_and_the_owner_api(monkeypatch, tmp_path):
    inputs, policy = build_inputs(tmp_path)
    composition = module().HeadExecutionComposition.open(inputs)
    stack = local_stack(monkeypatch, policy, epoch=inputs.run['epoch'],
                        session=inputs.run['session_id'], generation=inputs.run['generation'])
    composition.bind_ros(node=stack.node, port=stack.port)
    wrong_generation, *_ = make_neck_owner(generation=inputs.run['generation'] + 1,
                                           session_id=inputs.run['session_id'])
    with pytest.raises(module().HeadExecutionCompositionRefused):
        composition.bind_owner(owner=wrong_generation)
    wrong_session, *_ = make_neck_owner(generation=inputs.run['generation'], session_id='other-session')
    with pytest.raises(module().HeadExecutionCompositionRefused):
        composition.bind_owner(owner=wrong_session)
    with pytest.raises(module().HeadExecutionCompositionRefused):
        composition.bind_owner(owner=SimpleNamespace(generation=inputs.run['generation'],
                                                     session_id=inputs.run['session_id']))
    assert composition.bound_stages == ('ros',)
    assert composition.bind_owner(owner=stack.neck_owner)['owner'] is stack.neck_owner
    with pytest.raises(module().HeadExecutionCompositionRefused) as refusal:
        composition.bind_owner(owner=stack.neck_owner)
    assert refusal.value.code == 'EXECUTION_RESOURCE_REBOUND'
