"""Relay edge-triggered Gazebo attachment events to durable ROS state."""

from . import __doc__ as _cli_package_loaded  # noqa: F401


def main(arguments: list[str] | None = None) -> int:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from std_msgs.msg import Empty, String

    from ..gazebo.attachment import AttachmentStateReducer
    from ..gazebo.transport import GazeboTransport

    rclpy.init(args=arguments)
    node = Node("gazebo_attachment_state_relay")
    node.declare_parameter("event_topic", "/so101/object_attached_event")
    node.declare_parameter("state_topic", "/so101/object_attached")
    node.declare_parameter("ready_topic", "/so101/object_attachment_relay_ready")
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    state_publisher = node.create_publisher(String, node.get_parameter("state_topic").value, qos)
    ready_publisher = node.create_publisher(Empty, node.get_parameter("ready_topic").value, qos)
    reducer = AttachmentStateReducer()
    transport = GazeboTransport()

    def event(value: str) -> None:
        if reducer.accept(value):
            message = String()
            message.data = reducer.state or ""
            state_publisher.publish(message)

    def publish_durable_state() -> None:
        state = reducer.state
        if state is not None:
            transport.publish_string(node.get_parameter("state_topic").value, state)

    if not transport.subscribe_string(node.get_parameter("event_topic").value, event):
        node.get_logger().error("failed to subscribe to Gazebo attachment events")
        node.destroy_node()
        rclpy.shutdown()
        return 1
    node.create_timer(0.05, publish_durable_state)
    ready_publisher.publish(Empty())
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
