"""Process lifecycle for the installed simulation-only Teleop server."""

from __future__ import annotations

import os
from pathlib import Path

from .api import create_app, validate_bind_address
from .camera import CameraController, load_camera_presets
from .server import RosTelemetryWorker
from .service import TeleopService
from .web_bundle import WebBundleError, validate_web_bundle


def installed_web_assets() -> Path:
    override = os.environ.get("SO101_TELEOP_WEB_ROOT")
    if override:
        try:
            return validate_web_bundle(Path(override).expanduser().resolve())
        except WebBundleError as error:
            raise RuntimeError(f"Invalid SO101_TELEOP_WEB_ROOT: {error}") from error
    try:
        from ament_index_python.packages import get_package_share_directory
        root = Path(get_package_share_directory("so101_gazebo_demo")) / "web"
    except Exception:
        root = Path(__file__).resolve().parents[1] / "web" / "dist"
    try:
        return validate_web_bundle(root)
    except WebBundleError as error:
        raise RuntimeError(f"Installed Teleop Web bundle is invalid: {error}") from error


def main() -> None:
    import uvicorn

    address = validate_bind_address(os.environ.get("SO101_TELEOP_BIND", "127.0.0.1"))
    worker = RosTelemetryWorker()
    worker.start()
    camera_config = os.environ.get("SO101_CAMERA_VIEWS")
    if camera_config is None:
        from ament_index_python.packages import get_package_share_directory
        camera_config = str(Path(get_package_share_directory("so101_gazebo_demo")) / "config" / "camera_views.yaml")
    camera = CameraController(load_camera_presets(camera_config))
    captures = Path(os.environ.get("SO101_TELEOP_CAPTURE_DIR", "/tmp/so101-teleop-captures"))
    uvicorn.run(
        create_app(TeleopService(worker, camera), installed_web_assets(), captures),
        host=address,
        port=int(os.environ.get("SO101_TELEOP_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
