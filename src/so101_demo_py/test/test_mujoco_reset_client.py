from types import SimpleNamespace

import pytest

from so101_demo.backends.mujoco.client import (
    FreeJointResetOverride,
    MujocoRosClient,
)
from so101_demo.backends.mujoco.reset import MujocoResetClient, ResetFailed


def _snapshot(
    *,
    epoch: int,
    sequence: int,
    session: str = "session",
    step: int = 0,
    position=(0.1, 0.2, 0.3),
    orientation=(0.0, 0.0, 0.0, 1.0),
    linear_velocity=(0.0, 0.0, 0.0),
    angular_velocity=(0.0, 0.0, 0.0),
):
    return SimpleNamespace(
        simulation_session_id=session,
        reset_epoch=epoch,
        publisher_sequence=sequence,
        simulation_step=step,
        paused=True,
        object_state=SimpleNamespace(
            position_world=position,
            orientation_xyzw=orientation,
            linear_velocity_world=linear_velocity,
            angular_velocity_world=angular_velocity,
        ),
        minimum_signed_distance_m=0.0,
        maximum_normal_force_n=0.0,
    )


class Observer:
    def __init__(self, values=None) -> None:
        self._values = iter(
            values
            or (
                _snapshot(epoch=3, sequence=100),
                _snapshot(epoch=4, sequence=101),
                _snapshot(epoch=4, sequence=102),
            )
        )

    def snapshot(self):
        return next(self._values)


class Services:
    def __init__(self) -> None:
        self.joint_callback_count = 10
        self.convergence_checks = 0
        self.pauses = []
        self.reset_calls = []

    def pause(self, paused: bool) -> bool:
        self.pauses.append(paused)
        return True

    def switch_controllers(self, *, activate, deactivate) -> bool:
        return True

    def reset_world(self, keyframe: str, free_joint_overrides=()) -> bool:
        self.reset_calls.append((keyframe, free_joint_overrides))
        return keyframe == "task_start"

    def controllers_active(self, names) -> bool:
        return True

    def joints_converged(self, expected, tolerance, *, after_callback_count) -> bool:
        self.convergence_checks += 1
        return self.convergence_checks >= 2


def test_reset_waits_for_joint_convergence_before_final_pause() -> None:
    services = Services()
    resetter = MujocoResetClient(
        services,
        Observer(),
        simulation_session_id="session",
        controller_names=("arm_controller", "gripper_controller"),
        expected_joint_positions=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        expected_object_position=(0.1, 0.2, 0.3),
        progress=lambda: setattr(
            services, "joint_callback_count", services.joint_callback_count + 1
        ),
    )

    receipt = resetter.reset("task_start")

    assert receipt.new_epoch == 4
    assert services.convergence_checks >= 3
    assert services.pauses[-1] is True


class _CompletedFuture:
    def __init__(self, result) -> None:
        self._result = result

    def done(self) -> bool:
        return True

    def exception(self):
        return None

    def result(self):
        return self._result


class _CapturingClient:
    def __init__(self, response) -> None:
        self.response = response
        self.request = None

    def wait_for_service(self, *, timeout_sec: float) -> bool:
        return timeout_sec > 0.0

    def call_async(self, request):
        self.request = request
        return _CompletedFuture(self.response)


class _ServiceNode:
    def __init__(self) -> None:
        self.clients = {}

    def create_client(self, _service_type, name: str):
        response = SimpleNamespace(success=True, ok=True, controller=[])
        client = _CapturingClient(response)
        self.clients[name] = client
        return client


class _JointNode:
    def create_subscription(self, *_args):
        return object()


def test_reset_world_sends_plastic_cup_override(monkeypatch) -> None:
    from so101_demo.backends.mujoco import client as client_module

    service_node = _ServiceNode()
    monkeypatch.setattr(
        client_module.rclpy,
        "spin_until_future_complete",
        lambda *_args, **_kwargs: None,
    )
    client = MujocoRosClient(service_node, _JointNode())
    override = FreeJointResetOverride(
        name="plastic_cup",
        position_world_m=(-0.03, -0.28, 0.165),
        orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
    )

    assert client.reset_world("task_start", (override,)) is True

    request = service_node.clients[
        "/mujoco_ros2_control_node/reset_world"
    ].request
    assert request.keyframe == "task_start"
    assert len(request.state_overrides.free_joints) == 1
    message = request.state_overrides.free_joints[0]
    assert message.name == "plastic_cup"
    assert message.pose.header.frame_id == ""
    assert message.twist.header.frame_id == ""
    assert (
        message.pose.pose.position.x,
        message.pose.pose.position.y,
        message.pose.pose.position.z,
    ) == (-0.03, -0.28, 0.165)
    assert (
        message.pose.pose.orientation.x,
        message.pose.pose.orientation.y,
        message.pose.pose.orientation.z,
        message.pose.pose.orientation.w,
    ) == (0.0, 0.0, 0.0, 1.0)
    assert (
        message.twist.twist.linear.x,
        message.twist.twist.linear.y,
        message.twist.twist.linear.z,
        message.twist.twist.angular.x,
        message.twist.twist.angular.y,
        message.twist.twist.angular.z,
    ) == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: FreeJointResetOverride("", (0.0, 0.0, 0.0)),
        lambda: FreeJointResetOverride("plastic_cup", (float("nan"), 0.0, 0.0)),
        lambda: FreeJointResetOverride(
            "plastic_cup", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 2.0)
        ),
    ],
)
def test_free_joint_override_rejects_invalid_values(factory) -> None:
    with pytest.raises(ValueError, match="free joint override"):
        factory()


def test_reset_world_rejects_duplicate_override_names(monkeypatch) -> None:
    from so101_demo.backends.mujoco import client as client_module

    service_node = _ServiceNode()
    monkeypatch.setattr(
        client_module.rclpy,
        "spin_until_future_complete",
        lambda *_args, **_kwargs: None,
    )
    client = MujocoRosClient(service_node, _JointNode())
    override = FreeJointResetOverride("plastic_cup", (0.02, -0.28, 0.165))

    with pytest.raises(ValueError, match="duplicate free joint override"):
        client.reset_world("task_start", (override, override))
    assert service_node.clients["/mujoco_ros2_control_node/reset_world"].request is None


@pytest.mark.parametrize(
    ("changed", "failure"),
    [
        ({"position": (0.2, 0.2, 0.3)}, "object pose convergence failed"),
        ({"orientation": (0.0, 0.0, 0.1, 0.995)}, "object orientation convergence failed"),
        ({"linear_velocity": (0.01, 0.0, 0.0)}, "object linear velocity convergence failed"),
        ({"angular_velocity": (0.0, 0.01, 0.0)}, "object angular velocity convergence failed"),
        ({"session": "other"}, "evidence session mismatch"),
        ({"step": 1}, "reset evidence is not step zero"),
        ({"epoch": 5}, "reset epoch mismatch"),
    ],
)
def test_reset_verifies_requested_atomic_object_state(changed, failure) -> None:
    new_snapshot = {
        "epoch": 4,
        "sequence": 101,
        **changed,
    }
    services = Services()
    resetter = MujocoResetClient(
        services,
        Observer(
            (
                _snapshot(epoch=3, sequence=100),
                _snapshot(**new_snapshot),
            )
        ),
        simulation_session_id="session",
        controller_names=("arm_controller", "gripper_controller"),
        expected_joint_positions=(0.0,) * 6,
        expected_object_position=(0.1, 0.2, 0.3),
    )

    with pytest.raises(ResetFailed, match=failure):
        resetter.reset("task_start")
    assert services.pauses[-1] is True


def test_reset_passes_free_joint_overrides_to_service() -> None:
    services = Services()
    resetter = MujocoResetClient(
        services,
        Observer(),
        simulation_session_id="session",
        controller_names=("arm_controller", "gripper_controller"),
        expected_joint_positions=(0.0,) * 6,
        expected_object_position=(0.1, 0.2, 0.3),
        progress=lambda: setattr(
            services, "joint_callback_count", services.joint_callback_count + 1
        ),
    )
    override = FreeJointResetOverride("plastic_cup", (0.1, 0.2, 0.3))

    resetter.reset("task_start", (override,))

    assert services.reset_calls == [("task_start", (override,))]
