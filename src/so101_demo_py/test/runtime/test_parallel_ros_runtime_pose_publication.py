"""The isolated ROS node, pose publication and consumer readiness."""

from __future__ import annotations

import json
import os
import time
from types import SimpleNamespace


def test_isolated_ros_node_owns_executor_for_its_private_context(monkeypatch):
    import rclpy.executors

    from so101_demo.runtime.parallel_ros_ports.isolated_node import _open_isolated_ros_node

    events = []

    class Context:
        def shutdown(self):
            events.append("private-shutdown")

    node = SimpleNamespace(destroy_node=lambda: events.append("node-destroy"))

    class Executor:
        def __init__(self, *, context):
            events.append(("executor", context))

        def add_node(self, value):
            events.append(("add", value))

        def spin_once(self, *, timeout_sec):
            events.append(("spin", timeout_sec))

        def remove_node(self, value):
            events.append(("remove", value))

        def shutdown(self):
            events.append("executor-shutdown")

    monkeypatch.setattr(rclpy.executors, "SingleThreadedExecutor", Executor)

    class Rclpy:
        context = SimpleNamespace(Context=Context)

        @staticmethod
        def ok():
            return True

        @staticmethod
        def init(*, context):
            events.append(("init", context))

        @staticmethod
        def create_node(name, *, context, **kwargs):
            events.append(("create", name, context, kwargs))
            return node

    owner = _open_isolated_ros_node(Rclpy, "isolated")
    assert owner.node is node
    assert events[0][0] == "init"
    assert events[1][0:2] == ("create", "isolated")
    assert events[0][1] is events[1][2]
    assert events[2] == ("executor", events[0][1])
    assert events[3] == ("add", node)
    owner.spin_once(timeout_sec=0.25)
    assert events[4] == ("spin", 0.25)
    owner.close()
    owner.close()
    assert events[-4:] == [
        ("remove", node), "executor-shutdown", "node-destroy", "private-shutdown"
    ]


def test_isolated_ros_node_can_keep_sim_clock_callbacks_live_in_background():
    import threading

    from so101_demo.runtime.parallel_ros_ports.isolated_node import _IsolatedRosNode

    spun = threading.Event()

    class Executor:
        def spin_once(self, *, timeout_sec):
            assert timeout_sec > 0.0
            spun.set()

        @staticmethod
        def remove_node(_node):
            return None

        @staticmethod
        def shutdown():
            return None

    owner = _IsolatedRosNode(
        SimpleNamespace(
            destroy_node=lambda: None,
            get_name=lambda: "background-clock-test",
        ),
        SimpleNamespace(shutdown=lambda: None),
        Executor(),
    )

    owner.start_background_spin()
    assert spun.wait(1.0)
    owner.close()


def test_pose_publication_waits_for_admitted_source_on_isolated_sim_clock(monkeypatch):
    import rclpy

    from so101_demo.core.task_geometry import Pose7
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    clock_ns = [0]
    created = {}
    published = []

    class Publisher:
        @staticmethod
        def get_subscription_count():
            return 1

        @staticmethod
        def publish(message):
            published.append((clock_ns[0], message))

    class Node:
        @staticmethod
        def create_publisher(*_args):
            return Publisher()

        @staticmethod
        def get_clock():
            return SimpleNamespace(
                now=lambda: SimpleNamespace(nanoseconds=clock_ns[0])
            )

        @staticmethod
        def destroy_node():
            return None

    def create_node(name, **kwargs):
        created.update(name=name, kwargs=kwargs)
        return Node()

    def spin_once(_node, *, timeout_sec):
        assert 0.0 < timeout_sec <= 0.05
        clock_ns[0] += 40_000_000

    monkeypatch.setattr(rclpy, "ok", lambda: True)
    monkeypatch.setattr(rclpy, "create_node", create_node)
    monkeypatch.setattr(rclpy, "spin_once", spin_once)
    admitted = SimpleNamespace(
        source_stamp_ns=100_000_000,
        pose_world=Pose7((1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0)),
    )
    ports = ParallelRosRuntimePorts(SimpleNamespace(), catalog={})

    assert ports.publish_pose(admitted) is True
    assert created["name"] == "so101_parallel_pose_publisher"
    overrides = created["kwargs"]["parameter_overrides"]
    assert [(parameter.name, parameter.value) for parameter in overrides] == [
        ("use_sim_time", True)
    ]
    assert published[0][0] >= admitted.source_stamp_ns
    message = published[0][1]
    assert (message.header.stamp.sec, message.header.stamp.nanosec) == (0, 100_000_000)
    assert message.header.frame_id == "world"
    assert (
        message.pose.position.x,
        message.pose.position.y,
        message.pose.position.z,
        message.pose.orientation.x,
        message.pose.orientation.y,
        message.pose.orientation.z,
        message.pose.orientation.w,
    ) == admitted.pose_world.values


def test_pose_publication_retransmits_until_consumer_subscription_closes(monkeypatch):
    import rclpy

    from so101_demo.core.task_geometry import Pose7
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    published = []
    spin_durations = []

    class Publisher:
        @staticmethod
        def get_subscription_count():
            return 0 if len(published) >= 25 else 1

        @staticmethod
        def publish(message):
            published.append(message)

    class Node:
        @staticmethod
        def create_publisher(*_args):
            return Publisher()

        @staticmethod
        def get_clock():
            return SimpleNamespace(
                now=lambda: SimpleNamespace(nanoseconds=200_000_000)
            )

        @staticmethod
        def destroy_node():
            return None

    monkeypatch.setattr(rclpy, "ok", lambda: True)
    monkeypatch.setattr(rclpy, "create_node", lambda *_args, **_kwargs: Node())
    monkeypatch.setattr(
        rclpy,
        "spin_once",
        lambda *_args, **kwargs: spin_durations.append(kwargs["timeout_sec"]),
    )
    admitted = SimpleNamespace(
        source_stamp_ns=100_000_000,
        pose_world=Pose7((1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0)),
    )

    assert ParallelRosRuntimePorts(SimpleNamespace(), catalog={}).publish_pose(
        admitted
    ) is True
    assert len(published) == 25
    assert spin_durations == [0.02] * 241


def test_pose_publication_allows_recovered_publisher_clock_to_catch_up(monkeypatch):
    import rclpy

    from so101_demo.core.task_geometry import Pose7
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    clock_ns = [0]
    monotonic_s = [0.0]
    published = []

    class Publisher:
        @staticmethod
        def get_subscription_count():
            return 0 if published else 1

        @staticmethod
        def publish(message):
            published.append(message)

    class Node:
        @staticmethod
        def create_publisher(*_args):
            return Publisher()

        @staticmethod
        def get_clock():
            return SimpleNamespace(
                now=lambda: SimpleNamespace(nanoseconds=clock_ns[0])
            )

        @staticmethod
        def destroy_node():
            return None

    def spin_once(_node, *, timeout_sec):
        monotonic_s[0] += timeout_sec
        clock_ns[0] += round(timeout_sec * 1_000_000_000)

    monkeypatch.setattr(rclpy, "ok", lambda: True)
    monkeypatch.setattr(rclpy, "create_node", lambda *_args, **_kwargs: Node())
    monkeypatch.setattr(rclpy, "spin_once", spin_once)
    monkeypatch.setattr(time, "monotonic", lambda: monotonic_s[0])
    admitted = SimpleNamespace(
        source_stamp_ns=3_000_000_000,
        pose_world=Pose7((1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0)),
    )

    assert ParallelRosRuntimePorts(SimpleNamespace(), catalog={}).publish_pose(
        admitted
    ) is True
    assert len(published) == 1
    assert clock_ns[0] >= admitted.source_stamp_ns


def test_consumer_readiness_primes_and_retains_isolated_pose_publisher(
    tmp_path, monkeypatch
):
    from so101_demo.core.task_geometry import Pose7
    from so101_demo.runtime import task_batch_runtime
    from so101_demo.runtime.parallel_ros_ports import observations as runtime_module_observations
    from so101_demo.runtime.parallel_ros_ports import perception as runtime_module_perception
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    events = []
    published = []

    class Publisher:
        @staticmethod
        def get_subscription_count():
            return 0 if published else 1

        @staticmethod
        def publish(message):
            published.append(message)

    class Node:
        @staticmethod
        def create_publisher(*_args):
            events.append("publisher-created")
            return Publisher()

        @staticmethod
        def get_node_names_and_namespaces():
            return [
                ("so101_parallel_pose_publisher", "/"),
                ("so101_dynamic_cup_pick_place", "/"),
            ]

        @staticmethod
        def get_clock():
            return SimpleNamespace(
                now=lambda: SimpleNamespace(nanoseconds=200_000_000)
            )

    class Owner:
        node = Node()
        closed = False

        @staticmethod
        def start_background_spin():
            events.append("background-spin-started")

        @staticmethod
        def spin_once(*, timeout_sec):
            events.append(("spin", timeout_sec))

        def close(self):
            self.closed = True
            events.append("closed")

    owner = Owner()

    class GraphProbe:
        def __init__(self):
            raise AssertionError("consumer readiness must not shell out to ros2")

    monkeypatch.setattr(task_batch_runtime, "RosGraphProbe", GraphProbe)
    monkeypatch.setattr(
        runtime_module_observations,
        "_open_isolated_ros_node",
        lambda *_args, **_kwargs: owner,
    )
    monkeypatch.setattr(
        runtime_module_perception,
        "_open_isolated_ros_node",
        lambda *_args, **_kwargs: owner,
    )
    worker_root = tmp_path / "worker-01"
    ready_receipt = (
        worker_root
        / "attempts/task_start/attempt-1/working/dynamic/consumer-ready.json"
    )
    ready_receipt.parent.mkdir(parents=True)
    ready_receipt.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "dynamic_consumer_ready",
                "session_id": "session-1",
                "reset_epoch": 1,
                "parallel_lease_identity": {
                    "batch_id": "batch-1",
                    "coordinator_epoch": 1,
                    "worker_id": "worker-01",
                    "worker_generation": 1,
                    "point_id": "task_start",
                    "attempt_id": "attempt-1",
                    "lease_generation": 1,
                },
                "ready_ros_ns": 100_000_000,
                "ready_monotonic_s": 1.0,
            }
        ),
        encoding="utf-8",
    )
    ready_receipt.chmod(0o600)
    child = SimpleNamespace(
        pid=os.getpid(),
        cmdline=(
            "python3",
            "-m",
            "so101_demo.cli.dynamic_cup_pick_place",
            "--batch-id",
            "batch-1",
            "--coordinator-epoch",
            "1",
            "--worker-id",
            "worker-01",
            "--worker-generation",
            "1",
            "--point-id",
            "task_start",
            "--attempt-id",
            "attempt-1",
            "--lease-generation",
            "1",
            "--session-id",
            "session-1",
            "--expected-reset-epoch",
            "1",
            "--ready-receipt",
            str(ready_receipt),
        ),
    )
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"),
        catalog={},
    )

    assert ports.consumer_ready(child) is True
    assert ports._minimum_inference_stamp_ns == 100_000_000
    assert events[0] == "publisher-created"
    assert events[1] == "background-spin-started"
    admitted = SimpleNamespace(
        source_stamp_ns=100_000_000,
        pose_world=Pose7((1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0)),
    )
    assert ports.publish_pose(admitted) is True
    assert len(published) == 1
    assert owner.closed is False

    ports.close_runtime()
    assert owner.closed is True


def _consumer_graph_rig(monkeypatch, *, nodes):
    """`consumer_ready` over a fake graph listing `nodes`; the receipt fence is a double, every graph name is checked."""
    from so101_demo.runtime.parallel_ros_ports import observations as runtime_module_observations
    from so101_demo.runtime.parallel_ros_ports import perception as runtime_module_perception
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    class Publisher:
        @staticmethod
        def get_subscription_count():
            return 1

    class Node:
        @staticmethod
        def create_publisher(*_args):
            return Publisher()

        @staticmethod
        def get_node_names_and_namespaces():
            return list(nodes)

        @staticmethod
        def get_clock():
            return SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=200_000_000))

    class Owner:
        node = Node()

        @staticmethod
        def start_background_spin():
            return None

        @staticmethod
        def spin_once(*, timeout_sec):
            del timeout_sec

        @staticmethod
        def close():
            return None

    for module in (runtime_module_observations, runtime_module_perception):
        monkeypatch.setattr(module, "_open_isolated_ros_node", lambda *_args, **_kwargs: Owner())
    monkeypatch.setattr(ParallelRosRuntimePorts, "_consumer_ready_fence", lambda self, child: 100_000_000)
    resources = SimpleNamespace(session_id="session-1", worker_root=None, controller_namespace="/")
    return ParallelRosRuntimePorts(resources, catalog={}), SimpleNamespace(pid=os.getpid())


def _stepping_clock(monkeypatch):
    """A monotonic clock that jumps 5 s per reading, so the 20 s readiness wait ends after a few polls."""
    import itertools
    import time

    ticks = itertools.count(1.0, 5.0)
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))


def test_consumer_readiness_finds_the_one_unnamespaced_consumer(monkeypatch):
    ports, child = _consumer_graph_rig(monkeypatch, nodes=[
        ("so101_parallel_pose_publisher", "/"), ("so101_dynamic_cup_pick_place", "/")])
    _stepping_clock(monkeypatch)

    assert ports.consumer_ready(child) is True


def test_consumer_readiness_refuses_a_missing_foreign_or_duplicate_consumer(monkeypatch):
    for nodes in (
        [("so101_dynamic_cup_pick_place", "/foreign")],
        [("so101_dynamic_cup_pick_place", "/"), ("so101_dynamic_cup_pick_place", "/foreign")],
        [("so101_dynamic_cup_pick_place", "/"), ("so101_dynamic_cup_pick_place", "/")],
        [],
    ):
        ports, child = _consumer_graph_rig(monkeypatch, nodes=nodes)
        _stepping_clock(monkeypatch)
        assert ports.consumer_ready(child) is False


def test_pose_publication_fails_closed_when_sim_clock_cannot_reach_source(monkeypatch):
    import rclpy

    from so101_demo.core.task_geometry import Pose7
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    monotonic_s = [0.0]
    published = []

    class Publisher:
        @staticmethod
        def get_subscription_count():
            return 1

        @staticmethod
        def publish(message):
            published.append(message)

    class Node:
        @staticmethod
        def create_publisher(*_args):
            return Publisher()

        @staticmethod
        def get_clock():
            return SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=0))

        @staticmethod
        def destroy_node():
            return None

    def monotonic():
        monotonic_s[0] += 1.0
        return monotonic_s[0]

    monkeypatch.setattr(time, "monotonic", monotonic)
    monkeypatch.setattr(rclpy, "ok", lambda: True)
    monkeypatch.setattr(rclpy, "create_node", lambda *_args, **_kwargs: Node())
    monkeypatch.setattr(rclpy, "spin_once", lambda *_args, **_kwargs: None)
    admitted = SimpleNamespace(
        source_stamp_ns=100_000_000,
        pose_world=Pose7((1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0)),
    )

    assert ParallelRosRuntimePorts(SimpleNamespace(), catalog={}).publish_pose(admitted) is False
    assert published == []
