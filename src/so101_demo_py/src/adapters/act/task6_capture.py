"""Lossless read-only Task 6 camera samples; no qualification or commands."""

from __future__ import annotations

from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading

from PIL import Image as PillowImage

from so101_demo.act.joints import ACT_JOINTS


def _finite(value) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("TASK6_SOURCE_INVALID")
    return float(value)


def _stamp(message) -> float:
    try:
        value = message.header.stamp.sec + message.header.stamp.nanosec * 1e-9
    except (AttributeError, TypeError) as error:
        raise ValueError("TASK6_SOURCE_INVALID") from error
    return _finite(value)


def _write_new(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


class Task6FrameRecorder:
    """Join one atomic physics step to causal dual RGB, info and measured joints."""

    CAMERAS = ("head", "wrist")

    def __init__(self, root: Path, *, session_id: str, reset_epoch: int,
                 source_floor_s: float, max_age_s: float, max_skew_s: float) -> None:
        root = Path(root)
        if (not root.is_absolute() or ".." in root.parts
                or not isinstance(session_id, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", session_id) is None
                or type(reset_epoch) is not int or reset_epoch < 1):
            raise ValueError("TASK6_CAPTURE_SCOPE_INVALID")
        floor, age, skew = (_finite(value) for value in (
            source_floor_s, max_age_s, max_skew_s,
        ))
        if floor < 0 or not 0 < age <= .5 or not 0 < skew <= age:
            raise ValueError("TASK6_CAPTURE_LIMIT_INVALID")
        root.parent.mkdir(parents=True, exist_ok=True)
        if root.parent.is_symlink():
            raise ValueError("TASK6_CAPTURE_SCOPE_INVALID")
        root.mkdir(mode=0o700, exist_ok=False)
        self.root, self.session_id, self.reset_epoch = root, session_id, reset_epoch
        self.floor_s, self.max_age_s, self.max_skew_s = floor, age, skew
        self._buffers = {key: deque(maxlen=32) for key in (
            "head", "wrist", "head_info", "wrist_info", "joints",
        )}
        self._lock = threading.RLock()
        self._last_step = -1
        self._last_source_stamps = {}
        self._count = 0
        self._rejections = 0
        self._closed = False
        self._rows = (root / "frames.jsonl").open("x", encoding="utf-8")
        self._rejects = (root / "rejections.jsonl").open("x", encoding="utf-8")

    def accept_image(self, camera: str, message) -> None:
        if camera not in self.CAMERAS:
            raise ValueError("TASK6_RGB_INVALID")
        try:
            stamp = _stamp(message)
            frame = message.header.frame_id
            raw = bytes(message.data)
            valid = ((message.encoding, message.width, message.height, message.step,
                      len(raw), frame) ==
                     ("rgb8", 640, 480, 1920, 921600, f"{camera}_camera_frame"))
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("TASK6_RGB_INVALID") from error
        if not valid or stamp <= self.floor_s:
            raise ValueError("TASK6_RGB_INVALID")
        with self._lock:
            self._buffers[camera].append((stamp, raw))

    def accept_info(self, camera: str, message) -> None:
        if camera not in self.CAMERAS:
            raise ValueError("TASK6_CAMERA_INFO_INVALID")
        try:
            stamp = _stamp(message)
            frame = message.header.frame_id
            k = tuple(_finite(value) for value in message.k)
            d = tuple(_finite(value) for value in message.d)
            distortion = message.distortion_model
            dimensions = (message.width, message.height)
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("TASK6_CAMERA_INFO_INVALID") from error
        if (stamp <= self.floor_s or frame != f"{camera}_camera_frame"
                or dimensions != (640, 480)
                or len(k) != 9 or not d or not isinstance(distortion, str)
                or not distortion):
            raise ValueError("TASK6_CAMERA_INFO_INVALID")
        with self._lock:
            self._buffers[f"{camera}_info"].append((stamp, (k, d, distortion)))

    def accept_joints(self, message) -> None:
        try:
            stamp = _stamp(message)
            names = tuple(message.name)
            if (len(set(names)) != len(names) or len(names) != len(message.position)
                    or len(names) != len(message.velocity)):
                raise ValueError("joint mapping")
            positions = dict(zip(names, message.position, strict=True))
            velocities = dict(zip(names, message.velocity, strict=True))
            q = tuple(_finite(positions[name]) for name in ACT_JOINTS)
            v = tuple(_finite(velocities[name]) for name in ACT_JOINTS)
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ValueError("TASK6_JOINTS_INVALID") from error
        if stamp <= self.floor_s:
            raise ValueError("TASK6_JOINTS_INVALID")
        with self._lock:
            self._buffers["joints"].append((stamp, (q, v)))

    def record_rejection(self, reason: str, *, at_s: float | None = None) -> None:
        if not isinstance(reason, str) or not reason:
            raise ValueError("TASK6_REJECTION_INVALID")
        row = {"reason": reason, "at_s": None if at_s is None else _finite(at_s)}
        with self._lock:
            if self._closed:
                raise ValueError("TASK6_CAPTURE_CLOSED")
            self._rejects.write(json.dumps(row, separators=(",", ":")) + "\n")
            self._rejects.flush()
            os.fsync(self._rejects.fileno())
            self._rejections += 1

    def _select(self, key: str, at_s: float):
        candidates = [item for item in self._buffers[key]
                      if self.floor_s < item[0] <= at_s
                      and 0 <= at_s - item[0] <= self.max_age_s]
        if not candidates:
            raise ValueError("TASK6_SOURCE_STALE")
        return max(candidates, key=lambda item: item[0])

    def capture(self, world) -> dict:
        try:
            at_s = _finite(world.simulation_time_s)
            epoch, step = world.reset_epoch, world.simulation_step
            position = tuple(_finite(value) for value in world.object_state.position_world)
            orientation = tuple(_finite(value) for value in world.object_state.orientation_xyzw)
            scope_valid = (world.simulation_session_id == self.session_id
                           and type(epoch) is int and epoch == self.reset_epoch
                           and type(step) is int and step > 0
                           and world.paused is False and world.truncated is False
                           and len(position) == 3 and len(orientation) == 4)
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("TASK6_WORLD_SCOPE_INVALID") from error
        if not scope_valid or at_s <= self.floor_s:
            raise ValueError("TASK6_WORLD_SCOPE_INVALID")
        with self._lock:
            if self._closed:
                raise ValueError("TASK6_CAPTURE_CLOSED")
            if step <= self._last_step:
                raise ValueError("TASK6_WORLD_SCOPE_INVALID")
            selected = {key: self._select(key, at_s) for key in (
                "head", "wrist", "joints",
            )}
            for camera in self.CAMERAS:
                stamp = selected[camera][0]
                info = [item for item in self._buffers[f"{camera}_info"]
                        if item[0] == stamp]
                if not info:
                    raise ValueError("TASK6_CAMERA_INFO_MISSING")
                selected[f"{camera}_info"] = info[-1]
                if stamp <= self._last_source_stamps.get(camera, self.floor_s):
                    raise ValueError("TASK6_SOURCE_STALE")
            if selected["joints"][0] <= self._last_source_stamps.get("joints", self.floor_s):
                raise ValueError("TASK6_SOURCE_STALE")
            stamps = [at_s, *(item[0] for item in selected.values())]
            if max(stamps) - min(stamps) > self.max_skew_s:
                raise ValueError("TASK6_SOURCE_SKEW")
            index = self._count
            cameras = {}
            for camera in self.CAMERAS:
                stamp, raw = selected[camera]
                path = self.root / f"{index:05d}-{camera}.png"
                with path.open("xb") as stream:
                    PillowImage.frombytes("RGB", (640, 480), raw).save(stream, format="PNG")
                    stream.flush()
                    os.fsync(stream.fileno())
                k, d, distortion = selected[f"{camera}_info"][1]
                cameras[camera] = {
                    "png_path": path.name,
                    "png_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                    "image_stamp_s": stamp, "info_stamp_s": selected[f"{camera}_info"][0],
                    "frame_id": f"{camera}_camera_frame",
                    "k": list(k), "d": list(d), "distortion_model": distortion,
                }
            joint_stamp, (q, v) = selected["joints"]
            row = {
                "index": index, "simulation_session_id": self.session_id,
                "reset_epoch": epoch, "simulation_step": step,
                "simulation_time_s": at_s,
                "object_position_world_m": list(position),
                "object_orientation_xyzw": list(orientation),
                "joint_stamp_s": joint_stamp,
                "joint_positions_rad": list(q), "joint_velocities_rad_s": list(v),
                **cameras,
            }
            self._rows.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
            self._rows.flush()
            os.fsync(self._rows.fileno())
            self._last_step = step
            self._last_source_stamps = {key: selected[key][0]
                                        for key in (*self.CAMERAS, "joints")}
            self._count += 1
            return row

    def finish(self) -> dict:
        with self._lock:
            if self._closed:
                raise ValueError("TASK6_CAPTURE_CLOSED")
            self._rows.close()
            self._rejects.close()
            summary = {
                "status": "RECORDED_UNQUALIFIED",
                "simulation_session_id": self.session_id,
                "reset_epoch": self.reset_epoch,
                "samples": self._count, "rejections": self._rejections,
                "frames_sha256": hashlib.sha256(
                    (self.root / "frames.jsonl").read_bytes()).hexdigest(),
                "rejections_sha256": hashlib.sha256(
                    (self.root / "rejections.jsonl").read_bytes()).hexdigest(),
            }
            _write_new(self.root / "result.json", (
                json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode())
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            self._closed = True
            return summary
