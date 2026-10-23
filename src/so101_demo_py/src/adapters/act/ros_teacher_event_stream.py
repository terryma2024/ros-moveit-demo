"""ROS publisher and subscription for the Teacher event stream (`std_msgs/String` JSON on `/so101/teacher/events`).

QoS choice (one profile for both ends, so the endpoints always match):

* RELIABLE: a live Recorder must not lose an event to ordinary congestion. DDS retransmits, and a loss that retransmission
  cannot repair still shows up as a gap in `seq`, which the Recorder turns into an INVALID data verdict.
* KEEP_LAST with a bounded depth (256, four times the Teacher's 64-event queue): `publish()` then never blocks on a slow
  reader and memory is bounded. KEEP_ALL could stall the publisher thread on flow control and grow without limit, which is
  exactly the coupling this stream exists to avoid.
* VOLATILE (no late-joiner replay): a Recorder that was not matched before the Teacher started is not given history.
  Replaying it would make a late Recorder look complete although its camera, physics and world sources missed the start,
  so the data must be INVALID, and a missed `seq` 1 is how the Recorder sees that. TRANSIENT_LOCAL would also pin
  history inside the Teacher process.
"""

from __future__ import annotations

from ...act.teacher_event_stream import STREAM_QOS, STREAM_TOPIC


def stream_qos():
    from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy

    return QoSProfile(
        history=QoSHistoryPolicy.KEEP_LAST, depth=STREAM_QOS["depth"],
        reliability=QoSReliabilityPolicy.RELIABLE, durability=QoSDurabilityPolicy.VOLATILE)


def make_ros_publish(node):
    """(publish(text), close()) for the Teacher side. Raises if the node cannot create the publisher."""

    from std_msgs.msg import String

    publisher = node.create_publisher(String, STREAM_TOPIC, stream_qos())

    def publish(text: str) -> None:
        publisher.publish(String(data=text))

    def close() -> None:
        node.destroy_publisher(publisher)

    return publish, close


class RosTeacherEventSubscription:
    """Recorder side: hand each message's JSON text to `on_text` from the node's callback (no parsing here)."""

    def __init__(self, node, on_text) -> None:
        from std_msgs.msg import String

        self._node = node
        self.subscription = node.create_subscription(
            String, STREAM_TOPIC, lambda message: on_text(message.data), stream_qos())

    def publisher_count(self) -> int:
        return self._node.count_publishers(STREAM_TOPIC)

    def close(self) -> None:
        self._node.destroy_subscription(self.subscription)


def start_teacher_event_stream(node, session_id, reset_epoch, lease_identity=None, request_id=None):
    """(stream, close_publisher, error): the ROS publisher plus the non-blocking stream for one Teacher attempt.

    Any failure returns (None, None, "<message>"): the Teacher then runs without a stream, never without a run.
    """

    try:
        from ...act.teacher_event_stream import StreamIdentity, TeacherEventStream

        attempt_id = (lease_identity or {}).get("attempt_id") or request_id or "unscoped"
        publish, close = make_ros_publish(node)
        stream = TeacherEventStream(
            StreamIdentity(session_id, reset_epoch, attempt_id),
            clock_ns=lambda: node.get_clock().now().nanoseconds, publish=publish)
        return stream, close, None
    except Exception as error:
        return None, None, f"{type(error).__name__}: {error}"[:300]
