"""Original-frame protections migrated from the retired online exposure tests."""

from copy import deepcopy
import threading

import pytest

from test_act_head_local_runtime import prime_current_inputs
from test_act_head_local_stopped_exposure import (
    exposure_setup, feed_joint, image_record, prime_exposure, stopped_request)


def prepared_exposure(monkeypatch):
    local = exposure_setup(monkeypatch)
    prime_current_inputs(local.row)
    settled, payload = prime_exposure(local)
    request = stopped_request(local.row, settled_wall_s=settled)
    return local, request, payload


@pytest.mark.parametrize('field,value', [
    ('generation', 99), ('motion_epoch', 1), ('policy_sha256', 'b'*64),
    ('simulation_policy_sha256', 'c'*64), ('observation_sequence', True)])
def test_wrong_request_identity_never_enters_detector(monkeypatch, field, value):
    local, request, _ = prepared_exposure(monkeypatch)
    request[field] = value
    try:
        with pytest.raises((PermissionError, ValueError)):
            local.exposures.infer(observation_request=request)
        assert not local.detector.calls and not local.exposures.results
        assert local.runtime.faulted
    finally:
        local.runtime.close(timeout_s=1.)


def test_pre_request_pair_and_missing_info_never_enter_detector(monkeypatch):
    local, request, _ = prepared_exposure(monkeypatch)
    try:
        image = local.exposures._pending[0]
        request['requested_wall_s'] = image['wall_s']
        assert local.exposures.infer(observation_request=request) is None
        assert not local.detector.calls and not local.runtime.faulted
        local.exposures._infos.clear()
        assert local.exposures.infer(observation_request=request) is None
        assert not local.detector.calls and not local.runtime.faulted
    finally:
        local.runtime.close(timeout_s=1.)


@pytest.mark.parametrize('damage', ['future', 'skew', 'rotation', 'translation', 'missing'])
def test_original_tf_must_be_available_finite_and_causal(monkeypatch, damage):
    local, request, _ = prepared_exposure(monkeypatch)
    lookup = local.buffer.lookup_transform
    def damaged_transform(*args):
        transform = lookup(*args)
        if damage == 'future':
            transform.header.stamp.nanosec += 1
        elif damage == 'skew':
            transform.header.stamp.nanosec -= 21_000_000
        elif damage == 'rotation':
            transform.transform.rotation.w = 0.
        elif damage == 'translation':
            transform.transform.translation.x = float('nan')
        return transform
    monkeypatch.setattr(local.buffer, 'lookup_transform', damaged_transform)
    try:
        if damage == 'missing':
            monkeypatch.setattr(local.buffer, 'can_transform', lambda *args: False)
            image_before = deepcopy(local.exposures._pending[0])
            assert local.exposures.infer(observation_request=request) is None
            assert not local.detector.calls and not local.runtime.faulted
            monkeypatch.setattr(local.buffer, 'can_transform', lambda *args: True)
            row = local.exposures.infer(observation_request=request)
            assert row['source_ns'] == image_before['source_ns']
            assert row['image_received_wall_s'] == image_before['wall_s']
            assert len(local.detector.calls) == 1
        else:
            with pytest.raises((PermissionError, ValueError)):
                local.exposures.infer(observation_request=request)
            assert not local.detector.calls and not local.exposures.results
            assert local.runtime.faulted
    finally:
        local.runtime.close(timeout_s=1.)


def test_motion_after_local_admission_cannot_start_detector(monkeypatch):
    local, request, _ = prepared_exposure(monkeypatch)
    set_deadline = local.runtime.inference_deadline
    def moved(deadline):
        result = set_deadline(deadline)
        if deadline is not None:
            feed_joint(local.row, local.row.clock.sim + .01, velocity=.5)
        return result
    monkeypatch.setattr(local.runtime, 'inference_deadline', moved)
    try:
        with pytest.raises(PermissionError, match='MOVED_AFTER_ADMISSION'):
            local.exposures.infer(observation_request=request)
        assert not local.detector.calls and not local.exposures.results
        assert local.runtime.faulted
    finally:
        local.runtime.close(timeout_s=1.)


@pytest.mark.parametrize('outcome', ['expired', 'fault', 'job_deadline', 'exception'])
def test_detector_return_keeps_original_age_job_and_fault_boundaries(monkeypatch, outcome):
    local, request, _ = prepared_exposure(monkeypatch)
    detect = local.detector.detect
    def changed(*args, **kwargs):
        result = detect(*args, **kwargs)
        if outcome == 'expired':
            prime_current_inputs(local.row, sim=local.row.clock.sim + .21)
        elif outcome == 'fault':
            local.runtime.fault('CONTROLLED_DURING_MODEL')
        elif outcome == 'job_deadline':
            job_deadline = local.exposures._stopped_candidate['claim']['job_deadline_ns']
            monkeypatch.setattr(local.exposures, 'monotonic', lambda: job_deadline*1e-9)
        else:
            raise RuntimeError('controlled detector failure')
        return result
    monkeypatch.setattr(local.detector, 'detect', changed)
    try:
        if outcome == 'expired':
            row = local.exposures.infer(observation_request=request)
            assert row['observation_outcome'] == 'EXPIRED'
            assert row['detections'] == [] and row['discarded_detections']
            assert row['inference_performed'] and not local.runtime.faulted
            assert local.runtime._inference_deadline_wall_s is None
        else:
            error = RuntimeError if outcome == 'exception' else PermissionError
            with pytest.raises(error):
                local.exposures.infer(observation_request=request)
            assert not local.exposures.results and local.runtime.faulted
            attempt = local.exposures.close()['original_attempts'][-1]
            assert attempt['outcome'] == 'REFUSED'
            assert attempt['phases']['cuda_started'] is not None
            assert attempt['job_deadline_ns'] <= request['search_deadline_ns']
        assert len(local.detector.calls) == 1
    finally:
        local.runtime.close(timeout_s=1.)


def test_replaced_candidate_finishes_short_drop_outside_cache_lock(monkeypatch):
    local, request, payload = prepared_exposure(monkeypatch)
    guard = local.exposures._guard
    save = local.exposures._save_stopped_observation
    replaced = []
    def replace_at_guard(deadline):
        guard(deadline)
        if local.exposures._stopped_candidate is not None and not replaced:
            original = local.exposures._pending[0]
            replacement = dict(original, source_ns=original['source_ns'] + 1)
            local.exposures.observe('IMAGE', replacement, payload=payload)
            replaced.append(original['source_ns'])
    def save_without_lock(*args, **kwargs):
        assert local.exposures._lock.acquire(blocking=False), 'save held exposure cache lock'
        local.exposures._lock.release()
        return save(*args, **kwargs)
    monkeypatch.setattr(local.exposures, '_guard', replace_at_guard)
    monkeypatch.setattr(local.exposures, '_save_stopped_observation', save_without_lock)
    try:
        row = local.exposures.infer(observation_request=request)
        assert replaced == [row['source_ns']]
        assert row['observation_outcome'] == 'SHORT_DROP' and row['detections'] == []
        assert not local.detector.calls and not local.runtime.faulted
    finally:
        local.runtime.close(timeout_s=1.)


def test_simulation_advance_at_journal_handoff_discards_without_rtf_assumption(monkeypatch):
    local, request, _ = prepared_exposure(monkeypatch)
    emit = local.exposures.emit
    def advanced(event, **fields):
        emit(event, **fields)
        if event == 'LIVE_STOPPED_OBSERVATION_FINISHED':
            prime_current_inputs(local.row, sim=local.row.clock.sim + .21)
    monkeypatch.setattr(local.exposures, 'emit', advanced)
    try:
        row = local.exposures.infer(observation_request=request)
        assert row['observation_outcome'] == 'EXPIRED' and row['detections'] == []
        assert row['discarded_detections'] and len(local.detector.calls) == 1
        assert not local.runtime.faulted
    finally:
        local.runtime.close(timeout_s=1.)


@pytest.mark.parametrize('damage', ['hash', 'short', 'frame', 'nonadvancing'])
def test_invalid_original_payload_never_enters_detector(monkeypatch, damage):
    local, request, payload = prepared_exposure(monkeypatch)
    original = local.exposures._pending[0]
    record = dict(original, source_ns=original['source_ns'] + 1)
    if damage == 'hash': record['payload_sha256'] = 'f'*64
    elif damage == 'short': payload = payload[:-1]
    elif damage == 'frame': record['frame_id'] = 'foreign'
    else: record['source_ns'] = original['source_ns']
    try:
        with pytest.raises((ValueError, PermissionError)):
            local.exposures.observe('IMAGE', record, payload=payload)
        assert local.runtime.faulted and not local.detector.calls
        assert not local.exposures.results
    finally:
        local.runtime.close(timeout_s=1.)


def test_reentrant_inference_cannot_clear_active_owner_call(monkeypatch):
    local, request, _ = prepared_exposure(monkeypatch)
    detect = local.detector.detect
    def nested(*args, **kwargs):
        with pytest.raises(PermissionError):
            local.exposures.infer(observation_request=request)
        assert local.exposures._busy
        return detect(*args, **kwargs)
    monkeypatch.setattr(local.detector, 'detect', nested)
    try:
        with pytest.raises(PermissionError):
            local.exposures.infer(observation_request=request)
        assert len(local.detector.calls) == 1 and local.runtime.faulted
        assert not local.exposures.results and not local.exposures._busy
    finally:
        local.runtime.close(timeout_s=1.)


def test_retirement_and_handoff_copies_preserve_original_records(monkeypatch):
    from so101_demo.adapters.act import head_live_exposure as module
    local, request, _ = prepared_exposure(monkeypatch)
    try:
        record = local.exposures.infer(observation_request=request)
        copy = local.exposures.next_completed_observation(0)
        copy['original_info']['frame_id'] = 'changed'
        assert local.exposures.next_completed_observation(0) == record
        wire = module._wire
        encoded = []
        def forbid_bulk(value):
            encoded.append(value)
            raise AssertionError('bulk encoding before runtime retirement')
        monkeypatch.setattr(module, '_wire', forbid_bulk)
        assert local.exposures.freeze_retirement()['retired']
        assert encoded == []
        with pytest.raises(PermissionError, match='PRIMARY_RETIRE_UNCONFIRMED'):
            local.exposures.retirement_snapshot()
        assert encoded == []
        local.runtime.close(timeout_s=1.)
        monkeypatch.setattr(module, '_wire', wire)
        first = local.exposures.retirement_snapshot()
        first['original_attempts'][0]['outcome'] = 'changed'
        assert local.exposures.retirement_snapshot()['original_attempts'][0]['outcome'] == 'COMPLETED'
        with pytest.raises(PermissionError):
            local.exposures.infer(observation_request=request)
        assert len(local.detector.calls) == 1
    finally:
        local.runtime.close(timeout_s=1.)


@pytest.mark.parametrize('damage', ['busy', 'foreign_owner', 'not_frozen'])
def test_retirement_refuses_unfinished_or_foreign_inference(monkeypatch, damage):
    local, _, _ = prepared_exposure(monkeypatch)
    try:
        if damage == 'busy':
            local.exposures._busy = True
            with pytest.raises(PermissionError, match='RETIRE_UNCONFIRMED'):
                local.exposures.freeze_retirement()
            assert not local.exposures._closed
            local.exposures._busy = False
        elif damage == 'not_frozen':
            local.runtime.close(timeout_s=1.)
            with pytest.raises(PermissionError, match='RETIRE_UNCONFIRMED'):
                local.exposures.retirement_snapshot()
        else:
            errors = []
            def foreign():
                try: local.exposures.freeze_retirement()
                except PermissionError as error: errors.append(error)
            worker = threading.Thread(target=foreign)
            worker.start(); worker.join(1.)
            assert not worker.is_alive() and len(errors) == 1
            assert not local.exposures._closed
    finally:
        local.runtime.close(timeout_s=1.)
