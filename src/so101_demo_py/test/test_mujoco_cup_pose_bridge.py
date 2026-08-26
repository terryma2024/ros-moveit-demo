import sys
from types import ModuleType

import pytest


class FakeRCLError(RuntimeError):
    """Stand in for the rclpy binding exception raised after context shutdown."""


class FakeExternalShutdownException(Exception):
    """Stand in for the public executor exception raised by external shutdown."""


def _install_runtime_modules(
    monkeypatch,
    *,
    context_ok: bool,
    error_message: str = "failed to initialize wait set: the given context is not valid",
    error_type: type[Exception] = FakeRCLError,
):
    state = {
        "destroy_node_calls": 0,
        "destroy_timer_calls": 0,
        "shutdown_calls": 0,
    }

    class FakeNode:
        def create_publisher(self, *_args):
            return object()

        def create_timer(self, *_args):
            return object()

        def destroy_timer(self, _timer):
            state["destroy_timer_calls"] += 1

        def destroy_node(self):
            state["destroy_node_calls"] += 1

    node = FakeNode()
    rclpy = ModuleType("rclpy")
    rclpy.init = lambda: None
    rclpy.create_node = lambda *_args, **_kwargs: node
    rclpy.spin = lambda _node: (_ for _ in ()).throw(
        error_type(error_message)
    )
    rclpy.ok = lambda: context_ok
    rclpy.shutdown = lambda: state.__setitem__(
        "shutdown_calls", state["shutdown_calls"] + 1
    )

    rclpy_parameter = ModuleType("rclpy.parameter")
    rclpy_parameter.Parameter = lambda *_args, **_kwargs: object()
    rclpy_qos = ModuleType("rclpy.qos")
    rclpy_qos.qos_profile_sensor_data = object()
    rclpy_bindings = ModuleType("rclpy._rclpy_pybind11")
    rclpy_bindings.RCLError = FakeRCLError
    rclpy_executors = ModuleType("rclpy.executors")
    rclpy_executors.ExternalShutdownException = FakeExternalShutdownException

    geometry_msgs = ModuleType("geometry_msgs")
    geometry_msgs_msg = ModuleType("geometry_msgs.msg")
    geometry_msgs_msg.PoseStamped = object
    geometry_msgs.msg = geometry_msgs_msg

    observer = ModuleType("so101_demo.backends.mujoco.observer")
    observer.EvidenceStale = RuntimeError
    observer.MujocoWorldObserver = lambda *_args, **_kwargs: object()

    monkeypatch.setitem(sys.modules, "rclpy", rclpy)
    monkeypatch.setitem(sys.modules, "rclpy.parameter", rclpy_parameter)
    monkeypatch.setitem(sys.modules, "rclpy.qos", rclpy_qos)
    monkeypatch.setitem(sys.modules, "rclpy._rclpy_pybind11", rclpy_bindings)
    monkeypatch.setitem(sys.modules, "rclpy.executors", rclpy_executors)
    monkeypatch.setitem(sys.modules, "geometry_msgs", geometry_msgs)
    monkeypatch.setitem(sys.modules, "geometry_msgs.msg", geometry_msgs_msg)
    monkeypatch.setitem(sys.modules, "so101_demo.backends.mujoco.observer", observer)
    return state


def test_main_exits_cleanly_when_spin_reports_an_invalid_shutdown_context(monkeypatch) -> None:
    from so101_demo.ros import mujoco_cup_pose_bridge

    state = _install_runtime_modules(monkeypatch, context_ok=False)

    assert mujoco_cup_pose_bridge.main(["--session-id", "shutdown-test"]) == 0
    assert state == {
        "destroy_node_calls": 1,
        "destroy_timer_calls": 1,
        "shutdown_calls": 0,
    }


def test_main_exits_cleanly_when_executor_reports_external_shutdown(monkeypatch) -> None:
    from so101_demo.ros import mujoco_cup_pose_bridge

    state = _install_runtime_modules(
        monkeypatch,
        context_ok=False,
        error_message="",
        error_type=FakeExternalShutdownException,
    )

    assert mujoco_cup_pose_bridge.main(["--session-id", "external-shutdown-test"]) == 0
    assert state == {
        "destroy_node_calls": 1,
        "destroy_timer_calls": 1,
        "shutdown_calls": 0,
    }


def test_main_does_not_swallow_rcl_error_while_context_is_valid(monkeypatch) -> None:
    from so101_demo.ros import mujoco_cup_pose_bridge

    state = _install_runtime_modules(monkeypatch, context_ok=True)

    with pytest.raises(FakeRCLError, match="context is not valid"):
        mujoco_cup_pose_bridge.main(["--session-id", "runtime-error-test"])
    assert state == {
        "destroy_node_calls": 1,
        "destroy_timer_calls": 1,
        "shutdown_calls": 1,
    }


def test_main_does_not_swallow_unrelated_rcl_error_after_context_shutdown(monkeypatch) -> None:
    from so101_demo.ros import mujoco_cup_pose_bridge

    state = _install_runtime_modules(
        monkeypatch,
        context_ok=False,
        error_message="failed to take timer: unrelated middleware error",
    )

    with pytest.raises(FakeRCLError, match="unrelated middleware error"):
        mujoco_cup_pose_bridge.main(["--session-id", "shutdown-race-test"])
    assert state == {
        "destroy_node_calls": 1,
        "destroy_timer_calls": 1,
        "shutdown_calls": 0,
    }
