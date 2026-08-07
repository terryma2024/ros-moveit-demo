"""Small typed wrapper around the Gazebo Harmonic Python transport binding."""

from collections.abc import Callable
import threading
import time
from typing import Any


def wait_for_connections(publisher: Any, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while not publisher.has_connections():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)
    return True


class GazeboTransport:
    def __init__(self) -> None:
        try:
            from gz.transport13 import Node
            from gz.msgs10.empty_pb2 import Empty
            from gz.msgs10.stringmsg_pb2 import StringMsg
        except ImportError as error:
            raise RuntimeError(
                "Gazebo Python bindings gz.transport13 and gz.msgs10 are required "
                "and must match the ROS-vendored Gazebo runtime"
            ) from error
        self._node = Node()
        self._empty_type = Empty
        self._string_type = StringMsg
        self._publishers: dict[str, Any] = {}
        self._lock = threading.Lock()

    def publish_empty(self, topic: str) -> bool:
        with self._lock:
            publisher = self._publishers.get(topic)
            if publisher is None:
                publisher = self._node.advertise(topic, self._empty_type)
                self._publishers[topic] = publisher
        if not publisher.valid():
            return False
        if not wait_for_connections(publisher, 1.0):
            return False
        publisher.publish(self._empty_type())
        return True

    def publish_string(self, topic: str, value: str) -> bool:
        key = f"string:{topic}"
        with self._lock:
            publisher = self._publishers.get(key)
            if publisher is None:
                publisher = self._node.advertise(topic, self._string_type)
                self._publishers[key] = publisher
        if not publisher.valid():
            return False
        message = self._string_type()
        message.data = value
        publisher.publish(message)
        return True

    def subscribe_string(self, topic: str, callback: Callable[[str], None]) -> bool:
        def receive(message) -> None:
            callback(str(message.data))

        return bool(self._node.subscribe(self._string_type, topic, receive))

    def topics(self) -> tuple[str, ...]:
        return tuple(self._node.topic_list())
