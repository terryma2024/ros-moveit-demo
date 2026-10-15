"""The RECORDER_DELIVERY_SLOW diagnostics: thresholds, throttling, and that they only ever log (never raise or change results)."""
import io
import json

from so101_demo.act.offline import delivery_diag as diag


class Clock:
    def __init__(self):
        self.now = 1_000_000_000

    def __call__(self):
        return self.now


def lines(stream):
    return [json.loads(line.split(" ", 1)[1]) for line in stream.getvalue().splitlines()]


def monitor(clock, stream, **kwargs):
    log = diag.SlowLineLog(stream=stream, monotonic_ns=clock, realtime_ns=lambda: 5_000_000_000)
    return diag.DeliveryGapMonitor(log=log, monotonic_ns=clock, realtime_ns=lambda: 5_000_000_000, **kwargs), log


def test_gap_logged_only_at_or_above_threshold_and_only_while_active():
    clock, stream = Clock(), io.StringIO()
    gaps, _ = monitor(clock, stream)
    gaps.on_message("/a")                      # not active: nothing
    clock.now += 400_000_000
    gaps.on_message("/b")
    assert stream.getvalue() == ""
    gaps.start()
    gaps.on_message("/a")                      # first receipt after start only sets the baseline
    clock.now += 149_999_999
    gaps.on_message("/b")
    assert stream.getvalue() == ""
    clock.now += 150_000_000
    gaps.on_message("/c")
    (record,) = lines(stream)
    assert record["kind"] == "receipt_gap" and record["gap_ms"] == 150.0
    assert (record["from_topic"], record["to_topic"]) == ("/b", "/c")
    assert record["mono_ns"] == clock.now - 150_000_000 and record["real_ns"] == 5_000_000_000 - 150_000_000
    gaps.stop()
    clock.now += 900_000_000
    gaps.on_message("/a")
    assert len(lines(stream)) == 1


def test_slow_lines_are_throttled_and_counted():
    clock, stream = Clock(), io.StringIO()
    gaps, log = monitor(clock, stream)
    gaps.start()
    gaps.on_message("/a")
    for _ in range(30):
        clock.now += 200_000_000 // 30
        gaps.on_message("/a")
        clock.now += 160_000_000
        gaps.on_message("/b")
    assert len(lines(stream)) == diag.MAX_LINES_PER_WINDOW
    assert log.suppressed > 0


def test_timed_logs_slow_operations_and_returns_the_result():
    clock, stream = Clock(), io.StringIO()
    log = diag.SlowLineLog(stream=stream, monotonic_ns=clock, realtime_ns=lambda: 7_000_000_000)

    def slow():
        clock.now += 100_000_000
        return 42

    def fast():
        clock.now += 99_999_999
        return 1

    assert diag.timed(log, "sidecar_fsync", fast, monotonic_ns=clock, realtime_ns=lambda: 7_000_000_000) == 1
    assert stream.getvalue() == ""
    assert diag.timed(log, "sidecar_fsync", slow, monotonic_ns=clock, realtime_ns=lambda: 7_000_000_000, queued=3) == 42
    (record,) = lines(stream)
    assert record["kind"] == "sidecar_fsync" and record["duration_ms"] == 100.0 and record["queued"] == 3


def test_timed_still_logs_and_propagates_when_the_operation_raises():
    clock, stream = Clock(), io.StringIO()
    log = diag.SlowLineLog(stream=stream, monotonic_ns=clock, realtime_ns=lambda: 1)

    def failing():
        clock.now += 200_000_000
        raise OSError("disk")

    try:
        diag.timed(log, "sidecar_write", failing, monotonic_ns=clock, realtime_ns=lambda: 1)
    except OSError:
        pass
    else:
        raise AssertionError("the error must propagate")
    assert len(lines(stream)) == 1
