"""Typed gateway for the MuJoCo viewer camera ROS services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeAlias

from .camera_presets import CameraPreset, FixedCameraPreset, FreeCameraPreset

SERVICE_TIMEOUT_SECONDS = 3.0
SET_SERVICE = "/mujoco_ros2_control_node/set_viewer_camera"
GET_SERVICE = "/mujoco_ros2_control_node/get_viewer_camera"


class ViewerCameraServiceError(RuntimeError):
    """Raised when viewer camera service discovery or invocation fails."""


@dataclass(frozen=True)
class FreeViewerCameraState:
    lookat: tuple[float, float, float]
    distance: float
    azimuth_deg: float
    elevation_deg: float
    orthographic: bool


@dataclass(frozen=True)
class FixedViewerCameraState:
    fixed_camera_name: str


ViewerCameraState: TypeAlias = FreeViewerCameraState | FixedViewerCameraState


class ViewerCameraGateway(Protocol):
    def set_camera(self, preset: CameraPreset) -> ViewerCameraState: ...

    def get_camera(self) -> ViewerCameraState: ...

    def close(self) -> None: ...


def viewer_camera_state_to_yaml_fields(state: ViewerCameraState) -> dict[str, object]:
    if isinstance(state, FreeViewerCameraState):
        return {
            "mode": "free",
            "lookat": list(state.lookat),
            "distance": state.distance,
            "azimuth_deg": state.azimuth_deg,
            "elevation_deg": state.elevation_deg,
            "orthographic": state.orthographic,
        }
    return {"mode": "fixed", "fixed_camera_name": state.fixed_camera_name}


def _state_from_message(message) -> ViewerCameraState:
    if message.mode == message.FREE:
        return FreeViewerCameraState(
            lookat=tuple(float(value) for value in message.lookat),
            distance=float(message.distance),
            azimuth_deg=float(message.azimuth_deg),
            elevation_deg=float(message.elevation_deg),
            orthographic=bool(message.orthographic),
        )
    if message.mode == message.FIXED:
        return FixedViewerCameraState(fixed_camera_name=message.fixed_camera_name)
    raise ViewerCameraServiceError(f"service returned unsupported camera mode: {message.mode}")


class RosViewerCameraGateway:
    """Synchronous, bounded ROS 2 viewer camera service gateway."""

    def __init__(self) -> None:
        import rclpy
        from mujoco_ros2_control_msgs.srv import GetViewerCamera, SetViewerCamera

        self._rclpy = rclpy
        self._get_type = GetViewerCamera
        self._set_type = SetViewerCamera
        self._initialized_rclpy = not rclpy.ok()
        if self._initialized_rclpy:
            rclpy.init(args=None)
        self._node = rclpy.create_node("so101_viewer_camera_client")
        self._set_client = self._node.create_client(SetViewerCamera, SET_SERVICE)
        self._get_client = self._node.create_client(GetViewerCamera, GET_SERVICE)
        self._closed = False

    def _call(self, client, request, service_label: str):
        if not client.wait_for_service(timeout_sec=SERVICE_TIMEOUT_SECONDS):
            raise ViewerCameraServiceError(
                f"{service_label} service unavailable after {SERVICE_TIMEOUT_SECONDS:.1f} seconds"
            )
        future = client.call_async(request)
        self._rclpy.spin_until_future_complete(
            self._node, future, timeout_sec=SERVICE_TIMEOUT_SECONDS
        )
        if not future.done():
            raise ViewerCameraServiceError(
                f"{service_label} service response timed out after {SERVICE_TIMEOUT_SECONDS:.1f} seconds"
            )
        try:
            return future.result()
        except Exception as error:
            raise ViewerCameraServiceError(
                f"{service_label} service call failed: {error}"
            ) from error

    def set_camera(self, preset: CameraPreset) -> ViewerCameraState:
        request = self._set_type.Request()
        if isinstance(preset, FreeCameraPreset):
            request.camera.mode = request.camera.FREE
            request.camera.lookat = list(preset.lookat)
            request.camera.distance = preset.distance
            request.camera.azimuth_deg = preset.azimuth_deg
            request.camera.elevation_deg = preset.elevation_deg
            request.camera.orthographic = preset.orthographic
            request.camera.fixed_camera_name = ""
        elif isinstance(preset, FixedCameraPreset):
            request.camera.mode = request.camera.FIXED
            request.camera.fixed_camera_name = preset.fixed_camera_name
        else:
            raise TypeError(f"unsupported camera preset: {type(preset).__name__}")
        response = self._call(self._set_client, request, "set viewer camera")
        if not response.success:
            raise ViewerCameraServiceError(response.message)
        return _state_from_message(response.applied_camera)

    def get_camera(self) -> ViewerCameraState:
        response = self._call(self._get_client, self._get_type.Request(), "get viewer camera")
        if not response.success:
            raise ViewerCameraServiceError(response.message)
        return _state_from_message(response.camera)

    def close(self) -> None:
        if self._closed:
            return
        self._node.destroy_node()
        if self._initialized_rclpy and self._rclpy.ok():
            self._rclpy.shutdown()
        self._closed = True
