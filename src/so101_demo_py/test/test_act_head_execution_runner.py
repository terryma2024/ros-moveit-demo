"""Directed production-runner regressions for binding, admission and retirement."""

import json

import pytest

from test_act_head_execution_composition import build_inputs
from test_act_head_execution_composition import observer_setup
import types
from test_act_head_local_runtime import Authority
from test_act_head_local_runtime import Revoker


DECLARATIONS = {
    'stop_declaration': {'trigger': 'OPERATOR_STOP', 'teardown_timeout_s': 1.},
    'seal_expectation': {'completion': True, 'artifacts': ['completion.json', 'seal.json']},
    'log_capture': {'stdout': 'pytest.stdout', 'stderr': 'pytest.stderr'},
    'fault_stop_probes': ['FAULT_PRIMARY'],
}


def declared_inputs(tmp_path):
    """build_inputs plus the four run declarations the closed schema requires before a run starts."""

    import importlib
    from test_act_head_execution_documents import CONFIG, write_config
    inputs, policy = build_inputs(tmp_path)
    inputs.document['refs']['development_config'] = write_config(tmp_path, CONFIG)
    # the material parses the report for its calibration bundle (CP-HFP-343/344), so this path
    # registers one as real JSON as well
    inputs.document['refs']['report'] = _register_report(tmp_path)
    inputs.refs['development_config'] = inputs.document['refs']['development_config']
    document = inputs.document
    document.update({name: json.loads(json.dumps(value)) for name, value in DECLARATIONS.items()})
    import hashlib as _hashlib
    root = inputs.document_path.parent / 'sealed-binding'
    root.mkdir(exist_ok=True)
    for name in ('binding', 'report'):
        # the report is the document the material parses for its calibration bundle, so it is written as real
        # JSON while binding keeps the placeholder its readers only take a path and digest from (CP-HFP-343/349)
        payload = _report_payload_for(tmp_path, document) if name == 'report' else json.dumps({'name': name}).encode()
        path = root / ('%s.json' % name)
        path.write_bytes(payload)
        document['refs'][name] = {'path': str(path),
                                  'sha256': _hashlib.sha256(payload).hexdigest()}
    snapshot = root / 'snapshot'
    snapshot.mkdir(exist_ok=True)
    document['snapshot_root'] = str(snapshot)
    inputs.document_path.write_text(json.dumps(document))
    module = importlib.import_module('so101_demo.act.head_execution_inputs')
    return module.HeadExecutionInputs.parse(inputs.document_path), policy


def runner_module():
    import importlib
    return importlib.import_module('so101_demo.cli.head_execution_runner')


def composition_module():
    import importlib
    return importlib.import_module('so101_demo.adapters.act.head_execution_composition')


class _Entry:
    """One handed-over constructor entry: a callable plus the keywords it needs."""

    def __init__(self, callable_, keywords):
        self.callable = callable_
        self.keywords = dict(keywords)


class _Capture:
    def __init__(self):
        self.sinks = []

    def bind_original_sink(self, sink):
        self.original_sink = sink

    def begin_live_capture(self):
        self.started = True

    def bind_live_sink(self, sink):
        self.sinks.append(sink)


class _Neck:
    def __init__(self):
        self.commands = []

    def command_neck(self, *arguments, **keywords):
        self.commands.append((arguments, keywords))


def _handle(monkeypatch, composition, inputs, *, capture=True, neck=True, settlement=True):
    """The handle the provider produces, with native/detector built by the runner itself."""

    row = observer_setup(monkeypatch, policy=composition.policy, bind_port_sink=False)
    from test_act_head_local_runtime import native_policy_receipt
    from so101_demo.adapters.act import head_native_policy_readback
    monkeypatch.setattr(head_native_policy_readback, 'read_native_policy',
                        lambda node, policy: native_policy_receipt(node, policy))
    stack = types.SimpleNamespace(node=row.node, port=row.port)
    built = {}

    def _construct(factory, rich_keywords, plain_keywords):
        """Build the fake with the rich keywords when it accepts them, else with the plain ones."""

        try:
            return factory(**rich_keywords)
        except TypeError:
            return factory(**plain_keywords)

    def make_authority(**keywords):
        built['authority'] = _construct(
            Authority,
            dict(arm_guard=keywords['arm_guard'], fault_callback=keywords['fault_callback'],
                 generation=inputs.run['generation'], session_id=inputs.run['session_id'],
                 controller_identity={'generation': inputs.run['generation'], 'incarnation': 'inc-1',
                                      'boot': 'boot-1'}),
            dict(arm_guard=keywords['arm_guard'], fault_callback=keywords['fault_callback']))
        return built['authority']

    def make_revoker(**keywords):
        built['revoker'] = _construct(Revoker, dict(generation=inputs.run['generation']), {})
        return built['revoker']

    handle = {
        'stack': stack,
        'controller_identity': {'generation': inputs.run['generation'], 'incarnation': 'inc-1',
                                'boot': 'boot-1'},
        'native_entry': {'callable': make_authority, 'keywords': {}},
        'revoker_entry': {'callable': make_revoker, 'keywords': {}},
        'detector_entry': {'callable': lambda **keywords: built.setdefault('detector', object()),
                           'keywords': {}},
    }
    if capture:
        handle['capture'] = _Capture()
    if neck:
        handle['neck'] = _Neck()
    if settlement:
        handle['settlement'] = lambda *arguments, **keywords: True
    return handle, stack, built


@pytest.mark.parametrize('missing,code', [
    ('capture', 'EXECUTION_RUNNER_SOURCE_ABSENT'),
    ('neck', 'EXECUTION_RUNNER_NECK_ABSENT'),
    ('settlement', 'EXECUTION_RUNNER_SETTLEMENT_ABSENT')])
def test_every_entry_supplied_resource_is_refused_before_construction(monkeypatch, tmp_path, missing, code):
    inputs, policy = declared_inputs(tmp_path)
    composition = composition_module().HeadExecutionComposition.open(inputs)
    handle, stack, built = _handle(monkeypatch, composition, inputs)
    handle.pop(missing)
    with pytest.raises(runner_module().HeadExecutionRunnerRefused) as refusal:
        runner_module().run_owned_search(composition, handle)
    assert refusal.value.code == code
    assert composition.bound_stages == ()
    assert built == {}


def test_a_composition_without_the_constructor_entries_is_refused(monkeypatch, tmp_path):
    inputs, policy = declared_inputs(tmp_path)
    composition = composition_module().HeadExecutionComposition.open(inputs)
    handle, stack, built = _handle(monkeypatch, composition, inputs)
    handle.pop('native_entry')
    with pytest.raises(runner_module().HeadExecutionRunnerRefused):
        runner_module().run_owned_search(composition, handle)
    assert composition.bound_stages == ()

class _FakeExposure:
    def __init__(self):
        self.frozen = 0
        self.observations = 0

    def observe(self, *arguments, **keywords):
        self.observations += 1

    def freeze_retirement(self):
        self.frozen += 1
        return {'frozen': True}


OWNERS = []


class _FakeOwner:
    """The owned inference thread, faked: it builds the detector through the factory and never blocks."""

    def __init__(self, *, factory, fault_callback, simulation_policy):
        self.factory = factory
        self.fault_callback = fault_callback
        self.simulation_policy = simulation_policy
        self._simulation_policy = simulation_policy  # the name the composition checks
        self.detector = None
        self.runtime_device = None
        self.closed = 0
        self.activated = 0
        self.requests = []
        OWNERS.append(self)

    def bind_live(self, binder, *, timeout_s=1.):
        self.detector = self.factory()
        self.runtime_device = 'cuda:0'
        exposure = binder(self.detector)
        exposure.frozen = 0
        self.exposure = exposure
        return exposure

    def activate_live(self):
        self.activated += 1

    def configuration(self, *, timeout_s=1.):
        return {'device': 'cuda:0'}

    def request_observation(self, request):
        self.requests.append(request)
        return len(self.requests)

    def next_completed_observation(self, *, timeout_s=1.):
        return None

    def close(self, *, timeout_s=1.):
        self.closed += 1
        return {'closed': True}


def test_model_startup_failure_still_retires_the_owner(monkeypatch, tmp_path):
    inputs, _ = declared_inputs(tmp_path)
    composition = composition_module().HeadExecutionComposition.open(inputs)
    handle, stack, _ = _handle(monkeypatch, composition, inputs)
    handle.pop('controller_identity')
    composition.bind_ros(node=stack.node, port=stack.port)

    class FailedOwner(_FakeOwner):
        def configuration(self, **kwargs):
            raise RuntimeError('controlled model initialization failure')

    OWNERS.clear()
    with pytest.raises(RuntimeError, match='controlled model initialization failure'):
        runner_module().run_owned_search(composition, handle, owner_factory=FailedOwner)
    assert len(OWNERS) == 1 and OWNERS[0].closed == 1
    assert OWNERS[0].activated == 0


@pytest.mark.parametrize('device',[None,'cpu','cuda:1'])
def test_runner_refuses_absent_or_wrong_owner_device_before_arm(monkeypatch,tmp_path,device):
    inputs,_=declared_inputs(tmp_path)
    composition=composition_module().HeadExecutionComposition.open(inputs)
    handle,stack,_=_handle(monkeypatch,composition,inputs)
    composition.bind_ros(node=stack.node,port=stack.port)
    class WrongDeviceOwner(_FakeOwner):
        def bind_live(self,binder,**kwargs):
            result=super().bind_live(binder,**kwargs)
            self.runtime_device=device
            return result
    OWNERS.clear()
    with pytest.raises(Exception,match='device|reports'):
        runner_module().run_owned_search(composition,handle,
            detector_loader=lambda *args:'binding',
            detector_builder=lambda *args,**kw:{'runtime':'detector'},
            owner_factory=WrongDeviceOwner,exposure_binder=lambda *args,**kw:_FakeExposure())
    assert composition.bound_stages==('ros','native')
    assert OWNERS[0].closed==1 and OWNERS[0].activated==0


def test_bound_loop_refuses_missing_originals_before_activation_and_retires(monkeypatch, tmp_path):
    inputs, policy = declared_inputs(tmp_path)
    docs = __import__('importlib').import_module('so101_demo.act.head_execution_documents')
    sealed = docs.load_search_config(inputs)
    composition = composition_module().HeadExecutionComposition.open(inputs)
    handle, stack, built = _handle(monkeypatch, composition, inputs)
    composition.bind_ros(node=stack.node, port=stack.port)
    exposures = []

    def exposure_binder(detector, **keywords):
        exposure = _FakeExposure()
        exposures.append((detector, exposure, keywords))
        return exposure

    class _Binding:
        def search_config(self, *, session_id, attempt_id, search_start_rad):
            return dict(sealed)

    # the fixture supplies no observation data, so the run must refuse while the loop starts rather
    # than tick blindly — and it must still retire whatever it built (CP-HFP-139)
    await_originals = runner_module()._await_originals
    monkeypatch.setattr(runner_module(), '_await_originals',
                        lambda observer, composition, **kw:
                        await_originals(observer, composition, timeout_s=.001))
    OWNERS.clear()
    with pytest.raises(Exception) as refusal:
        runner_module().run_owned_search(
            composition, handle, max_ticks=2,
            binding_loader=lambda *arguments: _Binding(),
            detector_loader=lambda *arguments: 'BINDING',
            detector_builder=lambda binding, *, snapshot_root: {'runtime': 'DETECTOR',
                                                                'runtime_device': 'cuda:0'},
            owner_factory=_FakeOwner, exposure_binder=exposure_binder)
    assert 'HEAD_LOCAL_OBSERVER_CLOCK_INVALID' in str(refusal.value), str(refusal.value)
    assert composition.bound_stages == ('ros', 'native', 'detector', 'inference', 'runtime', 'search')
    assert len(exposures) == 1, 'the detector the owner built is bound to exactly one exposure'
    assert callable(handle['capture'].original_sink)
    assert handle['capture'].sinks == [], 'startup refusal never enables live exposures'
    assert len(OWNERS) == 1, 'the run built exactly one owner'
    owner = OWNERS[-1]
    assert owner.closed == 1 and owner.activated == 0, 'the loop retires without activation'
    assert owner.exposure.frozen == 1, 'retirement freezes the exposure'
    assert owner.closed == 1, 'the refusal does not skip retirement'
    assert stack.port is not None

def _with_development_blocks(document):
    """Lift the flat fixture document's own controller fields into the blocks the plan shape uses.

    The fixtures declare their values at the top level, and the cases assert that the sealed configuration
    returns exactly those numbers (CP-HFP-304), so the blocks are built from the document — never from a
    reference config — and nothing the document declares is overridden (CP-HFP-294).
    """

    import json as _json
    from pathlib import Path as _Path

    reference = _Path(__file__).resolve().parents[1] / 'config/mujoco/act/head_search_v2.json'
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

def _register_report(tmp_path):
    """A report document carrying the values, the motion block and the calibration bundle the receipt names."""

    import hashlib as _hashlib
    import json as _json
    from pathlib import Path as _Path

    root = _Path(tmp_path)
    bundle = root / 'fixture-calibration-bundle.json'
    bundle.write_text(_json.dumps({'kind': 'head_search_calibration_bundle',
                                   'parameters': {'submit_lead_s': {'value': 0.004, 'unit': 's'},
                                                  'stop_latency_s': {'value': 0.07, 'unit': 's'},
                                                  'stop_velocity_rad_s': {'value': 0.041, 'unit': 'rad/s'},
                                                  'max_age_s': {'value': 0.0147, 'unit': 's'}}}))
    document = {'values': {name: 0.05 for name in
                           ('horizontal_fov_rad', 'coarse_step_rad', 'center_deadband_px',
                            'vertical_bounds_px', 'min_area_px2', 'min_confidence',
                            'max_fine_corrections', 'max_fine_total_rad', 'max_skew_s', 'max_age_s',
                            'search_timeout_s', 'stop_latency_s', 'stop_velocity_rad_s')},
                'motion': {'goal_tolerance_rad': 0.05, 'settle_velocity_rad_s': 0.05,
                           'neck_goal_duration_s': 0.5},
                'bundle': {'path': str(bundle)}}
    path = root / 'frozen' / 'report.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json.dumps(document).encode()
    path.write_bytes(payload)
    return {'path': str(path), 'sha256': _hashlib.sha256(payload).hexdigest()}

def _report_payload_for(tmp_path, document):
    """A report document with the values, the motion block and a bundle file that exists."""

    import json as _json
    from pathlib import Path as _Path

    bundle = _Path(tmp_path) / 'fixture-calibration-bundle.json'
    bundle.write_text(_json.dumps({'kind': 'head_search_calibration_bundle',
                                   'parameters': {'submit_lead_s': {'value': 0.004, 'unit': 's'},
                                                  'stop_latency_s': {'value': 0.07, 'unit': 's'},
                                                  'stop_velocity_rad_s': {'value': 0.041, 'unit': 'rad/s'},
                                                  'max_age_s': {'value': 0.0147, 'unit': 's'}}}))
    names = list((document.get('values') or {})) or ['search_timeout_s', 'stop_latency_s']
    values = {name: 0.05 for name in names}
    values.update({'search_timeout_s': 30.0, 'stop_latency_s': 1.0, 'max_age_s': 0.15})
    payload = {'values': values,
               'motion': {'goal_tolerance_rad': 0.05, 'settle_velocity_rad_s': 0.05,
                          'neck_goal_duration_s': 0.5},
               'bundle': {'path': str(bundle)}}
    return _json.dumps(payload).encode()


def test_runner_adapts_search_keyword_events_to_actual_runtime_writer(monkeypatch, tmp_path):
    inputs, _ = declared_inputs(tmp_path)
    composition = composition_module().HeadExecutionComposition.open(inputs)
    handle, stack, _ = _handle(monkeypatch, composition, inputs)
    composition.bind_ros(node=stack.node, port=stack.port)
    runner = runner_module()
    actual_search = runner.OwnedHeadSearch
    actual_emit = type(composition).emit
    delivered = []
    probe = {'decision': {'probe': 'keyword_fields'}}

    def capture_emit(owner, kind, record, **keywords):
        result = actual_emit(owner, kind, record, **keywords)
        if owner is composition and kind == 'SEARCH_INTERFACE_PROBE':
            delivered.append((record, keywords))
        return result

    def construct_search(**keywords):
        search = actual_search(**keywords)
        # Exercise the exact constructor callback supplied by the production
        # runner, through the actual typed runtime and bounded evidence writer.
        # This event declares a test interface probe, never motion or lock.
        search.emit('SEARCH_INTERFACE_PROBE', **probe)
        return search

    monkeypatch.setattr(type(composition), 'emit', capture_emit)
    monkeypatch.setattr(runner, 'OwnedHeadSearch', construct_search)
    await_originals = runner._await_originals
    monkeypatch.setattr(runner, '_await_originals', lambda observer, composition, **kw:
                        await_originals(observer, composition, timeout_s=.001))
    with pytest.raises(Exception, match='HEAD_LOCAL_OBSERVER_CLOCK_INVALID'):
        runner.run_owned_search(composition, handle, max_ticks=1,
            detector_loader=lambda *args: 'controlled detector binding',
            detector_builder=lambda *args, **kw: {'runtime': 'controlled detector'},
            owner_factory=_FakeOwner, exposure_binder=lambda *args, **kw: _FakeExposure())
    assert delivered == [(probe, {'source_stamp_ns': None, 'occurrence_mono_ns': None})]


def test_runner_adapts_live_exposure_keyword_events_to_actual_runtime_writer(monkeypatch, tmp_path):
    inputs, _ = declared_inputs(tmp_path)
    composition = composition_module().HeadExecutionComposition.open(inputs)
    handle, stack, _ = _handle(monkeypatch, composition, inputs)
    composition.bind_ros(node=stack.node, port=stack.port)
    runner = runner_module()
    actual_emit = type(composition).emit
    delivered = []
    probe = {'record': {'probe': 'live_keyword_fields'}}

    def capture_emit(owner, kind, record, **keywords):
        result = actual_emit(owner, kind, record, **keywords)
        if owner is composition and kind == 'LIVE_INTERFACE_PROBE':
            delivered.append((record, keywords))
        return result

    def bind_actual_exposure(detector, **keywords):
        exposure = runner._bind_exposure(detector, **keywords)
        exposure.emit('LIVE_INTERFACE_PROBE', **probe)
        # This unactivated object owns no worker or subscriptions. The runner
        # continues with its controlled retirement peer after the real callback
        # has reached the runtime writer; no live retirement is asserted here.
        return _FakeExposure()

    monkeypatch.setattr(type(composition), 'emit', capture_emit)
    await_originals = runner._await_originals
    monkeypatch.setattr(runner, '_await_originals', lambda observer, composition, **kw:
                        await_originals(observer, composition, timeout_s=.001))
    with pytest.raises(Exception, match='HEAD_LOCAL_OBSERVER_CLOCK_INVALID'):
        runner.run_owned_search(composition, handle, max_ticks=1,
            detector_loader=lambda *args: 'controlled detector binding',
            detector_builder=lambda *args, **kw: {'runtime': 'controlled detector'},
            owner_factory=_FakeOwner, exposure_binder=bind_actual_exposure)
    assert delivered == [(probe, {'source_stamp_ns': None, 'occurrence_mono_ns': None})]
