"""The nodes a process keeps between calls (the readiness session, the retained evidence reader) are not in the worker node inventory.

A real rclpy graph with the stand-in simulator of `test_retained_evidence` and a stand-in worker (the inventory's nodes, the goal
cancel services and the planning scene service). The point initial gate samples the graph of its ROS domain and refuses any node
the inventory does not know (POINT_INITIAL_GATE_OBSERVATION_REJECTED:worker_nodes); a kept node of the calling process would be
one of them, so the process closes what it keeps before it samples.
"""

import threading
import time

import pytest

from test_retained_evidence import FakeSimulator, SESSION

DOMAIN = "227"
INVENTORY_NODES = (
    ("arm_controller", "/"), ("gripper_controller", "/"), ("joint_state_broadcaster", "/"), ("move_group", "/"),
    ("robot_state_publisher", "/"), ("so101_base_to_camera_link", "/"),
    ("so101_camera_link_to_task_camera_frame", "/"), ("controller_manager", "/"), ("moveit", "/move_group"),
    ("moveit_simple_controller_manager", "/"), ("robotsystem", "/"), ("move_group_private_123456", "/"),
    ("moveit_654321", "/"), ("transform_listener_impl_5596856eff40", "/"),
)


class FakeWorker:
    """The nodes of a worker's graph plus the services the initial gate calls."""

    def __init__(self):
        import rclpy
        from moveit_msgs.srv import GetPlanningScene
        from action_msgs.srv import CancelGoal
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor

        self.context = Context()
        rclpy.init(context=self.context)
        self.nodes = [rclpy.create_node(name, namespace=namespace, context=self.context) for name, namespace in INVENTORY_NODES]
        host = self.nodes[0]
        for prefix in ("/execute_trajectory/_action", "/arm_controller/follow_joint_trajectory/_action",
                       "/gripper_controller/follow_joint_trajectory/_action"):
            host.create_service(CancelGoal, prefix + "/cancel_goal", lambda _request, response: response)
        host.create_service(GetPlanningScene, "/get_planning_scene", lambda _request, response: response)
        self.executor = SingleThreadedExecutor(context=self.context)
        for node in self.nodes:
            self.executor.add_node(node)
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while not self._stop.is_set():
            self.executor.spin_once(timeout_sec=0.01)

    def close(self):
        self._stop.set()
        self.thread.join(5.0)
        self.executor.shutdown()
        for node in self.nodes:
            node.destroy_node()
        self.context.try_shutdown()


@pytest.fixture
def stack(monkeypatch, tmp_path):
    import rclpy

    monkeypatch.delenv("ROS_NAMESPACE", raising=False)
    monkeypatch.setenv("SO101_ACT_INSTANCE_ROOT", str(tmp_path))
    monkeypatch.setenv("ROS_DOMAIN_ID", DOMAIN)
    rclpy.try_shutdown()
    simulator, worker = FakeSimulator(node_name="mujoco_ros2_control_node"), FakeWorker()   # the simulator is the inventory's simulation node
    time.sleep(1.0)     # discovery
    yield simulator, worker
    worker.close()
    simulator.close()
    rclpy.try_shutdown()


def boundary():
    from so101_demo.runtime.parallel_ros_ports.observations import ResetBoundaryReceipt

    return ResetBoundaryReceipt("reset-3", SESSION, 0.0, 0.0, joint_positions=(0.0,) * 6)


def kept_readiness_session(tmp_path):
    """A kept readiness check that holds its session, as an instance's does after the first task gate."""
    import os
    import sys
    from pathlib import Path

    from paths import PACKAGE_ROOT
    from so101_demo.act.rig_profile import DEFAULT_RIG, HEAD_WRIST_RIG
    from so101_demo.cli.act_stack_ready import StackReadinessSession
    from so101_demo.runtime.act_instance.program import instance_stack_launch
    from so101_demo.runtime.act_instance.ready_check import KeptActStackReadyCheck

    sys.path.insert(0, str(PACKAGE_ROOT / "test" / "runtime"))
    from test_act_rig_startup_readiness_composition import sleeping

    observer = tmp_path / "act_stack_ready"
    observer.write_text("#!/bin/sh\n")
    observer.chmod(0o700)
    (tmp_path / "stack").mkdir()
    launch = sleeping(instance_stack_launch({"simulation_session_id": SESSION}, ros2=Path(sys.executable), stack_root=tmp_path / "stack",
                                            environment=dict(os.environ), rig=HEAD_WRIST_RIG, share=PACKAGE_ROOT))
    check = KeptActStackReadyCheck(launch, observer, make_session=lambda: StackReadinessSession(
        session_id=SESSION, ros_domain_id=int(DOMAIN), rig=DEFAULT_RIG))
    check._session = check._make_session()
    return check


def observe(reader):
    """The initial gate's observation and what the worker node inventory says about its graph: (matches, nodes it does not know)."""
    from so101_demo.runtime.parallel_ros_ports.binding import RuntimeBinding
    from so101_demo.runtime.parallel_ros_ports.observations import observe_parallel_initial_gate

    observation = observe_parallel_initial_gate(boundary(), timeout_s=4.0, read_evidence=reader)
    nodes = observation.worker_node_fqns
    return RuntimeBinding.worker_node_inventory_matches(nodes), RuntimeBinding.worker_node_inventory_report(nodes)["unknown"]


def test_the_baseline_graph_matches_the_inventory(stack):
    from so101_demo.backends.mujoco.teleop_runtime import current_evidence

    assert observe(current_evidence) == (True, [])


def test_a_kept_readiness_session_does_not_reach_the_inventory(stack, tmp_path):
    from so101_demo.backends.mujoco.teleop_runtime import current_evidence

    check = kept_readiness_session(tmp_path)
    try:
        assert observe(current_evidence) == (True, [])      # before the fix: (False, ['/act_stack_ready_<pid>'])
    finally:
        check.close()


def test_the_retained_evidence_node_does_not_reach_the_inventory(stack):
    from so101_demo.backends.mujoco.teleop_runtime import RetainedEvidence

    reader = RetainedEvidence(SESSION)
    try:
        assert observe(reader) == (True, [])      # before the fix: (False, ['/so101_teleop_mujoco_evidence_retained'])
    finally:
        reader.close()


def test_both_kept_nodes_together_and_the_retained_reader_is_usable_again_afterwards(stack, tmp_path):
    from so101_demo.backends.mujoco.teleop_runtime import RetainedEvidence

    reader = RetainedEvidence(SESSION)
    check = kept_readiness_session(tmp_path)
    try:
        assert observe(reader) == (True, [])
        again = reader(SESSION, timeout_s=10.0)          # reopened by the next read
        assert again.simulation_session_id == SESSION and reader._node is not None
        assert observe(reader) == (True, [])
    finally:
        reader.close()
        check.close()
