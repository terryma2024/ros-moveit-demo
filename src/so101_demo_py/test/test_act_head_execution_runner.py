"""Directed production-runner regressions for binding, admission and retirement."""

import json

import pytest

from test_act_head_execution_composition import build_inputs
from test_act_head_execution_composition import observer_setup
import types
from head_owner_support import deadline, make as make_neck_owner


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
    """The handle the provider produces: the activated neck owner is the provider's, the detector the runner's."""

    row = observer_setup(monkeypatch, policy=composition.policy, bind_port_sink=False)
    stack = types.SimpleNamespace(node=row.node, port=row.port)
    built = {}
    neck_owner, *_ = make_neck_owner(policy=composition.policy, generation=inputs.run['generation'],
                                     session_id=inputs.run['session_id'], auto_window=True)
    neck_owner.activate(deadline=deadline())
    built['neck_owner'] = neck_owner
    handle = {
        'stack': stack,
        'neck_owner': neck_owner,
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
    assert set(built) == {'neck_owner'}, 'only the provider-built owner exists; the runner constructed nothing'


def test_a_handle_without_the_neck_owner_is_refused(monkeypatch, tmp_path):
    inputs, policy = declared_inputs(tmp_path)
    composition = composition_module().HeadExecutionComposition.open(inputs)
    handle, stack, built = _handle(monkeypatch, composition, inputs)
    handle.pop('neck_owner')
    with pytest.raises(runner_module().HeadExecutionRunnerRefused) as refusal:
        runner_module().run_owned_search(composition, handle)
    assert refusal.value.code == 'EXECUTION_RUNNER_OWNER_ABSENT'
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
    assert composition.bound_stages==('ros','owner')
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
    assert composition.bound_stages == ('ros', 'owner', 'detector', 'inference', 'runtime', 'search')
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


@pytest.mark.parametrize('phase',['readback','window','after_arm','capture'])
def test_runner_real_sigterm_startup_never_activates_owner(monkeypatch,phase):
    import signal,threading
    from test_act_head_local_runtime import runtime_setup,prime_current_inputs
    row=runtime_setup(monkeypatch);prime_current_inputs(row)
    seen=[];calls=[]
    original_arm=row.runtime.arm
    def observe_arm(*,cancel_event=None):
        assert isinstance(cancel_event,threading.Event)
        seen.append(cancel_event)
        return original_arm(cancel_event=cancel_event)
    monkeypatch.setattr(row.runtime,'arm',observe_arm)
    original_readback=row.owner.readback;original_window=row.owner.startup_stop_window
    def readback(**kwargs):
        reply=original_readback(**kwargs)
        if phase=='readback':signal.raise_signal(signal.SIGTERM)
        return reply
    def window(**kwargs):
        reply=original_window(**kwargs)
        if phase=='window':signal.raise_signal(signal.SIGTERM)
        return reply
    monkeypatch.setattr(row.owner,'readback',readback)
    monkeypatch.setattr(row.owner,'startup_stop_window',window)
    def after_arm():
        calls.append('after_arm')
        if phase=='after_arm':signal.raise_signal(signal.SIGTERM)
    def capture(sink):
        calls.append('capture')
        if phase=='capture':signal.raise_signal(signal.SIGTERM)
    owner=types.SimpleNamespace(activate_live=lambda:calls.append('activate'))
    composition=types.SimpleNamespace(event_log_enabled=True,emit=lambda *args:None)
    search=types.SimpleNamespace(tick=lambda:calls.append('tick'))
    try:
        assert runner_module()._drive(composition,search,row.runtime,owner,
            types.SimpleNamespace(bind_live_sink=capture),types.SimpleNamespace(observe=lambda *args:None),
            1,after_arm=after_arm)==1
        assert seen and seen[0].is_set()
        assert 'activate' not in calls and 'tick' not in calls
        assert row.runtime.stop_receipt()['stop_origin_kind']=='sigterm'
        assert not row.runtime.faulted
    finally:
        row.runtime.close(timeout_s=1.);row.owner.close()


@pytest.mark.parametrize('boundary',['readback','graph','window','identity'])
def test_runner_real_sigterm_and_failed_exchange_preserves_operator_stop(monkeypatch,boundary):
    import signal
    from test_act_head_local_runtime import runtime_setup,prime_current_inputs,wait_for
    row=runtime_setup(monkeypatch);prime_current_inputs(row);calls=[]
    def refused(*args,**kwargs):
        signal.raise_signal(signal.SIGTERM)
        raise OSError('channel disconnected')
    name={'readback':'readback','graph':'graph_proof','window':'startup_stop_window','identity':'identity'}[boundary]
    monkeypatch.setattr(row.owner,name,refused)
    composition=types.SimpleNamespace(event_log_enabled=True,emit=lambda *args:calls.append(args))
    try:
        assert runner_module()._drive(composition,types.SimpleNamespace(tick=lambda:calls.append('tick')),
            row.runtime,types.SimpleNamespace(activate_live=lambda:calls.append('activate')),
            types.SimpleNamespace(bind_live_sink=lambda *args:None),types.SimpleNamespace(observe=lambda *args:None),1)==1
        assert not row.runtime.faulted and not row.runtime.ready
        assert row.runtime.stop_receipt()['stop_origin_kind']=='sigterm'
        assert 'activate' not in calls and 'tick' not in calls
        assert any(isinstance(c,tuple) and c[0]=='EXECUTION_OPERATOR_TERMINAL' for c in calls)
        assert wait_for(lambda:row.closed_count()==1), 'the operator stop latches the controller'
    finally:
        row.runtime.close(timeout_s=1.);row.owner.close()


def test_earlier_fault_survives_later_startup_sigterm(monkeypatch):
    import signal
    from test_act_head_local_runtime import runtime_setup,prime_current_inputs
    row=runtime_setup(monkeypatch);prime_current_inputs(row)
    def failed(*args,**kwargs):
        row.runtime.fault('EARLIER_OWNER_FAULT')
        origin=row.runtime.local_state.fault_occurrence_ns
        signal.raise_signal(signal.SIGTERM)
        row.runtime.fault('HEAD_NECK_LATE_FAULT')
        assert row.runtime.local_state.fault_occurrence_ns==origin
        raise OSError('cancelled exchange')
    monkeypatch.setattr(row.owner,'readback',failed)
    try:
        assert runner_module()._drive(types.SimpleNamespace(event_log_enabled=False),None,row.runtime,
            types.SimpleNamespace(activate_live=lambda:pytest.fail('activated')),
            types.SimpleNamespace(bind_live_sink=lambda *args:None),None,1)==1
        assert row.runtime.faulted and row.runtime.fault_reason=='EARLIER_OWNER_FAULT'
        assert row.runtime.stop_receipt()['stop_origin_kind']=='fault'
        assert not row.runtime.ready
    finally:
        row.runtime.close(timeout_s=1.);row.owner.close()
