"""Test-only MuJoCo truth-to-``/cup_pose`` bridge for local E2E validation."""

from __future__ import annotations

import argparse


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mujoco_cup_pose_bridge")
    parser.add_argument("--session-id", required=True)
    options = parser.parse_args(arguments)

    import rclpy
    from geometry_msgs.msg import PoseStamped
    from rclpy._rclpy_pybind11 import RCLError
    from rclpy.parameter import Parameter
    from rclpy.qos import qos_profile_sensor_data

    from ..backends.mujoco.observer import EvidenceStale, MujocoWorldObserver

    rclpy.init()
    node = rclpy.create_node(
        "so101_mujoco_cup_pose_bridge",
        parameter_overrides=[Parameter("use_sim_time", value=True)],
    )
    publisher = node.create_publisher(PoseStamped, "/cup_pose", qos_profile_sensor_data)
    observer = MujocoWorldObserver(node, options.session_id, max_age_s=0.5)

    def publish() -> None:
        try:
            evidence = observer.snapshot()
        except EvidenceStale:
            return
        message = PoseStamped()
        message.header.frame_id = "world"
        message.header.stamp = node.get_clock().now().to_msg()
        position = evidence.object_state.position_world
        orientation = evidence.object_state.orientation_xyzw
        message.pose.position.x, message.pose.position.y, message.pose.position.z = position
        (
            message.pose.orientation.x,
            message.pose.orientation.y,
            message.pose.orientation.z,
            message.pose.orientation.w,
        ) = orientation
        publisher.publish(message)

    timer = node.create_timer(0.05, publish)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except RCLError:
        if rclpy.ok():
            raise
    finally:
        node.destroy_timer(timer)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
