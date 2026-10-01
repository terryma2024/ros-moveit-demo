"""The Teleop head-camera backend: it consumes the closed head-search connection, never a detector.

The backend owns no detector and constructs none. It reads the closed descriptor named by
``SO101_HEAD_CAMERA_CONNECTION``, derives the ROS/session/generation/controller environment from it, and
refuses to compose when the socket root, runtime id or owner do not match exactly. Frames it publishes carry
the identity they were produced with, and the only detector reference is the one injected by the caller.
"""

from __future__ import annotations

import hashlib
import math
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

#: The websocket types are imported at module scope on purpose. This module carries
#: ``from __future__ import annotations``, so every annotation is a *string* that FastAPI resolves against
#: the module's globals; with a local import the stream endpoint's ``WebSocket`` was unresolvable, so
#: FastAPI validated the socket itself as a query parameter named ``websocket`` and closed every
#: handshake (403) before the handler ran (HS-325). The placeholders keep the backend half importable
#: without FastAPI, which was the only reason the import was local in the first place.
try:  # pragma: no cover - FastAPI is a hard dependency of the service that serves this router
    from fastapi import WebSocket, WebSocketDisconnect
except ImportError:  # pragma: no cover - a backend-only consumer needs no websocket types
    WebSocket = object  # type: ignore[assignment,misc]
    WebSocketDisconnect = Exception  # type: ignore[assignment,misc]

CONNECTION_ENV = "SO101_HEAD_CAMERA_CONNECTION"
SOCKET_DIR_ENV = "SO101_UNIFIED_SOCKET_DIR"
RUNTIME_ID_ENV = "SO101_UNIFIED_RUNTIME_ID"
MAX_FRAME_AGE_S = 0.5
#: a stop is only complete after this many consecutive raw samples
STOP_SAMPLES = 3


class CompositionBlocked(RuntimeError):
    """Composition cannot proceed: the environment and the closed descriptor disagree."""


class HeadCameraUnavailable(RuntimeError):
    """The Head Camera domain is unavailable because no closed connection was supplied."""


@dataclass(frozen=True, slots=True)
class FrameEnvelope:
    sequence: int
    jpeg_sha256: str
    detections: tuple[Mapping[str, object], ...]
    captured_wall_s: float
    model_id: str
    bundle_sha256: str


@dataclass
class HeadCameraBackend:
    """One head camera over the descriptor's exact runtime, with no detector of its own."""

    descriptor: Mapping[str, object]
    detector: object | None = None
    detector_factory_calls: int = 0
    sequence: int = 0
    stop_samples: int = 0
    _last_stop_stamp: float | None = field(default=None, repr=False)
    _last_frame: FrameEnvelope | None = field(default=None, repr=False)

    @property
    def runtime_owner(self) -> Mapping[str, object]:
        return dict(self.descriptor["owner"])

    @property
    def simulation_session_id(self) -> str:
        return str(self.descriptor["simulation_session_id"])

    @property
    def execution_generation(self) -> int:
        return int(self.descriptor["execution_generation"])

    @property
    def model_id(self) -> str:
        return str(self.descriptor["model_id"])

    def safe_interval_rad(self) -> list:
        """The sealed interval the target route is bounded by, or a zero-width one.

        A descriptor that declares no interval exposes a zero-width interval rather than nothing: the
        shipped panel destructures this field unconditionally, so an omission crashed the tab while the
        domain was perfectly available (HS-325). Zero width also means no motion is claimable, which is
        the honest reading of a descriptor that seals no interval.
        """

        interval = self.descriptor.get("safe_interval_rad")
        if not isinstance(interval, (list, tuple)) or len(interval) != 2:
            return [0.0, 0.0]
        return [float(interval[0]), float(interval[1])]

    def qualified(self) -> bool:
        """True only when the descriptor carries the closed head-only report the plan requires."""

        report = self.descriptor.get("qualification_report")
        return bool(isinstance(report, Mapping) and report.get("status") == "HEAD_SEARCH_QUALIFIED")

    def status(self) -> dict:
        return {
            "available": True,
            "operation": self.descriptor["operation"],
            "runtime_id": self.descriptor["runtime_id"],
            "model_id": self.model_id,
            "state": self.stop_state(),
            "detector_constructed": self.detector_factory_calls,
            "safe_interval_rad": self.safe_interval_rad(),
            "qualified": self.qualified(),
            # the composition verifies the owner before it composes; authority is the descriptor's own
            # declaration and is never inferred from a live process alone
            "authority": bool(self.descriptor.get("authority", False)),
        }

    def publish_once(self, *, jpeg: bytes = b"", detections: tuple = ()) -> FrameEnvelope:
        """Publish one frame carrying the identity it was produced with, never a detector's."""

        self.sequence += 1
        envelope = FrameEnvelope(
            sequence=self.sequence,
            jpeg_sha256=hashlib.sha256(jpeg).hexdigest(),
            detections=tuple(detections),
            captured_wall_s=time.time(),
            model_id=self.model_id,
            bundle_sha256=str(self.descriptor["bundle_sha256"]),
        )
        self._last_frame = envelope
        return envelope

    def submit_target(self, *, target_rad: float, safe_interval_rad) -> dict:
        low, high = (float(value) for value in safe_interval_rad)
        if not low <= float(target_rad) <= high:
            raise ValueError("HEAD_TARGET_OUT_OF_RANGE")
        return {"submitted_rad": float(target_rad), "status": "SUBMITTED"}

    def stop_state(self) -> str:
        """STOPPED only once the proof is complete; a stop in progress is never reported as stopped."""

        return "STOPPED" if self.stop_samples >= STOP_SAMPLES else "STOPPING"

    def stop(self, *, raw_sample: Mapping[str, object] | None = None) -> dict:
        """Count one raw sample towards the stop proof; only real, fresh samples count.

        The proof is built from samples, never from a caller's assertion: a sample must carry a finite
        non-negative velocity and a timestamp no older than the last one seen, and anything else resets the
        count instead of advancing it.
        """

        accepted = False
        if isinstance(raw_sample, Mapping):
            velocity = raw_sample.get("neck_velocity_rad_s")
            stamp = raw_sample.get("sim_time_s")
            if (
                isinstance(velocity, (int, float))
                and not isinstance(velocity, bool)
                and isinstance(stamp, (int, float))
                and not isinstance(stamp, bool)
                and math.isfinite(float(velocity))
                and float(velocity) >= 0.0
                and math.isfinite(float(stamp))
                and float(stamp) >= 0.0
                and (self._last_stop_stamp is None or float(stamp) > self._last_stop_stamp)
            ):
                accepted = True
                self._last_stop_stamp = float(stamp)
        self.stop_samples = self.stop_samples + 1 if accepted else 0
        return {"state": self.stop_state(), "consecutive_samples": self.stop_samples}

    def capture(self, *, now_wall_s: float | None = None) -> dict:
        """Return the last frame atomically, refusing a missing, stale or mismatched one."""

        frame = self._last_frame
        if frame is None:
            raise ValueError("HEAD_CAPTURE_NO_FRAME")
        now = time.time() if now_wall_s is None else float(now_wall_s)
        if now - frame.captured_wall_s > MAX_FRAME_AGE_S:
            raise ValueError("HEAD_CAPTURE_STALE_FRAME")
        if frame.bundle_sha256 != str(self.descriptor["bundle_sha256"]):
            raise ValueError("HEAD_CAPTURE_FRAME_MISMATCH")
        return {
            "sequence": frame.sequence,
            "jpeg_sha256": frame.jpeg_sha256,
            "detections": list(frame.detections),
            "model_id": frame.model_id,
            "bundle_sha256": frame.bundle_sha256,
        }


def load_descriptor(environment: Mapping[str, str] | None = None) -> dict:
    """Read the closed descriptor the environment names, or report the domain unavailable."""

    env = dict(os.environ if environment is None else environment)
    named = env.get(CONNECTION_ENV)
    if not named:
        raise HeadCameraUnavailable(
            "HEAD_CAMERA_UNAVAILABLE: the closed head-search connection was not supplied"
        )
    path = Path(named)
    if not path.is_file():
        raise HeadCameraUnavailable(f"HEAD_CAMERA_UNAVAILABLE: {path} does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


def compose_head_camera(environment: Mapping[str, str] | None = None, *, detector_factory=None):
    """Compose the backend, refusing any drift between the environment and the descriptor.

    The detector is never constructed here: the factory, when one is supplied, is recorded and called only
    if a caller asks for it explicitly, so a view-only composition constructs nothing.
    """

    env = dict(os.environ if environment is None else environment)
    descriptor = load_descriptor(env)
    socket_dir = env.get(SOCKET_DIR_ENV)
    runtime_id = env.get(RUNTIME_ID_ENV)
    if not socket_dir or Path(socket_dir).resolve() != Path(str(descriptor["bridge_socket_root"])).resolve():
        raise CompositionBlocked(
            "HEAD_CAMERA_CONNECTION_MISMATCH: the socket directory does not match the descriptor"
        )
    if not runtime_id or runtime_id != str(descriptor["runtime_id"]):
        raise CompositionBlocked(
            "HEAD_CAMERA_CONNECTION_MISMATCH: the runtime id does not match the descriptor"
        )
    owner = descriptor.get("owner")
    verify_owner(owner, expected_owner=env.get(OWNER_PID_ENV))
    return HeadCameraBackend(descriptor=dict(descriptor))


def head_camera_router(services) -> object:
    """The five Teleop Head Camera endpoints over a composed backend, or over an unavailable domain.

    The router reads the backend from the composed services; when the domain is unavailable every endpoint
    reports that rather than composing anything, so a view-only process exposes no head camera.
    """

    from fastapi import APIRouter, HTTPException

    router = APIRouter()

    def backend_or_503():
        backend = getattr(services, "head_camera", None)
        if backend is None:
            raise HTTPException(status_code=503, detail={"code": "HEAD_CAMERA_UNAVAILABLE"})
        return backend

    @router.get("/teleop/head-camera/status")
    def status() -> dict:
        return backend_or_503().status()

    @router.websocket("/teleop/head-camera/stream")
    async def stream(websocket: WebSocket) -> None:
        backend = getattr(services, "head_camera", None)
        await websocket.accept()
        if backend is None:
            await websocket.send_json({"code": "HEAD_CAMERA_UNAVAILABLE", "status": 503})
            await websocket.close(code=1013)
            return
        try:
            while True:
                await websocket.receive_text()
                envelope = backend.publish_once()
                await websocket.send_json(
                    {
                        "sequence": envelope.sequence,
                        "jpeg_sha256": envelope.jpeg_sha256,
                        "model_id": envelope.model_id,
                        "bundle_sha256": envelope.bundle_sha256,
                    }
                )
        except WebSocketDisconnect:
            return

    @router.post("/teleop/head-camera/target")
    def target(payload: dict) -> dict:
        backend = backend_or_503()
        if "safe_interval_rad" in payload:
            raise HTTPException(status_code=409, detail={"code": "HEAD_TARGET_INTERVAL_SEALED"})
        # the interval is the descriptor's, never the caller's
        interval = backend.descriptor["safe_interval_rad"]
        try:
            return backend.submit_target(target_rad=payload["target_rad"], safe_interval_rad=interval)
        except ValueError as error:
            if "HEAD_TARGET_OUT_OF_RANGE" in str(error):
                raise HTTPException(
                    status_code=409, detail={"code": "HEAD_TARGET_OUT_OF_RANGE"}
                ) from error
            raise

    @router.post("/teleop/head-camera/stop")
    def stop(payload: dict | None = None) -> dict:
        backend = backend_or_503()
        # the proof comes from the raw sample, never from a caller's boolean
        return backend.stop(raw_sample=payload)

    @router.post("/teleop/head-camera/capture")
    def capture() -> dict:
        backend = backend_or_503()
        try:
            return backend.capture()
        except ValueError as error:
            raise HTTPException(status_code=409, detail={"code": str(error)}) from error

    return router


OWNER_PID_ENV = "SO101_HEAD_CAMERA_OWNER_PID"


def process_start_ticks(pid: int) -> int | None:
    """The kernel's start ticks for a *running* process, or None when it is gone or a zombie.

    After the comm field, index 0 is the state; a process in state Z has exited and only awaits reaping, so
    it must not be accepted as a live owner even though its /proc entry and start ticks still exist.
    """

    try:
        fields = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
    except (OSError, ValueError):
        return None
    if not fields or fields[0] == "Z":
        return None
    return int(fields[19])


def verify_owner(owner, *, expected_owner=None) -> None:
    """Refuse a descriptor whose owner is absent, dead, drifted or not the expected process."""

    if not isinstance(owner, Mapping) or not owner.get("pid"):
        raise CompositionBlocked("HEAD_CAMERA_CONNECTION_MISMATCH: the descriptor names no owner")
    pid = int(owner["pid"])
    if pid <= 0:
        raise CompositionBlocked("HEAD_CAMERA_CONNECTION_MISMATCH: the owner pid is not positive")
    ticks = process_start_ticks(pid)
    if ticks is None:
        raise CompositionBlocked("HEAD_CAMERA_CONNECTION_MISMATCH: the owner process is not running")
    recorded = owner.get("started_ticks")
    if not isinstance(recorded, int) or recorded != ticks:
        raise CompositionBlocked(
            "HEAD_CAMERA_CONNECTION_MISMATCH: the owner start ticks do not match the live process"
        )
    if expected_owner is not None and str(pid) != str(expected_owner):
        raise CompositionBlocked("HEAD_CAMERA_CONNECTION_MISMATCH: the owner is not the expected process")
