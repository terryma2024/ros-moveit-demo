"""Disabled Head logging performs no evidence work and retains control fences."""

import json
import secrets
import sys
import threading

import pytest

from test_act_head_execution_composition import build_inputs, local_stack, module
from test_act_head_inventory_dispatch import composed
from test_act_head_search_restarts import socket_root
from test_act_head_paused_admission import paused_head, command
from test_act_head_trajectory_guard import guard
from test_act_head_revocation import native_server, ack
from test_act_head_execution_native import child


def logging_inputs(tmp_path, enabled):
    inputs, policy = build_inputs(tmp_path)
    document = json.loads(inputs.document_path.read_text())
    document['event_log_enabled'] = enabled
    inputs.document_path.write_text(json.dumps(document))
    from so101_demo.act.head_execution_inputs import HeadExecutionInputs
    return HeadExecutionInputs.parse(inputs.document_path), policy


def bind_all(composition, monkeypatch):
    inputs = composition.inputs
    stack = local_stack(monkeypatch, composition.policy, epoch=inputs.run['epoch'],
                        session=inputs.run['session_id'], generation=inputs.run['generation'])
    composition.bind_ros(node=stack.node, port=stack.port)
    composition.bind_native(authority=stack.authority, revoker=stack.revoker)
    composition.bind_detector(object(), runtime_device='cuda:0')
    composition.bind_inference(stack.owner)
    composition.bind_runtime(observer=stack.observer, runtime=stack.runtime)
    composition.bind_search(stack.search)
    return stack


def test_old_inputs_default_to_logging_on(tmp_path):
    inputs, _ = build_inputs(tmp_path)
    assert inputs.event_log_enabled is True


@pytest.mark.parametrize('value', [None, 0, 1, 'false', [], {}])
def test_logging_flag_refuses_non_booleans(tmp_path, value):
    from so101_demo.act.head_execution_inputs import HeadExecutionInputsRefused
    with pytest.raises(HeadExecutionInputsRefused, match='event_log_enabled'):
        logging_inputs(tmp_path, value)


def test_off_opens_no_writer_or_manifest_and_closes_without_a_seal(tmp_path, monkeypatch):
    inputs, _ = logging_inputs(tmp_path, False)
    threads = set(threading.enumerate())
    composition = module().HeadExecutionComposition.open(inputs)
    assert composition.writer is None
    assert set(threading.enumerate()) == threads
    assert not inputs.run_root.exists()
    stamps = []
    composition.monotonic_ns = lambda: stamps.append(True) or 100
    bind_all(composition, monkeypatch)
    assert stamps == []
    composition.begin_resource_lifetime('producer')
    with pytest.raises(module().HeadExecutionCompositionRefused, match='UNRETIRED'):
        composition.seal({'execution': 'SUCCEEDED', 'business_return_code': 0})
    composition.finish_resource_lifetime('producer', confirmed=True)
    result = composition.seal({'execution': 'SUCCEEDED', 'business_return_code': 0})
    assert result['business_return_code'] == 0
    assert result['file_evidence_generated'] is False
    assert composition.sealed is None and composition.closed is True
    assert composition.readback()['event_log_enabled'] is False
    assert composition.readback()['sealed'] is False
    assert not inputs.run_root.exists()
    with pytest.raises(module().HeadExecutionCompositionRefused, match='CLOSED'):
        composition.bind_ros()


@pytest.mark.parametrize('outcome', [0, 1])
def test_off_cli_keeps_business_outcome_without_file_acceptance(tmp_path, monkeypatch, capsys, outcome):
    from so101_demo.cli.head_execution_run import main
    inputs, _ = logging_inputs(tmp_path, False)

    def provider(composition, verified):
        assert verified.event_log_enabled is False
        bind_all(composition, monkeypatch)
        return outcome

    assert main(['--execution-inputs', str(inputs.document_path), '--print-readback'],
                provider=provider) == outcome
    view = json.loads(capsys.readouterr().out)
    assert view['closed'] is True and view['sealed'] is False
    assert view['file_evidence_generated'] is False
    assert not inputs.run_root.exists()


def test_off_router_delivers_invalid_original_without_an_audit_copy(monkeypatch):
    from test_act_head_local_observer import observer_setup
    from so101_demo.adapters.act.head_original_router import HeadOriginalRouter
    import so101_demo.adapters.act.head_original_router as router_module
    row = observer_setup(monkeypatch, bind_port_sink=False)
    router = HeadOriginalRouter(row.port, None)
    router.bind_primary(row.observer)
    copied = []
    real_copy = router_module.deepcopy

    def count_copy(value):
        copied.append(value)
        return real_copy(value)

    monkeypatch.setattr(router_module, 'deepcopy', count_copy)
    original = dict(source_ns=1_000_000_000, wall_s=10., valid=False, sequence=1,
                    positions=[0.], velocities=[])
    try:
        router('JOINT', original)
        assert row.observer.local_state.faulted and row.observer.failed
        assert len(copied) == 1  # the owned observer's copy, no audit copy
    finally:
        row.observer.close()
        row.port.close_head_io(timeout_s=1.)


def test_off_child_capture_creates_no_log_handle_or_file(tmp_path):
    from so101_demo.act.head_execution_stack import RestartStack
    stack = RestartStack(controller_config_path=tmp_path/'controller.yaml', environment={},
                         urdf_path=tmp_path/'robot.urdf', scene_path=tmp_path/'scene.xml',
                         plugin_config_path=tmp_path/'plugins.yaml', workspace=tmp_path,
                         session_id='off-child', event_log_enabled=False, teardown_timeout_s=1.)
    stack.log_path = tmp_path/'child.log'
    child = stack._spawn([sys.executable, '-c', 'print("child output")'], 'test-child')
    stack.processes.append(child)
    try:
        assert child.wait(timeout=2.) == 0
        assert stack.handles == [] and not stack.log_path.exists()
        assert stack.stop()['closed'] is True
    finally:
        stack.stop()


def test_off_runtime_fault_and_stop_never_call_record(monkeypatch):
    from test_act_head_local_runtime import runtime_setup
    row = runtime_setup(monkeypatch)
    row.runtime._sink = None
    calls = []
    row.runtime.record = lambda *args, **kwargs: calls.append((args, kwargs))
    try:
        row.runtime.fault('OFF_REAL_FAULT')
        assert row.runtime.local_state.faulted and row.runtime.stop_requested
        assert row.runtime.fault_reason == 'OFF_REAL_FAULT'
        row.runtime.stop('signal')
        assert calls == []
    finally:
        row.runtime.close(timeout_s=1.)


def test_off_stopped_inference_keeps_causal_result_without_audit_traces(monkeypatch):
    from test_act_head_local_stopped_exposure import exposure_setup, prime_exposure, stopped_request
    local = exposure_setup(monkeypatch)
    from so101_demo.cli.head_execution_runner import _bind_exposure
    local.runtime._sink = None
    local.exposures = _bind_exposure(local.detector, port=local.row.port,
                                    primary=local.runtime, policy=local.row.policy,
                                    buffer=local.buffer)
    local.exposures.activate()
    import so101_demo.adapters.act.head_live_exposure as exposure_module
    hashes = []
    actual_digest = exposure_module.digest

    def count_digest(value):
        hashes.append(value)
        return actual_digest(value)

    monkeypatch.setattr(exposure_module, 'digest', count_digest)
    try:
        settled, _ = prime_exposure(local)
        request = stopped_request(local.row, settled_wall_s=settled)
        result = local.exposures.infer(observation_request=request)
        assert result['observation_outcome'] == 'VALID'
        assert result['observation_sequence'] == 1 and len(local.detector.calls) == 1
        assert local.exposures.next_completed_observation(0)['source_ns'] == result['source_ns']
        assert local.exposures._original_attempts is None
        assert not local.runtime._inference_deadlines
        assert hashes == []
    finally:
        local.runtime.close(timeout_s=1.)
        local.exposures.close()


def test_off_dispatch_still_owns_exact_cdr_before_native_and_sdk(composed):
    from test_act_head_inventory_dispatch import send_target
    from so101_demo.adapters.act.head_inventory_dispatch import HeadInventoryDispatcher
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config, emit=None)
    gid = send_target(sender, config)
    assert events == ['OWN_INVENTORY', 'NATIVE_RESERVE', 'SDK_SEND']
    assert not faults and len(owned) == 1
    assert sender.inventory[gid]['payload_sha256'] == owned[0][0]['payload_sha256']
    assert sender.local_state.prepared_cdr(gid) == owned[0][1]
    assert sender.dispatch_traces == ()
    assert 'sdk_dispatch_wall_s' not in config['port']._goals[gid]
    assert 'sdk_returned_wall_s' not in config['port']._goals[gid]


def test_off_original_delivery_keeps_executor_progress_and_has_no_rgb_sink(tmp_path, monkeypatch):
    from so101_demo.cli.head_execution_runner import _bind_originals
    from test_act_head_execution_runner import _Capture
    inputs, _ = logging_inputs(tmp_path, False)
    composition = module().HeadExecutionComposition.open(inputs)
    from test_act_head_local_observer import observer_setup
    row = observer_setup(monkeypatch, bind_port_sink=False)
    capture = _Capture()
    progress = []
    from types import SimpleNamespace
    router = _bind_originals(composition, capture, row.port, row.observer,
                             SimpleNamespace(executor_progress=lambda: progress.append(True)))
    try:
        assert capture.emit is None and router.sink is None
        router('CLOCK', dict(source_ns=1_000_000_000, wall_s=10., valid=True))
        assert progress == [True] and row.observer._clock['source_ns'] == 1_000_000_000
        assert not inputs.run_root.exists()
    finally:
        row.observer.close()
        row.port.close_head_io(timeout_s=1.)


def test_off_search_locks_on_fresh_frames_without_observation_audit_history():
    from test_act_head_owned_search import driver, exposure
    row = driver()
    row.search.emit = None
    for sequence in (1, 2, 3):
        row.rows.append(exposure(sequence))
        row.clock[0] = row.rows[-1]['image_received_wall_s'] + .01
        result = row.search.tick()
    assert result['status'] == 'TARGET_LOCKED' and row.search.controller.lock_count == 3
    assert row.sent == [] and row.search.observations == []


def test_off_prepared_neck_keeps_uuid_and_resume_without_trace_encoding(paused_head, monkeypatch):
    case = paused_head
    case.scene.emit = None
    case.dispatcher._emit = None
    reads = []
    actual_trace_property = type(case.dispatcher).dispatch_traces

    def count_traces(owner):
        reads.append(True)
        return actual_trace_property.__get__(owner)

    monkeypatch.setattr(type(case.dispatcher), 'dispatch_traces', property(count_traces))
    gid = command(case)
    assert case.neck._goals == [gid] and gid in case.row.state.inventory
    assert [row[0] for row in case.events] == ['pause', 'NATIVE_RESERVE', 'SDK_SEND', 'pause']
    assert case.state['paused'] is False and not case.row.runtime.faulted
    assert reads == []


@pytest.mark.parametrize('channel', ['main', 'revoker'])
@pytest.mark.parametrize('valid_ack', [True, False])
@pytest.mark.skipif(sys.platform != 'linux', reason='native Head transport requires Linux peer credentials')
def test_off_native_close_keeps_ack_validation_without_exchange_audit(native_server, channel, valid_ack):
    path, owner, process = native_server(ack(5 if valid_ack else 6))
    keywords = dict(capability=secrets.token_bytes(32), native_owner=owner,
                    generation=5, event_log_enabled=False)
    if channel == 'main':
        from so101_demo.adapters.act.head_reservation_authority import HeadReservationAuthority
        path.rename(path.parent / 'neck.sock')
        faults = []
        client = HeadReservationAuthority(directory=path.parent, session_id='session',
            arm_guard=lambda: True, fault_callback=faults.append, **keywords)
        client._armed.add('neck')
        close = client.close
        audit = client._channel
    else:
        from so101_demo.adapters.act.head_revocation import NativeRevocationClient
        from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
        client = NativeRevocationClient(path, timeout_s=.05,
            simulation_policy=HeadSimulationPolicy.default_document(), **keywords)
        close = client.close_strict
        audit = client
    if valid_ack:
        receipt = close()
        assert receipt['ack_validated'] and receipt['native_owner'] == owner
        assert 0 <= receipt['ack_wall_s'] - receipt['request_wall_s'] <= .05
    else:
        with pytest.raises((PermissionError, RuntimeError)):
            close()
        if channel == 'main':
            assert faults and client._registration_failed
    assert process.stdout.readline() == 'RECEIVED\n'
    assert audit.exchange_trace is None
    if channel == 'main':
        assert client.exchange_receipts == ()


@pytest.mark.skipif(sys.platform != 'linux', reason='native Head provisioning requires Linux procfs')
def test_off_native_provisions_still_bind_owned_child_without_receipt_hashes(tmp_path, child, monkeypatch):
    from types import SimpleNamespace
    from test_act_head_execution_native import scoped_inputs, native_module
    inputs, policy, directory = scoped_inputs(tmp_path)
    inputs.document['event_log_enabled'] = False
    process = child(inputs.document['ros']['environment'])
    stack = SimpleNamespace(processes=[process], environment=inputs.document['ros']['environment'])
    native = native_module()
    hashes = []
    actual = native.hashlib.sha256
    monkeypatch.setattr(native, 'hashlib', SimpleNamespace(
        sha256=lambda data: (hashes.append(True), actual(data))[1]))
    pair = native.provision_owned_native(inputs, stack, policy)
    assert pair['native_keywords']['native_owner']['pid'] == process.pid
    assert pair['native_keywords']['capability'] != pair['revoker_keywords']['capability']
    assert (directory / 'neck.provision').is_file()
    assert (directory / 'neck-primary-revoke.provision').is_file()
    assert pair['provision_receipts'] == {} and hashes == []
