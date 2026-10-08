"""CP-3441: Teacher event and reporting clocks are current at the actual call; the ACM diff keeps the attached colour;
the stop proof's simulation clock matches its monotonic instant; only the final boundary `normal_stop` is published.
None of this changes control: the tests only read stamps, scene message content and published events."""

import copy
from types import SimpleNamespace

import pytest

from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution


def REQ():
    from moveit_msgs.srv import ApplyPlanningScene
    return ApplyPlanningScene.Request()


def RESP():
    from moveit_msgs.srv import ApplyPlanningScene
    return ApplyPlanningScene.Response(success=True)


class LaggingClock:
    """A ROS clock that is behind the simulation until the node has been spun: `spin()` brings it to `truth`."""

    def __init__(self, lagging_ns, truth_ns):
        self.value, self.truth = lagging_ns, truth_ns
        self.spins = 0

    def now(self):
        return SimpleNamespace(nanoseconds=self.value)

    def spin(self, *args, **kwargs):
        self.spins += 1
        self.value = self.truth


# ---- 1. scene-operation stamps come from the current clock ----------------------------------------------------------

def test_record_scene_service_call_refreshes_the_clock_before_every_stamp():
    from so101_demo.control.planning_scene.task_scene import record_scene_service_call

    clock = LaggingClock(21_906_000_000, 22_085_000_000)
    order = []
    records = []
    record_scene_service_call(
        request=REQ(), phase="APPLY", service="/apply_planning_scene",
        invoke=lambda: order.append("invoke") or RESP(), records=records, ros_clock=clock,
        clock_refresh=lambda: (order.append("refresh"), clock.spin()))
    record = records[0]
    assert record["request_ros_clock"]["sim_time_ns"] == 22_085_000_000
    assert order == ["refresh", "invoke", "refresh"], "request and response clocks are both read after a refresh"


def test_the_floor_lifts_a_clock_that_is_still_behind_the_newest_world_sample():
    from so101_demo.control.planning_scene.task_scene import record_scene_service_call

    clock = LaggingClock(21_906_000_000, 21_906_000_000)
    records = []
    record_scene_service_call(
        request=REQ(), phase="APPLY", service="/apply_planning_scene", invoke=lambda: RESP(),
        records=records, ros_clock=clock, clock_floor=lambda: 22_000_000_000)
    assert records[0]["request_ros_clock"]["sim_time_ns"] == 22_000_000_000
    assert records[0]["response_ros_clock"]["sim_time_ns"] == 22_000_000_000


def test_a_failing_refresh_or_floor_never_changes_the_call():
    from so101_demo.control.planning_scene.task_scene import record_scene_service_call

    clock = LaggingClock(5, 5)
    records = []

    def boom():
        raise RuntimeError("EXECUTOR_BUSY")

    response = record_scene_service_call(
        request=REQ(), phase="APPLY", service="/apply_planning_scene", invoke=lambda: RESP(),
        records=records, ros_clock=clock, clock_refresh=boom, clock_floor=boom)
    assert response.success and records[0]["request_ros_clock"]["sim_time_ns"] == 5


def test_the_setup_port_stamps_its_apply_from_a_node_clock_spun_at_the_call(monkeypatch):
    import rclpy
    from moveit_msgs.msg import PlanningScene
    from so101_demo.control.planning_scene.task_scene import RosTaskScenePort

    clock = LaggingClock(21_906_000_000, 22_085_000_000)
    monkeypatch.setattr(rclpy, "spin_once", clock.spin)
    monkeypatch.setattr(rclpy, "spin_until_future_complete", lambda *a, **k: None)

    class Client:
        def wait_for_service(self, timeout_sec=None):
            return True

        def call_async(self, request):
            return SimpleNamespace(done=lambda: True, result=lambda: RESP())

    class Node:
        def create_client(self, kind, name):
            return Client()

        def get_clock(self):
            return clock

    port = RosTaskScenePort(Node(), "mujoco", 1.0)
    port._apply(PlanningScene(), "APPLY")
    record = port.service_call_records()[0]
    assert record["request_ros_clock"]["sim_time_ns"] == 22_085_000_000


def _teacher(clock, world_ns=None):
    value = object.__new__(RosDynamicMujocoExecution)
    value._node = SimpleNamespace(get_clock=lambda: clock)
    value._scene_service_calls = []
    value._check_stop = lambda: None
    value._wait_progress = lambda: None
    value._event_stream = None
    value._apply_scene = SimpleNamespace(
        wait_for_service=lambda timeout_sec=None: True,
        call_async=lambda request: SimpleNamespace(done=lambda: True, result=lambda: RESP()))
    value._get_scene = value._apply_scene
    if world_ns is not None:
        from so101_demo.core.simulation.types import ReceivedSimulationEvidence
        value.observer = SimpleNamespace(snapshot_with_receipt=lambda: ReceivedSimulationEvidence(
            SimpleNamespace(simulation_time_s=world_ns / 1e9), 1.0))
    return value


def test_the_teacher_stamps_each_scene_call_from_a_node_clock_spun_at_the_call(monkeypatch):
    import rclpy
    from moveit_msgs.msg import PlanningScene
    from moveit_msgs.srv import ApplyPlanningScene

    clock = LaggingClock(21_906_000_000, 22_085_000_000)
    monkeypatch.setattr(rclpy, "spin_once", clock.spin)
    value = _teacher(clock)
    value._call(value._apply_scene, ApplyPlanningScene.Request(scene=PlanningScene()), 1.0, "DYNAMIC_ACM_APPLY")
    record = value._scene_service_calls[0]
    assert record["request_ros_clock"]["sim_time_ns"] == 22_085_000_000
    assert clock.spins >= 2


# ---- 2. the ACM-only apply keeps the attached cup (and so its colour) ------------------------------------------------

def moveit_replaces_robot_state(scene):
    """MoveIt `PlanningScene::setPlanningSceneDiffMsg`: `if (!robot_state.attached_collision_objects.empty() ||
    !robot_state.is_diff) setCurrentState(robot_state)`. `setCurrentState` of a non-diff state re-creates the attached
    bodies from the message, so an attached cup absent from the message loses its attachment record and colour."""
    state = scene.robot_state
    return bool(state.attached_collision_objects) or not state.is_diff


def test_the_acm_only_apply_leaves_the_robot_state_and_so_the_attached_cup_colour_alone():
    from moveit_msgs.msg import AllowedCollisionMatrix
    from moveit_msgs.srv import GetPlanningScene

    value = object.__new__(RosDynamicMujocoExecution)
    sent = []

    def call(client, request, timeout, code, **kwargs):
        if code == "DYNAMIC_ACM_READBACK":
            return GetPlanningScene.Response(scene=SimpleNamespace(allowed_collision_matrix=AllowedCollisionMatrix()))
        sent.append(request)
        return SimpleNamespace(success=True)

    value._call = call
    value._get_scene = value._apply_scene = object()
    value._set_touch_collision(True)
    scene = sent[0].scene
    assert scene.is_diff is True
    assert not moveit_replaces_robot_state(scene), "an ACM diff must not replace the robot state"
    assert list(scene.robot_state.attached_collision_objects) == [] and list(scene.object_colors) == []


# ---- 3. the stop proof's simulation clock is the clock at its monotonic instant ---------------------------------------

def _stop_teacher(clock_ns, world_step=56055):
    from test_act_dynamic_release_safety import boundary, world
    value, selected, commands = boundary()
    sim_world = world(step=world_step, sequence=5)
    from so101_demo.core.simulation.types import ReceivedSimulationEvidence
    value.observer.snapshot_with_receipt = lambda: ReceivedSimulationEvidence(sim_world, 10.0)
    value._node = SimpleNamespace(get_clock=lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=clock_ns)))
    return value, sim_world


def test_the_stop_proof_claims_the_current_simulation_clock_at_its_own_monotonic_instant(monkeypatch):
    import rclpy
    monkeypatch.setattr(rclpy, "spin_once", lambda *a, **k: None)
    value, sim_world = _stop_teacher(clock_ns=round(56056 * 0.002 * 1e9))
    proof = value._normal_stop_proof()
    clock = proof["source_clock"]
    assert clock["begin_monotonic_ns"] == clock["end_monotonic_ns"]
    assert clock["begin_monotonic_ns"] >= round(proof["stop_confirmed_wall_s"] * 1e9)
    assert clock["sim_time_ns"] == round(56056 * 0.002 * 1e9), "not the older world record's 2 ms earlier time"
    assert clock["sim_time_ns"] >= round(sim_world.simulation_time_s * 1e9)


def test_the_stop_proof_never_claims_a_time_before_its_world_record(monkeypatch):
    import rclpy
    monkeypatch.setattr(rclpy, "spin_once", lambda *a, **k: None)
    value, sim_world = _stop_teacher(clock_ns=1)
    clock = value._normal_stop_proof()["source_clock"]
    assert clock["sim_time_ns"] == round(sim_world.simulation_time_s * 1e9)


# ---- 4. only the final boundary stop is published ---------------------------------------------------------------------

def test_an_intermediate_stop_proof_is_recorded_but_not_published(monkeypatch):
    import rclpy
    monkeypatch.setattr(rclpy, "spin_once", lambda *a, **k: None)
    value, _ = _stop_teacher(clock_ns=0)
    published = []
    value._publish_teacher_event = lambda kind, payload: published.append((kind, payload))
    value._normal_stop_proof()
    assert published == [] and len(value._document["normal_stop_proofs"]) == 1


def test_the_final_boundary_publishes_exactly_one_normal_stop(monkeypatch):
    import rclpy
    monkeypatch.setattr(rclpy, "spin_once", lambda *a, **k: None)
    value, _ = _stop_teacher(clock_ns=0)
    published = []
    value._publish_teacher_event = lambda kind, payload: published.append((kind, payload))
    value.final_stop_proof_enabled = True
    value._normal_stop_proof()                     # an intermediate (release) proof
    value._publish_final_normal_stop()
    assert [kind for kind, _ in published] == ["normal_stop"]
    assert published[0][1]["proof"] is value._document["normal_stop_proofs"][-1]
