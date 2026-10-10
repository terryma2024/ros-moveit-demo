"""An ACT (seven-joint, neck controller) reset through `MujocoResetClient` over fake services. No broker."""
import json
import sys
from types import SimpleNamespace

from so101_demo.act.joints import ACT_JOINTS

CONTROLLERS = ("arm_controller", "gripper_controller", "neck_controller")


def snapshot(epoch, sequence, step=0):
    return SimpleNamespace(
        simulation_session_id="session", reset_epoch=epoch, publisher_sequence=sequence, simulation_step=step,
        simulation_time_s=0.0, paused=True,
        object_state=SimpleNamespace(position_world=(0.1, 0.2, 0.3), orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
                                     linear_velocity_world=(0.0, 0.0, 0.0), angular_velocity_world=(0.0, 0.0, 0.0)),
        minimum_signed_distance_m=0.0, maximum_normal_force_n=0.0)


class Observer:
    def __init__(self):
        self.values = iter((snapshot(3, 100), snapshot(4, 101), snapshot(4, 102)))

    def snapshot(self):
        return next(self.values)


class Services:
    def __init__(self):
        self.joint_callback_count = 10
        self.scalar_joint_callback_count = 20
        self.events, self.audit = [], False
        self.checks = 0

    def enable_reset_joint_audit(self):
        self.audit = True

    def pause(self, paused):
        self.events.append(("pause", paused))
        return True

    def switch_controllers(self, *, activate, deactivate):
        self.events.append(("switch", tuple(activate), tuple(deactivate)))
        return True

    def reset_world(self, keyframe, free_joint_overrides=(), *, joint_overrides=()):
        self.events.append(("reset_world", keyframe, tuple(item.name for item in joint_overrides)))
        self.scalar_joint_callback_count += 1
        return True

    def controllers_active(self, names):
        return True

    def latest_joint_velocities(self, names):
        return (0.0,) * len(names)

    def joints_converged(self, expected, tolerance, *, after_callback_count, names=None):
        self.checks += 1
        self.last_names = names
        return self.checks >= 2

    def reset_joint_snapshot(self, names):
        return {"callback_count": self.scalar_joint_callback_count, "simulation_session_id": "session",
                "reset_epoch": 4, "simulation_step": 0, "paused": True, "sim_time_s": 0.0,
                "positions": (0.0,) * len(names), "velocities": (0.0,) * len(names)}


def run():
    from so101_demo.backends.mujoco.client import JointResetOverride
    from so101_demo.backends.mujoco.reset import MujocoResetClient

    services = Services()
    resetter = MujocoResetClient(
        services, Observer(), simulation_session_id="session", controller_names=CONTROLLERS,
        expected_joint_positions=(0.0,) * 7, expected_object_position=(0.1, 0.2, 0.3), expected_joint_names=ACT_JOINTS,
        progress=lambda: setattr(services, "joint_callback_count", services.joint_callback_count + 1))
    receipt = resetter.reset("task_start", joint_overrides=tuple(JointResetOverride(n, 0.0) for n in ACT_JOINTS))
    broker = sorted(name for name in sys.modules if name.rsplit(".", 1)[-1] in (
        "leased_action_client", "command_broker", "ros_broker", "teacher_worker_lifecycle",
        "controller_reservation_client", "teacher_owner_peer"))
    return dict(new_epoch=receipt.new_epoch, events=services.events, audit=services.audit,
                names=list(services.last_names or ()), scalar=resetter.last_reset_joint_snapshot is not None,
                broker=broker)


if __name__ == "__main__":
    print("B1BJSON " + json.dumps(run()))
