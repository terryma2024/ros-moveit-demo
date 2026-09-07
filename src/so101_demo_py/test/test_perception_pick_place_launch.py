from __future__ import annotations

import importlib.util
import hashlib
import math
import os
from pathlib import Path

import pytest
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    ExecuteProcess,
    OpaqueFunction,
    RegisterEventHandler,
    TimerAction,
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


def _eventual_actions(actions) -> list[object]:
    return [
        *actions,
        *(
            nested
            for action in actions
            if isinstance(action, TimerAction)
            for nested in action.actions
        ),
    ]


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


def _grounded_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "grounded-sam-bundle"
    bundle.mkdir()
    return bundle


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
        "perception_backend",
        "perception_weights",
        "perception_weights_sha256",
        "perception_model_root",
        "perception_model_manifest_sha256",
        "perception_device",
        "perception_allow_cpu_fallback",
        "perception_runtime",
        "perception_container_image",
        "perception_source_root",
        "grounding_box_threshold",
        "grounding_text_threshold",
        "grounding_duplicate_iou",
        "grounding_max_candidates",
        "sam_mask_quality_threshold",
        "sam_min_mask_pixels",
        "sam_max_mask_area_ratio",
        "profiling",
        "profiling_output_root",
        "profiling_require_system_trace",
    } <= declared.keys()
    assert _default(declared["headless"]) == "false"
    assert _default(declared["mujoco_initial_keyframe"]) == "task_start"
    assert _default(declared["perception_startup_timeout_s"]) == "30.0"
    assert _default(declared["cup_pose_timeout_s"]) == "45.0"
    assert _default(declared["perception_backend"]) == "color_geometry"
    assert _default(declared["perception_runtime"]) == "auto"
    assert _default(declared["perception_source_root"]) == ""
    assert _default(declared["profiling"]) == "off"
    assert _default(declared["profiling_output_root"]) == ""
    assert _default(declared["profiling_require_system_trace"]) == "false"
    assert (
        _default(declared["perception_container_image"])
        == "so101-yolo11n-seg-inference:ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115"
    )

    assert LAUNCH_PATH.is_file()
    source = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "DeclareLaunchArgument" not in source
    spec = importlib.util.spec_from_file_location("perception_launch", LAUNCH_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.generate_launch_description() is not None


def test_perception_argument_default_is_owned_by_the_calling_launch() -> None:
    from so101_demo.runtime.perception_launch import declare_perception_arguments

    legacy = {
        argument.name: argument
        for argument in declare_perception_arguments(default_backend="color_geometry")
    }
    text_e2e = {
        argument.name: argument
        for argument in declare_perception_arguments(default_backend="yolo_seg")
    }

    assert set(legacy) == set(text_e2e) == {
        "perception_backend",
        "perception_weights",
        "perception_weights_sha256",
        "perception_model_root",
        "perception_model_manifest_sha256",
        "perception_device",
        "perception_allow_cpu_fallback",
        "perception_runtime",
        "perception_container_image",
        "perception_source_root",
        "grounding_box_threshold",
        "grounding_text_threshold",
        "grounding_duplicate_iou",
        "grounding_max_candidates",
        "sam_mask_quality_threshold",
        "sam_min_mask_pixels",
        "sam_max_mask_area_ratio",
    }
    assert _default(legacy["perception_backend"]) == "color_geometry"
    assert _default(text_e2e["perception_backend"]) == "yolo_seg"


def test_shared_perception_parser_resolves_macos_auto_without_model_artifacts(
    monkeypatch,
) -> None:
    from so101_demo.runtime import perception_launch

    context = LaunchContext()
    for argument in perception_launch.declare_perception_arguments(
        default_backend="color_geometry"
    ):
        context.launch_configurations[argument.name] = _default(argument)
    context.launch_configurations["perception_startup_timeout_s"] = "30.0"
    monkeypatch.setattr(perception_launch.platform, "system", lambda: "Darwin")

    options = perception_launch.parse_perception_options(context)

    assert options.backend == "color_geometry"
    assert options.runtime == "host"
    assert options.device == "mps"
    assert options.allow_cpu_fallback is False
    assert options.weights_path is None
    assert options.model_root is None
    assert options.grounded_thresholds is None


def test_shared_perception_builder_preserves_color_geometry_arguments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from so101_demo.runtime import perception_launch

    context = LaunchContext()
    for argument in perception_launch.declare_perception_arguments(
        default_backend="color_geometry"
    ):
        context.launch_configurations[argument.name] = _default(argument)
    context.launch_configurations["perception_startup_timeout_s"] = "30.0"
    monkeypatch.setattr(perception_launch.platform, "system", lambda: "Darwin")
    options = perception_launch.parse_perception_options(context)

    action = perception_launch.build_perception_action(
        options,
        evidence_root=tmp_path,
        request_id="session-123",
    )

    assert isinstance(action, Node)
    assert action.node_executable == "rgbd_cup_pose"
    assert action._Node__arguments == [
        "--startup-timeout-s",
        "30.0",
        "--output-topic",
        "/cup_pose",
        "--output-ply",
        str(tmp_path / "cup.ply"),
        "--evidence-json",
        str(tmp_path / "summary.json"),
    ]


def test_shared_perception_builder_requires_subscriber_for_yolo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from so101_demo.runtime import perception_launch

    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-v1")
    context = LaunchContext()
    for argument in perception_launch.declare_perception_arguments(
        default_backend="yolo_seg"
    ):
        context.launch_configurations[argument.name] = _default(argument)
    context.launch_configurations.update(
        {
            "perception_startup_timeout_s": "30.0",
            "perception_runtime": "host",
            "perception_weights": str(weights),
            "perception_weights_sha256": hashlib.sha256(b"weights-v1").hexdigest(),
        }
    )
    monkeypatch.setattr(perception_launch.platform, "system", lambda: "Darwin")
    options = perception_launch.parse_perception_options(context)

    action = perception_launch.build_perception_action(
        options,
        evidence_root=tmp_path / "evidence",
        request_id="session-123",
    )

    assert isinstance(action, Node)
    assert action.node_executable == "rgbd_object_pose"
    assert "--require-output-subscriber" in action._Node__arguments
    assert action._Node__arguments[
        action._Node__arguments.index("--request-id") + 1
    ] == "session-123"


def test_shared_perception_builder_forwards_grounded_sam_thresholds(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from so101_demo.runtime import perception_launch

    model_root = _grounded_bundle(tmp_path)
    context = LaunchContext()
    for argument in perception_launch.declare_perception_arguments(
        default_backend="grounded_sam"
    ):
        context.launch_configurations[argument.name] = _default(argument)
    context.launch_configurations.update(
        {
            "perception_startup_timeout_s": "30.0",
            "perception_runtime": "host",
            "perception_model_root": str(model_root),
            "perception_model_manifest_sha256": "a" * 64,
        }
    )
    monkeypatch.setattr(perception_launch.platform, "system", lambda: "Darwin")
    options = perception_launch.parse_perception_options(context)

    action = perception_launch.build_perception_action(
        options,
        evidence_root=tmp_path / "evidence",
        request_id="session-123",
    )

    assert isinstance(action, Node)
    assert action.node_executable == "rgbd_object_pose"
    assert action._Node__arguments[
        action._Node__arguments.index("--backend") + 1
    ] == "grounded_sam"
    assert action._Node__arguments[
        action._Node__arguments.index("--grounding-box-threshold") + 1
    ] == "0.35"
    assert "--require-output-subscriber" in action._Node__arguments


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
        ({"profiling": "enabled"}, "profiling"),
        ({"profiling": "trace", "profiling_output_root": "relative"}, "absolute"),
        (
            {"profiling": "trace", "profiling_require_system_trace": "yes"},
            "profiling_require_system_trace",
        ),
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


def test_model_backend_starts_after_dynamic_subscription_discovery(
    tmp_path: Path,
) -> None:
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-v1")
    context, actions, _exit_status = _materialize(
        evidence_file=tmp_path / "launch-run.json",
        perception_backend="yolo_seg",
        perception_runtime="host",
        perception_weights=weights,
        perception_weights_sha256=hashlib.sha256(b"weights-v1").hexdigest(),
    )

    scene_setup = _node(actions, "scene_setup")
    started = _dispatch_process_exit(actions, scene_setup, 0, context)

    assert [node.node_executable for node in _nodes(started)] == [
        "dynamic_cup_pick_place"
    ]
    timers = [action for action in started if isinstance(action, TimerAction)]
    assert len(timers) == 1
    assert timers[0].period == 1.0
    assert [node.node_executable for node in _nodes(timers[0].actions)] == [
        "rgbd_object_pose"
    ]

def test_perception_launch_caps_simulation_at_realtime_for_fresh_source_stamps(
    tmp_path: Path,
) -> None:
    context, actions, _exit_status = _materialize(
        evidence_file=tmp_path / "launch-run.json",
        headless="true",
    )
    simulator = _node(actions, "ros2_control_node")
    robot_description = evaluate_parameters(
        context, simulator._Node__parameters
    )[0]["robot_description"]

    assert '<param name="sim_speed_factor">1.0</param>' in robot_description


def test_yolo_backend_starts_one_object_pose_publisher_with_explicit_model_args(
    tmp_path: Path,
) -> None:
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-v1")
    digest = hashlib.sha256(b"weights-v1").hexdigest()
    context, actions, _exit_status = _materialize(
        evidence_file=tmp_path / "launch-run.json",
        perception_backend="yolo_seg",
        perception_weights=weights,
        perception_weights_sha256=digest,
        perception_device="mps",
        perception_allow_cpu_fallback="false",
        perception_runtime="host",
    )

    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)

    eventual = _eventual_actions(started)
    assert [node.node_executable for node in _nodes(eventual)] == [
        "dynamic_cup_pick_place",
        "rgbd_object_pose",
    ]
    perception = _node(eventual, "rgbd_object_pose")
    assert perception._Node__arguments == [
        "--startup-timeout-s",
        "30.0",
        "--output-topic",
        "/cup_pose",
        "--detections-topic",
        "/perception/detections",
        "--overlay-topic",
        "/perception/overlay",
        "--weights",
        str(weights),
        "--weights-sha256",
        digest,
        "--device",
        "mps",
        "--request-id",
        "session-123",
        "--evidence-root",
        str(tmp_path / "launch-run.d/session-123/perception"),
        "--require-output-subscriber",
    ]
    assert all(node.node_executable != "rgbd_cup_pose" for node in _nodes(started))


@pytest.mark.parametrize("backend", ("color_geometry", "yolo_seg", "grounded_sam"))
def test_enabled_trace_profiles_perception_and_dynamic_runtime_with_one_session(
    tmp_path: Path,
    backend: str,
) -> None:
    overrides: dict[str, object] = {
        "perception_backend": backend,
        "perception_runtime": "host",
        "profiling": "trace",
    }
    if backend == "yolo_seg":
        weights = tmp_path / "best.pt"
        weights.write_bytes(b"weights-v1")
        overrides.update(
            perception_weights=weights,
            perception_weights_sha256=hashlib.sha256(b"weights-v1").hexdigest(),
            perception_device="mps",
        )
    elif backend == "grounded_sam":
        overrides.update(
            perception_model_root=_grounded_bundle(tmp_path),
            perception_model_manifest_sha256="a" * 64,
            perception_device="mps",
        )

    context, actions, _exit_status = _materialize(
        evidence_file=tmp_path / f"{backend}.json",
        **overrides,
    )
    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)
    perception_executable = "rgbd_cup_pose" if backend == "color_geometry" else "rgbd_object_pose"
    eventual = _eventual_actions(started)
    perception = _node(eventual, perception_executable)
    workflow = _node(eventual, "dynamic_cup_pick_place")
    profiling_root = tmp_path / f"{backend}.d/session-123/profiling"
    common = [
        "--profiling",
        "trace",
        "--profiling-output-root",
        str(profiling_root),
        "--profiling-session-id",
        "session-123",
    ]

    assert perception._Node__arguments[-6:] == common
    assert workflow._Node__arguments[-6:] == common

    _dispatch_process_exit(actions, workflow, 0, context)
    _dispatch_process_exit(actions, perception, -15, context)
    assert (profiling_root / "manifest.json").is_file()
    assert (profiling_root / "summary.json").is_file()
    assert (profiling_root / "trace.json").is_file()


def test_linux_auto_yolo_backend_starts_cuda_container_with_ros_and_owned_mounts(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(launch_composition.platform, "system", lambda: "Linux")
    monkeypatch.setenv("ROS_DOMAIN_ID", "191")
    monkeypatch.setenv("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp")
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-v1")
    digest = hashlib.sha256(b"weights-v1").hexdigest()
    context, actions, _exit_status = _materialize(
        evidence_file=tmp_path / "launch-run.json",
        perception_backend="yolo_seg",
        perception_weights=weights,
        perception_weights_sha256=digest,
        perception_device="auto",
        perception_runtime="auto",
        perception_container_image="registry.example/so101-yolo:locked",
    )

    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)

    assert [node.node_executable for node in _nodes(started)] == [
        "dynamic_cup_pick_place"
    ]
    command = _plain_process_command(_plain_process(_eventual_actions(started)), context)
    assert command[:13] == [
        "docker",
        "run",
        "--rm",
        "--name",
        "so101-yolo-seg-session-123",
        "--gpus",
        "all",
        "--network",
        "host",
        "--ipc",
        "host",
        "--user",
        f"{os.geteuid()}:{os.getegid()}",
    ]
    assert ["--env", "ROS_DOMAIN_ID=191"] == command[
        command.index("--env") : command.index("--env") + 2
    ]
    assert "RMW_IMPLEMENTATION=rmw_fastrtps_cpp" in command
    assert (
        f"type=bind,src={weights},dst=/models/best.pt,readonly" in command
    )
    evidence_root = tmp_path / "launch-run.d/session-123/perception"
    assert f"type=bind,src={evidence_root},dst=/evidence" in command
    assert "registry.example/so101-yolo:locked" in command
    assert "PYTHONPATH=/workspace/so101-source" not in command
    assert not any("dst=/workspace/so101-source" in part for part in command)
    image_index = command.index("registry.example/so101-yolo:locked")
    assert command[image_index + 1 :] == [
        "--startup-timeout-s",
        "30.0",
        "--output-topic",
        "/cup_pose",
        "--detections-topic",
        "/perception/detections",
        "--overlay-topic",
        "/perception/overlay",
        "--weights",
        "/models/best.pt",
        "--weights-sha256",
        digest,
        "--device",
        "cuda",
        "--request-id",
        "session-123",
        "--evidence-root",
        "/evidence",
        "--require-output-subscriber",
    ]


def test_linux_yolo_profiling_mounts_the_correlated_root_into_the_container(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(launch_composition.platform, "system", lambda: "Linux")
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-v1")
    context, actions, _exit_status = _materialize(
        evidence_file=tmp_path / "launch-run.json",
        perception_backend="yolo_seg",
        perception_weights=weights,
        perception_weights_sha256=hashlib.sha256(b"weights-v1").hexdigest(),
        perception_runtime="docker",
        profiling="summary",
    )

    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)
    command = _plain_process_command(_plain_process(_eventual_actions(started)), context)
    profiling_root = tmp_path / "launch-run.d/session-123/profiling"
    assert f"type=bind,src={profiling_root},dst=/profiling" in command
    image_index = command.index(
        "so101-yolo11n-seg-inference:ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115"
    )
    assert command[image_index + 1 :][-6:] == [
        "--profiling",
        "summary",
        "--profiling-output-root",
        "/profiling",
        "--profiling-session-id",
        "session-123",
    ]


def test_linux_docker_dev_mounts_only_the_explicit_python_source(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(launch_composition.platform, "system", lambda: "Linux")
    source_root = tmp_path / "python-source"
    (source_root / "runtime").mkdir(parents=True)
    (source_root / "__init__.py").write_text("", encoding="utf-8")
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-v1")
    digest = hashlib.sha256(b"weights-v1").hexdigest()
    context, actions, _exit_status = _materialize(
        evidence_file=tmp_path / "launch-run.json",
        perception_backend="yolo_seg",
        perception_weights=weights,
        perception_weights_sha256=digest,
        perception_runtime="docker_dev",
        perception_source_root=source_root,
    )

    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)

    command = _plain_process_command(_plain_process(_eventual_actions(started)), context)
    assert "PYTHONPATH=/workspace/so101-source" in command
    assert (
        f"type=bind,src={source_root},"
        "dst=/workspace/so101-source/so101_demo,readonly" in command
    )


@pytest.mark.parametrize("source_root", ["", "relative/source"])
def test_linux_docker_dev_rejects_missing_or_relative_source(
    tmp_path: Path, monkeypatch, source_root: str
) -> None:
    monkeypatch.setattr(launch_composition.platform, "system", lambda: "Linux")
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-v1")

    with pytest.raises(RuntimeError, match="perception_source_root"):
        _materialize(
            evidence_file=tmp_path / "launch-run.json",
            perception_backend="yolo_seg",
            perception_weights=weights,
            perception_weights_sha256=hashlib.sha256(b"weights-v1").hexdigest(),
            perception_runtime="docker_dev",
            perception_source_root=source_root,
        )


def test_macos_auto_yolo_backend_keeps_host_process_and_resolves_mps(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(launch_composition.platform, "system", lambda: "Darwin")
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-v1")
    digest = hashlib.sha256(b"weights-v1").hexdigest()
    context, actions, _exit_status = _materialize(
        evidence_file=tmp_path / "launch-run.json",
        perception_backend="yolo_seg",
        perception_weights=weights,
        perception_weights_sha256=digest,
        perception_device="auto",
        perception_runtime="auto",
    )

    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)

    assert [
        action.node_executable
        for action in _nodes(_eventual_actions(started))
    ] == ["dynamic_cup_pick_place", "rgbd_object_pose"]
    perception = _node(_eventual_actions(started), "rgbd_object_pose")
    device_index = perception._Node__arguments.index("--device") + 1
    assert perception._Node__arguments[device_index] == "mps"
    assert not [
        action
        for action in started
        if isinstance(action, ExecuteProcess) and not isinstance(action, Node)
    ]


def test_macos_rejects_explicit_docker_yolo_runtime_before_processes(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(launch_composition.platform, "system", lambda: "Darwin")
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-v1")

    with pytest.raises(RuntimeError, match="supported only on Linux"):
        _materialize(
            evidence_file=tmp_path / "launch-run.json",
            perception_backend="yolo_seg",
            perception_weights=weights,
            perception_weights_sha256=hashlib.sha256(b"weights-v1").hexdigest(),
            perception_runtime="docker",
            perception_device="cuda",
        )


def test_grounded_sam_backend_starts_the_object_pose_cli_with_default_thresholds(
    tmp_path: Path,
) -> None:
    bundle = _grounded_bundle(tmp_path)
    digest = "a" * 64
    context, actions, _exit_status = _materialize(
        evidence_file=tmp_path / "launch-run.json",
        perception_backend="grounded_sam",
        perception_model_root=bundle,
        perception_model_manifest_sha256=digest,
        perception_device="mps",
        perception_runtime="host",
    )

    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)

    eventual = _eventual_actions(started)
    assert [node.node_executable for node in _nodes(eventual)] == [
        "dynamic_cup_pick_place",
        "rgbd_object_pose",
    ]
    perception = _node(eventual, "rgbd_object_pose")
    assert perception._Node__arguments == [
        "--startup-timeout-s",
        "30.0",
        "--output-topic",
        "/cup_pose",
        "--detections-topic",
        "/perception/detections",
        "--overlay-topic",
        "/perception/overlay",
        "--backend",
        "grounded_sam",
        "--model-root",
        str(bundle),
        "--model-manifest-sha256",
        digest,
        "--device",
        "mps",
        "--grounding-box-threshold",
        "0.35",
        "--grounding-text-threshold",
        "0.25",
        "--duplicate-iou",
        "0.85",
        "--max-candidates",
        "16",
        "--sam-quality-threshold",
        "0.75",
        "--min-mask-pixels",
        "64",
        "--max-mask-area-ratio",
        "0.50",
        "--request-id",
        "session-123",
        "--evidence-root",
        str(tmp_path / "launch-run.d/session-123/perception"),
        "--require-output-subscriber",
    ]
    assert "--allow-cpu-fallback" not in perception._Node__arguments


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {
                "perception_backend": "grounded_sam",
                "perception_model_root": "",
                "perception_model_manifest_sha256": "a" * 64,
            },
            "perception_model_root",
        ),
        (
            {
                "perception_backend": "grounded_sam",
                "perception_model_root": "relative-bundle",
                "perception_model_manifest_sha256": "a" * 64,
            },
            "perception_model_root",
        ),
        (
            {
                "perception_backend": "grounded_sam",
                "perception_model_manifest_sha256": "A" * 64,
            },
            "perception_model_manifest_sha256",
        ),
        (
            {
                "perception_backend": "grounded_sam",
                "perception_weights": __file__,
                "perception_weights_sha256": "a" * 64,
            },
            "perception_weights",
        ),
    ],
)
def test_grounded_sam_rejects_missing_or_mixed_backend_artifacts(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    bundle = _grounded_bundle(tmp_path)
    overrides.setdefault("perception_model_root", bundle)
    overrides.setdefault("perception_model_manifest_sha256", "a" * 64)

    with pytest.raises(RuntimeError, match=message):
        _materialize(evidence_file=tmp_path / "result.json", **overrides)


def test_grounded_sam_rejects_a_symlinked_model_root_before_nodes(tmp_path: Path) -> None:
    bundle = _grounded_bundle(tmp_path)
    linked_bundle = tmp_path / "linked-grounded-sam-bundle"
    linked_bundle.symlink_to(bundle, target_is_directory=True)

    with pytest.raises(RuntimeError, match="perception_model_root"):
        _materialize(
            evidence_file=tmp_path / "result.json",
            perception_backend="grounded_sam",
            perception_model_root=linked_bundle,
            perception_model_manifest_sha256="a" * 64,
        )


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("grounding_box_threshold", "0"),
        ("grounding_box_threshold", "1"),
        ("grounding_text_threshold", "0"),
        ("grounding_text_threshold", "1"),
        ("grounding_duplicate_iou", "0"),
        ("grounding_duplicate_iou", "1"),
        ("sam_mask_quality_threshold", "0"),
        ("sam_mask_quality_threshold", "1"),
        ("sam_max_mask_area_ratio", "1"),
        ("grounding_max_candidates", "1"),
        ("sam_min_mask_pixels", "1"),
    ],
)
def test_grounded_sam_accepts_threshold_contract_boundaries(
    tmp_path: Path, argument: str, value: str
) -> None:
    bundle = _grounded_bundle(tmp_path)

    _context, actions, _exit_status = _materialize(
        evidence_file=tmp_path / f"accepted-{argument}-{value}.json",
        perception_backend="grounded_sam",
        perception_model_root=bundle,
        perception_model_manifest_sha256="a" * 64,
        **{argument: value},
    )
    assert _node(actions, "scene_setup")


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("grounding_box_threshold", "-0.01"),
        ("grounding_box_threshold", "1.01"),
        ("grounding_box_threshold", "nan"),
        ("grounding_box_threshold", "inf"),
        ("grounding_text_threshold", "-0.01"),
        ("grounding_text_threshold", "1.01"),
        ("grounding_text_threshold", "nan"),
        ("grounding_text_threshold", "inf"),
        ("grounding_duplicate_iou", "-0.01"),
        ("grounding_duplicate_iou", "1.01"),
        ("grounding_duplicate_iou", "nan"),
        ("grounding_duplicate_iou", "inf"),
        ("sam_mask_quality_threshold", "-0.01"),
        ("sam_mask_quality_threshold", "1.01"),
        ("sam_mask_quality_threshold", "nan"),
        ("sam_mask_quality_threshold", "inf"),
        ("sam_max_mask_area_ratio", "-0.01"),
        ("sam_max_mask_area_ratio", "0"),
        ("sam_max_mask_area_ratio", "1.01"),
        ("sam_max_mask_area_ratio", "nan"),
        ("sam_max_mask_area_ratio", "inf"),
        ("grounding_max_candidates", "0"),
        ("grounding_max_candidates", "-1"),
        ("grounding_max_candidates", "1.5"),
        ("sam_min_mask_pixels", "0"),
        ("sam_min_mask_pixels", "-1"),
        ("sam_min_mask_pixels", "1.5"),
    ],
)
def test_grounded_sam_rejects_threshold_values_outside_the_contract(
    tmp_path: Path, argument: str, value: str
) -> None:
    bundle = _grounded_bundle(tmp_path)

    with pytest.raises(RuntimeError, match=argument):
        _materialize(
            evidence_file=tmp_path / f"rejected-{argument}-{value}.json",
            perception_backend="grounded_sam",
            perception_model_root=bundle,
            perception_model_manifest_sha256="a" * 64,
            **{argument: value},
        )


@pytest.mark.parametrize("backend", ("color_geometry", "yolo_seg"))
@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("perception_model_root", "/tmp/grounded-sam-bundle"),
        ("perception_model_manifest_sha256", "a" * 64),
        ("grounding_box_threshold", "0.36"),
        ("grounding_text_threshold", "0.26"),
        ("grounding_duplicate_iou", "0.84"),
        ("grounding_max_candidates", "17"),
        ("sam_mask_quality_threshold", "0.76"),
        ("sam_min_mask_pixels", "65"),
        ("sam_max_mask_area_ratio", "0.51"),
    ],
)
def test_non_grounded_backends_reject_grounded_sam_only_arguments(
    tmp_path: Path, backend: str, argument: str, value: str
) -> None:
    overrides: dict[str, object] = {"perception_backend": backend, argument: value}
    if backend == "yolo_seg":
        weights = tmp_path / "best.pt"
        weights.write_bytes(b"weights-v1")
        overrides.update(
            perception_weights=weights,
            perception_weights_sha256=hashlib.sha256(b"weights-v1").hexdigest(),
        )

    with pytest.raises(RuntimeError, match=argument):
        _materialize(evidence_file=tmp_path / "result.json", **overrides)


@pytest.mark.parametrize("backend", ("color_geometry", "yolo_seg"))
def test_non_grounded_backends_accept_explicit_grounded_sam_default_thresholds(
    tmp_path: Path, backend: str
) -> None:
    overrides: dict[str, object] = {
        "perception_backend": backend,
        "grounding_box_threshold": "0.35",
        "grounding_text_threshold": "0.25",
        "grounding_duplicate_iou": "0.85",
        "grounding_max_candidates": "16",
        "sam_mask_quality_threshold": "0.75",
        "sam_min_mask_pixels": "64",
        "sam_max_mask_area_ratio": "0.50",
    }
    if backend == "yolo_seg":
        weights = tmp_path / "best.pt"
        weights.write_bytes(b"weights-v1")
        overrides.update(
            perception_weights=weights,
            perception_weights_sha256=hashlib.sha256(b"weights-v1").hexdigest(),
        )

    _context, actions, _exit_status = _materialize(
        evidence_file=tmp_path / "result.json", **overrides
    )
    assert _node(actions, "scene_setup")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"perception_backend": "unknown"}, "perception_backend"),
        ({"perception_backend": "yolo_seg"}, "perception_weights"),
        (
            {
                "perception_backend": "yolo_seg",
                "perception_weights": "/tmp/missing-best.pt",
                "perception_weights_sha256": "a" * 64,
            },
            "perception_weights",
        ),
        (
            {
                "perception_backend": "yolo_seg",
                "perception_weights": __file__,
                "perception_weights_sha256": "not-a-sha",
            },
            "perception_weights_sha256",
        ),
    ],
)
def test_invalid_yolo_backend_configuration_fails_before_nodes(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        _materialize(evidence_file=tmp_path / "result.json", **overrides)


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
        ("graceful_shutdown_move_group", "MoveIt move_group"),
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
        _node(actions, "graceful_shutdown_move_group"),
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
            "graceful_shutdown_move_group",
            "static_transform_publisher",
        }
    ]
    required.append(perception)
    required.extend(node for node in _nodes(actions) if node.node_executable == "spawner")

    _dispatch_process_exit(actions, workflow, 0, context)
    emitted = [_dispatch_process_exit(actions, target, -15, context) for target in required]

    assert emitted == [[] for _target in required]
    assert exit_status.returncode == 0
