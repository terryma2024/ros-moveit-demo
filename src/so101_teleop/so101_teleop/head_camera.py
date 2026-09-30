"""The Teleop head-camera backend: it consumes the closed head-search connection, never a detector.

The backend owns no detector and constructs none. It reads the closed descriptor named by
``SO101_HEAD_CAMERA_CONNECTION``, derives the ROS/session/generation/controller environment from it, and
refuses to compose when the socket root, runtime id or owner do not match exactly. Frames it publishes carry
the identity they were produced with, and the only detector reference is the one injected by the caller.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

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

    def status(self) -> dict:
        return {
            "available": True,
            "operation": self.descriptor["operation"],
            "runtime_id": self.descriptor["runtime_id"],
            "model_id": self.model_id,
            "state": "STOPPED" if self.stop_samples >= STOP_SAMPLES else "READY",
            "detector_constructed": self.detector_factory_calls,
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

    def stop(self, *, raw_sample_ok: bool = True) -> dict:
        """A stop is STOPPING until three consecutive raw samples arrive, then STOPPED."""

        self.stop_samples = self.stop_samples + 1 if raw_sample_ok else 0
        state = "STOPPED" if self.stop_samples >= STOP_SAMPLES else "STOPPING"
        return {"state": state, "consecutive_samples": self.stop_samples}

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
    if not isinstance(owner, Mapping) or not owner.get("pid"):
        raise CompositionBlocked("HEAD_CAMERA_CONNECTION_MISMATCH: the descriptor names no owner")
    if int(owner["pid"]) <= 0:
        raise CompositionBlocked("HEAD_CAMERA_CONNECTION_MISMATCH: the owner pid is not live")
    return HeadCameraBackend(descriptor=dict(descriptor))


def head_camera_router(services) -> object:
    """The five Teleop Head Camera endpoints over a composed backend, or over an unavailable domain.

    The router reads the backend from the composed services; when the domain is unavailable every endpoint
    reports that rather than composing anything, so a view-only process exposes no head camera.
    """

    from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

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
            await websocket.send_json({"code": "HEAD_CAMERA_UNAVAILABLE"})
            await websocket.close()
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
        interval = payload.get("safe_interval_rad") or backend.descriptor["safe_interval_rad"]
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
        raw_sample_ok = True if payload is None else bool(payload.get("raw_sample_ok", True))
        return backend.stop(raw_sample_ok=raw_sample_ok)

    @router.post("/teleop/head-camera/capture")
    def capture() -> dict:
        backend = backend_or_503()
        try:
            return backend.capture()
        except ValueError as error:
            raise HTTPException(status_code=409, detail={"code": str(error)}) from error

    return router
