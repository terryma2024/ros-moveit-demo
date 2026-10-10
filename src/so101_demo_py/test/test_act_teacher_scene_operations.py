"""The Teacher publishes its own scene calls and changes nothing else (Phase A4b).

Every Apply/GetPlanningScene call the Teacher makes becomes a `scene_operation` event; the requests it sends are the same
bytes whether collection is off, on or failing, and no data-side path builds or sends an ApplyPlanningScene request.
"""

import ast
import base64
import time
from types import SimpleNamespace

import pytest

from so101_demo.act.teacher_event_stream import StreamIdentity, TeacherEventStream, decode_event
from so101_demo.core.domain import State
from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
from test_act_recorder_scene import Context, over_dds
from test_act_scene_association import frozen_scene  # noqa: F401  (pytest fixture)
from paths import PACKAGE_ROOT

SRC = PACKAGE_ROOT / "src"


class Client:
    """A scene service double that records the exact wire bytes of every request, in order across both services."""

    def __init__(self, wire, name, respond):
        self.wire, self.name, self.respond = wire, name, respond

    def wait_for_service(self, timeout_sec=None):
        return True

    def call_async(self, request):
        # Raw CDR carries uninitialised alignment padding, so two serialisations of one message differ in those bytes;
        # the wire identity is the request's canonical content (every field, in order) and its decoded message.
        from rosidl_runtime_py.convert import message_to_ordereddict
        from so101_demo.act.scene_association import canonical
        self.wire.append((self.name, canonical(message_to_ordereddict(request))))
        response = over_dds(self.respond(request))
        return SimpleNamespace(done=lambda: True, result=lambda: response)


def harness(ctx, *, stream=None, binding=None):
    """The real `_attach`/`_detach_or_sync`/`_call` over fake clients; returns (adapter, wire)."""
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from so101_demo.core.simulation.types import ReceivedSimulationEvidence

    adapter = RosDynamicMujocoExecution.__new__(RosDynamicMujocoExecution)
    wire, gets = [], []
    scenes = {"get": [ctx.attached_scene(0.0), ctx.world_scene()]}
    adapter._apply_scene = Client(wire, "apply", lambda request: ApplyPlanningScene.Response(success=True))
    adapter._get_scene = Client(wire, "get", lambda request: GetPlanningScene.Response(scene=scenes["get"].pop(0)))
    adapter._scene_service_calls, adapter._document = [], {"state_events": [], "planning_attempts": []}
    adapter._write = lambda: None
    adapter._progress = lambda: None
    adapter._node = SimpleNamespace(get_clock=lambda: ctx.clock)
    adapter._task_geometry = ctx.base
    adapter._execution_snapshot_root = ctx.root
    adapter._session_id, adapter._expected_reset_epoch = ctx.world.simulation_session_id, ctx.world.reset_epoch
    adapter._touch_collision_allowed = False
    adapter._attached = False
    adapter._snapshot = lambda: ctx.world
    adapter._supported_release_preflight = lambda: ctx.world
    adapter._selected_release_source = ReceivedSimulationEvidence(ctx.world, time.monotonic())
    adapter._monotonic = time.monotonic
    adapter._release_runtime_policy = {"safety_release": {"support_distance_max_m": .002}}
    adapter._teacher_execution_policy = {"state_max_age_s": 60.0}
    adapter._record = lambda *args, **kwargs: None
    if binding is not None:
        adapter._scene_source_binding = binding
    adapter._event_stream = stream
    return adapter, wire


def drive(adapter):
    adapter._scene_state_value = State.ATTACH_MOVEIT.value
    adapter._attach(State.ATTACH_MOVEIT)
    adapter._scene_state_value = State.DETACH_MOVEIT.value
    adapter._detach_or_sync(State.DETACH_MOVEIT)


def stream_of(published, **kwargs):
    return TeacherEventStream(StreamIdentity("alignment-session", 1, "alignment-attempt"), clock_ns=lambda: 7,
                              publish=published.append, start=False, **kwargs)


def test_every_teacher_scene_call_is_published_with_its_exact_request_bytes_and_its_source(frozen_scene):
    ctx = Context(frozen_scene)
    ctx.stamp()
    published = []
    stream = stream_of(published)
    adapter, wire = harness(ctx, stream=stream)
    drive(adapter)
    stream.pump()
    events = [decode_event(text) for text in published]
    assert [event["type"] for event in events] == ["scene_operation"] * 4
    payloads = [event["payload"] for event in events]
    assert [item["operation"] for item in payloads] == ["attach", "readback", "detach", "readback"]
    assert [item["state"] for item in payloads] == ["ATTACH_MOVEIT"] * 2 + ["DETACH_MOVEIT"] * 2
    assert [item["service"] for item in payloads] == ["/apply_planning_scene", "/get_planning_scene"] * 2
    assert all(item["success"] is True and item["oversize"] is False for item in payloads)
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from so101_demo.act.scene_association import canonical
    types = {"/apply_planning_scene": ApplyPlanningScene.Request, "/get_planning_scene": GetPlanningScene.Request}
    sent = [canonical(message_to_ordereddict(deserialize_message(base64.b64decode(item["request_cdr_base64"]),
                                                                 types[item["service"]]))) for item in payloads]
    assert sent == [data for _, data in wire], "the published request is the request that was sent"
    assert payloads[2]["source"] == {"simulation_step": ctx.world.simulation_step,
                                     "publisher_sequence": ctx.world.publisher_sequence,
                                     "simulation_time_s": ctx.world.simulation_time_s}
    assert payloads[0]["source"] is None and adapter._scene_op_source is None
    assert [item["call_id"] for item in payloads] == [call["call_id"] for call in adapter._scene_service_calls]
    assert payloads[0]["request_ros_clock"] == adapter._scene_service_calls[0]["request_ros_clock"]


def test_the_acm_calls_of_the_touch_collision_are_published_too_and_the_rest_is_unchanged(frozen_scene):
    from moveit_msgs.msg import AllowedCollisionMatrix, PlanningScene
    from moveit_msgs.srv import GetPlanningScene

    ctx = Context(frozen_scene)
    ctx.stamp()
    published = []
    stream = stream_of(published)
    adapter, wire = harness(ctx, stream=stream)
    scene = PlanningScene()
    scene.allowed_collision_matrix = AllowedCollisionMatrix()
    adapter._get_scene.respond = lambda request: GetPlanningScene.Response(scene=scene)
    adapter._scene_state_value = "DESCEND"
    adapter._set_touch_collision(True)
    stream.pump()
    payloads = [decode_event(text)["payload"] for text in published]
    assert [item["operation"] for item in payloads] == ["acm_readback", "acm_apply"]
    assert adapter._touch_collision_allowed is True


@pytest.mark.parametrize("mode", ["collection_on", "collection_failing"])
def test_the_teachers_scene_requests_are_byte_identical_with_collection_off_on_and_failing(frozen_scene, mode):
    ctx = Context(frozen_scene)
    ctx.stamp()
    baseline, baseline_wire = harness(ctx)
    drive(baseline)
    ctx.stamp()
    stream = None
    if mode == "collection_on":
        stream = stream_of([])
        binding = None
    else:
        def refuse(text):
            raise RuntimeError("DDS_DOWN")
        stream = TeacherEventStream(StreamIdentity("alignment-session", 1, "alignment-attempt"), clock_ns=lambda: 7,
                                    publish=refuse, start=False)
        binding = SimpleNamespace(physics_adapter=None, observer=None, hazards=[], model_identity={})
    adapter, wire = harness(ctx, stream=stream, binding=binding)
    drive(adapter)
    stream.pump()
    assert wire == baseline_wire, "the Teacher's requests are the same bytes whatever the data side does"
    assert [call["request"] for call in adapter._scene_service_calls] == \
        [call["request"] for call in baseline._scene_service_calls]
    assert adapter._attached is baseline._attached is False
    assert adapter._document["scene_transactions"][-1]["geometry_verification"]["mismatches"] == []


def test_the_first_state_issues_no_scene_call_at_all(frozen_scene, monkeypatch):
    """Where the data side used to apply the initial world association, nothing is sent any more."""
    import rclpy
    from so101_demo.core.domain import ActionStatus
    from test_dynamic_teacher_result import START, _adapter, _sample

    monkeypatch.setattr(rclpy, "spin_once", lambda *args, **kwargs: None)
    adapter = _adapter()
    adapter._apply_scene = SimpleNamespace(call_async=lambda request: pytest.fail("a first-state scene apply"))
    adapter._get_scene = SimpleNamespace(call_async=lambda request: pytest.fail("a first-state scene query"))
    adapter._node = SimpleNamespace(get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=1)))
    start = _sample(START[:3], START[3:], time_s=1.0)
    adapter._snapshot = lambda: start
    adapter._command_gripper = lambda state, target, before=None: None
    assert adapter.perform(State.PREPARE_OPEN_GRIPPER, None).status is ActionStatus.SUCCEEDED


# ---- no data path writes the MoveIt scene --------------------------------------------------------------------

def _functions_building_apply_requests(path):
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for inner in ast.walk(node):
                if (isinstance(inner, ast.Attribute) and isinstance(inner.value, ast.Name)
                        and inner.value.id == "ApplyPlanningScene"):
                    names.add(node.name)
    return names


def test_apply_planning_scene_requests_are_only_built_in_the_teachers_own_scene_states():
    """AST evidence: in the execution, only `_attach`, `_detach_or_sync` and `_set_touch_collision` build an apply.

    (`_sync_collection_world`, the data side's initial world apply, is gone.)"""
    names = _functions_building_apply_requests(SRC / "ros/dynamic_mujoco_execution.py")
    assert names == {"_attach", "_detach_or_sync", "_set_touch_collision"}
    assert not hasattr(RosDynamicMujocoExecution, "_sync_collection_world")
    assert not hasattr(RosDynamicMujocoExecution, "_initial_world_sync_best_effort")


DATA_SIDE_MODULES = ("act/offline/engine.py", "act/offline/sources.py", "act/recorder_scene.py",
                     "act/scene_operation.py", "act/live_physical_audit.py", "act/episode_physical_readback.py",
                     "adapters/act/ros_episode_physics.py", "adapters/act/ros_observation.py",
                     "adapters/act/scene_state.py", "adapters/act/ros_teacher_event_stream.py")


@pytest.mark.parametrize("module", DATA_SIDE_MODULES)
def test_no_data_side_module_creates_a_client_or_sends_an_apply_request(module):
    tree = ast.parse((SRC / module).read_text())
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("create_client", "call_async", "call") and node.func.attr != "call":
                calls.append((node.func.attr, [ast.unparse(arg) for arg in node.args[:2]]))
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "ApplyPlanningScene" and node.attr == "Request"
                and module not in ("act/scene_operation.py", "act/scene_association.py")):
            raise AssertionError(f"{module} builds an ApplyPlanningScene request")
    if module == "act/scene_operation.py":
        assert calls == []
    else:
        assert calls == [], calls


def test_the_scene_operation_decoder_only_reads_apply_messages_it_never_sends_them():
    source = (SRC / "act/scene_operation.py").read_text()
    assert "deserialize_message" in source and "create_client" not in source and "call_async" not in source


# ---- the stream exists before the setup scene, and the setup calls are on it ------------------------------------

def _wired(monkeypatch, tmp_path, *, faults=frozenset()):
    from so101_demo.adapters.act import ros_teacher_event_stream
    from test_dynamic_scene_sync import RecordingTaskScenePort, _observation, _options, _runtime

    events = []
    offered, closed = [], []
    stream = SimpleNamespace(offer=lambda kind, payload=None: offered.append((kind, payload)) or True,
                             close=lambda flush_timeout_s=1.0: closed.append("stream"),
                             snapshot=lambda: {}, attach=None)

    def start(node, session_id, reset_epoch, lease_identity=None, request_id=None):
        events.append("stream.start")
        return stream, lambda: closed.append("publisher"), None

    monkeypatch.setattr(ros_teacher_event_stream, "start_teacher_event_stream", start)
    scene = RecordingTaskScenePort()
    scene.on_service_call = None   # the attribute the real port has
    runtime = _runtime(events, observations=(_observation(simulator_x=-.03, moveit_x=.02),
                                             _observation(simulator_x=-.03), _observation(simulator_x=-.03)),
                       scene=scene, faults=faults)
    created = []
    original_execution = runtime.execution
    runtime.execution = lambda node, *a, **kw: (created.append(kw), original_execution(node, *a, **kw))[1]
    return runtime, events, offered, closed, scene, created, stream, _options(tmp_path)


def test_the_stream_is_started_before_the_first_scene_call_and_handed_to_the_execution(monkeypatch, tmp_path):
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    runtime, events, offered, closed, scene, created, stream, options = _wired(monkeypatch, tmp_path)
    assert run_dynamic_execute(options, _runtime=runtime) == 0
    assert events.index("stream.start") < events.index("task_scene.create") < events.index("task_scene.apply")
    assert created and created[0]["event_stream"] is stream
    assert callable(scene.on_service_call), "the setup scene port publishes its calls"


def test_a_setup_scene_call_is_offered_to_the_stream_as_a_setup_scene_operation(monkeypatch, tmp_path):
    from moveit_msgs.srv import ApplyPlanningScene
    from so101_demo.control.planning_scene.task_scene import make_plain_attach_scene, record_scene_service_call
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    runtime, events, offered, closed, scene, created, stream, options = _wired(monkeypatch, tmp_path)
    run_dynamic_execute(options, _runtime=runtime)
    records = []
    clock = SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=5))
    record_scene_service_call(request=ApplyPlanningScene.Request(scene=make_plain_attach_scene()), phase="APPLY",
                              service="/apply_planning_scene", invoke=lambda: ApplyPlanningScene.Response(success=True),
                              records=records, ros_clock=clock, on_record=scene.on_service_call)
    kind, payload = offered[-1]
    assert kind == "scene_operation" and payload["state"] == "SETUP" and payload["operation"] == "apply"


def test_a_run_that_fails_before_an_execution_exists_still_retires_the_stream(monkeypatch, tmp_path):
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    runtime, events, offered, closed, scene, created, stream, options = _wired(
        monkeypatch, tmp_path, faults=frozenset())
    runtime.reachability_preflight = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("DYNAMIC_PLAN_FAILED"))
    assert run_dynamic_execute(options, _runtime=runtime) == 1
    assert created == [] and closed == ["stream", "publisher"]


def test_the_real_task_scene_port_offers_every_apply_and_read_back_to_its_hook(monkeypatch, frozen_scene):
    import rclpy
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from so101_demo.control.planning_scene.task_scene import RosTaskScenePort

    ctx = Context(frozen_scene)
    ctx.stamp()
    monkeypatch.setattr(rclpy, "spin_until_future_complete", lambda *args, **kwargs: None)
    wire = []

    class FakeNode:
        def create_client(self, kind, name):
            respond = ((lambda request: ApplyPlanningScene.Response(success=True)) if kind is ApplyPlanningScene
                       else (lambda request: GetPlanningScene.Response(scene=ctx.world_scene())))
            return Client(wire, name, respond)

        def get_clock(self):
            return ctx.clock

    port = RosTaskScenePort(FakeNode(), "mujoco", 1.0)
    seen = []
    port.on_service_call = lambda record, request, response: seen.append((record["phase"], type(response).__name__))
    assert port.apply_task_scene(ctx.expected_world).success
    assert port.observe_task_scene(ctx.expected_world, expected_cup_attachment=None).success
    assert seen == [("APPLY", "ApplyPlanningScene_Response"), ("READ_BACK", "GetPlanningScene_Response")]
    port.on_service_call = lambda *a: (_ for _ in ()).throw(RuntimeError("HOOK_BROKE"))
    assert port.apply_task_scene(ctx.expected_world).success, "a failing hook never changes the Teacher's call"


# ---- verify_task_scene: the two audit-only modes ---------------------------------------------------------------

def test_verify_task_scene_world_pose_audit_only_records_the_delta_and_keeps_everything_else_strict(frozen_scene):
    from so101_demo.control.planning_scene.task_scene import verify_task_scene

    ctx = Context(frozen_scene)
    strict = verify_task_scene(ctx.world_scene(0.01), ctx.expected_world)
    assert not strict.success and "plastic_cup.pose" in strict.evidence["mismatches"]
    assert "cup_world_pose_audit" not in strict.evidence
    audited = verify_task_scene(ctx.world_scene(0.01), ctx.expected_world, cup_world_pose_audit_only=True)
    assert audited.success and audited.evidence["cup_world_pose_audit"]["translation_delta_m"] == pytest.approx(0.01)
    gone = ctx.world_scene(0.01)
    gone.world.collision_objects = [item for item in gone.world.collision_objects if item.id != "plastic_cup"]
    result = verify_task_scene(gone, ctx.expected_world, cup_world_pose_audit_only=True)
    assert not result.success and result.evidence["cup_world_pose_audit"]["reason"] == "OBSERVED_CUP_NOT_PRESENT"
    with pytest.raises(ValueError, match="cup_world_pose_audit_only"):
        verify_task_scene(ctx.attached_scene(), ctx.expected_world, expected_cup_attachment="gripper",
                          cup_world_pose_audit_only=True)
