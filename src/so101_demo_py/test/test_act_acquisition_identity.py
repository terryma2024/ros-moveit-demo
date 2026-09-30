"""Task 2: acquisition identity must be minted where the real frame is produced.

The head and wrist frames come from the C++ camera plugin, which publishes a `sensor_msgs/Image`
whose `header.stamp` is the MuJoCo sim time. Neither the plugin nor the message carries a source
sequence number, so the identity has to be created at the first place a real published frame exists
in Python, on the received pixels, and never reconstructed later from a consumer's selection or from
a file that was already written.
"""

import hashlib

import numpy as np
import pytest

from so101_demo.act.acquisition import (
    CAMERAS,
    Acquisition,
    AcquisitionGuard,
    AcquisitionMinter,
    pixel_digest,
)


def frame(camera="head", *, session="s", reset_epoch=1, sequence=1, stamp_s=0.1,
          received_monotonic_ns=1, pixels=None, **overrides):
    pixels = np.zeros((480, 640, 3), dtype=np.uint8) if pixels is None else pixels
    return Acquisition(
        camera, session, reset_epoch, sequence, f"{session}/{reset_epoch}/{camera}/{sequence}",
        stamp_s, received_monotonic_ns, (480, 640, 3), "uint8", pixel_digest(pixels))


def test_one_acquisition_cannot_fill_two_rows():
    a = Acquisition("head", "s", 1, 1, "s/1/head/1", 0.1, 1,
                    (480, 640, 3), "uint8", "a" * 64)
    guard = AcquisitionGuard()
    guard.accept(a)
    with pytest.raises(ValueError, match="ACQUISITION_REUSED"):
        guard.accept(a)


def test_new_acquisition_with_identical_pixels_is_accepted():
    """A still scene produces identical pixels; identity, not pixel change, decides."""

    guard = AcquisitionGuard()
    pixels = np.zeros((480, 640, 3), dtype=np.uint8)
    first = frame(sequence=7, stamp_s=1.0, pixels=pixels)
    second = frame(sequence=8, stamp_s=1.1, pixels=pixels)
    assert first.pixel_sha256 == second.pixel_sha256
    assert first.acquisition_id != second.acquisition_id
    guard.accept(first)
    guard.accept(second)


def test_guard_refuses_reuse_backwards_sequences_and_unknown_cameras():
    guard = AcquisitionGuard()
    guard.accept(frame(camera="head", sequence=4, stamp_s=1.0))
    guard.accept(frame(camera="wrist", sequence=4, stamp_s=1.0))

    with pytest.raises(ValueError, match="ACQUISITION_REUSED"):
        guard.accept(frame(camera="head", sequence=3, stamp_s=1.1))
    with pytest.raises(ValueError, match="ACQUISITION_REUSED"):
        guard.accept(frame(camera="head", sequence=4, stamp_s=1.2))
    with pytest.raises(ValueError, match="ACQUISITION_CAMERA_INVALID"):
        guard.accept(Acquisition("neck", "s", 1, 5, "s/1/neck/5", 1.2, 1,
                                 (480, 640, 3), "uint8", "a" * 64))


def test_guard_keeps_the_cameras_independent():
    guard = AcquisitionGuard()
    guard.accept(frame(camera="head", sequence=1))
    guard.accept(frame(camera="head", sequence=2))
    guard.accept(frame(camera="wrist", sequence=1))
    assert set(guard.last) == set(CAMERAS)
    assert guard.last["head"].sequence == 2
    assert guard.last["wrist"].sequence == 1


def test_a_forged_or_malformed_acquisition_is_refused():
    """Every field the later audit depends on is part of the identity, not decoration."""

    good = frame(sequence=3)
    for overrides, code in (
            ({"acquisition_id": "s/1/head/4"}, "ACQUISITION_ID_INVALID"),
            ({"acquisition_id": ""}, "ACQUISITION_ID_INVALID"),
            ({"sequence": 0}, "ACQUISITION_SEQUENCE_INVALID"),
            ({"sequence": True}, "ACQUISITION_SEQUENCE_INVALID"),
            ({"reset_epoch": -1}, "ACQUISITION_RESET_EPOCH_INVALID"),
            ({"session_id": ""}, "ACQUISITION_SESSION_INVALID"),
            ({"stamp_s": -0.1}, "ACQUISITION_STAMP_INVALID"),
            ({"stamp_s": float("nan")}, "ACQUISITION_STAMP_INVALID"),
            ({"received_monotonic_ns": 0}, "ACQUISITION_RECEIPT_INVALID"),
            ({"shape": (640, 480, 3)}, "ACQUISITION_SHAPE_INVALID"),
            ({"dtype": "float32"}, "ACQUISITION_DTYPE_INVALID"),
            ({"pixel_sha256": "A" * 64}, "ACQUISITION_DIGEST_INVALID"),
            ({"pixel_sha256": "a" * 63}, "ACQUISITION_DIGEST_INVALID")):
        broken = {field: getattr(good, field) for field in good.__dataclass_fields__}
        broken.update(overrides)
        with pytest.raises(ValueError, match=code):
            Acquisition(**broken)


def test_the_digest_is_computed_on_the_received_pixels_not_on_a_file():
    pixels = np.arange(480 * 640 * 3, dtype=np.uint8).reshape((480, 640, 3))
    digest = pixel_digest(pixels)
    assert digest == hashlib.sha256(np.ascontiguousarray(pixels).tobytes()).hexdigest()
    assert digest != pixel_digest(np.flipud(pixels))
    with pytest.raises(ValueError, match="ACQUISITION_PIXELS_INVALID"):
        pixel_digest(np.zeros((480, 640), dtype=np.uint8))
    with pytest.raises(ValueError, match="ACQUISITION_PIXELS_INVALID"):
        pixel_digest(np.zeros((480, 640, 3), dtype=np.float32))


def test_the_minter_creates_identity_at_the_moment_the_frame_arrives():
    minter = AcquisitionMinter()
    pixels = np.zeros((480, 640, 3), dtype=np.uint8)
    first = minter.mint("head", session_id="s", reset_epoch=1, stamp_s=0.1,
                        received_monotonic_ns=10, pixels=pixels)
    second = minter.mint("head", session_id="s", reset_epoch=1, stamp_s=0.2,
                         received_monotonic_ns=20, pixels=pixels)
    assert (first.sequence, second.sequence) == (1, 2)
    assert (first.acquisition_id, second.acquisition_id) == ("s/1/head/1", "s/1/head/2")
    assert first.pixel_sha256 == second.pixel_sha256
    assert minter.mint("wrist", session_id="s", reset_epoch=1, stamp_s=0.2,
                       received_monotonic_ns=20, pixels=pixels).sequence == 1


def test_the_minter_restarts_the_sequence_on_a_new_reset_epoch():
    minter = AcquisitionMinter()
    pixels = np.zeros((480, 640, 3), dtype=np.uint8)
    minter.mint("head", session_id="s", reset_epoch=1, stamp_s=0.1,
                received_monotonic_ns=10, pixels=pixels)
    fresh = minter.mint("head", session_id="s", reset_epoch=2, stamp_s=5.0,
                        received_monotonic_ns=30, pixels=pixels)
    assert (fresh.reset_epoch, fresh.sequence, fresh.acquisition_id) == (2, 1, "s/2/head/1")
    # and going back to an older epoch is refused rather than silently re-numbered
    with pytest.raises(ValueError, match="ACQUISITION_EPOCH_REGRESSED"):
        minter.mint("head", session_id="s", reset_epoch=1, stamp_s=6.0,
                    received_monotonic_ns=40, pixels=pixels)


def test_the_minter_refuses_a_stamp_that_goes_backwards():
    minter = AcquisitionMinter()
    pixels = np.zeros((480, 640, 3), dtype=np.uint8)
    minter.mint("head", session_id="s", reset_epoch=1, stamp_s=1.0,
                received_monotonic_ns=10, pixels=pixels)
    with pytest.raises(ValueError, match="ACQUISITION_STAMP_REGRESSED"):
        minter.mint("head", session_id="s", reset_epoch=1, stamp_s=0.5,
                    received_monotonic_ns=20, pixels=pixels)
    # an identical stamp is a duplicate publish of the same instant, not a new acquisition
    with pytest.raises(ValueError, match="ACQUISITION_STAMP_REGRESSED"):
        minter.mint("head", session_id="s", reset_epoch=1, stamp_s=1.0,
                    received_monotonic_ns=30, pixels=pixels)


class _Node:
    def create_subscription(self, *args, **kwargs):
        return None


class _Capture:
    def __init__(self):
        self.frames = []

    def on_acquisition(self, frame, pixels):
        self.frames.append((frame, pixels))


def _image_message(stamp_s, pixels):
    class _Stamp:
        sec = int(stamp_s)
        nanosec = int(round((stamp_s - int(stamp_s)) * 1e9))

    class _Header:
        stamp = _Stamp()

    class _Message:
        header = _Header()
        encoding = "rgb8"
        width = 640
        height = 480
        step = 1920
        data = pixels.tobytes()

    return _Message()


def test_the_production_adapter_mints_identity_from_the_published_frame():
    """Identity comes from the real published frame, not from a later selection or a PNG write."""

    from so101_demo.act.synchronizer import RgbObservationSynchronizer
    from so101_demo.adapters.act.ros_observation import RosObservationAdapter

    capture = _Capture()
    adapter = RosObservationAdapter(
        _Node(), RgbObservationSynchronizer(max_age_s=0.1, max_skew_s=0.1), capture=capture)
    adapter.reset("s", source_floor_s=0.0, reset_epoch=1)
    pixels = np.arange(480 * 640 * 3, dtype=np.uint8).reshape((480, 640, 3))

    adapter._image_locked("head", _image_message(1.0, pixels), received_monotonic_s=5.0)
    frame, seen = capture.frames[0]
    assert (frame.camera, frame.session_id, frame.reset_epoch) == ("head", "s", 1)
    assert (frame.sequence, frame.acquisition_id) == (1, "s/1/head/1")
    assert frame.stamp_s == 1.0 and frame.received_monotonic_ns == 5_000_000_000
    assert frame.pixel_sha256 == pixel_digest(pixels)
    assert np.array_equal(seen, pixels)

    adapter._image_locked("head", _image_message(1.1, pixels), received_monotonic_s=6.0)
    assert capture.frames[1][0].sequence == 2
    adapter._image_locked("head", _image_message(1.1, pixels), received_monotonic_s=7.0)
    assert len(capture.frames) == 2, "a duplicate publish must not mint a second identity"
    assert "ACQUISITION_STAMP_REGRESSED" in adapter.rejected
    assert adapter.last_acquisitions["head"].acquisition_id == "s/1/head/2"
