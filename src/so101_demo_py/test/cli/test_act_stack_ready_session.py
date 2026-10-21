"""A kept `StackReadinessSession` judges a stack exactly as the `act_stack_ready` command line does.

A real rclpy graph with a stand-in stack (evidence topic, joint states, the rig's cameras, the controller manager listing, the
planning services and the trajectory action servers). Every scenario is observed twice on the same live graph: by the command
line in a new process, and by one session that is kept for all of them. The verdict, the failing check and the artifact's keys must
agree; a kept session must also give the same answer when asked again.
"""

import json
import os
import subprocess
import sys
import threading
import time

import pytest

SESSION = "ready-session"
FIRST_DOMAIN, DOMAIN_COUNT = 205, 18     # 205..222: none of the gate stages (demo 203, teleop 204, jtc 229, upstream groups 223-226) or other tests (227, 230-232) uses them


def domain_for(worker):
    """The ROS domain of one xdist worker. Every parametrisation and both tests of this file run on a live graph with the same session id: two of them on one
    domain at the same time see each other's publishers (sequence gaps, ACT_STACK_SOURCE_REJECTED), so each worker gets a domain of its own."""
    number = int(worker[2:]) if worker.startswith("gw") and worker[2:].isdigit() else 0
    return str(FIRST_DOMAIN + number % DOMAIN_COUNT)


DOMAIN = domain_for(os.environ.get("PYTEST_XDIST_WORKER", "gw0"))
TIMEOUT_S = 4.0


class FakeStack:
    def __init__(self, rig):
        import rclpy
        from control_msgs.action import FollowJointTrajectory
        from controller_manager_msgs.msg import ControllerState
        from controller_manager_msgs.srv import ListControllers
        from moveit_msgs.action import ExecuteTrajectory
        from moveit_msgs.srv import ApplyPlanningScene, GetMotionPlan, GetPlanningScene
        from rclpy.action import ActionServer
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import Image, JointState
        from so101_demo.act.joints import ACT_JOINTS, ARM_JOINTS
        from so101_demo.adapters.act.ros_observation import RGB_QOS
        from so101_demo.backends.mujoco.observer import ATOMIC_EVIDENCE_QOS
        from so101_demo.cli.act_stack_ready import _SERVICES, actions_for, controllers_for
        from so101_mujoco_support.msg import SimulationEvidence

        self.rig = rig
        self.paused = False
        self.camera_on = True
        self.velocity = 0.0
        self.inactive = set()
        self.services_on = set(_SERVICES)
        self._controller_state, self._evidence_type, self._image_type, self._joint_type = (
            ControllerState, SimulationEvidence, Image, JointState)
        self._joint_names = ACT_JOINTS if rig.has_neck else ARM_JOINTS
        self._controllers = controllers_for(rig)
        self._step, self._sequence, self._sim_time = 0, 0, 0.0
        self._stop = threading.Event()
        self.context = Context()
        rclpy.init(context=self.context)
        self.node = rclpy.create_node("fake_stack", context=self.context)
        node = self.node
        self.evidence = node.create_publisher(SimulationEvidence, "/so101/simulation/evidence", ATOMIC_EVIDENCE_QOS)
        self.joints = node.create_publisher(JointState, "/joint_states", qos_profile_sensor_data)
        self.cameras = {camera.name: node.create_publisher(Image, camera.image_topic, RGB_QOS) for camera in rig.cameras}
        node.create_service(ListControllers, "/controller_manager/list_controllers", self._list_controllers)
        self._service_objects = {}
        for name, kind in zip(_SERVICES, (ApplyPlanningScene, GetPlanningScene, GetMotionPlan), strict=True):
            self._service_objects[name] = (kind, node.create_service(kind, name, lambda _request, response: response))
        required = actions_for(rig)
        kinds = (ExecuteTrajectory, *(FollowJointTrajectory for _ in required[1:]))
        self._servers = [ActionServer(node, kind, name, lambda goal: None) for name, kind in zip(required, kinds, strict=True)]
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(node)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _list_controllers(self, _request, response):
        response.controller = [self._controller_state(name=name, state="inactive" if name in self.inactive else "active")
                               for name in self._controllers]
        return response

    def drop_service(self, name):
        kind, service = self._service_objects.pop(name)
        self.node.destroy_service(service)
        self._dropped = (name, kind)

    def restore(self):
        self.paused, self.camera_on, self.velocity, self.inactive = False, True, 0.0, set()
        if getattr(self, "_dropped", None) is not None:
            name, kind = self._dropped
            self._service_objects[name] = (kind, self.node.create_service(kind, name, lambda _request, response: response))
            self._dropped = None

    def _stamp(self, message):
        message.header.stamp.sec, message.header.stamp.nanosec = divmod(round(self._sim_time * 1e9), 1_000_000_000)

    def _tick(self):
        self._sequence += 1
        if not self.paused:
            self._step += 1
            self._sim_time += 0.01
        evidence = self._evidence_type()
        evidence.publisher_sequence, evidence.simulation_step, evidence.reset_epoch = self._sequence, max(self._step, 1), 1
        evidence.simulation_session_id, evidence.paused, evidence.object_body = SESSION, self.paused, "cup"
        evidence.header.frame_id = "world"
        self._stamp(evidence)
        self.evidence.publish(evidence)
        joints = self._joint_type()
        joints.name = list(self._joint_names)
        joints.position = [0.0] * len(joints.name)
        joints.velocity = [self.velocity] * len(joints.name)
        self._stamp(joints)
        self.joints.publish(joints)
        if self.camera_on and self._sequence % 5 == 0:
            for publisher in self.cameras.values():
                image = self._image_type()
                image.width, image.height, image.encoding, image.step = 640, 480, "rgb8", 1920
                image.data = bytes(640 * 480 * 3)
                self._stamp(image)
                publisher.publish(image)

    def _run(self):
        next_tick = 0.0
        while not self._stop.is_set():
            self.executor.spin_once(timeout_sec=0.002)
            if time.monotonic() >= next_tick:
                self._tick()
                next_tick = time.monotonic() + 0.02

    def close(self):
        self._stop.set()
        self.thread.join(5.0)
        self.executor.shutdown()
        for server in self._servers:
            server.destroy()
        self.node.destroy_node()
        self.context.try_shutdown()


def unrejected(observe):
    """Run `observe` again while it says ACT_STACK_SOURCE_REJECTED: the observer refuses a sequence gap, and a depth-one subscription
    loses samples when the host is busy (the gate runs these tests beside everything else). No scenario expects that code."""
    for _attempt in range(5):
        outcome = observe()
        if outcome[0] or outcome[2] != "ACT_STACK_SOURCE_REJECTED":
            break
    return outcome


def command_line(rig_arguments):
    return unrejected(lambda: _command_line(rig_arguments))


def _command_line(rig_arguments):
    environment = {**os.environ, "ROS_DOMAIN_ID": DOMAIN}
    environment.pop("SO101_ACT_INSTANCE_ROOT", None)
    done = subprocess.run([sys.executable, "-m", "so101_demo.cli.act_stack_ready", "--session-id", SESSION,
                           "--ros-domain-id", DOMAIN, "--timeout-s", str(TIMEOUT_S), *rig_arguments],
                          capture_output=True, text=True, env=environment, timeout=60)
    if done.returncode == 0:
        artifact = json.loads(done.stdout)
        return True, artifact["checks"], sorted(artifact)
    report = json.loads(done.stderr.strip().splitlines()[-1])
    return False, report["checks"], report["failure_code"]


def kept(session):
    return unrejected(lambda: _kept(session))


def _kept(session):
    outcome = session.check(TIMEOUT_S)
    if outcome.ready:
        return True, outcome.artifact["checks"], sorted(outcome.artifact)
    return False, outcome.report["checks"], outcome.report["failure_code"]


def scenarios():
    def paused(stack): stack.paused = True
    def stale_camera(stack): stack.camera_on = False
    def moving(stack): stack.velocity = 0.5
    def inactive(stack): stack.inactive = {"arm_controller"}
    def no_service(stack): stack.drop_service("/get_planning_scene")
    return [("ready", lambda stack: None, None),
            ("paused", paused, "ACT_STACK_WORLD_SESSION_INVALID"),
            ("camera_missing", stale_camera, "ACT_STACK_HEAD_RGB_INVALID"),
            ("moving", moving, "ACT_STACK_NOT_PHYSICALLY_STOPPED"),
            ("controller_inactive", inactive, "ACT_STACK_CONTROLLER_NOT_ACTIVE"),
            ("service_missing", no_service, "ACT_STACK_GRAPH_INCOMPLETE")]


@pytest.fixture(params=["default_context", "instance_context"])
def graph(request, monkeypatch, tmp_path):
    import rclpy
    from so101_demo.act.rig_profile import DEFAULT_RIG

    monkeypatch.setenv("ROS_DOMAIN_ID", DOMAIN)
    monkeypatch.delenv("ROS_NAMESPACE", raising=False)
    if request.param == "instance_context":
        monkeypatch.setenv("SO101_ACT_INSTANCE_ROOT", str(tmp_path))
    else:
        monkeypatch.delenv("SO101_ACT_INSTANCE_ROOT", raising=False)
    rclpy.try_shutdown()
    stack = FakeStack(DEFAULT_RIG)
    yield stack
    stack.close()
    rclpy.try_shutdown()


def test_the_kept_session_and_the_command_line_judge_every_scenario_alike(graph):
    from so101_demo.act.rig_profile import DEFAULT_RIG
    from so101_demo.cli.act_stack_ready import StackReadinessSession

    session = StackReadinessSession(session_id=SESSION, ros_domain_id=int(DOMAIN), rig=DEFAULT_RIG)
    try:
        first = kept(session)
        assert first[0] is True, first            # the stand-in stack is ready before anything is broken
        assert kept(session) == first             # and the kept session gives the same answer when asked again
        for name, damage, failure in scenarios():
            damage(graph)
            time.sleep(0.3)
            expected = command_line([])
            assert kept(session) == expected, name
            assert (expected[0], expected[2] if failure else None) == (failure is None, failure), (name, expected)
            graph.restore()
            time.sleep(0.5)
            assert kept(session)[0] is True, name     # a kept session is ready again as soon as the stack is
    finally:
        session.close()


def test_a_session_that_is_not_ready_recovers_when_the_stack_does(graph):
    from so101_demo.act.rig_profile import DEFAULT_RIG
    from so101_demo.cli.act_stack_ready import StackReadinessSession

    session = StackReadinessSession(session_id=SESSION, ros_domain_id=int(DOMAIN), rig=DEFAULT_RIG)
    try:
        graph.paused = True
        time.sleep(0.3)
        assert session.check(1.5).ready is False
        graph.paused = False
        time.sleep(0.3)
        assert kept(session)[0] is True
    finally:
        session.close()


def test_each_xdist_worker_has_a_domain_of_its_own_and_none_that_another_stage_or_test_uses():
    reserved = {203, 204, 223, 224, 225, 226, 227, 229, 230, 231, 232}
    domains = [int(domain_for(f"gw{number}")) for number in range(DOMAIN_COUNT)]
    assert len(set(domains)) == DOMAIN_COUNT and not reserved & set(domains) and max(domains) <= 232
    assert domain_for("master") == domain_for("gw0") == str(FIRST_DOMAIN)
