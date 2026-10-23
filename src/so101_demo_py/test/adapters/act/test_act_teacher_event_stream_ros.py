"""One real-topic round trip of the Teacher event stream through rclpy (Phase A4a).

A private ROS domain keeps the test off any other stack on the host. The publisher thread of the Teacher stream, the
reliable/volatile/keep_last QoS and the strict consumer monitor are the production objects.
"""

import time

import pytest

from so101_demo.act.teacher_event_stream import (EVENT_TYPES, STREAM_TOPIC, EventStreamMonitor, StreamIdentity,
                                                 TeacherEventStream, decode_event)

IDENTITY = StreamIdentity("session-ros", 4, "attempt-ros")


@pytest.fixture
def ros_context(isolated_ros_domain):
    import rclpy
    from rclpy.context import Context

    context = Context()
    rclpy.init(context=context, domain_id=isolated_ros_domain)
    try:
        yield context
    finally:
        rclpy.shutdown(context=context)


def _nodes(context):
    import rclpy
    from rclpy.executors import SingleThreadedExecutor

    teacher = rclpy.create_node("teacher_stream_test", context=context)
    recorder = rclpy.create_node("recorder_stream_test", context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(teacher)
    executor.add_node(recorder)
    return teacher, recorder, executor


def _spin_until(executor, condition, timeout_s):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        executor.spin_once(timeout_sec=0.05)
        if condition():
            return True
    return condition()


def test_the_published_stream_arrives_complete_in_order_over_a_real_topic(ros_context):
    from so101_demo.adapters.act.ros_teacher_event_stream import RosTeacherEventSubscription, make_ros_publish

    teacher, recorder, executor = _nodes(ros_context)
    received = []
    subscription = RosTeacherEventSubscription(recorder, received.append)
    try:
        publish, close = make_ros_publish(teacher)
        assert _spin_until(executor, lambda: teacher.count_subscribers(STREAM_TOPIC) >= 1, 10.0), "no DDS match"
        stream = TeacherEventStream(IDENTITY, clock_ns=lambda: 7, publish=publish, poll_s=0.001)
        for index, kind in enumerate(EVENT_TYPES):
            stream.offer(kind, {"n": index})
        assert _spin_until(executor, lambda: len(received) == len(EVENT_TYPES), 10.0), received
        stream.close(flush_timeout_s=2.0)
        monitor = EventStreamMonitor(IDENTITY)
        events = [monitor.accept(text) for text in received]
        assert [event["type"] for event in events] == list(EVENT_TYPES)
        assert [event["seq"] for event in events] == list(range(1, len(EVENT_TYPES) + 1))
        assert stream.snapshot()["published"] == len(EVENT_TYPES) and stream.snapshot()["publish_failures"] == 0
        close()
    finally:
        subscription.close()
        executor.shutdown()
        teacher.destroy_node()
        recorder.destroy_node()


def test_the_documented_qos_is_reliable_volatile_keep_last_with_a_bounded_depth(ros_context):
    from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSReliabilityPolicy

    from so101_demo.adapters.act.ros_teacher_event_stream import stream_qos

    qos = stream_qos()
    assert qos.reliability is QoSReliabilityPolicy.RELIABLE
    assert qos.durability is QoSDurabilityPolicy.VOLATILE
    assert qos.history is QoSHistoryPolicy.KEEP_LAST and qos.depth == 256


def test_a_teacher_with_no_subscriber_publishes_without_blocking_or_failing(ros_context):
    from so101_demo.adapters.act.ros_teacher_event_stream import make_ros_publish

    teacher, recorder, executor = _nodes(ros_context)
    try:
        publish, close = make_ros_publish(teacher)
        stream = TeacherEventStream(IDENTITY, clock_ns=lambda: 1, publish=publish, poll_s=0.001)
        began = time.monotonic()
        for index in range(64):
            stream.offer("phase_begin", {"n": index})
        assert time.monotonic() - began < 0.5
        deadline = time.monotonic() + 5.0
        while stream.snapshot()["published"] < 64 and time.monotonic() < deadline:
            time.sleep(0.01)
        stream.close(flush_timeout_s=2.0)
        snapshot = stream.snapshot()
        assert snapshot["published"] == 64 and snapshot["publish_failures"] == 0 and snapshot["dropped"] == 0
        close()
    finally:
        executor.shutdown()
        teacher.destroy_node()
        recorder.destroy_node()


def test_a_late_subscriber_gets_no_history_so_a_late_recorder_sees_a_gap(ros_context):
    from so101_demo.adapters.act.ros_teacher_event_stream import RosTeacherEventSubscription, make_ros_publish

    teacher, recorder, executor = _nodes(ros_context)
    received = []
    try:
        publish, close = make_ros_publish(teacher)
        stream = TeacherEventStream(IDENTITY, clock_ns=lambda: 1, publish=publish, poll_s=0.001)
        stream.offer("reset_complete", {"n": 1})
        stream.offer("teacher_start_observation", {"n": 2})
        deadline = time.monotonic() + 5.0
        while stream.snapshot()["published"] < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        subscription = RosTeacherEventSubscription(recorder, received.append)
        assert _spin_until(executor, lambda: teacher.count_subscribers(STREAM_TOPIC) >= 1, 10.0)
        stream.offer("phase_begin", {"n": 3})
        assert _spin_until(executor, lambda: len(received) >= 1, 10.0)
        stream.close(flush_timeout_s=2.0)
        assert [decode_event(text)["seq"] for text in received] == [3], "volatile: seq 1 and 2 are never replayed"
        monitor = EventStreamMonitor(IDENTITY)
        with pytest.raises(Exception, match="TEACHER_EVENT_SEQUENCE_GAP"):
            monitor.accept(received[0])
        subscription.close()
        close()
    finally:
        executor.shutdown()
        teacher.destroy_node()
        recorder.destroy_node()
