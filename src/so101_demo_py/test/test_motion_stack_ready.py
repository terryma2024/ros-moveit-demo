def test_readiness_reports_all_required_dependencies() -> None:
    from so101_demo.cli.motion_stack_ready import evaluate_readiness

    result = evaluate_readiness(
        controllers={
            "joint_state_broadcaster": "active",
            "arm_controller": "active",
            "gripper_controller": "active",
        },
        services={
            "/apply_planning_scene": True,
            "/get_planning_scene": True,
            "/plan_kinematic_path": True,
        },
        actions={
            "/execute_trajectory": True,
            "/arm_controller/follow_joint_trajectory": True,
            "/gripper_controller/follow_joint_trajectory": True,
        },
    )

    assert result.ready
    assert result.failure_code is None


def test_readiness_reports_first_missing_dependency_by_stable_order() -> None:
    from so101_demo.cli.motion_stack_ready import evaluate_readiness

    result = evaluate_readiness(
        controllers={"joint_state_broadcaster": "inactive"},
        services={},
        actions={},
    )

    assert not result.ready
    assert result.phase == "CONTROLLERS"
    assert result.failure_code == "MOTION_STACK_CONTROLLER_NOT_ACTIVE"
    assert result.evidence["dependency"] == "joint_state_broadcaster"


def test_readiness_reports_moveit_service_before_actions() -> None:
    from so101_demo.cli.motion_stack_ready import evaluate_readiness

    controllers = {
        "joint_state_broadcaster": "active",
        "arm_controller": "active",
        "gripper_controller": "active",
    }
    result = evaluate_readiness(
        controllers=controllers,
        services={"/apply_planning_scene": True, "/get_planning_scene": False},
        actions={},
    )

    assert result.phase == "MOVEIT_SERVICES"
    assert result.failure_code == "MOTION_STACK_MOVEIT_SERVICE_UNAVAILABLE"
    assert result.evidence["dependency"] == "/get_planning_scene"


def test_readiness_reports_missing_motion_action() -> None:
    from so101_demo.cli.motion_stack_ready import evaluate_readiness

    controllers = {
        "joint_state_broadcaster": "active",
        "arm_controller": "active",
        "gripper_controller": "active",
    }
    services = {
        "/apply_planning_scene": True,
        "/get_planning_scene": True,
        "/plan_kinematic_path": True,
    }
    result = evaluate_readiness(
        controllers=controllers,
        services=services,
        actions={"/execute_trajectory": False},
    )

    assert result.phase == "ACTIONS"
    assert result.failure_code == "MOTION_STACK_ACTION_UNAVAILABLE"
    assert result.evidence["dependency"] == "/execute_trajectory"


def test_controller_query_is_not_gated_by_the_moveit_graph() -> None:
    """Direct controller traffic must start as soon as its own service is visible.

    Waiting for the whole MoveIt service/action graph before the first controller query is
    what made the earlier failure unattributable: a station stuck in hardware bring-up and a
    station with missing MoveIt services looked identical.
    """

    from so101_demo.cli.motion_stack_ready import controller_query_allowed

    assert controller_query_allowed(controller_service_visible=True)
    assert not controller_query_allowed(controller_service_visible=False)


def test_readiness_separates_dds_invisibility_from_a_call_timeout() -> None:
    from so101_demo.cli.motion_stack_ready import evaluate_readiness

    invisible = evaluate_readiness(
        controllers={},
        services={},
        actions={},
        controller_service_visible=False,
    )
    timed_out = evaluate_readiness(
        controllers={},
        services={},
        actions={},
        controller_service_visible=True,
        controller_call_timed_out=True,
    )
    not_active = evaluate_readiness(
        controllers={"joint_state_broadcaster": "inactive"},
        services={},
        actions={},
    )

    assert invisible.failure_code == "MOTION_STACK_CONTROLLER_SERVICE_INVISIBLE"
    assert timed_out.failure_code == "MOTION_STACK_CONTROLLER_CALL_TIMEOUT"
    assert not_active.failure_code == "MOTION_STACK_CONTROLLER_NOT_ACTIVE"
    assert len(
        {invisible.failure_code, timed_out.failure_code, not_active.failure_code}
    ) == 3
    assert invisible.phase == timed_out.phase == not_active.phase == "CONTROLLERS"


def test_readiness_ignores_the_call_timeout_once_controllers_answer() -> None:
    from so101_demo.cli.motion_stack_ready import evaluate_readiness

    result = evaluate_readiness(
        controllers={
            "joint_state_broadcaster": "active",
            "arm_controller": "active",
            "gripper_controller": "active",
        },
        services={
            "/apply_planning_scene": True,
            "/get_planning_scene": True,
            "/plan_kinematic_path": True,
        },
        actions={
            "/execute_trajectory": True,
            "/arm_controller/follow_joint_trajectory": True,
            "/gripper_controller/follow_joint_trajectory": True,
        },
        controller_service_visible=True,
        controller_call_timed_out=True,
    )

    assert result.ready
    assert result.failure_code is None


def test_controller_query_keeps_one_pending_request_until_response() -> None:
    from so101_demo.cli.motion_stack_ready import poll_controller_states

    class Future:
        def __init__(self) -> None:
            self.complete = False

        def done(self) -> bool:
            return self.complete

        def result(self):
            controller = type(
                "Controller", (), {"name": "arm_controller", "state": "active"}
            )
            return type("Response", (), {"controller": [controller()]})()

    class Client:
        def __init__(self) -> None:
            self.calls = 0
            self.future = Future()

        def service_is_ready(self) -> bool:
            return True

        def call_async(self, _request):
            self.calls += 1
            return self.future

    client = Client()
    spin_calls = []

    def request_factory():
        return object()

    def spin(*args, **kwargs):
        spin_calls.append((args, kwargs))

    pending, observed = poll_controller_states(
        client,
        None,
        request_factory=request_factory,
        spin_until_future_complete=spin,
        node=object(),
        timeout_s=0.25,
    )
    assert pending is client.future
    assert observed is None
    assert client.calls == 1

    pending, observed = poll_controller_states(
        client,
        pending,
        request_factory=request_factory,
        spin_until_future_complete=spin,
        node=object(),
        timeout_s=0.25,
    )
    assert pending is client.future
    assert observed is None
    assert client.calls == 1

    client.future.complete = True
    pending, observed = poll_controller_states(
        client,
        pending,
        request_factory=request_factory,
        spin_until_future_complete=spin,
        node=object(),
        timeout_s=0.25,
    )
    assert pending is None
    assert observed == {"arm_controller": "active"}
    assert client.calls == 1
    assert len(spin_calls) == 3
