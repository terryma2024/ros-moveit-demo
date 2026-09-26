"""Observe an isolated ACT run for Task 6 without driving the robot."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import time

from so101_demo.adapters.act.task6_capture import Task6FrameRecorder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record unqualified ACT Task 6 RGB evidence")
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--reset-epoch", type=int, required=True)
    parser.add_argument("--source-floor-s", type=float, required=True)
    parser.add_argument("--max-age-s", type=float, required=True)
    parser.add_argument("--max-skew-s", type=float, required=True)
    parser.add_argument("--duration-s", type=float, required=True)
    options = parser.parse_args(argv)
    root = options.evidence_root
    if (not root.is_absolute() or ".." in root.parts or not root.is_dir()
            or root.is_symlink()
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", options.run_id) is None
            or not 0 < options.duration_s <= 120):
        raise ValueError("TASK6_CAPTURE_SCOPE_INVALID")
    experiments = root / "experiments"
    if not experiments.is_dir() or experiments.is_symlink():
        raise ValueError("TASK6_CAPTURE_SCOPE_INVALID")
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.parameter import Parameter
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import CameraInfo, Image, JointState

    from so101_demo.adapters.act.ros_observation import RGB_QOS
    from so101_demo.backends.mujoco.observer import EvidenceStale, MujocoWorldObserver

    recorder = Task6FrameRecorder(
        experiments / options.run_id,
        session_id=options.session_id, reset_epoch=options.reset_epoch,
        source_floor_s=options.source_floor_s,
        max_age_s=options.max_age_s, max_skew_s=options.max_skew_s,
    )
    node = executor = None
    finished = False
    finalizing = False
    try:
        rclpy.init()
        name = "act_task6_capture_" + options.run_id.replace("-", "_")
        node = rclpy.create_node(
            name, parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        observer = MujocoWorldObserver(
            node, options.session_id, max_age_s=options.max_age_s,
        )

        def accept(method, *args):
            try:
                method(*args)
            except ValueError as error:
                recorder.record_rejection(str(error))

        for camera in ("head", "wrist"):
            node.create_subscription(
                Image, f"/{camera}_camera/color",
                lambda message, label=camera: accept(recorder.accept_image, label, message),
                RGB_QOS,
            )
            node.create_subscription(
                CameraInfo, f"/{camera}_camera/camera_info",
                lambda message, label=camera: accept(recorder.accept_info, label, message),
                RGB_QOS,
            )
        node.create_subscription(
            JointState, "/joint_states",
            lambda message: accept(recorder.accept_joints, message),
            qos_profile_sensor_data,
        )
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        deadline = time.monotonic() + options.duration_s
        next_sample = time.monotonic()
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=.01)
            now = time.monotonic()
            if now < next_sample:
                continue
            next_sample += .1
            if now > next_sample + .1:
                recorder.record_rejection("TASK6_SAMPLE_TIMER_GAP")
                next_sample = now + .1
            try:
                world = observer.recent_with_receipts()[-1].evidence
                recorder.capture(world)
            except (EvidenceStale, ValueError) as error:
                recorder.record_rejection(str(error))
        finalizing = True
        summary = recorder.finish()
        finished = True
        return 0 if summary["samples"] > 0 else 2
    except BaseException as error:
        if not finished and not finalizing:
            recorder.record_rejection(f"TASK6_CAPTURE_ABORT: {type(error).__name__}: {error}")
        raise
    finally:
        try:
            if executor is not None:
                executor.shutdown(timeout_sec=2.)
            if node is not None:
                node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
        finally:
            if not finished and not finalizing:
                recorder.finish()


if __name__ == "__main__":
    raise SystemExit(main())
