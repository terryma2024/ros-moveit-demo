"""A Task 8 stack needs one bounded, coherent pre-reset readback."""

from copy import deepcopy

from so101_demo.cli.act_stack_ready import evaluate_act_stack_readiness


NOW = 100.0


def observations():
    return {
        "session_id": "session-283", "ros_domain_id": 230, "now_s": NOW,
        "worlds": (
            {"session_id": "session-283", "reset_epoch": 0, "step": 100,
             "sim_time_s": 10.0, "paused": False, "received_s": NOW - 0.10},
            {"session_id": "session-283", "reset_epoch": 0, "step": 125,
             "sim_time_s": 10.05, "paused": False, "received_s": NOW - 0.01},
        ),
        "joints": tuple({"stamp_s": 10.0 + n * 0.02,
                         "received_s": NOW - 0.06 + n * 0.02,
                         "velocity": (0.0,) * 7} for n in range(3)),
        "rgb": {stream: {"stamp_s": 10.04, "received_s": NOW - 0.02,
                         "width": 640, "height": 480, "encoding": "rgb8",
                         "step": 1920, "byte_count": 640 * 480 * 3}
                for stream in ("head", "wrist")},
        "controllers": {name: "active" for name in (
            "joint_state_broadcaster", "arm_controller", "gripper_controller",
            "neck_controller",
        )},
        "services": {name: True for name in (
            "/apply_planning_scene", "/get_planning_scene", "/plan_kinematic_path",
        )},
        "actions": {name: True for name in (
            "/execute_trajectory", "/arm_controller/follow_joint_trajectory",
            "/gripper_controller/follow_joint_trajectory",
            "/neck_controller/follow_joint_trajectory",
        )},
    }


def test_coherent_stack_observation_emits_consumer_schema():
    result = evaluate_act_stack_readiness(**observations())
    assert result.ready is True
    assert result.failure_code is None
    assert result.artifact == {
        "schema_version": 1, "session_id": "session-283", "ros_domain_id": 230,
        "captured_monotonic_ns": 100_000_000_000,
        "checks": {key: True for key in (
            "mujoco_session", "advancing_physics", "controller_states",
            "moveit_graph", "physical_stop", "head_rgb", "wrist_rgb",
        )},
    }


def test_foreign_session_and_stalled_physics_never_become_ready():
    value = deepcopy(observations())
    value["worlds"][-1]["session_id"] = "other-session"
    assert evaluate_act_stack_readiness(**value).failure_code == "ACT_STACK_WORLD_SESSION_INVALID"
    value = deepcopy(observations())
    value["worlds"][-1]["step"] = value["worlds"][0]["step"]
    assert evaluate_act_stack_readiness(**value).failure_code == "ACT_STACK_PHYSICS_NOT_ADVANCING"


def test_moving_or_stale_seven_joint_feedback_does_not_prove_stop():
    value = deepcopy(observations())
    value["joints"][1]["velocity"] = (0.0, 0.0, 0.0, 0.02, 0.0, 0.0, 0.0)
    assert evaluate_act_stack_readiness(**value).failure_code == "ACT_STACK_NOT_PHYSICALLY_STOPPED"
    value = deepcopy(observations())
    value["joints"][-1]["received_s"] = NOW - 1.0
    assert evaluate_act_stack_readiness(**value).failure_code == "ACT_STACK_JOINTS_STALE"
    value = deepcopy(observations())
    value["joints"][-1]["stamp_s"] = 8.0
    assert evaluate_act_stack_readiness(**value).failure_code == "ACT_STACK_NOT_PHYSICALLY_STOPPED"


def test_stale_or_malformed_rgb_is_rejected_per_stream():
    value = deepcopy(observations())
    value["rgb"]["head"]["stamp_s"] = 8.0
    assert evaluate_act_stack_readiness(**value).failure_code == "ACT_STACK_HEAD_RGB_STALE"
    value = deepcopy(observations())
    value["rgb"]["wrist"]["byte_count"] -= 1
    assert evaluate_act_stack_readiness(**value).failure_code == "ACT_STACK_WRIST_RGB_INVALID"


def test_neck_controller_and_action_are_required():
    value = deepcopy(observations())
    value["controllers"]["neck_controller"] = "inactive"
    assert evaluate_act_stack_readiness(**value).failure_code == "ACT_STACK_CONTROLLER_NOT_ACTIVE"
    value = deepcopy(observations())
    value["actions"]["/neck_controller/follow_joint_trajectory"] = False
    assert evaluate_act_stack_readiness(**value).failure_code == "ACT_STACK_GRAPH_INCOMPLETE"


def test_controller_query_settles_once_then_stays_idle():
    from so101_demo.cli.act_stack_ready import advance_controller_query

    class Future:
        def done(self):
            return True

        def result(self):
            controller = [type("State", (), {"name": name, "state": "active"})()
                          for name in observations()["controllers"]]
            return type("Response", (), {"controller": controller})()

    class Client:
        calls = 0

        def service_is_ready(self):
            return True

        def call_async(self, _request):
            self.calls += 1
            return Future()

    client = Client()
    pending, states, next_query = advance_controller_query(
        client, None, {}, now_s=1.0, next_query_s=0.0,
        request_factory=lambda: object(),
    )
    assert pending is not None and client.calls == 1
    pending, states, next_query = advance_controller_query(
        client, pending, states, now_s=1.1, next_query_s=next_query,
        request_factory=lambda: object(),
    )
    assert pending is None and all(state == "active" for state in states.values())
    pending, states, _ = advance_controller_query(
        client, pending, states, now_s=2.0, next_query_s=next_query,
        request_factory=lambda: object(),
    )
    assert pending is None and client.calls == 1
