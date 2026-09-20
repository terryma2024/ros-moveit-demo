"""Process lifecycle for the installed simulation-only Teleop server."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Mapping

from .api import create_app, validate_bind_address
from .backends.cli_adapter import CliBackendAdapter
from .backends.protocol import BackendProtocol
from .backends.registry import load_backend_profile
from .backends.protocol import BackendOperation
from .camera import BackendCameraController, CameraController, load_camera_presets
from .server import RosTelemetryWorker
from .service import TeleopService
from .models import TaskPointModel
from .task_artifacts import ManifestArtifactStore
from .task_gateway import CliTaskGateway
from .task_service import TaskService
from .web_bundle import WebBundleError, validate_web_bundle


def select_backend(
    environment: Mapping[str, str],
    *,
    profile_loader: Callable = load_backend_profile,
    adapter_factory: Callable = CliBackendAdapter,
) -> BackendProtocol:
    backend_id = environment.get("SO101_TELEOP_BACKEND")
    if not backend_id:
        raise RuntimeError("SO101_TELEOP_BACKEND is required")
    backend = adapter_factory(profile_loader(backend_id))
    probe = backend.probe()
    if not probe.ok:
        raise RuntimeError(
            f"{probe.error.code}: {probe.error.message}"
            if probe.error is not None else "BACKEND_PROBE_FAILED"
        )
    return backend


def task_station_mujoco_pid(environment: Mapping[str, str]) -> int:
    value = environment.get("SO101_TASK_STATION_MUJOCO_PID")
    try:
        pid = int(value) if value is not None else 0
    except ValueError as error:
        raise RuntimeError(
            "SO101_TASK_STATION_MUJOCO_PID must be a positive integer"
        ) from error
    if pid <= 0:
        raise RuntimeError("SO101_TASK_STATION_MUJOCO_PID must be a positive integer")
    return pid


def installed_web_assets() -> Path:
    override = os.environ.get("SO101_TELEOP_WEB_ROOT")
    if override:
        try:
            return validate_web_bundle(Path(override).expanduser().resolve())
        except WebBundleError as error:
            raise RuntimeError(f"Invalid SO101_TELEOP_WEB_ROOT: {error}") from error
    try:
        from ament_index_python.packages import get_package_share_directory
        root = Path(get_package_share_directory("so101_teleop")) / "web"
    except Exception:
        root = Path(__file__).resolve().parents[1] / "web" / "dist"
    try:
        return validate_web_bundle(root)
    except WebBundleError as error:
        raise RuntimeError(f"Installed Teleop Web bundle is invalid: {error}") from error


def main() -> None:
    """Deprecated console entry.

    The unified service is the only web listener in this package. This entry used to build the ROS
    worker and then call ``uvicorn.run(create_app(...))``, which is a second web entry point on its
    own port - exactly what the unified design removes. It now delegates, so an existing habit cannot
    raise a second listener, and no production path builds the legacy app any more.
    """
    import sys

    print(
        "so101_teleop.main is deprecated; use so101_unified_web_server.py "
        "(or `python -m so101_teleop.unified.main`)",
        file=sys.stderr,
    )
    from .unified.main import main as unified_main

    unified_main()


if __name__ == "__main__":
    main()
