"""Recorder round 2 (CP-3403): the node's callbacks are served by the receiver thread, so a stalled loop cannot age a receipt.

A real rclpy node, a real publisher at 200 Hz, a main thread that runs pure-Python work for 160 ms (a deepcopy-sized pass, the
class the L2 evidence shows at 3.2, 6.6, 8.2, 10.0 and 11.8 s). The same stream, served the old way (the loop's own
`spin_burst` once per pass), is aged by the whole stall - that control is the L2 behaviour.
"""
import threading
import time

import pytest

rclpy = pytest.importorskip("rclpy")
from std_msgs.msg import String

from so101_demo.ros.recorder_receiver import NodeReceiver
from so101_demo.ros import episode_recorder_sources as sources_module


def busy(seconds):
    end = time.perf_counter() + seconds
    total = 0
    while time.perf_counter() < end:
        total += sum(range(200))
    return total


class Rig:
    def __init__(self):
        self.context = rclpy.context.Context()
        rclpy.init(context=self.context)
        self.topic = f"/rec2_receiver_{id(self)}"
        self.sub_node = rclpy.create_node("rec2_sub", context=self.context)
        self.pub_node = rclpy.create_node("rec2_pub", context=self.context)
        self.delays_ms = []
        self.sub_node.create_subscription(String, self.topic, self._on_message, 100)
        self.publisher = self.pub_node.create_publisher(String, self.topic, 100)
        self.stop = threading.Event()
        self.thread = None

    def _on_message(self, message):
        stamp = time.monotonic_ns()
        self.delays_ms.append((stamp - int(message.data)) / 1e6)

    def publish_loop(self):
        while not self.stop.is_set():
            self.publisher.publish(String(data=str(time.monotonic_ns())))
            time.sleep(0.005)

    def start_publishing(self):
        deadline = time.monotonic() + 10
        while self.publisher.get_subscription_count() < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.thread = threading.Thread(target=self.publish_loop)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join()
        self.sub_node.destroy_node()
        self.pub_node.destroy_node()
        rclpy.shutdown(context=self.context)


@pytest.fixture
def rig(isolated_ros_domain):
    value = Rig()
    yield value
    value.close()


def test_the_receiver_stamps_at_delivery_while_the_loop_is_busy_for_160_ms(rig):
    receiver = NodeReceiver(rig.sub_node, executor=rclpy.executors.SingleThreadedExecutor(context=rig.context))
    receiver.start()
    try:
        rig.start_publishing()
        # Warm-up (a test artefact): the first samples after a match wait for the discovery handshake. Measure after
        # delivery is steady: twenty consecutive receipts under 20 ms.
        end = time.monotonic() + 15.0
        while time.monotonic() < end and not (len(rig.delays_ms) >= 20 and max(rig.delays_ms[-20:]) < 20.0):
            time.sleep(0.05)
        assert len(rig.delays_ms) >= 20 and max(rig.delays_ms[-20:]) < 20.0, "delivery never became steady"
        rig.delays_ms.clear()
        for _ in range(3):
            busy(0.16)
            time.sleep(0.1)
        assert len(rig.delays_ms) > 40, len(rig.delays_ms)      # enough receipts overlapped the three stalls (a count, not a bound)
        assert max(rig.delays_ms) < 60.0, max(rig.delays_ms)
        assert receiver.alive() and receiver.failure() is None
    finally:
        receiver.stop()
    assert not receiver.alive()


def test_control_served_by_the_loop_the_same_stall_ages_every_receipt(rig):
    executor = rclpy.executors.SingleThreadedExecutor(context=rig.context)
    executor.add_node(rig.sub_node)
    rig.start_publishing()
    end = time.monotonic() + 0.3
    while time.monotonic() < end:
        executor.spin_once(timeout_sec=0.005)
    rig.delays_ms.clear()
    for _ in range(3):
        busy(0.16)                                   # nothing serves the node during the pass
        end = time.monotonic() + 0.05
        while time.monotonic() < end:
            executor.spin_once(timeout_sec=0.0)
    assert max(rig.delays_ms) > 100.0, max(rig.delays_ms)
    executor.remove_node(rig.sub_node)


def test_a_raising_callback_is_reported_and_the_receiver_keeps_serving(rig):
    class Flaky:
        def __init__(self):
            self.calls = 0

        def add_node(self, node):
            pass

        def spin_once(self, timeout_sec=None):
            self.calls += 1
            time.sleep(0.002)
            if self.calls == 3:
                raise ValueError("callback broke")

        def remove_node(self, node):
            pass

        def shutdown(self):
            pass

    flaky = Flaky()
    receiver = NodeReceiver(rig.sub_node, executor=flaky)
    receiver.start()
    time.sleep(0.1)
    try:
        assert receiver.alive() and receiver.failure() is None and flaky.calls > 10
        assert receiver.take_callback_errors() == ["ValueError: callback broke"]
        assert receiver.take_callback_errors() == [] and receiver.stats()["callback_errors"] == 1
    finally:
        receiver.stop()


def test_a_receiver_whose_context_is_gone_reports_it_instead_of_going_silent(rig):
    class Broken:
        def add_node(self, node):
            pass

        def spin_once(self, timeout_sec=None):
            raise KeyboardInterrupt("interpreter going down")

        def remove_node(self, node):
            pass

        def shutdown(self):
            pass

    receiver = NodeReceiver(rig.sub_node, executor=Broken())
    receiver.start()
    time.sleep(0.1)
    assert not receiver.alive() and "going down" in receiver.failure()
    receiver.stop()
