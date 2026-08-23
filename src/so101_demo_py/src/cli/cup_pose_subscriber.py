"""Continuously read externally published cup poses and fail closed on bad input."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Callable
from typing import Any


class CupPoseValidationError(ValueError):
    """A received /cup_pose message does not satisfy the input contract."""


class CupPoseTimeoutError(TimeoutError):
    """No /cup_pose message arrived before the configured deadline."""


ValidatedPose = tuple[str, tuple[float, float, float], tuple[float, float, float, float]]


def status_line(status: str, **fields: object) -> str:
    """Format a status record as one terminal line."""

    values = {"status": status, **fields}
    return " ".join(
        f"{name}={' '.join(str(value).splitlines())}" for name, value in values.items()
    )


def _finite(value: Any, field: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise CupPoseValidationError(f"{field} must be finite") from error
    if not math.isfinite(numeric):
        raise CupPoseValidationError(f"{field} must be finite")
    return numeric


def validate_pose_message(message: Any) -> ValidatedPose:
    """Validate a geometry_msgs/msg/PoseStamped-shaped message without substituting a pose."""

    frame_id = message.header.frame_id
    if not frame_id:
        raise CupPoseValidationError("frame_id must be non-empty")
    position = tuple(
        _finite(getattr(message.pose.position, axis), f"position.{axis}")
        for axis in ("x", "y", "z")
    )
    orientation = tuple(
        _finite(getattr(message.pose.orientation, axis), f"orientation.{axis}")
        for axis in ("x", "y", "z", "w")
    )
    if not any(orientation):
        raise CupPoseValidationError("quaternion must be non-zero")
    return frame_id, position, orientation


def listen_for_pose_messages(
    *,
    receive: Callable[[], Any | None],
    spin_once: Callable[[float], None],
    on_pose: Callable[[ValidatedPose], None],
    timeout_s: float,
    on_invalid: Callable[[CupPoseValidationError], None] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    """Validate and publish every received pose until SIGINT or message inactivity stops us."""

    if not math.isfinite(timeout_s) or timeout_s <= 0.0:
        raise ValueError("timeout_s must be finite and positive")
    last_message_at = monotonic()
    while True:
        message = receive()
        if message is not None:
            last_message_at = monotonic()
            try:
                on_pose(validate_pose_message(message))
            except CupPoseValidationError as error:
                if on_invalid is None:
                    raise
                on_invalid(error)
            continue
        remaining = timeout_s - (monotonic() - last_message_at)
        if remaining <= 0.0:
            raise CupPoseTimeoutError(
                f"no /cup_pose message received within {timeout_s} seconds"
            )
        spin_once(min(0.1, remaining))


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cup_pose_subscriber")
    parser.add_argument("--timeout-s", type=float, default=5.0)
    options = parser.parse_args(arguments)
    if not math.isfinite(options.timeout_s) or options.timeout_s <= 0.0:
        parser.error("--timeout-s must be finite and positive")

    import rclpy
    from geometry_msgs.msg import PoseStamped

    rclpy.init()
    node = rclpy.create_node("so101_cup_pose_subscriber")
    received_messages: list[PoseStamped] = []

    def receive(message: PoseStamped) -> None:
        received_messages.append(message)

    def take_received_message() -> PoseStamped | None:
        if received_messages:
            return received_messages.pop(0)
        return None

    def report_pose(pose: ValidatedPose) -> None:
        frame_id, position, orientation = pose
        print(
            json.dumps(
                {
                    "frame_id": frame_id,
                    "orientation_xyzw": orientation,
                    "position_xyz": position,
                    "status": "OK",
                },
                sort_keys=True,
            ),
            flush=True,
        )

    def report_invalid(error: CupPoseValidationError) -> None:
        print(
            status_line("ERROR", failure="CUP_POSE_INVALID", message=error),
            flush=True,
        )

    subscription = node.create_subscription(PoseStamped, "/cup_pose", receive, 10)
    try:
        listen_for_pose_messages(
            receive=take_received_message,
            spin_once=lambda timeout_s: rclpy.spin_once(node, timeout_sec=timeout_s),
            on_pose=report_pose,
            on_invalid=report_invalid,
            timeout_s=options.timeout_s,
        )
    except KeyboardInterrupt:
        print(status_line("STOPPED", reason="SIGINT"), flush=True)
        return 0
    except CupPoseTimeoutError as error:
        print(
            status_line("ERROR", failure="CUP_POSE_TIMEOUT", message=error),
            flush=True,
        )
        return 1
    except CupPoseValidationError as error:
        print(
            status_line("ERROR", failure="CUP_POSE_INVALID", message=error),
            flush=True,
        )
        return 1
    finally:
        del subscription
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
