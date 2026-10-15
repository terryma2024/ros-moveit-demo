"""TEACHER_SOURCE_TRACE: diagnostics for the gap between a scene apply's named source and the Teacher's /clock, no behaviour change."""

import io
import json
import struct
from types import SimpleNamespace

from so101_demo.ros.teacher_source_trace import ClockReceiptProbe, emit_source_trace


def clock_message(sec, nanosec):
    return b'\x00\x01\x00\x00' + struct.pack('<iI', sec, nanosec)


class Node:
    def __init__(self, now_ns=7_000_000_000):
        self.subscriptions, self.now_ns = [], now_ns

    def create_subscription(self, message_type, topic, callback, qos, **kwargs):
        self.subscriptions.append((message_type, topic, callback, qos, kwargs))
        return object()

    def get_clock(self):
        return SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=self.now_ns))


def probe_with_clock(sec, nanosec, *, mono=1_000, real=9_000):
    node = Node()
    ticks = iter([mono])
    probe = ClockReceiptProbe(node, clock_type=object, qos=object(), monotonic_ns=lambda: next(ticks), realtime_ns=lambda: real)
    node.subscriptions[0][2](clock_message(sec, nanosec))
    return node, probe


def test_probe_subscribes_to_clock_raw_and_keeps_the_latest_receipt():
    node, probe = probe_with_clock(5, 250)
    assert [(s[1], s[4]) for s in node.subscriptions] == [('/clock', {'raw': True})]
    assert probe.latest() == dict(sim_ns=5_000_000_250, real_ns=9_000, mono_ns=1_000, count=1)


def test_probe_with_no_message_yet_reports_none_and_a_broken_message_changes_nothing():
    node = Node()
    probe = ClockReceiptProbe(node, clock_type=object, qos=object())
    assert probe.latest() is None
    node.subscriptions[0][2](b'\x00')
    assert probe.latest() is None


def test_trace_line_has_the_named_source_the_latest_clock_and_the_lag():
    node, probe = probe_with_clock(5, 0, mono=1_000_000)
    stream = io.StringIO()
    emit_source_trace(node, probe, phase='DYNAMIC_DETACH_SYNC', state='DETACH_MOVEIT',
                      source=dict(simulation_time_s=4.9, simulation_step=2450, publisher_sequence=88),
                      stream=stream, monotonic_ns=lambda: 4_000_000, realtime_ns=lambda: 12_000)
    prefix, payload = stream.getvalue().rstrip('\n').split(' ', 1)
    document = json.loads(payload)
    assert prefix == 'TEACHER_SOURCE_TRACE'
    assert document == dict(phase='DYNAMIC_DETACH_SYNC', state='DETACH_MOVEIT', request_mono_ns=4_000_000, request_real_ns=12_000,
        source_sim_ns=4_900_000_000, source_step=2450, source_sequence=88, node_clock_ns=7_000_000_000,
        probe_clock_sim_ns=5_000_000_000, probe_clock_real_ns=9_000, probe_clock_mono_ns=1_000_000,
        clock_cb_age_ms=3.0, clock_count=1, source_behind_clock_ms=100.0)


def test_trace_without_source_or_probe_still_emits_and_never_raises():
    stream = io.StringIO()
    emit_source_trace(Node(), None, phase='DYNAMIC_ATTACH', state=None, source=None, stream=stream)
    document = json.loads(stream.getvalue().split(' ', 1)[1])
    assert document['phase'] == 'DYNAMIC_ATTACH' and document['source_sim_ns'] is None and document['probe_clock_sim_ns'] is None

    class Broken:
        def get_clock(self):
            raise RuntimeError('boom')
    emit_source_trace(Broken(), None, phase='X', state=None, source=None, stream=io.StringIO())


def test_a_failing_stream_never_raises():
    class Bad:
        def write(self, _):
            raise OSError('closed')

        def flush(self):
            raise OSError('closed')
    emit_source_trace(Node(), None, phase='X', state=None, source=None, stream=Bad())
