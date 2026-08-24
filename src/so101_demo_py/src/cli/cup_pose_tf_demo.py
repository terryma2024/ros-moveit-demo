"""Transform one camera-frame cup pose into the robot planning frame with tf2."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Callable
from typing import Any

from so101_demo.cli.cup_pose_subscriber import (
    CupPoseValidationError,
    status_line,
    validate_pose_message,
)


def transform_pose_message(
    message: Any,
    *,
    target_frame: str,
    query_time: Any,
    lookup_transform: Callable[[str, str, Any], Any],
    apply_transform: Callable[[Any, Any], Any],
) -> Any:
    """Look up target<-source and apply it to the complete PoseStamped message."""

    source_frame, _, _ = validate_pose_message(message)
    if not target_frame:
        raise ValueError("target_frame must be non-empty")
    transform = lookup_transform(target_frame, source_frame, query_time)
    return apply_transform(message, transform)


def _pose_record(input_frame: str, transformed: Any) -> dict[str, object]:
    pose = transformed.pose
    return {
        "input_frame_id": input_frame,
        "orientation_xyzw": [
            pose.orientation.x,
            pose.orientation.y,
            pose.orientation.z,
            pose.orientation.w,
        ],
        "output_frame_id": transformed.header.frame_id,
        "position_xyz": [pose.position.x, pose.position.y, pose.position.z],
        "status": "OK",
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cup_pose_tf_demo")
    parser.add_argument("--input-topic", default="/cup_pose_camera")
    parser.add_argument("--output-topic", default="/cup_pose")
    parser.add_argument("--target-frame", default="world")
    parser.add_argument("--timeout-s", type=float, default=10.0)
    options = parser.parse_args(arguments)
    if not options.input_topic:
        parser.error("--input-topic must be non-empty")
    if not options.output_topic:
        parser.error("--output-topic must be non-empty")
    if not options.target_frame:
        parser.error("--target-frame must be non-empty")
    if not math.isfinite(options.timeout_s) or options.timeout_s <= 0.0:
        parser.error("--timeout-s must be finite and positive")

    import rclpy
    from geometry_msgs.msg import PoseStamped
    from rclpy.time import Time
    from tf2_geometry_msgs import do_transform_pose_stamped
    from tf2_ros import Buffer, TransformException, TransformListener

    rclpy.init()
    node = rclpy.create_node("so101_cup_pose_tf_demo")
    tf_buffer = Buffer()
    tf_listener = TransformListener(tf_buffer, node)
    publisher = node.create_publisher(PoseStamped, options.output_topic, 10)
    received_messages: list[PoseStamped] = []

    def receive(message: PoseStamped) -> None:
        received_messages.append(message)

    subscription = node.create_subscription(
        PoseStamped,
        options.input_topic,
        receive,
        10,
    )
    pending_message: PoseStamped | None = None
    last_tf_error: TransformException | None = None
    deadline = time.monotonic() + options.timeout_s

    try:
        while rclpy.ok() and time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            rclpy.spin_once(node, timeout_sec=min(0.05, max(0.0, remaining)))
            if received_messages:
                pending_message = received_messages[-1]
                received_messages.clear()
                last_tf_error = None
            if pending_message is None:
                continue

            try:
                transformed = transform_pose_message(
                    pending_message,
                    target_frame=options.target_frame,
                    query_time=Time.from_msg(pending_message.header.stamp),
                    lookup_transform=tf_buffer.lookup_transform,
                    apply_transform=do_transform_pose_stamped,
                )
            except CupPoseValidationError as error:
                print(
                    status_line("ERROR", failure="CUP_POSE_INVALID", message=error),
                    flush=True,
                )
                return 1
            except TransformException as error:
                last_tf_error = error
                continue

            publisher.publish(transformed)
            rclpy.spin_once(node, timeout_sec=0.05)
            print(
                json.dumps(
                    _pose_record(pending_message.header.frame_id, transformed),
                    sort_keys=True,
                ),
                flush=True,
            )
            return 0

        if pending_message is not None and last_tf_error is not None:
            print(
                status_line(
                    "ERROR",
                    failure="CUP_POSE_TF_UNAVAILABLE",
                    message=last_tf_error,
                ),
                flush=True,
            )
        else:
            print(
                status_line(
                    "ERROR",
                    failure="CUP_POSE_TIMEOUT",
                    message=(
                        f"no pose received on {options.input_topic} "
                        f"within {options.timeout_s} seconds"
                    ),
                ),
                flush=True,
            )
        return 1
    except KeyboardInterrupt:
        print(status_line("STOPPED", reason="SIGINT"), flush=True)
        return 0
    finally:
        del subscription
        del publisher
        del tf_listener
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
