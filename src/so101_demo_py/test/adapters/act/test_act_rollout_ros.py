"""The ROS side of the rollout executor, with fakes only (no ROS graph, no GPU).

The camera set and the state width are inputs here: every behaviour is checked for the shipped (head, wrist, 8) bundle and for a
rig-v2 style (side, wrist, 6) bundle.
"""

import math
import time
from types import SimpleNamespace

import numpy as np
import pytest

from so101_demo.act.execution import prefix_sha256
from so101_demo.act.joints import ARM_JOINTS
from so101_demo.act.rollout_config import load_rollout_config
from so101_demo.adapters.act import rollout_ros as rr
from so101_demo.adapters.act.inference_process import ActInferenceProcess
from paths import PACKAGE_ROOT

pytestmark = pytest.mark.usefixtures("isolated_ros_domain")      # real nodes: a ROS domain of this test's own (not the gate's 203)

SHAPE = (4, 6, 3)
ARM = {name: 0.1 * index for index, name in enumerate(ARM_JOINTS)}
CONFIG = load_rollout_config(PACKAGE_ROOT / "config/act/rollout.yaml")


def _frame(value):
    return np.full(SHAPE, value, dtype=np.uint8)


def _joints(neck=0.5):
    return {**ARM, "neck_yaw_joint": neck}


def _assembler(cameras=("head", "wrist"), state_dim=8, floor=0.0):
    assembler = rr.ObservationAssembler(cameras=cameras, state_dim=state_dim, max_age_s=0.1, max_skew_s=0.1,
                                        image_shape=SHAPE, monotonic=lambda: 50.0)
    assembler.reset("session-1", source_floor_s=floor)
    return assembler


def _feed(assembler, cameras, stamp, *, joints=True):
    if joints:
        assembler.push_joints(stamp, _joints())
    for index, camera in enumerate(cameras):
        assert assembler.push_image(camera, stamp, _frame(index + 1))


@pytest.mark.parametrize("cameras,state_dim", [(("head", "wrist"), 8), (("side", "wrist"), 6)])
def test_an_observation_is_emitted_once_per_complete_new_image_set(cameras, state_dim):
    assembler = _assembler(cameras, state_dim)
    assembler.push_joints(1.0, _joints())
    assembler.push_image(cameras[0], 1.0, _frame(1))
    assert assembler.poll() is None                                  # one camera is not an image set
    assembler.push_image(cameras[1], 1.0, _frame(2))
    observation, audit = assembler.poll()
    assert set(observation) == {"sim_time_s", "state", *cameras}
    assert observation["sim_time_s"] == 1.0 and len(observation["state"]) == state_dim
    assert observation[cameras[0]].shape == SHAPE and int(observation[cameras[1]][0, 0, 0]) == 2
    assert set(audit["pixel_sha256"]) == set(cameras) and audit["stamps"] == {name: 1.0 for name in cameras}
    assert assembler.poll() is None                                  # the same set is never emitted twice
    _feed(assembler, cameras, 1.1)
    assert assembler.poll()[0]["sim_time_s"] == 1.1


def test_the_state_is_the_arm_and_only_the_eight_wide_state_carries_the_neck_encoding():
    wide = _assembler(("head", "wrist"), 8)
    _feed(wide, ("head", "wrist"), 1.0)
    state = wide.poll()[0]["state"]
    assert state[:6] == pytest.approx([ARM[name] for name in ARM_JOINTS])
    assert state[6:] == pytest.approx([math.sin(0.5), math.cos(0.5)])
    narrow = _assembler(("side", "wrist"), 6)
    narrow.push_joints(1.0, {name: ARM[name] for name in ARM_JOINTS})          # no neck joint exists in this rig
    narrow.push_image("side", 1.0, _frame(1))
    narrow.push_image("wrist", 1.0, _frame(2))
    assert narrow.poll()[0]["state"] == pytest.approx([ARM[name] for name in ARM_JOINTS])


def test_frames_at_or_below_the_reset_boundary_and_unknown_cameras_are_refused():
    assembler = _assembler(floor=2.0)
    assert assembler.push_image("head", 2.0, _frame(1)) is False
    assert assembler.push_joints(1.9, _joints()) is False
    assert assembler.push_image("side", 3.0, _frame(1)) is False            # not a configured camera
    assert assembler.push_image("head", 3.0, np.zeros((2, 2, 3), dtype=np.uint8)) is False
    assert assembler.push_image("head", 3.0, _frame(1)) is True
    assert assembler.push_image("head", 3.0, _frame(1)) is False            # stamps must increase
    assert {"INPUT_RESET_STALE", "INPUT_SESSION_INVALID", "INPUT_RGB_INVALID", "INPUT_TIMESTAMP_INVALID"} <= set(
        assembler.rejected)


def test_the_assembler_counts_the_sets_it_does_not_emit_by_reason_and_the_inputs_it_refuses():
    skewed = _assembler()
    skewed.push_joints(1.3, _joints())
    skewed.push_image("head", 1.0, _frame(1))
    skewed.push_image("wrist", 1.3, _frame(2))
    assert skewed.poll() is None and skewed.poll_skips == {"rgb_skew": 1}
    stale = _assembler()
    stale.push_joints(1.0, _joints())
    stale.push_image("head", 0.8, _frame(1))
    stale.push_image("wrist", 0.8, _frame(2))
    assert stale.poll() is None and stale.poll_skips == {"rgb_stale": 1}
    fine = _assembler()
    fine.push_joints(1.0, _joints())
    fine.push_image("head", 1.0, _frame(1))
    assert fine.poll() is None and fine.poll_skips == {}             # an incomplete set is waiting, not a reject
    fine.push_image("wrist", 1.0, _frame(2))
    assert fine.poll() is not None and fine.poll_skips == {}
    assert fine.poll() is None and fine.poll_skips == {}             # the same set again is not a reject either
    fine.note_rejected("INPUT_RGB_INVALID")
    assert fine.rejected_count == 1
    document = fine.reject_document()
    assert document == {"input_rejects": 1, "recent_input_rejects": ["INPUT_RGB_INVALID"], "poll_skips": {}, "rgb_sync_rejects": 1}


def test_a_set_that_is_skewed_or_stale_is_not_emitted():
    skewed = _assembler()
    skewed.push_joints(1.3, _joints())
    skewed.push_image("head", 1.0, _frame(1))
    skewed.push_image("wrist", 1.3, _frame(2))
    assert skewed.poll() is None                                     # 0.3 s apart
    stale = _assembler()
    stale.push_joints(1.0, _joints())
    stale.push_image("head", 0.8, _frame(1))
    stale.push_image("wrist", 0.8, _frame(2))
    assert stale.poll() is None                                      # older than the frozen age against the joint clock
    assert stale.sim_time() == 1.0


def test_the_assembler_refuses_a_malformed_configuration():
    for kwargs in (dict(cameras=(), state_dim=8), dict(cameras=("head", "head"), state_dim=8),
                   dict(cameras=("head",), state_dim=7), dict(cameras=("head",), state_dim=8, image_shape=(4, 6))):
        with pytest.raises(ValueError, match="ROLLOUT_OBSERVATION_CONFIG_INVALID"):
            rr.ObservationAssembler(max_age_s=0.1, max_skew_s=0.1, **kwargs)


def _prefix(positions=((0.0,) * 6,), observed=1.0):
    return {"session_id": "s", "attempt_id": "a", "sequence": 0, "observation_time_s": observed,
            "target_times_s": (observed + 0.1,), "positions": positions}


def test_the_permit_checks_the_joint_limits_and_nothing_else():
    permit = rr.JointLimitPermit()
    prefix = _prefix()
    assert permit.require(permit.issue(prefix), prefix) is None
    with pytest.raises(PermissionError, match="PERMIT_INVALID"):
        permit.require({"prefix_sha256": "0" * 64}, prefix)
    outside = _prefix(((0.0, 0.0, 0.0, 0.0, 0.0, 9.0),))
    with pytest.raises(ValueError, match="JOINT_LIMIT_INVALID"):
        permit.require({"prefix_sha256": prefix_sha256(outside)}, outside)
    permit.revoke("STOP")
    with pytest.raises(PermissionError, match="PERMIT_REVOKED"):
        permit.require(permit.issue(prefix), prefix)


def test_the_reference_is_the_measured_position_then_the_goal_in_flight():
    goal_arm = {"header_stamp_s": 10.0, "time_from_start_s": (0.0, 0.1, 0.2),
                "positions": ((0.0,) * 5, (1.0,) * 5, (2.0,) * 5)}
    goal_gripper = {"header_stamp_s": 10.0, "time_from_start_s": (0.0, 0.1, 0.2), "positions": ((0.0,), (0.5,), (0.7,))}
    goals = []
    reference = rr.ControllerReference(measured=lambda: (0.3,) * 6, last_goals=lambda: goals[-1] if goals else None)
    assert reference(10.0) == (0.3,) * 6
    goals.append((goal_arm, goal_gripper))
    assert reference(9.0) == (0.0,) * 5 + (0.0,)                      # before the first knot
    assert reference(10.05) == pytest.approx((0.5,) * 5 + (0.25,))
    assert reference(10.15) == pytest.approx((1.5,) * 5 + (0.6,))
    assert reference(11.0) == (2.0,) * 5 + (0.7,)                     # held after the last knot
    unavailable = rr.ControllerReference(measured=lambda: None, last_goals=lambda: None)
    with pytest.raises(RuntimeError, match="CONTROLLER_REFERENCE_UNAVAILABLE"):
        unavailable(1.0)


def _wait(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.002)
    raise AssertionError("timed out")


def test_the_thread_transport_serves_the_boundary_and_drops_replies_of_abandoned_requests():
    gate = {"release": False}

    def infer(observation):
        if observation["slow"]:
            _wait(lambda: gate["release"])
        return ((float(observation["value"]),) * 6,)

    transport = rr.ThreadInferenceTransport(infer)
    boundary = ActInferenceProcess(
        config={"inference": {"device": "cuda", "request_timeout_s": 5.0, "max_reply_age_s": 5.0}},
        transport=transport, clock=time.monotonic)
    try:
        boundary.submit({"slow": False, "value": 1.0}, sequence=0)
        reply = _wait(lambda: boundary.poll())
        assert reply["sequence"] == 0 and reply["actions"] == ((1.0,) * 6,) and reply["age_s"] >= 0
        boundary.submit({"slow": True, "value": 2.0}, sequence=1)
        _wait(lambda: transport._busy)
        boundary.abandon()
        boundary.submit({"slow": False, "value": 3.0}, sequence=2)
        gate["release"] = True                                        # request 1 finishes late: its reply must vanish
        reply = _wait(lambda: boundary.poll())
        assert reply["sequence"] == 2 and reply["actions"] == ((3.0,) * 6,)
        assert transport.receive() is None
        assert transport.quiesce(5.0) is True
    finally:
        assert boundary.close() is None


def test_a_failing_model_call_becomes_a_reply_the_boundary_refuses():
    def infer(_observation):
        raise RuntimeError("cuda out of memory")

    transport = rr.ThreadInferenceTransport(infer)
    boundary = ActInferenceProcess(
        config={"inference": {"device": "cuda", "request_timeout_s": 5.0, "max_reply_age_s": 5.0}},
        transport=transport, clock=time.monotonic)
    boundary.submit({"x": 1}, sequence=0)
    with pytest.raises(ValueError, match="INFERENCE_REPLY_INVALID"):
        _wait(lambda: boundary.poll())
    boundary.close()
    with pytest.raises(ValueError, match="INFERENCE_PROCESS_CLOSED"):
        transport.send({"sequence": 1, "observation": {}})


def _evidence(**changes):
    state = SimpleNamespace(position_world=(0.1, -0.3, 0.165), orientation_xyzw=(0.0, 0.0, 0.0, 1.0), body="plastic_cup",
                            linear_velocity_world=(0.0, 0.0, 0.0))
    return SimpleNamespace(object_state=state, simulation_time_s=12.5, frame_id="world", simulation_session_id="sim-1",
                           reset_epoch=2, publisher_sequence=7, simulation_step=900, **changes)


def test_the_world_observer_gives_the_teachers_observation_document_or_none():
    class Observer:
        def __init__(self):
            self.error = None

        def snapshot_with_receipt(self):
            if self.error:
                raise self.error
            return SimpleNamespace(evidence=_evidence(), received_monotonic_s=1.0)

    observer = Observer()
    world = rr.WorldCupObserver(observer)
    pose = world.cup_pose()
    assert pose["position"] == [0.1, -0.3, 0.165] and pose["orientation"] == {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    assert (pose["simulation_time_s"], pose["frame_id"], pose["object_id"], pose["session_id"], pose["reset_epoch"]) == (
        12.5, "world", "plastic_cup", "sim-1", 2)
    observer.error = RuntimeError("atomic evidence age 2.0s exceeds 1.0s")
    assert world.cup_pose() is None and "exceeds" in world.last_error
    with pytest.raises(ValueError, match="ROLLOUT_WORLD_OBSERVER_INVALID"):
        rr.WorldCupObserver(object())


class FakeAdapter:
    def __init__(self):
        self.calls, self.audit, self.state = [], [], "READY"

    def begin_attempt(self, session_id, attempt_id):
        self.calls.append(("begin", session_id, attempt_id))

    def submit(self, prefix, permit):
        self.calls.append(("submit", prefix["sequence"], permit))
        return "g1:g2"

    def stop(self, reason):
        self.calls.append(("stop", reason))
        self.state = "STOPPED"
        return self.state

    def poll_stop(self):
        return self.state


def _session(sim_time=1.0, adapter=None):
    assembler = _assembler()
    assembler.push_joints(sim_time, _joints())
    closes = []
    session = rr.RolloutSession(assembler=assembler, adapter=adapter or FakeAdapter(), permit=rr.JointLimitPermit(),
                                world=SimpleNamespace(cup_pose=lambda: {"p": 1}), spin=lambda: None,
                                close=lambda: closes.append(1), submit_lead_s=0.03)
    return session, closes


def test_a_late_or_out_of_limit_prefix_is_refused_before_the_adapter_can_stop_the_arm():
    session, _ = _session(sim_time=1.08)
    adapter = session.adapter
    with pytest.raises(ValueError, match="PREFIX_LATE"):
        session.submit_prefix(_prefix(observed=1.0))                 # 1.08 + 0.03 >= 1.1
    with pytest.raises(ValueError, match="JOINT_LIMIT_INVALID"):
        session.submit_prefix(_prefix(((0.0, 0.0, 0.0, 0.0, 0.0, 9.0),), observed=2.0))
    assert adapter.calls == []                                       # neither refusal reached the controllers
    session.assembler.push_joints(1.09, _joints())
    on_time = _prefix(observed=1.08)
    assert session.submit_prefix(on_time) == "g1:g2"
    assert adapter.calls == [("submit", 0, {"prefix_sha256": prefix_sha256(on_time)})]


def test_the_session_delegates_control_and_closes_once():
    session, closes = _session()
    session.begin("sim-1", "attempt-1")
    assert session.sim_time() == 1.0 and session.cup_pose() == {"p": 1}
    assert session.stop_confirmed() is False
    assert session.stop("ROLLOUT_HORIZON") == "STOPPED" and session.stop_confirmed() is True
    session.close()
    session.close()
    assert closes == [1] and session.adapter.calls[0] == ("begin", "sim-1", "attempt-1")
    empty = rr.RolloutSession(assembler=_assembler(), adapter=FakeAdapter(), permit=rr.JointLimitPermit(),
                              world=None, spin=lambda: None, close=lambda: None, submit_lead_s=0.03)
    with pytest.raises(RuntimeError, match="ROLLOUT_SIM_CLOCK_UNAVAILABLE"):
        empty.sim_time()


def test_the_session_is_ready_only_after_the_first_joint_state_of_this_session():
    session, _ = _session()
    assert session.ready() is True
    empty = rr.RolloutSession(assembler=_assembler(), adapter=FakeAdapter(), permit=rr.JointLimitPermit(),
                              world=None, spin=lambda: None, close=lambda: None, submit_lead_s=0.03)
    assert empty.ready() is False
    empty.assembler.push_joints(0.5, _joints())
    assert empty.ready() is True


class FakeNode:
    def __init__(self):
        self.subscriptions = []

    def create_subscription(self, message_type, topic, callback, qos):
        self.subscriptions.append((message_type, topic, callback, qos))


class FakeBinding:
    def __init__(self):
        self.nodes, self.clients, self.spinning, self.stopped, self.destroyed = [], [], [], [], []
        self.message_types = {"Image": "Image", "JointState": "JointState", "FollowJointTrajectory": "Follow"}
        self.image_qos, self.sensor_qos = "image-qos", "sensor-qos"
        self.ready, self.probe_error, self.probed = True, None, []

    def probe_action_services(self, client, *, timeout_s):
        self.probed.append(client.action)
        if self.probe_error is not None:
            raise self.probe_error
        return {"cancel_rtt_s": 0.001, "result_rtt_s": 0.002}

    def create_node(self, name):
        node = FakeNode()
        node.name = name
        self.nodes.append(node)
        return node

    def action_client(self, node, action_type, name):
        client = SimpleNamespace(action=name, server_is_ready=lambda: self.ready)
        self.clients.append(name)
        return client

    def start_spinning(self, node):
        self.spinning.append(node)
        return lambda: self.stopped.append(node)

    def destroy_action_client(self, client):
        self.destroyed_clients = getattr(self, "destroyed_clients", [])
        self.destroyed_clients.append(client.action)
        self.destroyed.append(("client", client.action))

    def destroy_node(self, node):
        self.destroyed.append(node)


TIMING = {"submit_lead_s": 0.03, "accept_timeout_s": 0.02, "stop_timeout_s": 1.0, "stop_velocity_rad_s": 0.002,
          "max_age_s": 0.5}


def _build(binding, cameras, state_dim):
    return rr.build_ros_session(
        binding=binding, config=CONFIG, cameras=cameras, state_dim=state_dim, image_shape=SHAPE, session_id="sim-1",
        source_floor_s=0.0, timing=TIMING, rgb_sync={"max_age_s": 0.1, "max_skew_s": 0.1},
        world_observer_factory=lambda node, session_id: SimpleNamespace(snapshot_with_receipt=lambda: None))


@pytest.mark.parametrize("cameras,state_dim", [(("head", "wrist"), 8), (("side", "wrist"), 6)])
def test_the_session_subscribes_to_the_topics_of_the_cameras_the_bundle_names(cameras, state_dim):
    binding = FakeBinding()
    session = _build(binding, cameras, state_dim)
    node = binding.nodes[0]
    topics = {topic for _type, topic, _callback, _qos in node.subscriptions}
    assert {CONFIG["camera_topics"][name] for name in cameras} <= topics
    assert CONFIG["joint_state_topic"] in topics
    other = {"head", "wrist", "side"} - set(cameras)
    assert not {CONFIG["camera_topics"][name] for name in other} & topics     # no camera outside the bundle's set
    assert binding.clients == [CONFIG["controller_actions"]["arm"], CONFIG["controller_actions"]["gripper"]]
    assert binding.spinning == [node]
    # a published frame reaches the assembler under the camera's name, and a full set becomes an observation
    # the controller ports listen to the joint states too: only the executor's own subscription feeds the assembler
    callbacks = {topic: callback for _type, topic, callback, _qos in node.subscriptions
                 if getattr(callback, "__name__", "") != "_feedback"}
    assert sum(1 for _type, topic, _callback, _qos in node.subscriptions if topic == CONFIG["joint_state_topic"]) == 3

    def image(value):
        data = bytes([value]) * (SHAPE[0] * SHAPE[1] * 3)
        return SimpleNamespace(encoding="rgb8", width=SHAPE[1], height=SHAPE[0], step=SHAPE[1] * 3, data=data,
                               header=SimpleNamespace(stamp=SimpleNamespace(sec=5, nanosec=500_000_000)))

    names = list(ARM_JOINTS) + (["neck_yaw_joint"] if state_dim == 8 else [])
    callbacks[CONFIG["joint_state_topic"]](SimpleNamespace(
        name=names, position=[0.1] * len(names), velocity=[0.0] * len(names),
        header=SimpleNamespace(stamp=SimpleNamespace(sec=5, nanosec=500_000_000))))
    for index, camera in enumerate(cameras):
        callbacks[CONFIG["camera_topics"][camera]](image(index + 1))
    observation, _audit = session.observe()
    assert set(observation) == {"sim_time_s", "state", *cameras} and observation["sim_time_s"] == 5.5
    session.close()
    assert binding.stopped == [node] and binding.destroyed[-1] == node and len(binding.destroyed) == 3


def test_a_camera_without_a_topic_is_refused_before_any_node_exists():
    binding = FakeBinding()
    with pytest.raises(ValueError, match="ROLLOUT_CAMERA_TOPIC_UNMAPPED: top"):
        _build(binding, ("top", "wrist"), 6)
    assert binding.nodes == []


def test_a_wiring_failure_stops_the_spinner_and_destroys_the_node():
    binding = FakeBinding()
    original = binding.action_client

    def broken(node, action_type, name):
        if name == CONFIG["controller_actions"]["gripper"]:
            raise RuntimeError("no such action")
        return original(node, action_type, name)

    binding.action_client = broken
    with pytest.raises(RuntimeError, match="no such action"):
        _build(binding, ("head", "wrist"), 8)
    assert binding.destroyed == [("client", CONFIG["controller_actions"]["arm"]), *binding.nodes] and binding.spinning == []


def test_closing_the_session_destroys_its_action_clients_before_its_node():
    """An action client keeps its node in the ROS graph after `destroy_node` (found live: the next episode's initial gate saw
    `/act_rollout_executor` and refused), so every client is destroyed first."""
    binding = FakeBinding()
    session = _build(binding, ("side", "wrist"), 6)
    session.close()
    session.close()
    assert binding.destroyed == [("client", CONFIG["controller_actions"]["arm"]),
                                 ("client", CONFIG["controller_actions"]["gripper"]), binding.nodes[0]]
    assert binding.stopped == binding.nodes


def test_the_real_binding_leaves_the_default_ros_context_to_the_scene_reset():
    """The reset (`execute_scene_operation`) calls `rclpy.init()` and `rclpy.shutdown()` on the default context of the process;
    a binding that had initialised it would make every reset fail with `Context.init() must only be called once` (found live)."""
    rclpy = pytest.importorskip("rclpy")
    pytest.importorskip("control_msgs.action")
    binding = rr.RclpyBinding()
    try:
        assert rclpy.ok() is False                          # the default context is untouched
        node = binding.create_node("act_rollout_binding_test")
        stop = binding.start_spinning(node)
        stop()
        binding.destroy_node(node)
        rclpy.init()                                          # what the reset does
        rclpy.shutdown()
    finally:
        binding.shutdown()
    assert binding._context.ok() is False


def test_stop_diagnostics_name_what_keeps_a_stop_unconfirmed():
    import threading

    class Port:
        stop_velocity, max_age = 0.002, 0.5
        monotonic = staticmethod(lambda: 10.0)

        def __init__(self, velocity, goals):
            self._lock, self._velocity, self._received, self._goals = threading.RLock(), velocity, 9.9, goals

    done = {"accepted": True, "result": SimpleNamespace(status=4), "cancel_requested": True}
    running = {"accepted": True, "result": None, "cancel_requested": True}
    adapter = FakeAdapter()
    adapter.arm, adapter.gripper = Port((0.0, 0.01), {"a": done, "b": running}), Port((0.0,), {"a": done})
    session, _ = _session(adapter=adapter)
    report = session.stop_diagnostics()
    assert report["arm"]["max_abs_velocity_rad_s"] == 0.01 and report["arm"]["open_goal_count"] == 1
    assert report["arm"]["feedback_age_s"] == pytest.approx(0.1) and report["gripper"]["open_goal_count"] == 0
    bare, _ = _session()                                      # a port that cannot be read is reported, never raised
    assert "unreadable" in bare.stop_diagnostics()["arm"]


def test_the_horizon_stop_lets_the_goals_in_flight_finish_before_it_cancels_anything():
    """Goals last one action step and the horizon is an observation tick, so the last goal finishes at the horizon; a cancel in
    that instant leaves it CANCELING forever (found live: no result, the stop could never be proven)."""
    order = []

    class Port:
        def __init__(self, left):
            self.left = left

        def unfinished_goals(self):
            order.append(("poll", self.left))
            value, self.left = self.left, max(0, self.left - 1)
            return value

    class Adapter(FakeAdapter):
        def stop(self, reason):
            order.append(("stop", reason))
            return super().stop(reason)

    adapter = Adapter()
    adapter.arm, adapter.gripper = Port(2), Port(1)
    session, _ = _session(adapter=adapter)
    assert session.stop("ROLLOUT_HORIZON") == "STOPPED"
    assert order[-1] == ("stop", "ROLLOUT_HORIZON") and [item for item in order if item[0] == "stop"] == [order[-1]]
    assert all(item == ("poll", 0) for item in order[-3:-1])                    # nothing was left unfinished at the cancel
    # a safety or fault stop is never delayed
    order.clear()
    adapter.arm, adapter.gripper = Port(5), Port(5)
    session.stop("ROLLOUT_FAULT")
    assert order == [("stop", "ROLLOUT_FAULT")]


def test_the_drain_is_bounded():
    class Stuck:
        def unfinished_goals(self):
            return 1

    ticks = iter(x * 0.4 for x in range(100))
    adapter = FakeAdapter()
    adapter.arm, adapter.gripper = Stuck(), Stuck()
    session, _ = _session(adapter=adapter)
    session.monotonic = lambda: next(ticks)
    assert session.drain_goals() is False


def test_the_controller_port_counts_goals_without_an_outcome():
    pytest.importorskip("control_msgs.action")
    from so101_demo.adapters.act.ros_execution import RosControllerPort

    node = SimpleNamespace(create_subscription=lambda *args, **kwargs: None)
    port = RosControllerPort(node, None, ("1",), stop_velocity_rad_s=0.002, max_age_s=0.5)
    assert port.unfinished_goals() == 0
    port._goals = {"a": {"accepted": None, "result": None}, "b": {"accepted": True, "result": None},
                   "c": {"accepted": True, "result": SimpleNamespace(status=4)}, "d": {"accepted": False, "result": None}}
    assert port.unfinished_goals() == 2


def test_the_session_reports_the_observation_rejects_of_its_assembler():
    session, _closes = _session()
    assert session.observation_rejects() == session.assembler.reject_document()
    assert session.observation_rejects()["rgb_sync_rejects"] == 0


def test_the_session_waits_for_the_controller_servers_and_proves_their_services_before_the_first_goal():
    binding = FakeBinding()
    session = _build(binding, ("side", "wrist"), 6)
    assert binding.probed == [CONFIG["controller_actions"]["arm"], CONFIG["controller_actions"]["gripper"]]
    readiness = session.controller_readiness()
    assert set(readiness["server_ready_wait_s"]) == {"arm", "gripper"} and set(readiness["probes"]) == {"arm", "gripper"}
    assert readiness["probes"]["arm"] == {"cancel_rtt_s": 0.001, "result_rtt_s": 0.002} and readiness["timeout_s"] == 10.0


def test_a_server_that_becomes_ready_during_the_bound_is_waited_for():
    clock = {"t": 0.0}
    polls = {"n": 0}

    def ready():
        polls["n"] += 1
        return polls["n"] > 6

    clients = {"arm": SimpleNamespace(server_is_ready=ready), "gripper": SimpleNamespace(server_is_ready=lambda: True)}

    def sleep(seconds):
        clock["t"] += seconds

    result = rr.await_controllers_ready(SimpleNamespace(), clients, timeout_s=1.0, monotonic=lambda: clock["t"], sleep=sleep)
    assert result["server_ready_wait_s"]["arm"] > 0.0 and result["server_ready_wait_s"]["gripper"] == 0.0 and result["probes"] == {}


def test_a_server_that_is_not_ready_in_the_bound_is_an_infrastructure_fault_and_the_nodes_are_released():
    binding = FakeBinding()
    binding.ready = False
    timing = dict(TIMING, controller_ready_timeout_s=0.05)
    with pytest.raises(RuntimeError, match="CONTROLLER_ACTION_SERVER_NOT_READY: arm,gripper"):
        rr.build_ros_session(
            binding=binding, config=CONFIG, cameras=("side", "wrist"), state_dim=6, image_shape=SHAPE, session_id="sim-1",
            source_floor_s=0.0, timing=timing, rgb_sync={"max_age_s": 0.1, "max_skew_s": 0.1},
            world_observer_factory=lambda node, session_id: SimpleNamespace(snapshot_with_receipt=lambda: None))
    assert binding.stopped == binding.spinning and binding.destroyed_clients == [
        CONFIG["controller_actions"]["arm"], CONFIG["controller_actions"]["gripper"]] and binding.probed == []


def test_a_service_probe_that_fails_is_an_infrastructure_fault():
    binding = FakeBinding()
    binding.probe_error = TimeoutError("cancel service did not answer")
    with pytest.raises(RuntimeError, match="CONTROLLER_ACTION_SERVICES_NOT_READY: arm: TimeoutError"):
        _build(binding, ("side", "wrist"), 6)
    assert binding.stopped == binding.spinning


def test_a_binding_without_a_probe_still_needs_the_servers():
    clients = {"arm": SimpleNamespace(server_is_ready=lambda: True)}
    assert rr.await_controllers_ready(SimpleNamespace(), clients, timeout_s=1.0)["probes"] == {}
