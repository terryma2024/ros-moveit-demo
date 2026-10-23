"""The raw recorder's probe writes a per-message receipt trace for the camera topics and /clock, off the receipt thread."""

import json
import struct

import pytest

from so101_demo.act.offline.probe_trace import TRACE_TOPICS, ProbeTrace, header_stamp_ns


def cdr(sec, nanosec, *, little=True, tail=b'\x00' * 16):
    return (b'\x00\x01\x00\x00' if little else b'\x00\x00\x00\x00') + struct.pack('<iI' if little else '>iI', sec, nanosec) + tail


def test_header_stamp_is_read_from_the_first_header_field_of_a_cdr_message():
    assert header_stamp_ns(cdr(12, 345)) == 12 * 10**9 + 345
    assert header_stamp_ns(cdr(7, 8, little=False)) == 7 * 10**9 + 8
    assert header_stamp_ns(b'\x00\x01') is None and header_stamp_ns(None) is None


def read(path):
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    return lines[0], lines[1:]


def test_records_receipt_clock_stamp_and_topic_for_traced_topics_only_and_flushes_on_close(tmp_path):
    clocks = iter(range(1000, 100000, 10))
    real = iter(range(5_000_000, 10_000_000, 100))
    trace = ProbeTrace(tmp_path/'trace.jsonl', realtime_ns=lambda: next(real), monotonic_ns=lambda: next(clocks), flush_every_s=3600)
    trace.on_message('/clock', cdr(1, 0))
    trace.on_message('/head_camera/color', cdr(1, 5))
    trace.on_message('/so101/simulation/joints', cdr(1, 6))   # not traced
    trace.on_message('/wrist_camera/camera_info', cdr(2, 9))
    trace.close()
    header, rows = read(tmp_path/'trace.jsonl')
    assert header['kind'] == 'PROBE_TRACE' and header['fields'] == ['topic', 'real_ns', 'mono_ns', 'stamp_ns']
    assert [row[0] for row in rows] == ['/clock', '/head_camera/color', '/wrist_camera/camera_info']
    assert rows[1][1] > rows[0][1] and rows[1][3] == 10**9+5 and rows[2][3] == 2*10**9+9
    assert trace.count == 3 and trace.dropped == 0


def test_close_is_idempotent_and_later_messages_are_ignored(tmp_path):
    trace = ProbeTrace(tmp_path/'trace.jsonl', flush_every_s=3600)
    trace.on_message('/clock', cdr(1, 0))
    trace.close()
    trace.close()
    trace.on_message('/clock', cdr(2, 0))
    assert len(read(tmp_path/'trace.jsonl')[1]) == 1


def test_a_write_failure_never_raises_into_the_receipt_path(tmp_path):
    trace = ProbeTrace(tmp_path/'missing-dir'/'trace.jsonl', flush_every_s=3600)
    trace.on_message('/clock', cdr(1, 0))
    trace.close()   # the file could not be opened: nothing raised, the failure is reported
    assert trace.failure is not None


def test_the_buffer_is_bounded(tmp_path):
    trace = ProbeTrace(tmp_path/'trace.jsonl', flush_every_s=3600, max_buffered=5)
    for i in range(8):
        trace.on_message('/clock', cdr(i, 0))
    assert trace.dropped == 3
    trace.close()
    assert len(read(tmp_path/'trace.jsonl')[1]) == 5


def test_traced_topics_are_cameras_clock_and_the_state_topics_whose_samples_the_bag_can_lose():
    states = {'/joint_states', '/arm_controller/controller_state', '/gripper_controller/controller_state',
              '/so101/simulation/scene_state'}
    assert set(TRACE_TOPICS) == {'/clock', '/head_camera/color', '/head_camera/camera_info',
                                 '/wrist_camera/color', '/wrist_camera/camera_info', '/neck_controller/controller_state'} | states


def test_a_rig_without_a_neck_traces_no_neck_state():
    from so101_demo.act.rig_profile import DEFAULT_RIG
    from dataclasses import replace
    from so101_demo.act.offline.probe_trace import trace_topics_for

    assert '/neck_controller/controller_state' in trace_topics_for(DEFAULT_RIG)
    assert '/neck_controller/controller_state' not in trace_topics_for(replace(DEFAULT_RIG, has_neck=False))


def test_state_messages_are_traced_with_their_header_stamp(tmp_path):
    trace = ProbeTrace(tmp_path/'trace.jsonl', flush_every_s=3600)
    for topic in ('/joint_states', '/arm_controller/controller_state', '/gripper_controller/controller_state', '/so101/simulation/scene_state'):
        trace.on_message(topic, cdr(3, 4))
    trace.close()
    _header, rows = read(tmp_path/'trace.jsonl')
    assert [(row[0], row[3]) for row in rows] == [(topic, 3*10**9+4) for topic in (
        '/joint_states', '/arm_controller/controller_state', '/gripper_controller/controller_state', '/so101/simulation/scene_state')]
