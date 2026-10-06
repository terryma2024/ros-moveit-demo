"""Original routing in the production execution composition."""

import hashlib
import json
from types import SimpleNamespace
import pytest

from rosgraph_msgs.msg import Clock

from test_act_head_execution_composition import build_inputs, module
from test_act_head_local_observer import observer_setup, joint_record
from test_act_head_stopped_capture import image, info


def test_drive_success_requests_stop_and_waits_for_callback_progress():
    from so101_demo.cli.head_execution_runner import _drive
    trace, stops = [], []
    outcomes = iter((None,dict(status='TARGET_LOCKED')))
    runtime = SimpleNamespace(start=lambda:trace.append('start'),arm=lambda:trace.append('arm'),
        faulted=False,stop_requested=False,policy=SimpleNamespace(watchdog_period_s=.02),
        _shutdown=SimpleNamespace(wait=lambda period:trace.append(('wait',period))),
        stop=lambda *a:stops.append(a),fault=lambda *a:trace.append(('fault',a)))
    result = _drive(SimpleNamespace(emit=lambda *a:None),SimpleNamespace(tick=lambda:next(outcomes)),
        runtime,SimpleNamespace(activate_live=lambda:trace.append('activate')),
        SimpleNamespace(bind_live_sink=lambda *a:trace.append('live')),
        SimpleNamespace(observe=lambda *a:None),3,after_arm=lambda:trace.append('prepared'))
    assert result == 0 and stops[0][0] == 'success'
    assert trace == ['start','arm','prepared','live','activate',('wait',.02)]


def test_drive_binding_failure_faults_before_live_camera_or_inference():
    from so101_demo.cli.head_execution_runner import _drive
    import pytest
    trace = []
    runtime = SimpleNamespace(start=lambda:None,arm=lambda:None,
                              fault=lambda reason:trace.append(reason))
    def refused(): raise PermissionError('prepared binding refused')
    with pytest.raises(PermissionError):
        _drive(None,None,runtime,SimpleNamespace(activate_live=lambda:trace.append('activate')),
            SimpleNamespace(bind_live_sink=lambda *a:trace.append('live')),None,1,after_arm=refused)
    assert trace == ['HEAD_EXECUTION_TRAJECTORY_BINDING_FAILED']


@pytest.mark.parametrize('reset_time_s,valid', [
    (0., True), (2.07, True), (-1., False), (float('nan'), False),
    (float('inf'), False), (True, False), ('2.07', False), (None, False)])
def test_paused_verified_reset_clears_only_unused_diagnostic_source_floors(monkeypatch, tmp_path, reset_time_s, valid):
    from so101_demo.adapters.act.head_execution_reset import rebase_startup_originals
    from so101_demo.adapters.act.head_stopped_capture import StoppedHeadCapture
    row = observer_setup(monkeypatch, bind_port_sink=False)
    update = lambda message: None
    row.node._time_source = SimpleNamespace(ros_time_is_active=True,clock_callback=update,
        _clock_sub=SimpleNamespace(callback=update,topic_name='/clock'))
    capture = StoppedHeadCapture(row.node,row.port,frame_id='head_camera_frame',strict=False)
    row.port._head_source_watermark = 90_000_000_000
    capture._last = dict(CLOCK=90_000_000_000)
    proof = dict(paused=True,simulation_step=0,simulation_time_s=reset_time_s,reset_epoch=3)
    if not valid:
        with pytest.raises(ValueError, match='HEAD_RESET_ORIGINAL_BOUNDARY_INVALID'):
            rebase_startup_originals(capture,row.port,proof)
        assert capture._last == dict(CLOCK=90_000_000_000)
        assert row.port._head_source_watermark == 90_000_000_000
        return
    rebase_startup_originals(capture,row.port,proof)
    assert capture._last == {} and row.port._head_source_watermark is None
    capture.bind_original_sink(lambda *a: None)
    with pytest.raises(PermissionError): rebase_startup_originals(capture,row.port,proof)


def test_execution_routes_raw_originals_and_payload_without_measurement_window(monkeypatch, tmp_path):
    """A missing capture/port route must leave observer inputs and file evidence incomplete."""
    from so101_demo.cli import head_execution_runner as runner
    from so101_demo.adapters.act.head_stopped_capture import StoppedHeadCapture

    row = observer_setup(monkeypatch, camera_frame='head_camera_frame', bind_port_sink=False)
    update = lambda message: None
    row.node._time_source = SimpleNamespace(ros_time_is_active=True, clock_callback=update,
        _clock_sub=SimpleNamespace(callback=update, topic_name='/clock'))
    capture = StoppedHeadCapture(row.node, row.port, frame_id='head_camera_frame',
                                 monotonic=row.clock.monotonic)
    inputs, _ = build_inputs(tmp_path, policy=row.policy)
    composition = module().HeadExecutionComposition.open(inputs)
    progress = []
    runtime = SimpleNamespace(executor_progress=lambda: progress.append(True))
    try:
        runner._bind_originals(composition, capture, row.port, row.observer, runtime)
        # More than the former pending measurement capacity, without declaring,
        # sleeping through, or sealing a twenty-second calibration window.
        for sequence in range(1, 41):
            source = 1_000_000_000 + sequence * 10_000_000
            row.clock.sim = source * 1e-9
            row.clock.wall += .01
            clock = Clock()
            clock.clock.sec, clock.clock.nanosec = divmod(source, 1_000_000_000)
            capture._clock(clock)
            row.port._head_original_sink('JOINT', joint_record(
                row.clock, source * 1e-9, sequence=sequence))
            capture._image(image(source))
            capture._info(info(source))
            current = row.observer.current_inputs(row.clock.wall)
            assert current['camera_pair']['source_ns'] == source
            assert current['joint']['sequence'] == sequence
            capture.check()
        assert len(progress) >= 40
        assert not row.state.faulted
        assert capture._window is None
        live = []
        capture.bind_live_sink(lambda kind, record, **kw: live.append(kind))
        capture._image(image(source + 10_000_000))
        capture._info(info(source + 10_000_000))
        assert live == ['IMAGE', 'INFO']
    finally:
        composition.writer.finish({'execution': 'FAILED', 'reason': 'no-motion regression'})
    events = [json.loads(line) for line in (inputs.run_root / 'events.jsonl').read_text().splitlines()]
    for kind in ('CLOCK', 'JOINT', 'IMAGE', 'INFO'):
        originals = [event for event in events if event['kind'] == kind]
        assert len(originals) >= 40
        assert originals[0]['record']['source_ns'] == 1_010_000_000
        assert originals[0]['source_stamp_ns'] == 1_010_000_000
    payload_events = [event for event in events if event['kind'] == 'IMAGE_PAYLOAD']
    assert len(payload_events) == 41
    for event in payload_events:
        ref, = event['artifact_refs']
        raw = (inputs.run_root / ref['path']).read_bytes()
        assert raw == bytes(640 * 480 * 3)
        assert hashlib.sha256(raw).hexdigest() == ref['sha256']


def test_drive_does_not_activate_inference_after_real_prearm_refusal(monkeypatch):
    """Invalid originals must stop startup at arm, before inference activation."""
    import pytest
    from so101_demo.cli import head_execution_runner as runner
    from test_act_head_execution_composition import local_stack
    from test_act_head_local_observer import simulation_policy

    stack = local_stack(monkeypatch, simulation_policy())
    from test_act_head_local_runtime import native_policy_receipt
    stack.runtime.bind_native_policy_readback(native_policy_receipt(stack.node, stack.runtime.policy))
    activated = []
    capture = SimpleNamespace(bind_live_sink=lambda sink: None)
    exposure = SimpleNamespace(observe=lambda *a, **k: None)
    owner = SimpleNamespace(activate_live=lambda: activated.append(True))
    try:
        with pytest.raises(PermissionError, match='HEAD_LOCAL_RUNTIME_ORIGINALS_INVALID'):
            runner._drive(None, stack.search, stack.runtime, owner, capture, exposure, 1)
        assert activated == []
        assert stack.runtime.armed is False
    finally:
        stack.runtime.close(timeout_s=1.)


def test_startup_timeout_reports_the_first_missing_original(monkeypatch):
    import pytest
    from so101_demo.cli import head_execution_runner as runner
    row = observer_setup(monkeypatch, bind_port_sink=False)
    events = []
    composition = SimpleNamespace(emit=lambda kind, record: events.append((kind, record)))
    with pytest.raises(runner.HeadExecutionRunnerRefused, match='HEAD_LOCAL_OBSERVER_CLOCK_INVALID'):
        runner._await_originals(row.observer, composition, timeout_s=.001)
    assert events[-1][1]['first_error'] == 'HEAD_LOCAL_OBSERVER_CLOCK_INVALID'
    assert row.state.faulted is False
