"""Recorder rounds 5-6 (CP-3409/3410): the spooler converts each chunk to its record in its own process (the Recorder's physics reader
spent ~25 ms of GIL per chunk on it, 24 s of a 96 s run), and the Recorder judges the converted chunk with the unchanged rules."""
import copy
import json
import math
import time
from types import SimpleNamespace

import pytest

from test_act_raw_physics_chunks import _chunk
from test_rec6_late_chunks import adapter, chunk_at


def sequences(appended):
    return [record["chunk"]["chunk_sequence"] for record in appended]


def record_of(message, receipt, **limits):
    from so101_demo.act.raw_physics_chunks import raw_chunk_from_ros
    return raw_chunk_from_ros(message, received_monotonic_ns=receipt, **limits)


def test_a_converted_frame_round_trips_beside_the_original_frame_kind(tmp_path):
    from so101_demo.act.chunk_spool import SpoolReader, SpoolWriter
    writer, reader = SpoolWriter(tmp_path, max_bytes=1 << 20), SpoolReader(tmp_path)
    writer.write(1, b"cdr-bytes")
    writer.write(2, b'{"a":1}', record=True)
    assert reader.read_frames() == [(False, 1, b"cdr-bytes"), (True, 2, b'{"a":1}')]
    writer2 = SpoolWriter(tmp_path / "x", max_bytes=1 << 20) if (tmp_path / "x").mkdir() is None else None
    writer2.write(3, b"zz")
    assert SpoolReader(tmp_path / "x").read() == [(3, b"zz")], "the plain reader still answers (receipt, bytes)"


def test_the_transform_equals_the_main_process_conversion_and_falls_back_to_the_original_bytes():
    from rclpy.serialization import serialize_message
    from so101_demo.act.chunk_spool import make_record_transform
    message, receipt = chunk_at(3)
    transform = make_record_transform(None, None)
    is_record, payload = transform(receipt, serialize_message(message))
    assert is_record is True and json.loads(payload) == json.loads(json.dumps(record_of(message, receipt)))
    bad = copy.deepcopy(message)
    bad.samples[0].model_qpos[0] = math.nan                         # cannot be a lossless JSON record
    raw = serialize_message(bad)
    is_record, payload = transform(receipt, raw)
    assert is_record is False and payload == raw
    is_record, payload = make_record_transform(2, None)(receipt, serialize_message(message))
    assert is_record is False, "a producer-bounds refusal travels as the original bytes, judged by the Recorder as before"


def test_the_adapter_judges_a_converted_record_with_the_same_rules_and_hazards():
    value, appended = adapter()
    for index in (1, 2, 3):
        message, receipt = chunk_at(index)
        value.accept_record(json.loads(json.dumps(record_of(message, receipt))), receipt_ns=receipt)
    value.drain()
    assert sequences(appended) == [1, 2, 3]
    message, receipt = chunk_at(5)                                   # chunk 4 lost
    value.accept_record(json.loads(json.dumps(record_of(message, receipt))), receipt_ns=receipt)
    assert value.hazard == "PHYSICS_RAW_CONTINUITY_INVALID"
    assert value._rejected["record"]["chunk"]["chunk_sequence"] == 5


def test_a_late_converted_record_is_admitted_with_its_lateness_recorded():
    value, appended = adapter()
    message, receipt = chunk_at(1, delay_ms=400.0)
    value.accept_record(record_of(message, receipt), receipt_ns=receipt)
    value.drain()
    assert value.hazard is None and sequences(appended) == [1]
    assert value.receipt_diagnostics()["late_count"] == 1
    assert value.receipt_diagnostics()["latency_ms"]["publish_to_receipt"]["count"] == 1


def test_the_reader_stops_deserializing_once_a_hazard_is_latched(tmp_path):
    from rclpy.serialization import serialize_message
    from so101_demo.act.chunk_spool import SpoolReader, SpoolWriter
    value, appended = adapter()
    value._spool = SpoolReader(tmp_path)
    writer = SpoolWriter(tmp_path, max_bytes=1 << 24)
    first, receipt = chunk_at(1)
    first.evidence_loss = True if hasattr(first, "evidence_loss") else None
    first.failed_publish_attempts = 1
    writer.write(receipt, serialize_message(first))
    for index in (2, 3, 4):
        message, receipt = chunk_at(index)
        writer.write(receipt, b"not a message")                       # would raise if it were deserialized
    value.start_spool_reader()
    end = time.monotonic() + 3
    while value.hazard is None and time.monotonic() < end:
        time.sleep(0.01)
    assert value.hazard == "PHYSICS_RAW_SOURCE_LOSS"
    value._receiver_stop.set()
    value._receiver_thread.join(2)
    assert value._receiver_thread.is_alive() is False


def test_a_real_spooler_process_delivers_converted_records_with_its_own_stamp(tmp_path, isolated_ros_domain):
    import os
    import rclpy
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from so101_mujoco_support.msg import PhysicsStepEvidenceChunk
    from so101_demo.act.chunk_spool import SpoolProcess, SpoolReader

    topic = f"/rec5_convert_{os.getpid()}"
    rclpy.init()
    process = SpoolProcess(tmp_path, topic=topic, max_bytes=1 << 26, convert=(None, None))
    try:
        node = rclpy.create_node("rec5_convert_pub")
        publisher = node.create_publisher(PhysicsStepEvidenceChunk, topic, QoSProfile(
            depth=100, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE))
        process.start()
        assert process.wait_ready(20.0)
        end = time.monotonic() + 10
        while publisher.get_subscription_count() < 1 and time.monotonic() < end:
            time.sleep(0.01)
        reader, frames, sequence = SpoolReader(tmp_path), [], 0
        end = time.monotonic() + 15
        while time.monotonic() < end and len(frames) < 4:
            sequence += 1
            publisher.publish(_chunk(sequence=sequence, first=101 + 5 * sequence, receipt=time.monotonic_ns() + 4_000_000))
            time.sleep(0.1)
            frames += reader.read_frames()
        assert len(frames) >= 4 and all(is_record for is_record, _, _ in frames)
        is_record, receipt, payload = frames[-1]
        record = json.loads(payload)
        assert record["received_monotonic_ns"] == receipt and record["chunk"]["chunk_sequence"] >= 1
        assert record["chunk"]["samples"][0]["physics_step"] >= 101
    finally:
        process.close()
        rclpy.shutdown()
    stats = json.loads((tmp_path / "stats.json").read_text())
    assert stats["converted"] >= 4 and stats["passed_through"] == 0
