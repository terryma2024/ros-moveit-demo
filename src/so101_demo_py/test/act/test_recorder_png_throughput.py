"""RECORDER_QUEUE_HIGH_WATERMARK on high-entropy table textures (metal_shelf) was a throughput problem: one writer thread encoded the
side and the wrist PNG one after the other (zlib level 6, about 31 ms per sample on metal_shelf against about 27 ms on laminate) and
the sample interval leaves about 30 ms of budget at the shard load. The cameras are now encoded concurrently (zlib releases the GIL).
The files, their sha256 and the decoded pixels are unchanged: only the wall time changes."""
import threading
import zlib

import numpy as np
import pytest

from so101_demo.act import recorder


def frames():
    rng = np.random.default_rng(7)
    noisy = rng.integers(0, 256, (480, 640, 3), dtype=np.uint8)
    smooth = np.tile(np.arange(640, dtype=np.uint8)[None, :, None], (480, 1, 3))
    return [noisy, smooth]


def decode(png):
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    start = png.index(b"IDAT")
    length = int.from_bytes(png[start - 4:start], "big")
    raw = zlib.decompress(png[start + 4:start + 4 + length])
    rows = np.frombuffer(raw, np.uint8).reshape(480, 1 + 1920)
    assert (rows[:, 0] == 0).all()
    return rows[:, 1:].reshape(480, 640, 3)


def test_concurrent_encoding_is_byte_identical_to_the_serial_encoder_and_keeps_the_order():
    given = frames()
    encoded = recorder._encode_pngs(given)
    assert encoded == [recorder._rgb_png(frame) for frame in given]
    for frame, png in zip(given, encoded):
        assert (decode(png) == frame).all()


def test_the_cameras_are_encoded_on_different_threads(monkeypatch):
    seen = []
    barrier = threading.Barrier(2, timeout=10)
    real = recorder._rgb_png

    def spy(frame):
        seen.append(threading.get_ident())
        barrier.wait()                       # both encodes must be in flight together
        return real(frame)

    monkeypatch.setattr(recorder, "_rgb_png", spy)
    recorder._encode_pngs(frames())
    assert len(set(seen)) == 2


def test_an_encoder_error_reaches_the_caller():
    with pytest.raises(Exception):
        recorder._encode_pngs([frames()[0], object()])
