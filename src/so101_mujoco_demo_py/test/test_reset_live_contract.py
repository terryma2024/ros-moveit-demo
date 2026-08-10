from __future__ import annotations

import json
import math
import os
import time

import pytest
import rclpy

from so101_mujoco_demo_py.mujoco.client import MujocoRosClient
from so101_mujoco_demo_py.mujoco.observer import EvidenceStale, MujocoWorldObserver
from so101_mujoco_demo_py.mujoco.reset import MujocoResetClient, ResetFailed


@pytest.mark.skipif(
    os.environ.get("SO101_MUJOCO_RESET_LIVE_TEST") != "1",
    reason="requires the task-owned isolated MuJoCo launch",
)
def test_two_live_task_start_reset_cycles_are_epoch_correlated() -> None:
    session_id = os.environ["SO101_MUJOCO_SESSION_ID"]
    rclpy.init()
    observer_node = rclpy.create_node("so101_mujoco_reset_live_observer")
    service_node = rclpy.create_node("so101_mujoco_reset_live_services")
    joint_node = rclpy.create_node("so101_mujoco_reset_live_joints")
    observer = MujocoWorldObserver(observer_node, session_id, max_age_s=0.5)
    services = MujocoRosClient(service_node, joint_node, service_timeout_s=5.0)

    def drain_feedback(duration_s: float = 0.1) -> None:
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            rclpy.spin_once(observer_node, timeout_sec=0.005)
            services.progress()

    events = []

    class RecordingServices:
        def __init__(self):
            self._pending_reset_snapshot = False

        def _timed(self, operation, callback):
            started = time.monotonic()
            result = callback()
            events.append({"operation": operation, "elapsed_s": time.monotonic() - started})
            return result

        def pause(self, paused):
            result = self._timed(f"pause:{paused}", lambda: services.pause(paused))
            if paused and result:
                drain_feedback()
                snapshot = observer.snapshot()
                if snapshot.paused:
                    events[-1].update(
                        {
                            "reset_epoch": snapshot.reset_epoch,
                            "simulation_step": snapshot.simulation_step,
                            "publisher_sequence": snapshot.publisher_sequence,
                            "paused": snapshot.paused,
                            "object_position": snapshot.object_state.position_world,
                            "object_linear_velocity": snapshot.object_state.linear_velocity_world,
                            "object_angular_velocity": snapshot.object_state.angular_velocity_world,
                            "joint_positions": services.latest_joint_positions(),
                            "post_reset_snapshot": self._pending_reset_snapshot,
                        }
                    )
                    self._pending_reset_snapshot = False
            return result

        def switch_controllers(self, *, activate, deactivate):
            label = "activate" if activate else "deactivate"
            return self._timed(
                label,
                lambda: services.switch_controllers(activate=activate, deactivate=deactivate),
            )

        def reset_world(self, keyframe):
            result = self._timed("reset", lambda: services.reset_world(keyframe))
            self._pending_reset_snapshot = result
            return result

        def controllers_active(self, names):
            return services.controllers_active(names)

        @property
        def joint_callback_count(self):
            return services.joint_callback_count

        def joints_converged(self, expected, tolerance, *, after_callback_count):
            return services.joints_converged(
                expected, tolerance, after_callback_count=after_callback_count
            )

    recording_services = RecordingServices()

    def progress() -> None:
        rclpy.spin_once(observer_node, timeout_sec=0.005)
        services.progress()

    resetter = MujocoResetClient(
        recording_services,
        observer,
        simulation_session_id=session_id,
        controller_names=("arm_controller", "gripper_controller"),
        expected_joint_positions=(0.0,) * 6,
        expected_object_position=(0.27, 0.0, 0.08),
        timeout_s=10.0,
        object_tolerance_m=0.003,
        progress=progress,
    )
    deadline = time.monotonic() + 10.0
    try:
        while True:
            rclpy.spin_once(observer_node, timeout_sec=0.1)
            services.progress()
            try:
                observer.snapshot()
                break
            except EvidenceStale:
                if time.monotonic() >= deadline:
                    raise AssertionError(
                        "observer readiness timeout: "
                        "publishers="
                        f"{observer_node.count_publishers('/so101/simulation/evidence')} "
                        f"callbacks={observer.callback_count} "
                        f"joint_callbacks={services.joint_callback_count} "
                        f"rejected={observer.rejected_count} "
                        f"last_rejection={observer.last_rejection!r}"
                    )
        receipts = [resetter.reset("task_start"), resetter.reset("task_start")]
        latest = observer.snapshot()
        assert receipts[0].new_epoch == receipts[0].old_epoch + 1
        assert receipts[1].old_epoch == receipts[0].new_epoch
        assert receipts[1].new_epoch == receipts[1].old_epoch + 1
        assert all(receipt.keyframe == "task_start" for receipt in receipts)
        assert latest.reset_epoch == receipts[-1].new_epoch
        assert latest.simulation_step == 0
        assert all(receipt.simulation_step == 0 for receipt in receipts)
        assert not any(event["operation"] == "step" for event in events)
        assert latest.paused
        assert latest.object_state.position_world == pytest.approx((0.27, 0.0, 0.08), abs=0.003)
        assert services.latest_joint_positions() == pytest.approx((0.0,) * 6, abs=0.002)
        assert services.controllers_active(("arm_controller", "gripper_controller"))
        pause_events = [event for event in events if event["operation"] == "pause:True"]
        assert len(pause_events) == 4
        for event in pause_events:
            assert event["paused"]
        post_reset_pause_events = [event for event in pause_events if event["post_reset_snapshot"]]
        assert len(post_reset_pause_events) == 2
        for event in post_reset_pause_events:
            assert event["object_position"] == pytest.approx((0.27, 0.0, 0.08), abs=0.003)
            assert event["joint_positions"] == pytest.approx((0.0,) * 6, abs=0.002)
            assert all(
                math.isfinite(value)
                for field in (
                    "object_position",
                    "object_linear_velocity",
                    "object_angular_velocity",
                    "joint_positions",
                )
                for value in event[field]
            )

        epoch_before_invalid = latest.reset_epoch
        with pytest.raises(ResetFailed, match="reset"):
            resetter.reset("not_a_keyframe")
        drain_feedback()
        failed = observer.snapshot()
        assert failed.paused
        assert failed.reset_epoch == epoch_before_invalid
        print(
            json.dumps(
                {
                    "epochs": [[item.old_epoch, item.new_epoch] for item in receipts],
                    "joint_positions": services.latest_joint_positions(),
                    "object_position": latest.object_state.position_world,
                    "simulation_step": latest.simulation_step,
                    "transaction_events": events,
                    "invalid_keyframe_epoch": failed.reset_epoch,
                    "invalid_keyframe_paused": failed.paused,
                },
                sort_keys=True,
            )
        )
    finally:
        try:
            services.pause(True)
        except Exception:
            pass
        observer_node.destroy_node()
        service_node.destroy_node()
        joint_node.destroy_node()
        rclpy.shutdown()
