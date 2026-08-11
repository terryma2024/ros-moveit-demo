from __future__ import annotations

import os
import signal
import subprocess
import time
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOCKED_FORK_INSTALL = (PROJECT_ROOT.parent / "ws_mujoco_ros2_control_fork" / "install").resolve()

pytestmark = pytest.mark.skipif(
    os.environ.get("SO101_MUJOCO_LIVE_TEST") != "1",
    reason="set SO101_MUJOCO_LIVE_TEST=1 to run the isolated live MuJoCo contract",
)


def wait_for_response(rclpy, node, client, request):
    future = client.call_async(request)
    rclpy.spin_until_future_complete(node, future, timeout_sec=10.0)
    assert future.done(), "camera service response timed out"
    return future.result()


def test_headless_viewer_camera_services_reject_explicitly_and_keep_reset_services() -> None:
    import rclpy
    from ament_index_python.packages import get_package_prefix
    from mujoco_ros2_control_msgs.srv import (
        GetViewerCamera,
        ResetWorld,
        SetPause,
        SetViewerCamera,
        StepSimulation,
    )

    assert Path(get_package_prefix("mujoco_ros2_control_msgs")).resolve() == LOCKED_FORK_INSTALL
    assert Path(get_package_prefix("mujoco_ros2_control")).resolve() == LOCKED_FORK_INSTALL

    environment = dict(os.environ)
    environment["ROS_DOMAIN_ID"] = environment.get("SO101_MUJOCO_TEST_DOMAIN_ID", "187")
    os.environ["ROS_DOMAIN_ID"] = environment["ROS_DOMAIN_ID"]
    command = [
        "ros2",
        "launch",
        "so101_mujoco_demo_py",
        "so101_mujoco.launch.py",
        "start_simulation:=true",
        "headless:=true",
        "readiness_timeout_s:=30.0",
        f"simulation_session_id:=viewer-camera-live-{uuid.uuid4().hex}",
    ]
    process = subprocess.Popen(
        command,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    initialized_here = not rclpy.ok()
    if initialized_here:
        rclpy.init(args=None)
    node = rclpy.create_node("viewer_camera_headless_contract")
    try:
        clients = {
            "get": node.create_client(
                GetViewerCamera, "/mujoco_ros2_control_node/get_viewer_camera"
            ),
            "set": node.create_client(
                SetViewerCamera, "/mujoco_ros2_control_node/set_viewer_camera"
            ),
            "reset": node.create_client(ResetWorld, "/mujoco_ros2_control_node/reset_world"),
            "pause": node.create_client(SetPause, "/mujoco_ros2_control_node/set_pause"),
            "step": node.create_client(StepSimulation, "/mujoco_ros2_control_node/step_simulation"),
        }
        deadline = time.monotonic() + 30.0
        missing = set(clients)
        while missing and time.monotonic() < deadline and process.poll() is None:
            missing = {
                name
                for name, client in clients.items()
                if not client.wait_for_service(timeout_sec=0.2)
            }
        assert process.poll() is None, "headless launch exited before services became ready"
        assert not missing, f"services unavailable: {sorted(missing)}"

        get_response = wait_for_response(rclpy, node, clients["get"], GetViewerCamera.Request())
        set_request = SetViewerCamera.Request()
        set_request.camera.mode = set_request.camera.FREE
        set_request.camera.lookat = [0.0, 0.0, 0.25]
        set_request.camera.distance = 1.2
        set_request.camera.azimuth_deg = 135.0
        set_request.camera.elevation_deg = -20.0
        set_request.camera.orthographic = False
        set_response = wait_for_response(rclpy, node, clients["set"], set_request)

        for response in (get_response, set_response):
            assert response.success is False
            assert response.message == "viewer unavailable"
    finally:
        node.destroy_node()
        if initialized_here and rclpy.ok():
            rclpy.shutdown()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5.0)
        if process.stdout is not None:
            output = process.stdout.read()
            evidence = Path("/tmp/so101-debug-mujoco-viewer-camera/task8-headless-live.log")
            evidence.write_text(output, encoding="utf-8")
