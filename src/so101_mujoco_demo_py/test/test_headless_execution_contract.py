from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from launch.actions import DeclareLaunchArgument, OpaqueFunction

from so101_mujoco_demo_py.headless_execution import (
    CONTROLLER_MAPPING,
    assert_headless_summary,
    strip_ros_arguments,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
LAUNCH_FILE = PACKAGE_ROOT / "launch/so101_pick_place.launch.py"


def load_launch_module():
    spec = importlib.util.spec_from_file_location("so101_pick_place_launch", LAUNCH_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def launch_arguments(description):
    return {
        action.name: action
        for action in description.entities
        if isinstance(action, DeclareLaunchArgument)
    }


def default_text(argument: DeclareLaunchArgument) -> str:
    return argument.default_value[0].text


def test_launch_defaults_are_headless_planning_only_and_execution_is_opt_in() -> None:
    module = load_launch_module()
    description = module.generate_launch_description()
    arguments = launch_arguments(description)

    assert default_text(arguments["run_mode"]) == "dry_run"
    assert default_text(arguments["execute"]) == "false"
    assert default_text(arguments["headless"]) == "true"
    assert default_text(arguments["start_simulation"]) == "true"
    assert default_text(arguments["safe_pose"]) == "task12_safe"
    assert sum(isinstance(action, OpaqueFunction) for action in description.entities) == 1


def test_ros_launch_arguments_do_not_enter_the_application_parser() -> None:
    assert strip_ros_arguments(
        [
            "--run-mode",
            "dry_run",
            "--evidence-file",
            "/tmp/result.json",
            "--ros-args",
            "--params-file",
            "/tmp/launch-params",
        ]
    ) == ["--run-mode", "dry_run", "--evidence-file", "/tmp/result.json"]


def test_launch_composes_every_headless_runtime_boundary_and_shutdown_owner() -> None:
    module = load_launch_module()
    composition = module.compose_launch(
        PACKAGE_ROOT,
        run_mode="dry_run",
        execute=False,
        headless=True,
        start_simulation=True,
        simulation_session_id="contract-session",
        evidence_file="/tmp/so101-headless-contract.json",
        safe_pose="task12_safe",
        readiness_timeout_s=30.0,
    )

    assert composition.node_executables == {
        ("mujoco_ros2_control", "ros2_control_node"),
        ("robot_state_publisher", "robot_state_publisher"),
        ("controller_manager", "spawner"),
        ("moveit_ros_move_group", "move_group"),
        ("so101_mujoco_demo_py", "headless_execution"),
    }
    assert composition.controller_spawners == {
        "joint_state_broadcaster",
        "arm_controller",
        "gripper_controller",
    }
    assert composition.includes_robot_description
    assert composition.includes_planning_scene
    assert composition.includes_observer
    assert composition.includes_reset_services
    assert composition.includes_workflow
    assert composition.shutdown_on_workflow_exit


def test_move_group_receives_frozen_joint_dynamics_limits() -> None:
    module = load_launch_module()

    parameters = module.moveit_parameters(PACKAGE_ROOT, "<robot name='so101'/>")

    assert parameters["robot_description_planning"] == {
        "default_velocity_scaling_factor": 0.1,
        "default_acceleration_scaling_factor": 0.1,
        "joint_limits": {
            "1": {
                "has_velocity_limits": True,
                "max_velocity": 10.0,
                "has_acceleration_limits": True,
                "max_acceleration": 5.0,
            },
            "2": {
                "has_velocity_limits": True,
                "max_velocity": 10.0,
                "has_acceleration_limits": True,
                "max_acceleration": 5.0,
            },
            "3": {
                "has_velocity_limits": True,
                "max_velocity": 10.0,
                "has_acceleration_limits": True,
                "max_acceleration": 5.0,
            },
            "4": {
                "has_velocity_limits": True,
                "max_velocity": 10.0,
                "has_acceleration_limits": True,
                "max_acceleration": 5.0,
            },
            "5": {
                "has_velocity_limits": True,
                "max_velocity": 10.0,
                "has_acceleration_limits": True,
                "max_acceleration": 5.0,
            },
            "6": {
                "has_velocity_limits": True,
                "max_velocity": 10.0,
                "has_acceleration_limits": True,
                "max_acceleration": 5.0,
            },
        },
    }


def controller_response(states: dict[str, str]) -> SimpleNamespace:
    return SimpleNamespace(
        controller=[SimpleNamespace(name=name, state=state) for name, state in states.items()]
    )


def test_controller_readiness_waits_for_concurrent_spawners(monkeypatch) -> None:
    module = __import__("so101_mujoco_demo_py.headless_execution", fromlist=["headless_execution"])
    responses = iter(
        [
            controller_response(
                {
                    "arm_controller": "active",
                    "joint_state_broadcaster": "active",
                }
            ),
            controller_response(
                {
                    "arm_controller": "active",
                    "gripper_controller": "active",
                    "joint_state_broadcaster": "active",
                }
            ),
        ]
    )
    calls = []
    monkeypatch.setattr(
        module,
        "_service_result",
        lambda node, client, request, deadline: calls.append(deadline) or next(responses),
    )
    monkeypatch.setattr(module.time, "monotonic", lambda: 0.0)

    states = module._wait_for_active_controllers(
        object(), SimpleNamespace(srv_name="/controller_manager/list_controllers"), object(), 10.0
    )

    assert states == {name: "active" for name in CONTROLLER_MAPPING}
    assert calls == [10.0, 10.0]


def test_controller_readiness_times_out_when_required_controller_never_activates(
    monkeypatch,
) -> None:
    module = __import__("so101_mujoco_demo_py.headless_execution", fromlist=["headless_execution"])
    monkeypatch.setattr(
        module,
        "_service_result",
        lambda node, client, request, deadline: controller_response(
            {
                "arm_controller": "active",
                "joint_state_broadcaster": "active",
            }
        ),
    )
    clock = iter([0.0, 0.5, 1.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))

    with pytest.raises(RuntimeError, match="controller readiness timeout"):
        module._wait_for_active_controllers(
            object(),
            SimpleNamespace(srv_name="/controller_manager/list_controllers"),
            object(),
            1.0,
        )


def test_controller_readiness_rejects_unexpected_required_controller_state(
    monkeypatch,
) -> None:
    module = __import__("so101_mujoco_demo_py.headless_execution", fromlist=["headless_execution"])
    responses = iter(
        [
            controller_response(
                {
                    "arm_controller": "inactive",
                    "gripper_controller": "active",
                    "joint_state_broadcaster": "active",
                }
            ),
            controller_response(
                {
                    "arm_controller": "active",
                    "gripper_controller": "active",
                    "joint_state_broadcaster": "active",
                }
            ),
        ]
    )
    calls = []
    monkeypatch.setattr(
        module,
        "_service_result",
        lambda node, client, request, deadline: calls.append(deadline) or next(responses),
    )
    monkeypatch.setattr(module.time, "monotonic", lambda: 0.0)

    states = module._wait_for_active_controllers(
        object(), SimpleNamespace(srv_name="/controller_manager/list_controllers"), object(), 10.0
    )

    assert states == {name: "active" for name in CONTROLLER_MAPPING}
    assert calls == [10.0, 10.0]


class FrozenPlanWorld:
    def __init__(self, *, initially_paused: bool = False) -> None:
        self.paused = initially_paused
        self.events: list[object] = []

    def pause(self, paused: bool) -> bool:
        self.events.append(("pause", paused))
        self.paused = paused
        return True

    def observe(self):
        self.events.append(("observe", self.paused))
        return SimpleNamespace(paused=self.paused) if self.paused else None

    def progress(self) -> None:
        self.events.append("progress")

    def capture(self) -> tuple[float, ...]:
        self.events.append(("capture", self.paused))
        return (0.25, 0.5)

    def plan(self, positions: tuple[float, ...]) -> str:
        self.events.append(("plan", positions, self.paused))
        return "trajectory"

    def execute(self, trajectory: str) -> str:
        self.events.append(("execute", trajectory, self.paused))
        return "succeeded"


def run_motion_boundary(world: FrozenPlanWorld, *, execute: bool = True):
    module = __import__("so101_mujoco_demo_py.headless_execution", fromlist=["headless_execution"])
    return module._run_motion_boundary(
        execute=execute,
        pause_world=world.pause,
        observe_evidence=world.observe,
        capture_start=world.capture,
        plan=world.plan,
        execute_trajectory=world.execute,
        progress=world.progress,
        monotonic=lambda: 0.0,
        deadline=10.0,
    )


def test_execute_freezes_and_authoritatively_observes_before_planning_then_resumes() -> None:
    world = FrozenPlanWorld()

    result = run_motion_boundary(world)

    assert result == ((0.25, 0.5), "trajectory", "succeeded")
    assert world.events == [
        ("pause", True),
        ("observe", True),
        ("capture", True),
        ("plan", (0.25, 0.5), True),
        ("pause", False),
        ("execute", "trajectory", False),
    ]
    assert world.paused is False


def test_execute_accepts_idempotent_pause_when_world_is_already_paused() -> None:
    world = FrozenPlanWorld(initially_paused=True)

    run_motion_boundary(world)

    assert world.events[:3] == [
        ("pause", True),
        ("observe", True),
        ("capture", True),
    ]
    assert world.paused is False


def test_execute_waits_for_authoritative_paused_observation_before_capture() -> None:
    world = FrozenPlanWorld()
    observations = iter([SimpleNamespace(paused=False), SimpleNamespace(paused=True)])

    def observe():
        evidence = next(observations)
        world.events.append(("observed_evidence", evidence.paused))
        return evidence

    world.observe = observe

    run_motion_boundary(world)

    assert world.events[:6] == [
        ("pause", True),
        ("observed_evidence", False),
        "progress",
        ("observed_evidence", True),
        ("capture", True),
        ("plan", (0.25, 0.5), True),
    ]


def test_planning_failure_resumes_world_and_never_executes() -> None:
    world = FrozenPlanWorld()

    def reject_plan(positions: tuple[float, ...]) -> str:
        world.events.append(("plan_rejected", positions, world.paused))
        raise RuntimeError("planning failed")

    world.plan = reject_plan

    with pytest.raises(RuntimeError, match="planning failed"):
        run_motion_boundary(world)

    assert world.events == [
        ("pause", True),
        ("observe", True),
        ("capture", True),
        ("plan_rejected", (0.25, 0.5), True),
        ("pause", False),
    ]
    assert world.paused is False


def test_execute_rejection_keeps_world_running_after_immediate_handoff() -> None:
    world = FrozenPlanWorld()

    def reject_execution(trajectory: str) -> str:
        world.events.append(("execute_rejected", trajectory, world.paused))
        raise RuntimeError("execution failed")

    world.execute = reject_execution

    with pytest.raises(RuntimeError, match="execution failed"):
        run_motion_boundary(world)

    assert world.events[-2:] == [
        ("pause", False),
        ("execute_rejected", "trajectory", False),
    ]
    assert world.paused is False


def test_dry_run_keeps_proven_running_planning_behavior_without_pause_or_execution() -> None:
    world = FrozenPlanWorld()

    result = run_motion_boundary(world, execute=False)

    assert result == ((0.25, 0.5), "trajectory", None)
    assert world.events == [
        ("capture", False),
        ("plan", (0.25, 0.5), False),
    ]
    assert world.paused is False


def valid_summary(mode: str) -> dict:
    execute = mode == "execute"
    return {
        "schema_version": 1,
        "run_mode": mode,
        "execution_requested": execute,
        "planning_group": "arm",
        "tcp_link": "so101_tcp",
        "safe_pose": "task12_safe",
        "ready": {
            "nodes": [
                "/controller_manager",
                "/move_group",
                "/robot_state_publisher",
                "/so101_headless_execution",
            ],
            "topics": [
                "/joint_states",
                "/monitored_planning_scene",
                "/so101/simulation/evidence",
                "/tf",
                "/tf_static",
            ],
            "services": [
                "/get_planning_scene",
                "/mujoco_ros2_control_node/reset_world",
                "/mujoco_ros2_control_node/set_pause",
                "/plan_kinematic_path",
            ],
            "actions": [
                "/arm_controller/follow_joint_trajectory",
                "/execute_trajectory",
            ],
            "controllers": {
                "arm_controller": ["1", "2", "3", "4", "5"],
                "gripper_controller": ["6"],
                "joint_state_broadcaster": [],
            },
            "tf_world_to_tcp": True,
            "moveit_planning_group": "arm",
        },
        "plan": {"accepted": True, "trajectory_points": 4},
        "execution": {
            "goal_sent": execute,
            "succeeded": execute,
            "controller_result": "SUCCEEDED" if execute else "NOT_REQUESTED",
        },
        "joint_state": {
            "converged": execute,
            "maximum_target_error_rad": 0.001 if execute else None,
            "maximum_motion_rad": 0.2 if execute else 0.0,
        },
        "mujoco": {
            "session_id": "contract-session",
            "publisher_sequence_delta": 30 if execute else 2,
            "simulation_step_delta": 30 if execute else 2,
            "reset_epoch_before": 0,
            "reset_epoch_after": 0,
        },
        "shutdown": {"launch_exit_code": 0, "domain_nodes_after": []},
    }


@pytest.mark.parametrize("mode", ["dry_run", "execute"])
def test_real_evidence_summary_proves_the_mode_specific_contract(mode: str) -> None:
    assert_headless_summary(valid_summary(mode), expected_mode=mode)


def test_dry_run_rejects_any_controller_execution() -> None:
    summary = valid_summary("dry_run")
    summary["execution"]["goal_sent"] = True
    with pytest.raises(AssertionError, match="dry_run sent an execution goal"):
        assert_headless_summary(summary, expected_mode="dry_run")


def test_execute_rejects_missing_joint_movement() -> None:
    summary = valid_summary("execute")
    summary["joint_state"]["maximum_motion_rad"] = 0.0
    with pytest.raises(AssertionError, match="joint movement"):
        assert_headless_summary(summary, expected_mode="execute")


def test_execute_rejects_missing_mujoco_movement() -> None:
    summary = valid_summary("execute")
    summary["mujoco"]["simulation_step_delta"] = 0
    with pytest.raises(AssertionError):
        assert_headless_summary(summary, expected_mode="execute")


@pytest.mark.skipif(
    not os.environ.get("SO101_MUJOCO_HEADLESS_SUMMARY"),
    reason="set after a fresh task-owned headless launch",
)
def test_fresh_live_headless_summary() -> None:
    summary_path = Path(os.environ["SO101_MUJOCO_HEADLESS_SUMMARY"])
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert_headless_summary(summary, expected_mode=os.environ["SO101_MUJOCO_HEADLESS_MODE"])
