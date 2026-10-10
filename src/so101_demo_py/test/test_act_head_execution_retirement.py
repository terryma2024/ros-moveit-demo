"""Actual local runtime/exposure/owner closure; no model or native peer claim."""

from so101_demo.act.head_execution_documents import retire_run_resources
from so101_demo.adapters.act.head_inference_owner import HeadInferenceOwner
from so101_demo.adapters.act.head_live_exposure import HeadLiveExposures
from test_act_head_local_runtime import runtime_setup
from test_act_head_local_stopped_exposure import FakeBuffer


class Detector:
    def reset(self): pass
    def detect(self,*args,**kwargs): return []


def test_requested_stop_collects_advancing_originals_before_runtime_retirement(monkeypatch):
    import threading
    import time
    from test_act_head_local_runtime import armed_runtime, prime_current_inputs
    from test_act_head_local_observer import wait_for

    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    runtime.fault('HEAD_TEST_FAULT_BEFORE_RETIREMENT')
    assert wait_for(lambda: row.port._stop_epoch is not None)
    original_deadline = runtime.stop_receipt()['stop_deadline_wall_s']
    errors = []

    def originals():
        time.sleep(.03)
        for _ in range(4):
            try:
                prime_current_inputs(row)
            except PermissionError as error:
                errors.append(str(error))
                return
            time.sleep(.01)

    producer = threading.Thread(target=originals)
    producer.start()
    outcomes = {}
    try:
        report = retire_run_resources(runtime, None, None, outcomes=outcomes,
                                      defer_original_retirement=True)
        assert report['runtime'] is None, outcomes
        assert outcomes['runtime']['confirmed_stop'] is True
        assert outcomes['runtime']['cancel_stop']['observation_count'] >= 3
        assert runtime.stop_receipt()['stop_deadline_wall_s'] == original_deadline
        assert runtime.retirement_confirmed is True
        assert row.observer.closed is False
    finally:
        producer.join(1.)
        runtime.close(timeout_s=.05)
        runtime.retire_originals()
    assert not errors


def test_real_local_owner_retires_after_runtime_workers_before_originals(monkeypatch):
    row=runtime_setup(monkeypatch)
    owner=HeadInferenceOwner(factory=lambda:{'runtime':Detector()},
        fault_callback=row.runtime.fault,simulation_policy=row.policy)
    try:
        owner.configuration(timeout_s=1.)
        owner.bind_live(lambda detector:HeadLiveExposures(port=row.port,buffer=FakeBuffer(),
            detector=detector,primary=row.runtime,monitor=None,camera_skew_s=.02,
            emit=lambda *args,**kwargs:None),timeout_s=1.)
        outcomes={}
        report=retire_run_resources(row.runtime,owner._live,owner,outcomes=outcomes,
                                   defer_original_retirement=True)
        assert not any(report.values()),report
        assert outcomes['owner']['thread_alive'] is False
        assert outcomes['owner']['live']['retired'] is True
        assert row.runtime.retirement_confirmed is True
        assert row.observer.closed is False
        row.runtime.retire_originals()
        assert row.observer.closed is True
    finally:
        row.runtime.close(timeout_s=1.)
        if owner._thread.is_alive():owner.close(timeout_s=1.)


def test_requested_stop_without_new_originals_waits_original_deadline_and_fails(monkeypatch):
    import time
    from test_act_head_local_runtime import armed_runtime
    from test_act_head_local_observer import wait_for

    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    try:
        runtime.fault('HEAD_TEST_MISSING_RAW_STOP_ORIGINALS')
        assert wait_for(lambda: runtime.stop_receipt()['native_close'].get('ack') is True)
        original = runtime.stop_receipt()
        deadline = original['stop_deadline_wall_s']
        outcomes = {}
        report = retire_run_resources(runtime, None, None, outcomes=outcomes,
                                      defer_original_retirement=True)
        assert time.monotonic() >= deadline
        assert time.monotonic() < deadline + 1.
        assert report['runtime'] == 'HEAD_RETIREMENT_UNCONFIRMED'
        receipt = runtime.stop_receipt()
        assert receipt['stop_deadline_wall_s'] == deadline
        assert receipt['stop_origin_wall_s'] == original['stop_origin_wall_s']
        assert receipt['physical_stop_confirmed'] is False
        assert receipt['cancel_stop']['observation_count'] > 0
        assert all(sample['stopped'] is False
                   for sample in receipt['cancel_stop']['raw_stop_observations'])
        assert receipt['cancel_stop']['raw_stop_confirmed'] is False
        assert runtime.retirement_confirmed is False
        assert row.observer.closed is False
    finally:
        runtime.close(timeout_s=.05)
        runtime.retire_originals()


def test_local_exposure_refuses_old_online_monitor(monkeypatch):
    import pytest
    row=runtime_setup(monkeypatch)
    try:
        with pytest.raises(ValueError,match='LOCAL|MONITOR'):
            HeadLiveExposures(port=row.port,buffer=FakeBuffer(),detector=Detector(),
                primary=row.runtime,monitor=object(),camera_skew_s=.02,
                emit=lambda *args,**kwargs:None)
    finally:row.runtime.close(timeout_s=1.)


def test_original_retirement_failure_remains_failure_on_repeated_close(monkeypatch):
    from so101_demo.act.head_execution_documents import retirement_unconfirmed
    row=runtime_setup(monkeypatch)
    monkeypatch.setattr(row.node,'destroy_client',lambda client:False)
    try:
        first=row.runtime.retire_originals()
        second=row.runtime.retire_originals()
        assert retirement_unconfirmed(first)
        assert retirement_unconfirmed(second)
        assert second['observer']['clients_retired'] is False
    finally:row.runtime.close(timeout_s=1.)
