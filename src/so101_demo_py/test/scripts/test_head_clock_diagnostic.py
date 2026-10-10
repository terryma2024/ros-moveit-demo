import json
import pytest
import threading
import time
from head_neck_timing_probe import clock_trace_health, monitor_clock_traces


def statuses(root, **changes):
    for stream in ('physics', 'loop'):
        value = dict(schema='SOCLK001', stream=stream, heartbeat_ns=1_000_000_000,
                     invalid_flags=0, final=False, reserved=10, committed=10, written=10)
        value.update(changes)
        (root / f'{stream}.status.json').write_text(json.dumps(value))


def test_fresh_complete_scoped_status_is_healthy(tmp_path):
    statuses(tmp_path)
    assert clock_trace_health(tmp_path, 1_100_000_000) is None


@pytest.mark.parametrize('changes', [dict(invalid_flags=1), dict(invalid_flags=2),
    dict(schema='other'), dict(final=True), dict(heartbeat_ns=4_000_000_000)])
def test_corrupt_or_failed_diagnostic_requests_original_stop(tmp_path, changes):
    statuses(tmp_path, **changes)
    with pytest.raises(RuntimeError, match='CLOCK_DIAGNOSTIC'):
        clock_trace_health(tmp_path, 1_100_000_000)


def test_missing_stream_requests_original_stop(tmp_path):
    statuses(tmp_path)
    (tmp_path / 'physics.status.json').unlink()
    with pytest.raises(RuntimeError, match='CLOCK_DIAGNOSTIC'):
        clock_trace_health(tmp_path, 1_100_000_000)


def test_two_second_old_heartbeat_requests_original_stop(tmp_path):
    statuses(tmp_path)
    with pytest.raises(RuntimeError, match='CLOCK_DIAGNOSTIC'):
        clock_trace_health(tmp_path, 3_000_000_000)


def test_status_refresh_during_read_uses_time_sample_after_read(tmp_path, monkeypatch):
    statuses(tmp_path)
    now = [900_000_000]
    from pathlib import Path
    original = Path.read_text
    def read_updated(path, *args, **kwargs):
        text = original(path, *args, **kwargs)
        now[0] = 1_100_000_000
        return text
    monkeypatch.setattr(Path, 'read_text', read_updated)
    assert clock_trace_health(tmp_path, lambda: now[0]) is None


def test_startup_failure_cancels_before_native_arm(tmp_path):
    statuses(tmp_path, heartbeat_ns=time.monotonic_ns(), invalid_flags=2)
    cancelled, finished = threading.Event(), threading.Event()
    errors = []
    monitor = threading.Thread(target=monitor_clock_traces, args=(tmp_path, cancelled,
        lambda: None, finished, errors, time.monotonic_ns()))
    monitor.start()
    try:
        assert cancelled.wait(1.)
        assert errors[0]['message'] == 'CLOCK_DIAGNOSTIC_STATUS_INVALID'
    finally:
        finished.set()
        monitor.join(1.)
    assert not monitor.is_alive()


def test_normal_work_deadline_cancels_with_cleanup_reserve(tmp_path):
    cancelled, finished = threading.Event(), threading.Event()
    errors = []
    monitor = threading.Thread(target=monitor_clock_traces, args=(tmp_path, cancelled,
        lambda: None, finished, errors, time.monotonic_ns() - 240_000_000_000))
    monitor.start()
    try:
        assert cancelled.wait(1.)
        assert errors[0]['message'] == 'CLOCK_DIAGNOSTIC_NORMAL_WORK_CANCELLED'
    finally:
        finished.set()
        monitor.join(1.)
    assert not monitor.is_alive()


def test_unreadable_status_directory_cancels_during_startup(tmp_path):
    statuses(tmp_path)
    tmp_path.chmod(0)
    cancelled, finished = threading.Event(), threading.Event()
    errors = []
    monitor = threading.Thread(target=monitor_clock_traces, args=(tmp_path, cancelled,
        lambda: None, finished, errors, time.monotonic_ns()))
    monitor.start()
    try:
        assert cancelled.wait(1.)
        assert errors[0]['type'] == 'PermissionError'
    finally:
        finished.set()
        monitor.join(1.)
        tmp_path.chmod(0o700)
    assert not monitor.is_alive()
