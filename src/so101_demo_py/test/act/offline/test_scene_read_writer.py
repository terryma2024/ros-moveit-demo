"""The planning-scene sidecar file is written, flushed and fsync'd on its own thread behind a bounded queue.

No ROS here: the writer is a plain thread over a file. The read loop that feeds it is covered in `test_act_raw_readiness.py`.
"""

import os
import threading
import time

import pytest

from so101_demo.act.offline import raw_recorder
from so101_demo.act.offline.scene_read_writer import SceneReadWriter, SceneReadWriterError


def lines(count):
    return [(f'{{"n":{index},"pad":"{"x" * (index % 7)}"}}').encode()+b"\n" for index in range(count)]


def old_path_bytes(path, records):
    """What the previous read-loop code produced: buffered writes in order, flush and fsync every 20 records and at the end."""
    with open(path, "ab") as stream:
        for index, record in enumerate(records, start=1):
            stream.write(record)
            if index % 20 == 0:
                stream.flush()
                os.fsync(stream.fileno())
        stream.flush()
        os.fsync(stream.fileno())
    return path.read_bytes()


def test_every_record_is_written_in_order_and_identical_to_the_old_path(tmp_path):
    records = lines(333)
    expected = old_path_bytes(tmp_path / "old.jsonl", records)
    writer = SceneReadWriter(tmp_path / "new.jsonl")
    writer.start()
    for record in records:
        writer.put(record)
    writer.close()
    assert writer.failure is None and writer.written == 333
    assert (tmp_path / "new.jsonl").read_bytes() == expected == b"".join(records)


def test_close_fsyncs_everything_it_wrote_before_it_returns(tmp_path, monkeypatch):
    sizes = []
    real = os.fsync

    def spy(descriptor):
        sizes.append(os.fstat(descriptor).st_size)
        return real(descriptor)

    monkeypatch.setattr(os, "fsync", spy)
    records = lines(45)
    writer = SceneReadWriter(tmp_path / "scene.jsonl")
    writer.start()
    for record in records:
        writer.put(record)
    writer.close()
    assert len(sizes) == 3 and sizes[0] == len(b"".join(records[:20])) and sizes[1] == len(b"".join(records[:40]))   # every 20 records
    assert sizes[-1] == len(b"".join(records)) == (tmp_path / "scene.jsonl").stat().st_size   # the final one covers all of it


def test_a_slow_writer_never_delays_put(tmp_path, monkeypatch):
    real = os.fsync
    monkeypatch.setattr(os, "fsync", lambda descriptor: (time.sleep(1.0), real(descriptor))[1])
    writer = SceneReadWriter(tmp_path / "scene.jsonl")
    writer.start()
    slowest = 0.0
    for record in lines(60):
        began = time.perf_counter()
        writer.put(record)
        slowest = max(slowest, time.perf_counter()-began)
        time.sleep(0.005)
    assert slowest < 0.05, slowest
    writer.close(timeout_s=30.0)
    assert writer.failure is None and writer.written == 60


def test_a_write_error_is_a_failure_and_later_puts_refuse(tmp_path, monkeypatch):
    real = os.fsync

    def broken(descriptor):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "fsync", broken)
    writer = SceneReadWriter(tmp_path / "scene.jsonl")
    writer.start()
    for record in lines(20):
        writer.put(record)
    deadline = time.monotonic()+5.0
    while writer.failure is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert writer.failure is not None and writer.failure.startswith("RAW_SCENE_SIDECAR_WRITE_FAILED")
    with pytest.raises(SceneReadWriterError, match="RAW_SCENE_SIDECAR_WRITE_FAILED"):
        writer.put(b"{}\n")
    writer.close()
    assert writer.failure.startswith("RAW_SCENE_SIDECAR_WRITE_FAILED")
    monkeypatch.setattr(os, "fsync", real)


def test_a_full_queue_is_a_failure_not_a_silent_drop(tmp_path):
    release = threading.Event()

    class Held(SceneReadWriter):
        def _write(self, record):
            release.wait(10.0)
            super()._write(record)

    writer = Held(tmp_path / "scene.jsonl", capacity=3)
    writer.start()
    raised = None
    for record in lines(10):
        try:
            writer.put(record)
        except SceneReadWriterError as error:
            raised = error
            break
    assert raised is not None and "RAW_SCENE_SIDECAR_QUEUE_FULL" in str(raised)
    assert writer.failure == "RAW_SCENE_SIDECAR_QUEUE_FULL"
    release.set()
    writer.close()
    assert writer.failure == "RAW_SCENE_SIDECAR_QUEUE_FULL"


def test_close_that_cannot_drain_in_time_is_a_failure(tmp_path):
    release = threading.Event()

    class Held(SceneReadWriter):
        def _write(self, record):
            release.wait(10.0)
            super()._write(record)

    writer = Held(tmp_path / "scene.jsonl")
    writer.start()
    writer.put(b"{}\n")
    writer.close(timeout_s=0.2)
    assert writer.failure == "RAW_SCENE_SIDECAR_DRAIN_TIMEOUT"
    release.set()


def test_the_sidecar_file_is_opened_for_append(tmp_path):
    path = tmp_path / "scene.jsonl"
    path.write_bytes(b"before\n")
    writer = SceneReadWriter(path)
    writer.start()
    writer.put(b"after\n")
    writer.close()
    assert path.read_bytes() == b"before\nafter\n"
    assert raw_recorder.SceneReadSidecar is not None
