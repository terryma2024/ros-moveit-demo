"""The Recorder's chunk receipt runs in its own small process: a main-process GIL stall (a long json.loads, a GC pass, an
import) can no longer age a chunk, because the receipt stamp is taken in the spooler at the true delivery boundary and the
100 ms age rule (receipt minus newest sample begin <= max_age) is evaluated with that stamp, unchanged.

Measured (CP-3401 analysis): one json.loads/json.dumps of a 17 MB document holds the GIL for ~160 ms, the source alignment build and the
Recorder startup do such work, and an in-process receiver callback cannot run meanwhile (chunk 33 reached the callback
541.8 ms after its newest sample began; other runs 100-110 ms at source alignment time)."""
import copy
import json
import os
import threading
import time
from types import SimpleNamespace

import pytest

from test_act_raw_physics_chunks import _chunk

NOW = 10_000_000_000
LAST_BEGIN_OFFSET = 4_000_000       # _chunk(receipt=R): newest sample begin = R - 4 ms


def serialized(chunk):
    from rclpy.serialization import serialize_message
    return serialize_message(chunk)


def spool_adapter(tmp_path, *, clock=None, **kw):
    from so101_demo.act.chunk_spool import SpoolReader
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    retained = []
    node = SimpleNamespace(create_subscription=lambda *a: 'owned', destroy_subscription=lambda v: None)
    reader = SpoolReader(tmp_path)
    adapter = RosEpisodePhysicsAdapter(
        node, session_id='live-source', reset_epoch=2, nq=2, nv=1,
        audit=SimpleNamespace(append_raw_physics=lambda value: retained.append(copy.deepcopy(value))),
        clock_ns=clock or time.monotonic_ns, spool=reader, **kw)
    return adapter, retained


def wait_for(predicate, seconds=3.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def test_frames_round_trip_and_a_partial_tail_waits_for_its_end(tmp_path):
    from so101_demo.act.chunk_spool import SpoolReader, SpoolWriter
    writer, reader = SpoolWriter(tmp_path, max_bytes=1 << 20), SpoolReader(tmp_path)
    writer.write(111, b"abc")
    writer.write(222, b"x" * 70_000)
    assert reader.read() == [(111, b"abc"), (222, b"x" * 70_000)]
    assert reader.read() == []
    with open(tmp_path / "chunks.spool", "ab", buffering=0) as stream:      # a frame whose payload is still being written
        stream.write(b"SPL1" + (333).to_bytes(8, "little") + (5).to_bytes(8, "little") + b"ab")
        assert reader.read() == []
        stream.write(b"cde")
    assert reader.read() == [(333, b"abcde")]


def test_overflow_is_marked_never_blocks_and_stops_writing(tmp_path):
    from so101_demo.act.chunk_spool import SpoolReader, SpoolWriter
    writer, reader = SpoolWriter(tmp_path, max_bytes=100), SpoolReader(tmp_path)
    writer.write(1, b"y" * 40)
    writer.write(2, b"y" * 80)        # does not fit: the marker is written, the callback returns at once
    writer.write(3, b"y" * 1)
    assert reader.read() == [(1, b"y" * 40)]
    assert reader.overflowed() is True


def test_a_chunk_stamped_fresh_is_admitted_even_when_the_main_thread_reads_it_300_ms_later(tmp_path):
    from so101_demo.act.chunk_spool import SpoolWriter
    adapter, retained = spool_adapter(tmp_path)
    writer = SpoolWriter(tmp_path, max_bytes=1 << 24)
    receipt = time.monotonic_ns()
    writer.write(receipt, serialized(_chunk(sequence=7, first=101, receipt=receipt)))
    time.sleep(0.3)                                  # a stalled main process: nothing reads for 300 ms
    adapter.start_spool_reader()
    try:
        assert wait_for(lambda: adapter.receipt_diagnostics()["chunk_count"] == 1)
        assert adapter.hazard is None
        adapter.drain()
        assert [item["chunk"]["chunk_sequence"] for item in retained] == [7]
        assert retained[0]["received_monotonic_ns"] == receipt        # the spooler's stamp, not the read time
    finally:
        adapter.close()


def test_a_chunk_stamped_late_is_admitted_and_recorded_whenever_it_is_read(tmp_path):
    """CP-3410: lateness is telemetry (it was PHYSICS_RAW_CLOCK_INVALID)."""
    from so101_demo.act.chunk_spool import SpoolWriter
    adapter, retained = spool_adapter(tmp_path)
    writer = SpoolWriter(tmp_path, max_bytes=1 << 24)
    now = time.monotonic_ns()
    writer.write(now, serialized(_chunk(sequence=7, first=101, receipt=now)))
    late = now + 400_000_000                       # delivered 404 ms after its newest sample began
    writer.write(late, serialized(_chunk(sequence=8, first=106, receipt=now + 10_000_000)))
    adapter.start_spool_reader()
    try:
        assert wait_for(lambda: adapter.receipt_diagnostics()["chunk_count"] == 2)
        assert adapter.hazard is None and adapter.receipt_diagnostics()["late_count"] == 1
        adapter.drain()
        assert [item["chunk"]["chunk_sequence"] for item in retained] == [7, 8]
    finally:
        adapter.close()


def test_a_stale_first_chunk_is_admitted_like_any_other(tmp_path):
    from so101_demo.act.chunk_spool import SpoolWriter
    adapter, retained = spool_adapter(tmp_path)
    writer = SpoolWriter(tmp_path, max_bytes=1 << 24)
    now = time.monotonic_ns()
    writer.write(now + 313_000_000, serialized(_chunk(sequence=25, first=101, receipt=now)))
    writer.write(now + 320_000_000, serialized(_chunk(sequence=26, first=106, receipt=now + 316_000_000)))
    adapter.start_spool_reader()
    try:
        assert wait_for(lambda: adapter.receipt_diagnostics()["chunk_count"] == 2)
        assert adapter.hazard is None
        adapter.drain()
        assert [item["chunk"]["chunk_sequence"] for item in retained] == [25, 26]
    finally:
        adapter.close()


def test_a_spool_overflow_or_a_dead_spooler_is_a_hazard_not_a_block(tmp_path):
    from so101_demo.act.chunk_spool import SpoolWriter
    adapter, _ = spool_adapter(tmp_path)
    writer = SpoolWriter(tmp_path, max_bytes=50)
    writer.write(1, b"z" * 200)
    adapter.start_spool_reader()
    try:
        assert wait_for(lambda: adapter.hazard is not None)
        assert adapter.hazard == "PHYSICS_RAW_SPOOL_OVERFLOW"
    finally:
        with pytest.raises(ValueError, match="PHYSICS_RAW_SPOOL_OVERFLOW"):      # close() surfaces the retained hazard
            adapter.close()
    dead_dir = tmp_path / "dead"
    dead_dir.mkdir()
    adapter, _ = spool_adapter(dead_dir)
    adapter._spool.child = SimpleNamespace(poll=lambda: 1, terminate=lambda: None, wait=lambda timeout=None: 1, kill=lambda: None)
    adapter.start_spool_reader()
    try:
        assert wait_for(lambda: adapter.hazard is not None)
        assert adapter.hazard == "PHYSICS_RAW_RECEIVER_FAILED"
    finally:
        with pytest.raises(ValueError, match="PHYSICS_RAW_RECEIVER_FAILED"):
            adapter.close()


def test_a_real_spooler_process_keeps_chunks_fresh_while_the_main_thread_stalls(tmp_path, isolated_ros_domain):
    """Real rclpy: a publisher at 10 Hz, the spooler subprocess, and a main thread that holds the GIL for ~160 ms."""
    import rclpy
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
    from so101_mujoco_support.msg import PhysicsStepEvidenceChunk
    from so101_demo.act.chunk_spool import SpoolProcess, SpoolReader

    topic = f"/c7_spool_test_{os.getpid()}"
    rclpy.init()
    process = SpoolProcess(tmp_path, topic=topic, max_bytes=1 << 26)
    try:
        node = rclpy.create_node("c7_spool_publisher")
        qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
        publisher = node.create_publisher(PhysicsStepEvidenceChunk, topic, qos)
        process.start()
        assert process.wait_ready(20.0)
        assert wait_for(lambda: publisher.get_subscription_count() >= 1, 10.0)      # discovery before the volatile publishes
        from rclpy.serialization import deserialize_message

        def delay_of(receipt, data):
            message = deserialize_message(data, PhysicsStepEvidenceChunk)
            return (receipt - message.samples[-1].clock_interval_begin_monotonic_ns) / 1e6

        sequence, step = 1, 101

        def publish_one():
            nonlocal sequence, step
            publisher.publish(_chunk(sequence=sequence, first=step, receipt=time.monotonic_ns() + 4_000_000))
            sequence, step = sequence + 1, step + 5

        # Warm-up (a test artefact, not a production delay): the first reliable samples after a match wait for the
        # discovery handshake (270-330 ms seen). Production meets the same first-chunk delay and now admits it as lateness
        # (CP-3410); this test measures the spooler's own stamping only after delivery is proven steady.
        reader = SpoolReader(tmp_path)
        seen = []
        end = time.monotonic() + 15.0
        while time.monotonic() < end:
            publish_one()
            time.sleep(0.1)
            seen += reader.read()
            if len(seen) >= 3 and all(delay_of(*frame) < 30.0 for frame in seen[-2:]):
                break
        else:
            raise AssertionError("delivery never became steady")
        skip = len(seen)
        big = json.dumps([{"k": list(range(200))} for _ in range(20000)])
        for index in range(8):
            publish_one()
            time.sleep(0.1)
            if index == 2:
                json.loads(big)                      # ~160 ms GIL stall in the main process
        end = time.monotonic() + 5.0
        while len(seen) < skip + 6 and time.monotonic() < end:
            seen += reader.read()
            time.sleep(0.02)
        measured = seen[skip:]
        assert len(measured) >= 6, (len(seen), skip, process.child.poll(), sorted(os.listdir(tmp_path)))
        delays = [delay_of(*frame) for frame in measured]
        assert max(delays) < 60.0, delays            # stamped in the spooler: the main stall is invisible
    finally:
        rclpy.shutdown()
