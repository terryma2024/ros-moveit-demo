"""`RetainedEvidence` returns what the one-shot `current_evidence` returns, over one node kept between calls.

A real rclpy graph with a stand-in simulator (the evidence topic and the pause service), as `test_teleop_runtime_contexts` uses real
contexts: what is under test is who opens what and how often, and that the evidence read is still a fresh paused snapshot.
"""

import threading
import time

import pytest

SESSION = "retained-session"


class FakeSimulator:
    """Publishes SimulationEvidence at 50 Hz on the transient-local topic and serves `set_pause`; paused stops the step counter."""

    def __init__(self, session=SESSION, epoch=3):
        import rclpy
        from mujoco_ros2_control_msgs.srv import SetPause
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from so101_demo.backends.mujoco.observer import ATOMIC_EVIDENCE_QOS
        from so101_mujoco_support.msg import SimulationEvidence

        self.session, self.epoch = session, epoch
        self.paused, self.pause_calls, self._sequence, self._step = False, 0, 0, 0
        self._stop = threading.Event()
        self._message = SimulationEvidence
        self.context = Context()
        rclpy.init(context=self.context)
        self.node = rclpy.create_node("fake_simulator", context=self.context)
        self.publisher = self.node.create_publisher(SimulationEvidence, "/so101/simulation/evidence", ATOMIC_EVIDENCE_QOS)
        self.node.create_service(SetPause, "/mujoco_ros2_control_node/set_pause", self._pause)
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.node)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _pause(self, request, response):
        self.paused, self.pause_calls = bool(request.paused), self.pause_calls + 1
        response.success = True
        return response

    def _publish(self):
        message = self._message()
        self._sequence += 1
        if not self.paused:
            self._step += 1
        message.publisher_sequence, message.simulation_step = self._sequence, self._step
        message.reset_epoch, message.simulation_session_id, message.paused = self.epoch, self.session, self.paused
        message.header.frame_id = "world"
        message.object_body = "cup"
        self.publisher.publish(message)

    def _run(self):
        next_publish = 0.0
        while not self._stop.is_set():
            self.executor.spin_once(timeout_sec=0.005)
            if time.monotonic() >= next_publish:
                self._publish()
                next_publish = time.monotonic() + 0.02

    def close(self):
        self._stop.set()
        self.thread.join(5.0)
        self.executor.shutdown()
        self.node.destroy_node()
        self.context.try_shutdown()


@pytest.fixture
def simulator(monkeypatch, tmp_path):
    import rclpy

    monkeypatch.delenv("ROS_NAMESPACE", raising=False)
    monkeypatch.setenv("SO101_ACT_INSTANCE_ROOT", str(tmp_path))
    monkeypatch.setenv("ROS_DOMAIN_ID", "230")
    rclpy.try_shutdown()
    fake = FakeSimulator()
    yield fake
    fake.close()
    rclpy.try_shutdown()


def count_nodes(monkeypatch):
    from so101_demo.backends.mujoco import teleop_runtime

    created = []
    original = teleop_runtime._RosScope.create_node

    def create_node(self, name):
        created.append(name)
        return original(self, name)

    monkeypatch.setattr(teleop_runtime._RosScope, "create_node", create_node)
    return created


def test_repeated_reads_open_one_node_and_return_what_the_one_shot_read_returns(simulator, monkeypatch):
    from so101_demo.backends.mujoco.teleop_runtime import RetainedEvidence, current_evidence

    created = count_nodes(monkeypatch)
    reader = RetainedEvidence(SESSION)
    try:
        reads = [reader(SESSION, timeout_s=10.0) for _ in range(3)]
        one_shot = current_evidence(SESSION, timeout_s=10.0)
    finally:
        reader.close()
    assert created.count("so101_teleop_mujoco_evidence_retained") == 1
    assert created.count("so101_teleop_mujoco_evidence") == 1
    for evidence in reads:
        assert (evidence.simulation_session_id, evidence.reset_epoch, evidence.paused) == (
            one_shot.simulation_session_id, one_shot.reset_epoch, one_shot.paused) == (SESSION, 3, True)
    assert simulator.pause_calls >= 1 and simulator.paused


def test_a_read_after_a_pause_gap_is_fresh_and_paused_again(simulator):
    from so101_demo.backends.mujoco.teleop_runtime import RetainedEvidence

    reader = RetainedEvidence(SESSION)
    try:
        first = reader(SESSION, timeout_s=10.0)
        simulator.paused = False       # the Teacher ran in between
        time.sleep(0.3)
        second = reader(SESSION, timeout_s=10.0)
    finally:
        reader.close()
    assert first.paused and second.paused
    assert second.publisher_sequence > first.publisher_sequence and second.simulation_step >= first.simulation_step


def test_a_reset_in_between_ends_in_the_one_shot_read_and_the_next_read_is_retained_again(simulator, monkeypatch):
    from so101_demo.backends.mujoco.teleop_runtime import RetainedEvidence

    created = count_nodes(monkeypatch)
    reader = RetainedEvidence(SESSION)
    try:
        first = reader(SESSION, timeout_s=10.0)
        assert first.reset_epoch == 3
        simulator.epoch, simulator._step, simulator.paused = 4, 0, False   # epoch 4 begins at step zero and runs on
        time.sleep(0.3)
        after = reader(SESSION, timeout_s=10.0)
        again = reader(SESSION, timeout_s=10.0)
    finally:
        reader.close()
    brief = [(e.publisher_sequence, e.simulation_step, e.reset_epoch, e.paused) for e in (first, after, again)]
    assert after.reset_epoch == again.reset_epoch == 4 and after.paused and again.paused, brief
    assert created.count("so101_teleop_mujoco_evidence_retained") <= 2


def test_close_releases_the_node_and_a_later_read_reopens(simulator, monkeypatch):
    from so101_demo.backends.mujoco.teleop_runtime import RetainedEvidence

    created = count_nodes(monkeypatch)
    reader = RetainedEvidence(SESSION)
    reader(SESSION, timeout_s=10.0)
    reader.close()
    assert reader._node is None and reader._scope is None
    reader.close()      # idempotent
    reader(SESSION, timeout_s=10.0)
    reader.close()
    assert created.count("so101_teleop_mujoco_evidence_retained") == 2


def test_other_session_or_no_instance_marker_is_the_one_shot_read():
    from so101_demo.backends.mujoco.teleop_runtime import RetainedEvidence

    calls = []
    one_shot = lambda session, timeout_s: calls.append((session, timeout_s)) or "one-shot"
    assert RetainedEvidence("a", one_shot=one_shot, in_instance=lambda: True)("b", timeout_s=2.0) == "one-shot"
    assert RetainedEvidence("a", one_shot=one_shot, in_instance=lambda: False)("a", timeout_s=3.0) == "one-shot"
    assert calls == [("b", 2.0), ("a", 3.0)]


def test_a_failing_retained_path_falls_back_to_the_one_shot_read_and_retries_the_open_next_time():
    from so101_demo.backends.mujoco.teleop_runtime import RetainedEvidence

    opened, calls = [], []

    class Reader(RetainedEvidence):
        def _open(self):
            opened.append(1)
            raise RuntimeError("no graph")

    reader = Reader("a", one_shot=lambda session, timeout_s: calls.append(session) or "one-shot", in_instance=lambda: True)
    assert reader("a", timeout_s=1.0) == reader("a", timeout_s=1.0) == "one-shot"
    assert opened == [1, 1] and calls == ["a", "a"]
    assert reader._node is None
