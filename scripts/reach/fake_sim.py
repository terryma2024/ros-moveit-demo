#!/usr/bin/env python3
"""Stand-in for the simulator of the light reachability stack: publishes /clock and a fixed rest /joint_states at 100 Hz.

Reachability planning needs a clock, a robot state and the planning scene, not physics; the joint names are those of the rig the launch file
renders (checked by scripts/tests/test_reach_light_stack.py), the rest values were read from a running full execution stack.
"""
import time

NAMES = ("1", "2", "3", "4", "5", "6", "neck_yaw_joint")
POS = (-2.4442328958726838e-08, 0.0005697151721652635, 0.0004571714828193788, 0.00015483286535603098,
       4.7658608606157994e-12, -9.367383673816405e-12, 0.0)
VEL = (0.0,) * 7
CLOCK_START_NS = 10_000_000_000


def clock_ns(elapsed_s: float) -> int:
    return int(elapsed_s * 1e9) + CLOCK_START_NS


def main():
    import rclpy
    from builtin_interfaces.msg import Time
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import JointState

    class FakeSim(Node):
        def __init__(self):
            super().__init__("fake_sim")
            qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
            self.clock_pub = self.create_publisher(Clock, "/clock", qos)
            self.js_pub = self.create_publisher(JointState, "/joint_states", qos)
            self.t0 = time.monotonic()
            self.create_timer(0.01, self.tick)

        def tick(self):
            ns = clock_ns(time.monotonic() - self.t0)
            stamp = Time(sec=ns // 10**9, nanosec=ns % 10**9)
            clock = Clock()
            clock.clock = stamp
            self.clock_pub.publish(clock)
            state = JointState()
            state.header.stamp = stamp
            state.header.frame_id = "base_link"
            state.name = list(NAMES)
            state.position = list(POS)
            state.velocity = list(VEL)
            state.effort = [float("nan")] * len(NAMES)
            self.js_pub.publish(state)

    rclpy.init()
    rclpy.spin(FakeSim())


if __name__ == "__main__":
    main()
