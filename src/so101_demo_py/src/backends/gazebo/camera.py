"""Gazebo GUI pose service adapter with explicit Boolean acknowledgement."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from typing import Any

from ...core.camera import CameraCommandReceipt, PoseCameraPreset


class CameraAdapterError(RuntimeError):
    def __init__(self, code: str, message: str, evidence: dict[str, object]) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.evidence = evidence


class GazeboCameraGateway:
    def __init__(
        self,
        *,
        runner: Callable[..., Any] = subprocess.run,
        service_timeout_ms: int = 3000,
        process_timeout_s: float = 5.0,
    ) -> None:
        self._runner = runner
        self._service_timeout_ms = service_timeout_ms
        self._process_timeout_s = process_timeout_s

    def apply(self, preset: PoseCameraPreset) -> CameraCommandReceipt:
        x, y, z = preset.position
        qx, qy, qz, qw = preset.orientation_xyzw
        request = (
            "pose: {"
            f" position: {{x: {x}, y: {y}, z: {z}}}"
            f" orientation: {{x: {qx}, y: {qy}, z: {qz}, w: {qw}}}"
            " }"
        )
        argv = [
            "gz",
            "service",
            "-s",
            "/gui/move_to/pose",
            "--reqtype",
            "gz.msgs.GUICamera",
            "--reptype",
            "gz.msgs.Boolean",
            "--timeout",
            str(self._service_timeout_ms),
            "--req",
            request,
        ]
        evidence: dict[str, object] = {
            "service": "/gui/move_to/pose",
            "position": preset.position,
            "orientation_xyzw": preset.orientation_xyzw,
            "service_timeout_ms": self._service_timeout_ms,
        }
        try:
            result = self._runner(
                argv,
                capture_output=True,
                text=True,
                check=False,
                shell=False,
                timeout=self._process_timeout_s,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired as error:
            raise CameraAdapterError(
                "CAMERA_SERVICE_TIMEOUT", str(error), evidence
            ) from error
        except OSError as error:
            raise CameraAdapterError(
                "CAMERA_SERVICE_UNAVAILABLE", str(error), evidence
            ) from error
        evidence.update(
            {
                "returncode": int(result.returncode),
                "stdout": str(result.stdout),
                "stderr": str(result.stderr),
            }
        )
        if result.returncode != 0:
            raise CameraAdapterError(
                "CAMERA_TRANSPORT_FAILED", "gz service returned nonzero", evidence
            )
        match = re.search(r"\bdata:\s*(true|false)\b", str(result.stdout).lower())
        if match is None:
            raise CameraAdapterError(
                "CAMERA_ACK_INVALID", "Boolean acknowledgement was absent", evidence
            )
        acknowledged = match.group(1) == "true"
        evidence["acknowledged"] = acknowledged
        if not acknowledged:
            raise CameraAdapterError(
                "CAMERA_ACK_REJECTED", "Gazebo rejected the camera pose", evidence
            )
        return CameraCommandReceipt(
            backend="gazebo",
            preset=preset.name,
            phase="ACKNOWLEDGE",
            success=True,
            failure_code=None,
            evidence=evidence,
        )
