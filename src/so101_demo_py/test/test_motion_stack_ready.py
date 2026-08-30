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
