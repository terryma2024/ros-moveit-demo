from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    ExecuteProcess,
    OpaqueFunction,
    RegisterEventHandler,
)
from launch.events import Shutdown as ShutdownEvent
from launch.events.process import ProcessExited
from launch.utilities import perform_substitutions
from launch_ros.actions import Node
from launch_ros.utilities import evaluate_parameters
from so101_demo.runtime import launch_composition
from so101_demo.profiling import launch_support as profiling_launch_support
from so101_demo.profiling.system_trace import (
    RequiredSystemTraceUnavailable,
    SystemTraceResult,
)
from so101_demo.runtime.provenance import InstalledExecutionIdentity

from launch import LaunchContext


PACKAGE_ROOT = Path(__file__).parents[1]
LAUNCH_PATH = PACKAGE_ROOT / "launch/so101_mujoco_text_pick_agent.launch.py"
INSTRUCTION = "Pick the plastic cup. Apply no constraints."


def _builder():
    assert hasattr(launch_composition, "build_text_pick_agent_launch_description"), (
        "dedicated text-agent launch builder is missing"
    )
    return launch_composition.build_text_pick_agent_launch_description


def _declared(description) -> dict[str, DeclareLaunchArgument]:
    return {
        action.name: action
        for action in description.entities
        if isinstance(action, DeclareLaunchArgument)
    }


def _default(argument: DeclareLaunchArgument) -> str:
    return perform_substitutions(LaunchContext(), argument.default_value)


def _materialize(monkeypatch, tmp_path: Path, **overrides):
    monkeypatch.setattr(
        launch_composition,
        "resolve_installed_execution_identity",
        lambda: InstalledExecutionIdentity(
            source_commit="a" * 40,
            package_prefix="/tmp/so101-text-agent-install",
        ),
    )
    exit_status = launch_composition.PerceptionLaunchExitStatus()
    description = _builder()(exit_status)
    declared = _declared(description)
    context = LaunchContext()
    for name, argument in declared.items():
        if argument.default_value is not None:
            context.launch_configurations[name] = perform_substitutions(
                context, argument.default_value
            )
    context.launch_configurations.update(
        {
            "instruction": INSTRUCTION,
            "run_mode": "execute",
            "execute": "true",
            "skip_confirmation": "true",
            "session_id": "text-e2e-session-001",
            "evidence_file": str(tmp_path / "run.json"),
            **{key: str(value) for key, value in overrides.items()},
        }
    )
    opaque = next(entity for entity in description.entities if isinstance(entity, OpaqueFunction))
    return context, opaque.execute(context), exit_status


def _nodes(actions) -> list[Node]:
    return [action for action in actions if isinstance(action, Node)]


def _node(actions, executable: str) -> Node:
    matches = [node for node in _nodes(actions) if node.node_executable == executable]
    assert len(matches) == 1, (executable, [node.node_executable for node in _nodes(actions)])
    return matches[0]


def _plain_process(actions) -> ExecuteProcess:
    matches = [
        action
        for action in actions
        if isinstance(action, ExecuteProcess) and not isinstance(action, Node)
    ]
    assert len(matches) == 1
    return matches[0]


def _plain_process_command(process: ExecuteProcess, context: LaunchContext) -> list[str]:
    return [perform_substitutions(context, part) for part in process.cmd]


def _dispatch_process_exit(actions, target, returncode: int, context: LaunchContext):
    executable = getattr(target, "node_executable", "text_pick_agent")
    event = ProcessExited(
        action=target,
        name=str(executable),
        cmd=[str(executable)],
        cwd=None,
        env=None,
        pid=101,
        returncode=returncode,
    )
    emitted = []
    for registration in actions:
        if not isinstance(registration, RegisterEventHandler):
            continue
        handler = registration.event_handler
        if handler.matches(event):
            emitted.extend(handler.handle(event, context) or [])
    return emitted


def _shutdown_reasons(actions) -> list[str]:
    return [
        action.event.reason
        for action in actions
        if isinstance(action, EmitEvent) and isinstance(action.event, ShutdownEvent)
    ]


def _assert_failure_status(actions, context: LaunchContext, pattern: str) -> None:
    failure_actions = [action for action in actions if isinstance(action, OpaqueFunction)]
    assert len(failure_actions) == 1
    with pytest.raises(RuntimeError, match=pattern):
        failure_actions[0].execute(context)


def test_public_text_agent_launch_is_thin_and_declares_contract() -> None:
    description = _builder()()
    declared = _declared(description)

    assert set(declared) == {
        "instruction",
        "run_mode",
        "execute",
        "skip_confirmation",
        "headless",
        "sensor_rendering",
        "session_id",
        "evidence_file",
        "readiness_timeout_s",
        "mujoco_scene",
        "mujoco_initial_keyframe",
        "perception_startup_timeout_s",
        "cup_pose_timeout_s",
        "profiling",
        "profiling_output_root",
        "profiling_require_system_trace",
    }
    assert declared["instruction"].default_value is None
    assert _default(declared["run_mode"]) == "dry_run"
    assert _default(declared["execute"]) == "false"
    assert _default(declared["skip_confirmation"]) == "false"
    assert _default(declared["headless"]) == "false"
    assert _default(declared["sensor_rendering"]) == "true"
    assert _default(declared["mujoco_initial_keyframe"]) == "task_start"
    assert _default(declared["perception_startup_timeout_s"]) == "30.0"
    assert _default(declared["cup_pose_timeout_s"]) == "45.0"
    assert _default(declared["profiling"]) == "off"
    assert _default(declared["profiling_output_root"]) == ""
    assert _default(declared["profiling_require_system_trace"]) == "false"

    assert LAUNCH_PATH.is_file()
    source = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "DeclareLaunchArgument" not in source
    assert "build_text_pick_agent_launch_description" in source
    spec = importlib.util.spec_from_file_location("text_agent_launch", LAUNCH_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.generate_launch_description() is not None


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"instruction": ""}, "instruction"),
        ({"run_mode": "dry_run"}, "run_mode=execute"),
        ({"execute": "false"}, "execute:=true"),
        ({"skip_confirmation": "false"}, "skip_confirmation:=true"),
        ({"sensor_rendering": "false"}, "sensor_rendering=true"),
        ({"headless": "sometimes"}, "headless"),
        ({"mujoco_initial_keyframe": "unknown"}, "initial keyframe"),
        ({"readiness_timeout_s": "0"}, "readiness_timeout_s"),
        ({"perception_startup_timeout_s": math.inf}, "perception_startup_timeout_s"),
        ({"cup_pose_timeout_s": "nan"}, "cup_pose_timeout_s"),
        ({"session_id": "../escape"}, "session_id"),
        ({"evidence_file": "relative.json"}, "evidence_file"),
        ({"mujoco_scene": "relative.xml"}, "mujoco_scene"),
        ({"profiling": "enabled"}, "profiling"),
        ({"profiling": "trace", "profiling_output_root": "relative"}, "absolute"),
        (
            {"profiling": "trace", "profiling_require_system_trace": "yes"},
            "profiling_require_system_trace",
        ),
    ),
)
def test_invalid_text_agent_inputs_fail_before_nodes_or_evidence(
    tmp_path: Path,
    monkeypatch,
    overrides: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        _materialize(monkeypatch, tmp_path, **overrides)
    assert not (tmp_path / "run.d").exists()


def test_valid_preflight_creates_exclusive_session_evidence_directories(
    tmp_path: Path, monkeypatch
) -> None:
    _context, actions, _exit_status = _materialize(monkeypatch, tmp_path)

    run_root = tmp_path / "run.d/text-e2e-session-001"
    assert run_root.is_dir()
    assert run_root.stat().st_mode & 0o777 == 0o700
    assert (run_root / "perception").is_dir()
    assert (run_root / "dynamic").is_dir()
    assert not (run_root / "profiling").exists()
    assert isinstance(actions, list)


def test_text_agent_uses_plain_process_without_ros_cli_arguments(
    tmp_path: Path, monkeypatch
) -> None:
    context, actions, _exit_status = _materialize(monkeypatch, tmp_path)
    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)

    command = _plain_process_command(_plain_process(started), context)
    assert command[0] == "/tmp/so101-text-agent-install/lib/so101_demo_py/text_pick_agent"
    assert "--ros-args" not in command


def test_scene_success_starts_only_rgbd_and_text_agent_with_exact_args(
    tmp_path: Path, monkeypatch
) -> None:
    context, actions, _exit_status = _materialize(monkeypatch, tmp_path)
    initial_executables = [node.node_executable for node in _nodes(actions)]

    assert initial_executables[:2] == [
        "static_transform_publisher",
        "static_transform_publisher",
    ]
    assert "scene_setup" in initial_executables
    assert "rgbd_cup_pose" not in initial_executables
    assert "text_pick_agent" not in initial_executables
    assert "dynamic_cup_pick_place" not in initial_executables

    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)
    assert [node.node_executable for node in _nodes(started)] == ["rgbd_cup_pose"]

    perception = _node(started, "rgbd_cup_pose")
    assert perception._Node__arguments == [
        "--startup-timeout-s",
        "30.0",
        "--output-topic",
        "/cup_pose",
        "--output-ply",
        str(tmp_path / "run.d/text-e2e-session-001/perception/cup.ply"),
        "--evidence-json",
        str(tmp_path / "run.d/text-e2e-session-001/perception/summary.json"),
    ]
    assert evaluate_parameters(context, perception._Node__parameters) == (
        {"use_sim_time": True},
    )

    workflow = _plain_process(started)
    assert _plain_process_command(workflow, context)[1:] == [
        "--instruction",
        INSTRUCTION,
        "--mode",
        "execute",
        "--execute",
        "--skip-confirmation",
        "--backend",
        "mujoco",
        "--cup-pose-timeout-s",
        "45.0",
        "--session-id",
        "text-e2e-session-001",
        "--expected-reset-epoch",
        "0",
        "--evidence-root",
        str(tmp_path / "run.d/text-e2e-session-001/dynamic"),
        "--source-commit",
        "a" * 40,
        "--installed-prefix",
        "/tmp/so101-text-agent-install",
    ]

    all_executables = initial_executables + [
        node.node_executable for node in _nodes(started)
    ] + [Path(_plain_process_command(workflow, context)[0]).name]
    assert all_executables.count("rgbd_cup_pose") == 1
    assert all_executables.count("text_pick_agent") == 1
    assert "dynamic_cup_pick_place" not in all_executables
    assert "cup_pose_tf_demo" not in all_executables
    assert "mujoco_cup_pose_bridge" not in all_executables


def test_enabled_trace_passes_correlated_child_arguments_and_finalizes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context, actions, _exit_status = _materialize(
        monkeypatch,
        tmp_path,
        profiling="trace",
    )
    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)
    profiling_root = tmp_path / "run.d/text-e2e-session-001/profiling"
    common = [
        "--profiling",
        "trace",
        "--profiling-output-root",
        str(profiling_root),
        "--profiling-session-id",
        "text-e2e-session-001",
    ]

    perception = _node(started, "rgbd_cup_pose")
    assert perception._Node__arguments[-6:] == common
    workflow = _plain_process(started)
    assert _plain_process_command(workflow, context)[-6:] == common

    _dispatch_process_exit(actions, workflow, 0, context)
    _dispatch_process_exit(actions, perception, -15, context)

    assert (profiling_root / "manifest.json").is_file()
    assert (profiling_root / "summary.json").is_file()
    assert (profiling_root / "trace.json").is_file()


def test_linux_trace_action_precedes_application_actions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    trace_action = object()
    monkeypatch.setattr(profiling_launch_support.sys, "platform", "linux")
    monkeypatch.setattr(
        profiling_launch_support,
        "build_system_trace",
        lambda **kwargs: SystemTraceResult(
            "ready",
            trace_action,
            "ros2_tracing",
            kwargs["profiling_root"]
            / "ros2-tracing"
            / f"so101-{kwargs['session_id']}",
        ),
    )

    _context, actions, _exit_status = _materialize(
        monkeypatch,
        tmp_path,
        profiling="trace",
        profiling_require_system_trace="true",
    )

    assert actions[0] is trace_action
    assert actions.index(trace_action) < actions.index(_node(actions, "scene_setup"))


def test_required_linux_trace_failure_precedes_owned_process_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(profiling_launch_support.sys, "platform", "linux")

    def unavailable(**_kwargs):
        raise RequiredSystemTraceUnavailable("required ros2_tracing unavailable")

    monkeypatch.setattr(
        profiling_launch_support,
        "build_system_trace",
        unavailable,
    )

    with pytest.raises(RequiredSystemTraceUnavailable):
        _materialize(
            monkeypatch,
            tmp_path,
            profiling="trace",
            profiling_require_system_trace="true",
        )

    run_root = tmp_path / "run.d/text-e2e-session-001"
    assert not (run_root / "perception").exists()
    assert not (run_root / "dynamic").exists()


def test_scene_failure_starts_no_sensor_or_text_agent_and_fails_launch(
    tmp_path: Path, monkeypatch
) -> None:
    context, actions, _exit_status = _materialize(monkeypatch, tmp_path)

    emitted = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 12, context)

    assert _nodes(emitted) == []
    assert _shutdown_reasons(emitted) == [
        "SO-101 Planning Scene setup failed with exit code 12"
    ]
    _assert_failure_status(emitted, context, "exit code 12")


@pytest.mark.parametrize("returncode", (0, 9))
def test_rgbd_exit_before_text_agent_completion_is_terminal(
    tmp_path: Path, monkeypatch, returncode: int
) -> None:
    context, actions, _exit_status = _materialize(monkeypatch, tmp_path)
    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)

    emitted = _dispatch_process_exit(
        actions, _node(started, "rgbd_cup_pose"), returncode, context
    )

    assert _shutdown_reasons(emitted) == [
        f"RGB-D perception exited before dynamic workflow completed with exit code {returncode}"
    ]
    _assert_failure_status(emitted, context, f"exit code {returncode}")


def test_clean_text_agent_exit_owns_shutdown_and_suppresses_teardown(
    tmp_path: Path, monkeypatch
) -> None:
    context, actions, exit_status = _materialize(monkeypatch, tmp_path)
    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)
    workflow = _plain_process(started)
    perception = _node(started, "rgbd_cup_pose")

    workflow_emitted = _dispatch_process_exit(actions, workflow, 0, context)
    perception_emitted = _dispatch_process_exit(actions, perception, -15, context)

    assert _shutdown_reasons(workflow_emitted) == [
        "Text Agent RGB-D workflow completed with exit code 0"
    ]
    assert not [
        action for action in workflow_emitted if isinstance(action, OpaqueFunction)
    ]
    assert perception_emitted == []
    assert exit_status.returncode == 0


def test_failed_text_agent_exit_preserves_failure_and_suppresses_teardown(
    tmp_path: Path, monkeypatch
) -> None:
    context, actions, exit_status = _materialize(monkeypatch, tmp_path)
    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)
    workflow = _plain_process(started)
    perception = _node(started, "rgbd_cup_pose")

    workflow_emitted = _dispatch_process_exit(actions, workflow, 23, context)
    perception_emitted = _dispatch_process_exit(actions, perception, -15, context)

    assert _shutdown_reasons(workflow_emitted) == [
        "Text Agent RGB-D workflow failed with exit code 23"
    ]
    _assert_failure_status(workflow_emitted, context, "exit code 23")
    assert perception_emitted == []
    assert exit_status.returncode == 23


@pytest.mark.parametrize(
    ("executable", "label"),
    (
        ("ros2_control_node", "MuJoCo runtime"),
        ("robot_state_publisher", "robot_state_publisher"),
        ("graceful_shutdown_move_group", "MoveIt move_group"),
        ("static_transform_publisher", "camera static TF"),
    ),
)
def test_required_long_lived_exit_before_text_agent_is_terminal(
    tmp_path: Path,
    monkeypatch,
    executable: str,
    label: str,
) -> None:
    context, actions, exit_status = _materialize(monkeypatch, tmp_path)
    target = next(node for node in _nodes(actions) if node.node_executable == executable)

    emitted = _dispatch_process_exit(actions, target, 17, context)

    assert exit_status.returncode == 17
    assert any(label in reason for reason in _shutdown_reasons(emitted))
    _assert_failure_status(emitted, context, "exit code 17")


@pytest.mark.parametrize("spawner_index", range(3))
@pytest.mark.parametrize("returncode", (0, 19))
def test_text_agent_controller_spawner_exit_policy(
    tmp_path: Path,
    monkeypatch,
    spawner_index: int,
    returncode: int,
) -> None:
    context, actions, exit_status = _materialize(monkeypatch, tmp_path)
    spawners = [node for node in _nodes(actions) if node.node_executable == "spawner"]

    emitted = _dispatch_process_exit(
        actions, spawners[spawner_index], returncode, context
    )

    if returncode == 0:
        assert emitted == []
        assert exit_status.returncode is None
    else:
        assert exit_status.returncode == 19
        _assert_failure_status(emitted, context, "exit code 19")


def test_first_text_agent_terminal_process_status_wins(tmp_path: Path, monkeypatch) -> None:
    context, actions, exit_status = _materialize(monkeypatch, tmp_path)

    _dispatch_process_exit(actions, _node(actions, "ros2_control_node"), 31, context)
    _dispatch_process_exit(
        actions, _node(actions, "graceful_shutdown_move_group"), 41, context
    )

    assert exit_status.returncode == 31
