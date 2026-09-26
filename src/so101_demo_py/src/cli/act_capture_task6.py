"""Observe an isolated ACT run for Task 6 without driving the robot."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from threading import Thread
import time

from so101_demo.adapters.act.task6_capture import Task6FrameRecorder


def _capture_best_world(recorder: Task6FrameRecorder, observer) -> dict:
    """Join the newest compatible fresh physics step to buffered camera sources."""
    history = observer.recent_with_receipts()
    try:
        return recorder.capture(history[-1].evidence)
    except ValueError as latest_error:
        first_error = latest_error
        if str(first_error) not in {
                "TASK6_SOURCE_STALE", "TASK6_SOURCE_SKEW",
                "TASK6_CAMERA_INFO_MISSING"}:
            raise
    for received in reversed(history[:-1]):
        try:
            return recorder.capture(received.evidence)
        except ValueError:
            continue
    raise first_error


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
    from so101_demo.backends.mujoco.observer import (
        EvidenceRejected, EvidenceStale, MujocoWorldObserver,
    )

    recorder = Task6FrameRecorder(
        experiments / options.run_id,
        session_id=options.session_id, reset_epoch=options.reset_epoch,
        source_floor_s=options.source_floor_s,
        max_age_s=options.max_age_s, max_skew_s=options.max_skew_s,
    )
    frame_node = world_node = frame_executor = world_executor = None
    threads: list[Thread] = []
    thread_errors: list[BaseException] = []
    finished = False
    finalizing = False
    try:
        rclpy.init()
        name = "act_task6_capture_" + options.run_id.replace("-", "_")
        frame_node = rclpy.create_node(
            name + "_frames", parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        world_node = rclpy.create_node(
            name + "_world", parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        observer = MujocoWorldObserver(
            world_node, options.session_id, max_age_s=options.max_age_s,
            subscription_depth=256,
        )

        def accept(method, *args):
            try:
                method(*args)
            except ValueError as error:
                recorder.record_rejection(str(error))

        for camera in ("head", "wrist"):
            frame_node.create_subscription(
                Image, f"/{camera}_camera/color",
                lambda message, label=camera: accept(recorder.accept_image, label, message),
                RGB_QOS,
            )
            frame_node.create_subscription(
                CameraInfo, f"/{camera}_camera/camera_info",
                lambda message, label=camera: accept(recorder.accept_info, label, message),
                RGB_QOS,
            )
        frame_node.create_subscription(
            JointState, "/joint_states",
            lambda message: accept(recorder.accept_joints, message),
            qos_profile_sensor_data,
        )
        frame_executor = SingleThreadedExecutor()
        world_executor = SingleThreadedExecutor()
        frame_executor.add_node(frame_node)
        world_executor.add_node(world_node)

        def spin(executor):
            try:
                executor.spin()
            except BaseException as error:
                thread_errors.append(error)

        for label, executor in (("frames", frame_executor), ("world", world_executor)):
            thread = Thread(target=spin, args=(executor,), name=name + "_" + label)
            thread.start()
            threads.append(thread)
        deadline = time.monotonic() + options.duration_s
        next_sample = time.monotonic()
        atomic_hazard = False
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now < next_sample:
                time.sleep(min(.01, next_sample - now))
                continue
            if thread_errors:
                recorder.record_rejection(
                    f"TASK6_SUBSCRIBER_ABORT: {type(thread_errors[0]).__name__}: {thread_errors[0]}"
                )
                atomic_hazard = True
                break
            next_sample += .1
            if now > next_sample + .1:
                recorder.record_rejection("TASK6_SAMPLE_TIMER_GAP")
                next_sample = now + .1
            try:
                _capture_best_world(recorder, observer)
            except EvidenceRejected as error:
                recorder.record_rejection(f"TASK6_ATOMIC_HAZARD: {error}")
                atomic_hazard = True
                break
            except (EvidenceStale, ValueError) as error:
                recorder.record_rejection(str(error))
        finalizing = True
        summary = recorder.finish()
        finished = True
        return 0 if summary["samples"] > 0 and not atomic_hazard else 2
    except BaseException as error:
        if not finished and not finalizing:
            recorder.record_rejection(f"TASK6_CAPTURE_ABORT: {type(error).__name__}: {error}")
        raise
    finally:
        try:
            for executor in (frame_executor, world_executor):
                if executor is not None:
                    executor.shutdown(timeout_sec=2.)
            for thread in threads:
                thread.join(timeout=2.)
            for node in (frame_node, world_node):
                if node is not None:
                    node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
        finally:
            if not finished and not finalizing:
                recorder.finish()


if __name__ == "__main__":
    raise SystemExit(main())
