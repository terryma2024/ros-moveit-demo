"""Acquisition identity for the two live cameras.

The head and wrist frames are rendered and published by the C++ camera plugin; the published
`sensor_msgs/Image` carries the MuJoCo sim time in `header.stamp` but no source sequence number, and
ROS 2 images have no `seq` field. The identity therefore has to be *created* at the first place a real
published frame exists, on the received pixels, and never rebuilt afterwards from a consumer's choice
or from a file that was already written.

`AcquisitionMinter` is that creator: one monotonic sequence per camera per session and reset epoch,
an acquisition id derived from that identity, and a digest computed on the uint8 array as it arrived,
in a fixed shape/dtype/byte order. `AcquisitionGuard` binds each acquisition to exactly one training
row, so a still scene — where consecutive acquisitions legitimately have identical pixels — can never
be filled by reusing an earlier frame.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re

import numpy as np

from .rig_profile import DEFAULT_RIG, KNOWN_RIGS

#: The cameras of the default rig (v1). Which cameras an episode may carry is its rig's business (`rig.camera_names`); an
#: Acquisition itself only has to be a camera of some known rig.
CAMERAS = DEFAULT_RIG.camera_names
ALL_CAMERAS = tuple(dict.fromkeys(name for rig in KNOWN_RIGS.values() for name in rig.camera_names))
_RGB_SHAPE = (480, 640, 3)
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _require_identifier(value, code: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or value != value.strip():
        raise ValueError(code)
    return value


def pixel_digest(pixels) -> str:
    """Digest the received pixels: fixed RGB shape, uint8 dtype and C byte order."""

    if (not isinstance(pixels, np.ndarray) or pixels.dtype != np.uint8
            or pixels.shape != _RGB_SHAPE):
        raise ValueError("ACQUISITION_PIXELS_INVALID")
    return hashlib.sha256(np.ascontiguousarray(pixels).tobytes()).hexdigest()


@dataclass(frozen=True)
class Acquisition:
    """One source frame of one camera, identified where it was produced."""

    camera: str
    session_id: str
    reset_epoch: int
    sequence: int
    acquisition_id: str
    stamp_s: float
    received_monotonic_ns: int
    shape: tuple
    dtype: str
    pixel_sha256: str

    def __post_init__(self) -> None:
        if self.camera not in ALL_CAMERAS:
            raise ValueError("ACQUISITION_CAMERA_INVALID")
        _require_identifier(self.session_id, "ACQUISITION_SESSION_INVALID")
        if type(self.reset_epoch) is not int or self.reset_epoch < 0:
            raise ValueError("ACQUISITION_RESET_EPOCH_INVALID")
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("ACQUISITION_SEQUENCE_INVALID")
        if (isinstance(self.stamp_s, bool) or not isinstance(self.stamp_s, (int, float))
                or not math.isfinite(self.stamp_s) or self.stamp_s < 0):
            raise ValueError("ACQUISITION_STAMP_INVALID")
        if type(self.received_monotonic_ns) is not int or self.received_monotonic_ns < 1:
            raise ValueError("ACQUISITION_RECEIPT_INVALID")
        if tuple(self.shape) != _RGB_SHAPE:
            raise ValueError("ACQUISITION_SHAPE_INVALID")
        if self.dtype != "uint8":
            raise ValueError("ACQUISITION_DTYPE_INVALID")
        if not isinstance(self.pixel_sha256, str) or _HEX64.fullmatch(self.pixel_sha256) is None:
            raise ValueError("ACQUISITION_DIGEST_INVALID")
        # the id is derived from the identity, so a copied frame cannot claim another slot
        if self.acquisition_id != canonical_acquisition_id(
                self.session_id, self.reset_epoch, self.camera, self.sequence):
            raise ValueError("ACQUISITION_ID_INVALID")


def canonical_acquisition_id(session_id: str, reset_epoch: int, camera: str,
                            sequence: int) -> str:
    return f"{session_id}/{reset_epoch}/{camera}/{sequence}"


class AcquisitionMinter:
    """Create the identity of a frame at the moment the real frame is received."""

    def __init__(self, rig=DEFAULT_RIG) -> None:
        self._last: dict = {}
        self.rig = rig

    def mint(self, camera, *, session_id, reset_epoch, stamp_s, received_monotonic_ns,
             pixels) -> Acquisition:
        if camera not in self.rig.camera_names:
            raise ValueError("ACQUISITION_CAMERA_INVALID")
        _require_identifier(session_id, "ACQUISITION_SESSION_INVALID")
        if type(reset_epoch) is not int or reset_epoch < 0:
            raise ValueError("ACQUISITION_RESET_EPOCH_INVALID")
        if (isinstance(stamp_s, bool) or not isinstance(stamp_s, (int, float))
                or not math.isfinite(stamp_s) or stamp_s < 0):
            raise ValueError("ACQUISITION_STAMP_INVALID")
        if type(received_monotonic_ns) is not int or received_monotonic_ns < 1:
            raise ValueError("ACQUISITION_RECEIPT_INVALID")

        previous = self._last.get(camera)
        if previous is not None and previous["session_id"] == session_id:
            if reset_epoch < previous["reset_epoch"]:
                raise ValueError("ACQUISITION_EPOCH_REGRESSED")
            if reset_epoch == previous["reset_epoch"]:
                if stamp_s <= previous["stamp_s"]:
                    # an identical stamp is a duplicate publish of one instant, not a new frame
                    raise ValueError("ACQUISITION_STAMP_REGRESSED")
                sequence = previous["sequence"] + 1
            else:
                sequence = 1
        else:
            sequence = 1

        digest = pixel_digest(pixels)
        self._last[camera] = {"session_id": session_id, "reset_epoch": reset_epoch,
                              "sequence": sequence, "stamp_s": float(stamp_s)}
        return Acquisition(camera, session_id, reset_epoch, sequence,
                           canonical_acquisition_id(session_id, reset_epoch, camera, sequence),
                           float(stamp_s), received_monotonic_ns, _RGB_SHAPE, "uint8", digest)


class AcquisitionGuard:
    """Bind each acquisition to one training row: reuse, regression and unknown cameras refuse."""

    def __init__(self) -> None:
        self.last: dict = {}

    def accept(self, frame: Acquisition) -> None:
        if not isinstance(frame, Acquisition):
            raise ValueError("ACQUISITION_INVALID")
        previous = self.last.get(frame.camera)
        if previous is not None:
            if (frame.acquisition_id == previous.acquisition_id
                    or frame.sequence == previous.sequence
                    or frame.sequence < previous.sequence):
                raise ValueError("ACQUISITION_REUSED")
        self.last[frame.camera] = frame
