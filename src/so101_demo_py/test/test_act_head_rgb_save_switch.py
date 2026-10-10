"""Unselected camera payloads must not enter detection-only evidence."""

import json
import time
from types import SimpleNamespace

import pytest

from test_act_head_execution_composition import build_inputs, module
from test_act_head_local_stopped_exposure import (
    exposure_setup, prime_current_inputs, prime_exposure, stopped_request)


class StoragePolicyClock:
    """Isolate storage selection from host scheduling; resume for shutdown."""

    def __init__(self):
        self.sim = 10.0
        self.frozen_ns = time.monotonic_ns()
        self.running = False

    @property
    def wall(self):
        return self.monotonic()

    def monotonic(self):
        if self.running:
            return time.monotonic()
        self.frozen_ns += 1000
        return self.frozen_ns * 1e-9

    def monotonic_ns(self):
        return time.monotonic_ns() if self.running else self.frozen_ns


def rgb_inputs(tmp_path, value=None, *, omitted=False, logging=True):
    from so101_demo.act.head_execution_inputs import HeadExecutionInputs
    inputs, _ = build_inputs(tmp_path)
    document = json.loads(inputs.document_path.read_text())
    document['event_log_enabled'] = logging
    if not omitted:
        document['save_all_rgb_frames'] = value
    inputs.document_path.write_text(json.dumps(document))
    return HeadExecutionInputs.parse(inputs.document_path)


def test_omitted_rgb_flag_defaults_to_detection_only(tmp_path):
    inputs = rgb_inputs(tmp_path, omitted=True)
    assert inputs.save_all_rgb_frames is False
    assert inputs.readback()['save_all_rgb_frames'] is False


@pytest.mark.parametrize('value', [None, 0, 1, 'false', [], {}])
def test_rgb_flag_rejects_non_boolean_values(tmp_path, value):
    from so101_demo.act.head_execution_inputs import HeadExecutionInputsRefused
    with pytest.raises(HeadExecutionInputsRefused, match='save_all_rgb_frames'):
        rgb_inputs(tmp_path, value)


@pytest.mark.parametrize('logging,all_frames', [
    (True, True), (True, False), (True, None),
    (False, True), (False, False), (False, None)])
def test_capture_sink_obeys_both_modes_without_disabling_originals(tmp_path, monkeypatch,
                                                                  logging, all_frames):
    from types import SimpleNamespace
    from so101_demo.cli.head_execution_runner import _bind_originals
    from test_act_head_execution_runner import _Capture
    from test_act_head_local_observer import observer_setup
    inputs = rgb_inputs(tmp_path, all_frames, omitted=all_frames is None,
                        logging=logging)
    effective_all_frames = all_frames is True
    composition = module().HeadExecutionComposition.open(inputs)
    row = observer_setup(monkeypatch, bind_port_sink=False)
    capture = _Capture()
    try:
        router = _bind_originals(composition, capture, row.port, row.observer,
                                 SimpleNamespace(executor_progress=lambda: None))
        assert callable(capture.emit) is (logging and effective_all_frames)
        assert callable(capture.detection_image_recorder) is (logging and not effective_all_frames)
        router('CLOCK', dict(source_ns=1_000_000_000, wall_s=10., valid=True))
        assert row.observer._clock['source_ns'] == 1_000_000_000
        assert (composition.writer is not None) is logging
        if logging and effective_all_frames:
            # Capture callbacks save both originals without any detector call.
            for source_ns, payload in [(1_020_000_000, b'first RGB'),
                                       (1_040_000_000, b'second RGB')]:
                capture.emit('IMAGE', record=dict(source_ns=source_ns, wall_s=10.),
                             payload=payload)
        if not logging:
            assert not inputs.run_root.exists()
    finally:
        row.observer.close()
        row.port.close_head_io(timeout_s=1.)
        if composition.writer is not None:
            composition.writer.finish({'test': 'done'})
    if logging and effective_all_frames:
        events = [json.loads(line) for line in
                  (inputs.run_root / 'events.jsonl').read_text().splitlines()]
        images = [event for event in events if event['kind'] == 'IMAGE_PAYLOAD']
        assert [event['source_stamp_ns'] for event in images] == [
            1_020_000_000, 1_040_000_000]
        assert len(images) == 2


@pytest.mark.parametrize('outcome', ['empty', 'detector_error', 'expired'])
def test_detection_mode_retains_only_payloads_that_enter_detection(tmp_path, monkeypatch, outcome):
    from so101_demo.adapters.act.head_live_exposure import HeadLiveExposures
    from so101_demo.act import head_local_state
    clock = StoragePolicyClock()
    # The fault origin must share the observer/runtime clock domain too.
    monkeypatch.setattr(head_local_state, 'time',
                        SimpleNamespace(monotonic_ns=clock.monotonic_ns))
    local = exposure_setup(monkeypatch, clock=clock)
    local.runtime.clock_ns = clock.monotonic_ns
    saved = []

    def save_image(kind, *, record, payload):
        # This external disk sink replaces only I/O. Admission and inference
        # selection exercise the actual exposure implementation.
        path = tmp_path / (str(record['source_ns']) + '.rgb')
        path.write_bytes(payload)
        saved.append((kind, record, path))

    old = local.exposures
    local.exposures = HeadLiveExposures(port=old.port, buffer=old.buffer,
        detector=old.detector, primary=old.primary, monitor=None,
        camera_skew_s=.02, emit=old.emit, image_recorder=save_image)
    local.exposures.activate()

    def detect(*args, **kwargs):
        if outcome == 'detector_error':
            raise RuntimeError('detector failed')
        return []

    local.detector.detect = detect
    try:
        prime_current_inputs(local.row)
        settled_wall, payload = prime_exposure(local,
            final_sim=10.35 if outcome == 'expired' else None)
        assert saved == []  # Camera delivery itself produces no RGB artifact.
        request = stopped_request(local.row, settled_wall_s=settled_wall - .02,
                                  requested_wall_s=settled_wall - .01)
        if outcome == 'detector_error':
            with pytest.raises(RuntimeError, match='detector failed'):
                local.exposures.infer(observation_request=request)
        else:
            result = local.exposures.infer(observation_request=request)
            assert result['inference_performed'] is (outcome != 'expired')
        assert len(saved) == (0 if outcome == 'expired' else 1)
        if saved:
            kind, record, path = saved[0]
            assert kind == 'IMAGE'
            # prime_current_inputs establishes 10.02 s; the image is 40 ms
            # later, not 40 ms after the helper's unprimed fallback.
            assert record['source_ns'] == 10_060_000_000
            assert record['wall_s'] >= settled_wall
            assert path.read_bytes() == payload
    finally:
        clock.running = True
        prime_current_inputs(local.row)
        local.runtime.close(timeout_s=1.)
