"""Read exactly one externally published Coke pose and fail closed on bad input."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Callable
from typing import Any


class CokePoseValidationError(ValueError):
    """A received /coke_pose message does not satisfy the input contract."""


class CokePoseTimeoutError(TimeoutError):
    """No /coke_pose message arrived before the configured deadline."""


ValidatedPose = tuple[str, tuple[float, float, float], tuple[float, float, float, float]]


def _finite(value: Any, field: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise CokePoseValidationError(f"{field} must be finite") from error
    if not math.isfinite(numeric):
        raise CokePoseValidationError(f"{field} must be finite")
    return numeric


def validate_pose_message(message: Any) -> ValidatedPose:
    """Validate a geometry_msgs/msg/PoseStamped-shaped message without substituting a pose."""

    frame_id = message.header.frame_id
    if not frame_id:
        raise CokePoseValidationError("frame_id must be non-empty")
    position = tuple(
        _finite(getattr(message.pose.position, axis), f"position.{axis}")
        for axis in ("x", "y", "z")
    )
    orientation = tuple(
        _finite(getattr(message.pose.orientation, axis), f"orientation.{axis}")
        for axis in ("x", "y", "z", "w")
    )
    if not any(orientation):
        raise CokePoseValidationError("quaternion must be non-zero")
    return frame_id, position, orientation


def wait_for_pose_message(
    *,
    receive: Callable[[], Any | None],
    spin_once: Callable[[float], None],
    timeout_s: float,
    monotonic: Callable[[], float] = time.monotonic,
) -> ValidatedPose:
    """Wait for one received message; a timeout never manufactures a fallback pose."""

    if not math.isfinite(timeout_s) or timeout_s <= 0.0:
        raise ValueError("timeout_s must be finite and positive")
    deadline = monotonic() + timeout_s
    while monotonic() < deadline:
        message = receive()
        if message is not None:
            return validate_pose_message(message)
        spin_once(min(0.1, max(0.0, deadline - monotonic())))
    raise CokePoseTimeoutError(
        f"no /coke_pose message received within {timeout_s} seconds"
    )


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coke_pose_subscriber")
    parser.add_argument("--timeout-s", type=float, default=5.0)
    options = parser.parse_args(arguments)
    if not math.isfinite(options.timeout_s) or options.timeout_s <= 0.0:
        parser.error("--timeout-s must be finite and positive")

    import rclpy
    from geometry_msgs.msg import PoseStamped

    rclpy.init()
    node = rclpy.create_node("so101_coke_pose_subscriber")
    latest_message: PoseStamped | None = None

    def receive(message: PoseStamped) -> None:
        nonlocal latest_message
        latest_message = message

    subscription = node.create_subscription(PoseStamped, "/coke_pose", receive, 10)
    try:
        frame_id, position, orientation = wait_for_pose_message(
            receive=lambda: latest_message,
            spin_once=lambda timeout_s: rclpy.spin_once(node, timeout_sec=timeout_s),
            timeout_s=options.timeout_s,
        )
    except CokePoseTimeoutError as error:
        print(f"status=ERROR\nfailure=COKE_POSE_TIMEOUT\nmessage={error}", flush=True)
        return 1
    except CokePoseValidationError as error:
        print(f"status=ERROR\nfailure=COKE_POSE_INVALID\nmessage={error}", flush=True)
        return 1
    finally:
        del subscription
        node.destroy_node()
        rclpy.shutdown()

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
