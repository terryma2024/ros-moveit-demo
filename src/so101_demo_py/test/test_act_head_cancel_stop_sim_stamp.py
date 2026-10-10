"""CANCEL_STOP carries the sim stamp of the raw-stop confirmation (design section 3, review 3 issue 3)."""

import threading
import time

from test_act_head_local_observer import wait_for
from test_act_head_local_runtime import armed_runtime, prime_current_inputs, runtime_setup


def _confirmed_runtime(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    runtime.fault('HEAD_TEST_FAULT_FOR_SIM_STAMP')
    assert wait_for(lambda: row.port._stop_epoch is not None)
    done = threading.Event()

    def originals():
        time.sleep(.03)
        while not done.is_set():
            try:
                prime_current_inputs(row)
            except PermissionError:
                return
            time.sleep(.01)

    producer = threading.Thread(target=originals, daemon=True)
    producer.start()
    return row, runtime, done, producer


def test_a_confirmed_raw_stop_records_the_sim_stamp_of_its_confirmation(monkeypatch):
    row, runtime, done, producer = _confirmed_runtime(monkeypatch)
    seen = []
    try:
        runtime.bind_stop_window_observer(seen.append)
        assert wait_for(lambda: any(kind == 'CANCEL_STOP' for kind, _, _ in row.sink.rows), 5.)
        record = [r for kind, r, _ in row.sink.rows if kind == 'CANCEL_STOP'][0]
        assert record['raw_stop_confirmed'] is True
        confirmation = row.port.raw_stop_confirmation()
        assert type(record['raw_stop_confirmed_sim_ns']) is int
        assert record['raw_stop_confirmed_sim_ns'] == confirmation['sim_ns'] > 0
        assert record['raw_stop_last_sample_source_ns'] == confirmation['last_sample_source_ns']
        assert record['raw_stop_last_sample_source_ns'] <= record['raw_stop_confirmed_sim_ns']
        assert seen == [record['raw_stop_confirmed_sim_ns']]
    finally:
        done.set()
        producer.join(1.)
        runtime.close(timeout_s=.05)
        runtime.retire_originals()


def test_an_unconfirmed_raw_stop_records_no_sim_stamp_and_notifies_nobody(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    seen = []
    try:
        runtime.bind_stop_window_observer(seen.append)
        runtime.fault('HEAD_TEST_NO_ORIGINALS')
        assert wait_for(lambda: runtime.stop_receipt()['native_close'].get('ack') is True)
        assert wait_for(lambda: any(kind == 'CANCEL_STOP' for kind, _, _ in row.sink.rows), 10.)
        record = [r for kind, r, _ in row.sink.rows if kind == 'CANCEL_STOP'][0]
        assert record['raw_stop_confirmed'] is False
        assert record['raw_stop_confirmed_sim_ns'] is None
        assert record['raw_stop_last_sample_source_ns'] is None
        assert seen == []
        assert row.port.raw_stop_confirmation() is None
    finally:
        runtime.close(timeout_s=.05)
        runtime.retire_originals()


def test_a_second_stop_window_observer_is_refused(monkeypatch):
    import pytest
    row = runtime_setup(monkeypatch)
    try:
        row.runtime.bind_stop_window_observer(lambda sim_ns: None)
        with pytest.raises(PermissionError, match='STOP_WINDOW_OBSERVER_REBOUND'):
            row.runtime.bind_stop_window_observer(lambda sim_ns: None)
        with pytest.raises(ValueError, match='STOP_WINDOW_OBSERVER_INVALID'):
            runtime_setup(monkeypatch).runtime.bind_stop_window_observer(None)
    finally:
        row.runtime.close(timeout_s=.05)
