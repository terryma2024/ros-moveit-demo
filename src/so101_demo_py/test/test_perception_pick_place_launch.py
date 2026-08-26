from __future__ import annotations

import importlib.util
import math
import os
from pathlib import Path

import pytest
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    OpaqueFunction,
    RegisterEventHandler,
)
from launch.events import Shutdown as ShutdownEvent
from launch.events.process import ProcessExited
from launch.utilities import perform_substitutions
from launch_ros.actions import Node
from launch_ros.utilities import evaluate_parameters
from so101_demo.runtime import launch_composition

from launch import LaunchContext

PACKAGE_ROOT = Path(__file__).parents[1]
LAUNCH_PATH = PACKAGE_ROOT / "launch/so101_mujoco_perception_pick_place.launch.py"


def _builder():
    assert hasattr(launch_composition, "build_perception_pick_place_launch_description"), (
        "dedicated perception launch builder is missing"
    )
    return launch_composition.build_perception_pick_place_launch_description


def _declared(description) -> dict[str, DeclareLaunchArgument]:
    return {
        action.name: action
        for action in description.entities
        if isinstance(action, DeclareLaunchArgument)
    }


def _default(argument: DeclareLaunchArgument) -> str:
    return perform_substitutions(LaunchContext(), argument.default_value)


def _materialize(*, evidence_file=None, **overrides):
    exit_status = launch_composition.PerceptionLaunchExitStatus()
    description = _builder()(exit_status)
    declared = _declared(description)
    context = LaunchContext()
    for name, argument in declared.items():
        context.launch_configurations[name] = perform_substitutions(context, argument.default_value)
    context.launch_configurations.update(
        {
            "run_mode": "execute",
            "execute": "true",
            "session_id": "session-123",
            "evidence_file": str(
                evidence_file
                or Path(
                    "/tmp/so101-debug-rgbd-perception-pick-place-20260826/"
                    "task-6/reviewer-fix/launch-run.json"
                )
            ),
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


def _dispatch_process_exit(actions, target: Node, returncode: int, context: LaunchContext):
    event = ProcessExited(
        action=target,
        name=str(target.node_executable),
        cmd=[str(target.node_executable)],
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


def test_public_launch_is_thin_and_declares_the_execute_contract() -> None:
    description = _builder()()
    declared = _declared(description)

    assert {
        "run_mode",
        "execute",
        "headless",
        "session_id",
        "evidence_file",
        "readiness_timeout_s",
        "mujoco_scene",
        "mujoco_initial_keyframe",
        "perception_startup_timeout_s",
        "cup_pose_timeout_s",
    } <= declared.keys()
    assert _default(declared["headless"]) == "false"
    assert _default(declared["mujoco_initial_keyframe"]) == "task_start"
    assert _default(declared["perception_startup_timeout_s"]) == "30.0"
    assert _default(declared["cup_pose_timeout_s"]) == "45.0"

    assert LAUNCH_PATH.is_file()
    source = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "DeclareLaunchArgument" not in source
    spec = importlib.util.spec_from_file_location("perception_launch", LAUNCH_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.generate_launch_description() is not None


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"run_mode": "dry_run"}, "run_mode=execute"),
        ({"execute": "false"}, "execute:=true"),
        ({"headless": "sometimes"}, "headless"),
        ({"mujoco_initial_keyframe": "unknown"}, "initial keyframe"),
        ({"readiness_timeout_s": "0"}, "readiness_timeout_s"),
        ({"perception_startup_timeout_s": math.inf}, "perception_startup_timeout_s"),
        ({"cup_pose_timeout_s": "nan"}, "cup_pose_timeout_s"),
        ({"session_id": ""}, "session_id"),
        ({"session_id": "../escape"}, "session_id"),
        ({"evidence_file": "relative.json"}, "evidence_file"),
        ({"evidence_file": "/tmp"}, "evidence_file"),
        ({"mujoco_scene": "relative.xml"}, "mujoco_scene"),
        ({"mujoco_scene": "/tmp/task-6-scene-does-not-exist.xml"}, "mujoco_scene"),
    ),
)
def test_invalid_execute_inputs_fail_before_actions_are_materialized(overrides, message) -> None:
    with pytest.raises(RuntimeError, match=message):
        _materialize(**overrides)


def test_scene_success_starts_only_perception_and_dynamic_workflow_with_exact_args(
    tmp_path: Path,
) -> None:
    evidence_file = tmp_path / "launch-run.json"
    context, actions, _exit_status = _materialize(evidence_file=evidence_file)
    initial_executables = [node.node_executable for node in _nodes(actions)]

    assert initial_executables[:2] == [
        "static_transform_publisher",
        "static_transform_publisher",
    ]
    assert "scene_setup" in initial_executables
    assert "rgbd_cup_pose" not in initial_executables
    assert "dynamic_cup_pick_place" not in initial_executables
    assert "cup_pose_tf_demo" not in initial_executables
    assert "mujoco_cup_pose_bridge" not in initial_executables

    scene_setup = _node(actions, "scene_setup")
    started = _dispatch_process_exit(actions, scene_setup, 0, context)
    assert [node.node_executable for node in _nodes(started)] == [
        "rgbd_cup_pose",
        "dynamic_cup_pick_place",
    ]

    perception = _node(started, "rgbd_cup_pose")
    assert perception._Node__arguments == [
        "--startup-timeout-s",
        "30.0",
        "--output-topic",
        "/cup_pose",
        "--output-ply",
        str(tmp_path / "launch-run.d/session-123/perception/cup.ply"),
        "--evidence-json",
        str(tmp_path / "launch-run.d/session-123/perception/summary.json"),
    ]
    assert evaluate_parameters(context, perception._Node__parameters) == ({"use_sim_time": True},)

    workflow = _node(started, "dynamic_cup_pick_place")
    assert workflow._Node__arguments == [
        "--backend",
        "mujoco",
        "--mode",
        "execute",
        "--execute",
        "--cup-pose-timeout-s",
        "45.0",
        "--scene-source",
        "observe_only",
        "--session-id",
        "session-123",
        "--expected-reset-epoch",
        "0",
        "--evidence-root",
        str(tmp_path / "launch-run.d/session-123/dynamic"),
    ]

    all_executables = initial_executables + [node.node_executable for node in _nodes(started)]
    assert all_executables.count("rgbd_cup_pose") == 1
    assert "cup_pose_tf_demo" not in all_executables
    assert "mujoco_cup_pose_bridge" not in all_executables


def test_evidence_preflight_creates_owned_run_directory_before_nodes(
    tmp_path: Path,
) -> None:
    evidence_file = tmp_path / "result.json"

    _context, actions, _exit_status = _materialize(evidence_file=evidence_file)

    run_root = tmp_path / "result.d/session-123"
    assert run_root.is_dir()
    assert run_root.resolve().is_relative_to(tmp_path.resolve())
    assert run_root.stat().st_uid == os.geteuid()
    assert run_root.stat().st_mode & 0o777 == 0o700
    assert (run_root / "perception").is_dir()
    assert (run_root / "dynamic").is_dir()
    assert _nodes(actions)


def test_evidence_preflight_keeps_valid_preexisting_base_directory(
    tmp_path: Path,
) -> None:
    base = tmp_path / "result.d"
    base.mkdir()

    _context, actions, _exit_status = _materialize(evidence_file=tmp_path / "result.json")

    run_root = base / "session-123"
    assert run_root.is_dir()
    assert _nodes(actions)


def test_evidence_preflight_rejects_preexisting_session_without_modifying_it(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "result.d/session-123"
    run_root.mkdir(parents=True)
    sentinel = run_root / "accepted.txt"
    sentinel.write_text("immutable", encoding="utf-8")

    with pytest.raises(RuntimeError, match="session evidence root already exists"):
        _materialize(evidence_file=tmp_path / "result.json")

    assert sentinel.read_text(encoding="utf-8") == "immutable"
    assert sorted(path.name for path in run_root.iterdir()) == ["accepted.txt"]


def test_evidence_preflight_rejects_existing_nominal_file(tmp_path: Path) -> None:
    evidence_file = tmp_path / "result.json"
    evidence_file.write_text("accepted", encoding="utf-8")

    with pytest.raises(RuntimeError, match="must not already exist"):
        _materialize(evidence_file=evidence_file)

    assert evidence_file.read_text(encoding="utf-8") == "accepted"
    assert not (tmp_path / "result.d").exists()


def test_evidence_preflight_rejects_broken_nominal_symlink(tmp_path: Path) -> None:
    evidence_file = tmp_path / "result.json"
    evidence_file.symlink_to(tmp_path / "missing.json")

    with pytest.raises(RuntimeError, match="must not already exist"):
        _materialize(evidence_file=evidence_file)

    assert evidence_file.is_symlink()
    assert not (tmp_path / "result.d").exists()


def test_evidence_preflight_passes_resolved_child_paths_to_nodes(
    tmp_path: Path,
) -> None:
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    alias_parent = tmp_path / "alias"
    alias_parent.symlink_to(real_parent, target_is_directory=True)

    context, actions, _exit_status = _materialize(evidence_file=alias_parent / "result.json")
    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)
    perception = _node(started, "rgbd_cup_pose")
    workflow = _node(started, "dynamic_cup_pick_place")

    resolved_run = real_parent.resolve() / "result.d/session-123"
    assert str(resolved_run / "perception/cup.ply") in perception._Node__arguments
    assert str(resolved_run / "dynamic") in workflow._Node__arguments


@pytest.mark.parametrize(
    ("component", "message"),
    (("base", "symlink"), ("session", "session evidence root already exists")),
)
def test_evidence_preflight_rejects_symlink_components(
    tmp_path: Path,
    component: str,
    message: str,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    base = tmp_path / "result.d"
    if component == "base":
        base.symlink_to(outside, target_is_directory=True)
    else:
        base.mkdir()
        (base / "session-123").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match=message):
        _materialize(evidence_file=tmp_path / "result.json")


@pytest.mark.parametrize(
    ("component", "message"),
    (("base", "directory"), ("session", "session evidence root already exists")),
)
def test_evidence_preflight_rejects_non_directory_components(
    tmp_path: Path,
    component: str,
    message: str,
) -> None:
    base = tmp_path / "result.d"
    if component == "base":
        base.write_text("conflict", encoding="utf-8")
    else:
        base.mkdir()
        (base / "session-123").write_text("conflict", encoding="utf-8")

    with pytest.raises(RuntimeError, match=message):
        _materialize(evidence_file=tmp_path / "result.json")


def test_evidence_preflight_rejects_conflicting_directory_owner(
    tmp_path: Path, monkeypatch
) -> None:
    base = tmp_path / "result.d"
    base.mkdir()
    monkeypatch.setattr(os, "geteuid", lambda: base.stat().st_uid + 1)

    with pytest.raises(RuntimeError, match="owned"):
        _materialize(evidence_file=tmp_path / "result.json")


def test_scene_failure_starts_no_sensor_or_workflow_and_fails_launch(
    tmp_path: Path,
) -> None:
    context, actions, _exit_status = _materialize(evidence_file=tmp_path / "launch-run.json")
    scene_setup = _node(actions, "scene_setup")

    emitted = _dispatch_process_exit(actions, scene_setup, 12, context)

    assert _nodes(emitted) == []
    assert _shutdown_reasons(emitted) == ["SO-101 Planning Scene setup failed with exit code 12"]
    _assert_failure_status(emitted, context, "exit code 12")


@pytest.mark.parametrize("returncode", (0, 9))
def test_perception_exit_before_workflow_completion_is_terminal(
    tmp_path: Path, returncode: int
) -> None:
    context, actions, _exit_status = _materialize(evidence_file=tmp_path / "launch-run.json")
    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)
    perception = _node(started, "rgbd_cup_pose")

    emitted = _dispatch_process_exit(actions, perception, returncode, context)

    assert _shutdown_reasons(emitted) == [
        f"RGB-D perception exited before dynamic workflow completed with exit code {returncode}"
    ]
    _assert_failure_status(emitted, context, f"exit code {returncode}")


def test_clean_workflow_exit_owns_shutdown_and_later_perception_exit_is_ignored(
    tmp_path: Path,
) -> None:
    context, actions, _exit_status = _materialize(evidence_file=tmp_path / "launch-run.json")
    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)
    workflow = _node(started, "dynamic_cup_pick_place")
    perception = _node(started, "rgbd_cup_pose")

    workflow_emitted = _dispatch_process_exit(actions, workflow, 0, context)
    perception_emitted = _dispatch_process_exit(actions, perception, -15, context)

    assert _shutdown_reasons(workflow_emitted) == [
        "Dynamic perception workflow completed with exit code 0"
    ]
    assert not [action for action in workflow_emitted if isinstance(action, OpaqueFunction)]
    assert perception_emitted == []


def test_failed_workflow_exit_preserves_failure_and_suppresses_shutdown_race(
    tmp_path: Path,
) -> None:
    context, actions, _exit_status = _materialize(evidence_file=tmp_path / "launch-run.json")
    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)
    workflow = _node(started, "dynamic_cup_pick_place")
    perception = _node(started, "rgbd_cup_pose")

    workflow_emitted = _dispatch_process_exit(actions, workflow, 23, context)
    perception_emitted = _dispatch_process_exit(actions, perception, -15, context)

    assert _shutdown_reasons(workflow_emitted) == [
        "Dynamic perception workflow failed with exit code 23"
    ]
    _assert_failure_status(workflow_emitted, context, "exit code 23")
    assert perception_emitted == []


@pytest.mark.parametrize(
    ("executable", "label"),
    (
        ("ros2_control_node", "MuJoCo runtime"),
        ("robot_state_publisher", "robot_state_publisher"),
        ("so101_move_group", "MoveIt move_group"),
        ("static_transform_publisher", "camera static TF"),
    ),
)
def test_required_long_lived_exit_before_workflow_is_terminal(
    tmp_path: Path,
    executable: str,
    label: str,
) -> None:
    context, actions, exit_status = _materialize(evidence_file=tmp_path / "required-process.json")
    target = next(node for node in _nodes(actions) if node.node_executable == executable)

    emitted = _dispatch_process_exit(actions, target, 17, context)

    assert exit_status.returncode == 17
    assert any(label in reason for reason in _shutdown_reasons(emitted))
    _assert_failure_status(emitted, context, "exit code 17")


def test_unexpected_clean_required_exit_normalizes_to_one(tmp_path: Path) -> None:
    context, actions, exit_status = _materialize(
        evidence_file=tmp_path / "clean-required-process.json"
    )
    simulator = _node(actions, "ros2_control_node")

    emitted = _dispatch_process_exit(actions, simulator, 0, context)

    assert exit_status.returncode == 1
    _assert_failure_status(emitted, context, "exit code 0")


@pytest.mark.parametrize("spawner_index", range(3))
@pytest.mark.parametrize("returncode", (0, 19))
def test_controller_spawner_exit_policy(
    tmp_path: Path,
    spawner_index: int,
    returncode: int,
) -> None:
    context, actions, exit_status = _materialize(
        evidence_file=tmp_path / f"spawner-{spawner_index}-{returncode}.json"
    )
    spawners = [node for node in _nodes(actions) if node.node_executable == "spawner"]

    emitted = _dispatch_process_exit(
        actions,
        spawners[spawner_index],
        returncode,
        context,
    )

    if returncode == 0:
        assert emitted == []
        assert exit_status.returncode is None
    else:
        assert exit_status.returncode == 19
        _assert_failure_status(emitted, context, "exit code 19")


def test_first_terminal_process_status_wins(tmp_path: Path) -> None:
    context, actions, exit_status = _materialize(evidence_file=tmp_path / "first-status.json")

    _dispatch_process_exit(
        actions,
        _node(actions, "ros2_control_node"),
        31,
        context,
    )
    _dispatch_process_exit(
        actions,
        _node(actions, "so101_move_group"),
        41,
        context,
    )

    assert exit_status.returncode == 31


def test_workflow_terminal_ignores_all_required_and_spawner_teardown_exits(
    tmp_path: Path,
) -> None:
    context, actions, exit_status = _materialize(evidence_file=tmp_path / "teardown.json")
    started = _dispatch_process_exit(
        actions,
        _node(actions, "scene_setup"),
        0,
        context,
    )
    workflow = _node(started, "dynamic_cup_pick_place")
    perception = _node(started, "rgbd_cup_pose")
    required = [
        node
        for node in _nodes(actions)
        if node.node_executable
        in {
            "ros2_control_node",
            "robot_state_publisher",
            "so101_move_group",
            "static_transform_publisher",
        }
    ]
    required.append(perception)
    required.extend(node for node in _nodes(actions) if node.node_executable == "spawner")

    _dispatch_process_exit(actions, workflow, 0, context)
    emitted = [_dispatch_process_exit(actions, target, -15, context) for target in required]

    assert emitted == [[] for _target in required]
    assert exit_status.returncode == 0
