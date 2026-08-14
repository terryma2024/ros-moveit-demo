from types import SimpleNamespace

from so101_demo.backends.mujoco.reset import MujocoResetClient


def _snapshot(*, epoch: int, sequence: int):
    return SimpleNamespace(
        simulation_session_id="session",
        reset_epoch=epoch,
        publisher_sequence=sequence,
        simulation_step=0,
        paused=True,
        object_state=SimpleNamespace(
            position_world=(0.1, 0.2, 0.3),
            orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
            linear_velocity_world=(0.0, 0.0, 0.0),
            angular_velocity_world=(0.0, 0.0, 0.0),
        ),
        minimum_signed_distance_m=0.0,
        maximum_normal_force_n=0.0,
    )


class Observer:
    def __init__(self) -> None:
        self._values = iter(
            (
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

    def pause(self, paused: bool) -> bool:
        self.pauses.append(paused)
        return True

    def switch_controllers(self, *, activate, deactivate) -> bool:
        return True

    def reset_world(self, keyframe: str) -> bool:
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
