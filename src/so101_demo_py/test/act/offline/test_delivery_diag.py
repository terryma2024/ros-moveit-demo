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


# --- RECORDER_ONLY_STALL: post-hoc comparison of the bag's receipt time with the probe trace (synthetic data only) ---

HEAD, WRIST = "/head_camera/color", "/wrist_camera/color"


def write_trace(path, rows):
    path.write_text("\n".join([json.dumps({"kind": "PROBE_TRACE", "fields": ["topic", "real_ns", "mono_ns", "stamp_ns"]})]
                              + [json.dumps(list(row)) for row in rows]) + "\n")


def stalls(tmp_path, trace_rows, bag_rows, **kwargs):
    """bag_rows are (topic, bag receipt ns, stamp); the fake reader's `data` is the stamp itself."""
    trace = tmp_path / "bag-probe-trace.jsonl"
    write_trace(trace, trace_rows)
    stream = io.StringIO()
    summary = diag.recorder_only_stalls(
        tmp_path / "bag", trace, stream=stream, header_stamp_ns=lambda data: data,
        read_messages=lambda uri, topics=None: iter([(t, "type", ns, stamp) for t, ns, stamp in bag_rows]), **kwargs)
    return summary, [json.loads(line.split(" ", 1)[1]) for line in stream.getvalue().splitlines()
                     if line.startswith("RECORDER_ONLY_STALL ")]


def test_recorder_only_stall_is_one_event_for_late_messages_of_both_cameras(tmp_path):
    ms = 1_000_000
    trace = [(HEAD, 1000 * ms + k * 33 * ms, 0, 100 + k) for k in range(6)] + [(WRIST, 1005 * ms, 0, 103), (WRIST, 1100 * ms, 0, 104)]
    bag = [(HEAD, 1000 * ms + k * 33 * ms + (250 * ms if k in (2, 3) else 2 * ms), 100 + k) for k in range(6)] \
        + [(WRIST, 1005 * ms + 300 * ms, 103), (WRIST, 1100 * ms + 1 * ms, 104)]
    summary, records = stalls(tmp_path, trace, bag)

    assert summary["error"] is None and summary["matched"] == 8 and summary["late_messages"] == 3
    (record,) = records
    assert record["topic_count"] == 2 and record["gap_ms"] == 300.0 and record["first_stamp"] == 102 and record["last_stamp"] == 103
    assert summary["events"] == 1 and summary["logged"] == 1


def test_a_gap_of_exactly_100_ms_or_a_message_missing_from_the_probe_is_not_reported(tmp_path):
    ms = 1_000_000
    summary, records = stalls(tmp_path, [(HEAD, 10 * ms, 0, 1)], [(HEAD, 110 * ms, 1), (HEAD, 900 * ms, 2)])
    assert records == [] and summary["matched"] == 1 and summary["late_messages"] == 0


def test_separate_events_are_logged_up_to_the_line_cap(tmp_path):
    ms = 1_000_000
    trace = [(HEAD, k * 1000 * ms, 0, k * 10**9) for k in range(5)]
    bag = [(HEAD, k * 1000 * ms + 200 * ms, k * 10**9) for k in range(5)]
    summary, records = stalls(tmp_path, trace, bag, max_lines=3)
    assert summary["events"] == 5 and summary["logged"] == 3 and len(records) == 3


def test_the_message_and_time_bounds_truncate_instead_of_failing(tmp_path):
    ms = 1_000_000
    trace = [(HEAD, k * ms, 0, k) for k in range(10)]
    bag = [(HEAD, k * ms + 500 * ms, k) for k in range(10)]
    summary, _ = stalls(tmp_path, trace, bag, max_messages=4)
    assert summary["truncated"] is True and summary["matched"] == 4 and summary["error"] is None
    ticks = iter(range(0, 1000, 5))
    summary, _ = stalls(tmp_path, trace, bag, max_seconds=7, monotonic=lambda: next(ticks))
    assert summary["truncated"] is True and summary["error"] is None


def test_recorder_only_stall_never_raises(tmp_path):
    summary = diag.recorder_only_stalls(tmp_path / "bag", tmp_path / "missing.jsonl", stream=io.StringIO())
    assert summary["error"] is not None and summary["logged"] == 0
    trace = tmp_path / "bad.jsonl"
    trace.write_text("{not json\n")
    assert diag.recorder_only_stalls(tmp_path / "bag", trace, stream=io.StringIO())["error"] is not None
