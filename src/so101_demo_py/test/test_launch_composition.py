import importlib.util
from pathlib import Path
from types import SimpleNamespace

from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    OpaqueFunction,
    RegisterEventHandler,
    Shutdown,
)
from launch.event_handlers import OnProcessExit
from launch.events.process import ProcessExited
from launch_ros.actions import Node
from launch_ros.utilities import evaluate_parameters
from so101_demo.runtime import launch_composition
from so101_demo.runtime.launch_composition import COMMON_ARGUMENTS, build_launch_description

from launch import LaunchContext

PACKAGE_ROOT = Path(__file__).parents[1]
LAUNCH_ROOT = PACKAGE_ROOT / "launch"
LAUNCHERS = (
    "so101_mujoco.launch.py",
    "so101_mujoco_pick_place.launch.py",
    "so101_gazebo.launch.py",
    "so101_gazebo_pick_place.launch.py",
)


def _declared(description) -> set[str]:
    return {
        action.name for action in description.entities if isinstance(action, DeclareLaunchArgument)
    }


def _execute_actions(backend: str, *, pick_place: bool):
    """The actions the launch description really builds, with the run selected as ``execute``.

    ``build_launch_description`` keeps its graph behind an ``OpaqueFunction``, so a test that only
    reads the description's declared arguments never sees the nodes, timers or event handlers the
    launch really installs. Running that function against a context filled from the declared
    defaults is the same path ``ros2 launch`` takes, without starting anything.
    """

    description = build_launch_description(backend=backend, pick_place=pick_place)
    context = LaunchContext()
    for action in description.entities:
        if isinstance(action, DeclareLaunchArgument):
            context.launch_configurations[action.name] = action.default_value[0].perform(context)
    context.launch_configurations.update({"run_mode": "execute", "execute": "true"})
    configured = next(
        action for action in description.entities if isinstance(action, OpaqueFunction)
    )
    return list(configured.execute(context)), context


def _walk(actions):
    """Every action in the graph, including the children of the timers that delay them."""

    for action in actions:
        yield action
        children = getattr(action, "actions", None)
        if isinstance(children, (list, tuple)):
            yield from _walk(children)


def _shape(actions) -> list[tuple]:
    return [
        (type(action).__name__, getattr(action, "node_executable", None),
         getattr(action, "period", None))
        for action in actions
    ]


def _handlers(actions):
    return [action.event_handler for action in actions if isinstance(action, RegisterEventHandler)]


def _exited(action, returncode: int = 0) -> ProcessExited:
    return ProcessExited(
        action=action, name=str(getattr(action, "node_executable", "process")),
        cmd=[str(getattr(action, "node_executable", "process"))], cwd=None, env=None,
        pid=4242, returncode=returncode,
    )


def _emitted(actions, event, context):
    """What the graph does when ``event`` happens: every matching handler's own answer."""

    emitted = []
    for handler in _handlers(actions):
        if handler.matches(event):
            emitted.extend(handler.handle(event, context) or [])
    return emitted


def _only_node(emitted, executable: str) -> Node:
    """The single node of that name the graph emits, or a failure naming what it emitted instead."""

    nodes = [
        action for action in emitted
        if isinstance(action, Node) and action.node_executable == executable
    ]
    assert len(nodes) == 1, (executable, [(type(item).__name__, item) for item in emitted])
    return nodes[0]


def test_launchers_exist_are_thin_and_do_not_declare_backend_argument() -> None:
    for name in LAUNCHERS:
        path = LAUNCH_ROOT / name
        source = path.read_text(encoding="utf-8")
        assert 'DeclareLaunchArgument("backend"' not in source
        assert "build_launch_description" in source
        spec = importlib.util.spec_from_file_location(name.replace(".", "_"), path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        assert module.generate_launch_description() is not None


def test_common_arguments_and_backend_specific_asset_arguments() -> None:
    for backend in ("mujoco", "gazebo"):
        declared = _declared(build_launch_description(backend=backend, pick_place=True))
        assert COMMON_ARGUMENTS <= declared
        assert "backend" not in declared
        if backend == "mujoco":
            assert "mujoco_scene" in declared
            assert "gazebo_world" not in declared
        else:
            assert "gazebo_world" in declared
            assert "mujoco_scene" not in declared


def test_default_readiness_budget_covers_macos_source_build_startup() -> None:
    description = build_launch_description(backend="mujoco", pick_place=False)
    argument = next(
        action
        for action in description.entities
        if isinstance(action, DeclareLaunchArgument) and action.name == "readiness_timeout_s"
    )

    assert float(argument.default_value[0].perform(LaunchContext())) >= 90.0


def test_mujoco_scene_setup_receives_the_launch_readiness_budget() -> None:
    context = LaunchContext()
    context.launch_configurations.update(
        {
            "mujoco_scene": str(PACKAGE_ROOT / "assets/mujoco/scene.xml"),
            "mujoco_initial_keyframe": "task_start",
            "headless": "true",
            "readiness_timeout_s": "123.0",
        }
    )
    stack = launch_composition._mujoco_stack_actions(context, PACKAGE_ROOT, "readiness-session")
    scene_setup = stack.scene_setup

    assert evaluate_parameters(context, scene_setup._Node__parameters) == (
        {"readiness_timeout_s": 123.0},
    )


def test_pick_place_toggle_changes_only_the_workflow_gate() -> None:
    """Both forms declare the same arguments and build the same stack, up to the workflow gate."""

    assert _declared(build_launch_description(backend="gazebo", pick_place=False)) == _declared(
        build_launch_description(backend="gazebo", pick_place=True)
    )

    stack, _ = _execute_actions("gazebo", pick_place=False)
    with_workflow, _ = _execute_actions("gazebo", pick_place=True)

    assert _shape(with_workflow)[: len(stack)] == _shape(stack)
    assert _shape(with_workflow)[len(stack):] == [
        ("TimerAction", None, 8.0),  # the delayed readiness probe
        ("RegisterEventHandler", None, None),  # readiness -> scene setup
        ("RegisterEventHandler", None, None),  # scene setup -> workflow
        ("RegisterEventHandler", None, None),  # workflow -> shutdown
    ]


def test_gazebo_workflow_is_gated_by_the_readiness_and_scene_events() -> None:
    """Readiness releases scene setup, scene setup releases the workflow, the workflow shuts down."""

    actions, context = _execute_actions("gazebo", pick_place=True)

    readiness = [
        action for action in _walk(actions)
        if getattr(action, "node_executable", None) == "motion_stack_ready"
    ]
    assert len(readiness) == 1, _shape(list(_walk(actions)))
    # One gate per phase boundary, and each one is a process-exit binding rather than a delay.
    handlers = _handlers(actions)
    assert len(handlers) == 3, handlers
    assert all(isinstance(handler, OnProcessExit) for handler in handlers), handlers
    scene_setup = _only_node(_emitted(actions, _exited(readiness[0]), context), "scene_setup")
    workflow = _only_node(_emitted(actions, _exited(scene_setup), context), "gazebo_execute")

    shutdowns = [
        action for action in _emitted(actions, _exited(workflow), context)
        if isinstance(action, Shutdown)
    ]
    assert len(shutdowns) == 1, shutdowns
    assert shutdowns[0].event.reason == "Gazebo execute complete"


def test_gazebo_phase_failure_propagates_with_the_phase_that_failed() -> None:
    """A gate whose process exits non-zero stops the launch and names its own phase."""

    actions, context = _execute_actions("gazebo", pick_place=True)
    readiness = next(
        action for action in _walk(actions)
        if getattr(action, "node_executable", None) == "motion_stack_ready"
    )
    scene_setup = _only_node(_emitted(actions, _exited(readiness), context), "scene_setup")

    def reasons(action):
        return [
            emitted.event.reason
            for emitted in _emitted(actions, _exited(action, returncode=1), context)
            if isinstance(emitted, EmitEvent)
        ]

    assert reasons(readiness) == ["Gazebo readiness failed with exit code 1"]
    assert reasons(scene_setup) == ["Gazebo Planning Scene setup failed with exit code 1"]


def test_gazebo_stack_without_pick_place_installs_no_workflow_gate() -> None:
    """The stack itself keeps no workflow node, no gate handler and no fixed late start."""

    actions, context = _execute_actions("gazebo", pick_place=False)

    assert _handlers(actions) == []
    assert not {
        "motion_stack_ready", "scene_setup", "gazebo_execute",
    } & {getattr(action, "node_executable", None) for action in _walk(actions)}
    assert [action for action in _walk(actions) if getattr(action, "period", None) == 12.0] == []


def test_mujoco_sensor_rendering_is_independent_from_headless_viewer() -> None:
    share = PACKAGE_ROOT

    headless_rgbd = launch_composition._render_mujoco_robot_description(
        share,
        "scene.xml",
        headless=True,
        sensor_rendering=True,
        platform_name="darwin",
    )
    headless_physics_only = launch_composition._render_mujoco_robot_description(
        share,
        "scene.xml",
        headless=True,
        sensor_rendering=False,
        platform_name="darwin",
    )
    linux_interactive = launch_composition._render_mujoco_robot_description(
        share,
        "scene.xml",
        headless=False,
        sensor_rendering=True,
        platform_name="linux",
    )
    macos_interactive = launch_composition._render_mujoco_robot_description(
        share,
        "scene.xml",
        headless=False,
        sensor_rendering=True,
        platform_name="darwin",
    )

    assert '<param name="headless">true</param>' in headless_rgbd
    assert '<param name="disable_rendering">false</param>' in headless_rgbd
    assert '<param name="disable_rendering">true</param>' in headless_physics_only
    assert '<param name="disable_rendering">false</param>' in linux_interactive
    assert '<param name="disable_rendering">false</param>' in macos_interactive


def test_mujoco_robot_description_renders_explicit_simulation_speed_factor() -> None:
    rendered = launch_composition._render_mujoco_robot_description(
        PACKAGE_ROOT,
        "scene.xml",
        headless=True,
        sensor_rendering=True,
        sim_speed_factor=1.0,
    )

    assert '<param name="sim_speed_factor">1.0</param>' in rendered


def test_perception_launch_defaults_sensor_rendering_on_for_headless_rgbd() -> None:
    description = launch_composition.build_perception_pick_place_launch_description()
    sensor_rendering = next(
        action
        for action in description.entities
        if isinstance(action, DeclareLaunchArgument) and action.name == "sensor_rendering"
    )

    assert sensor_rendering.default_value[0].perform(LaunchContext()) == "true"


def test_task_station_declares_both_headless_profiles_but_keeps_visible_default() -> None:
    description = launch_composition.build_task_station_launch_description()
    arguments = {
        action.name: action
        for action in description.entities
        if isinstance(action, DeclareLaunchArgument)
    }

    assert arguments["headless"].choices == ("true", "false")
    assert arguments["headless"].default_value[0].perform(LaunchContext()) == "false"
    assert arguments["sensor_rendering"].choices == ("true",)


def test_perception_launch_declares_the_grounded_sam_backend_contract() -> None:
    description = launch_composition.build_perception_pick_place_launch_description()
    arguments = {
        action.name: action
        for action in description.entities
        if isinstance(action, DeclareLaunchArgument)
    }

    assert arguments["perception_backend"].choices == (
        "color_geometry",
        "yolo_seg",
        "grounded_sam",
    )
    assert {
        "grounding_box_threshold": "0.35",
        "grounding_text_threshold": "0.25",
        "grounding_duplicate_iou": "0.85",
        "grounding_max_candidates": "16",
        "sam_mask_quality_threshold": "0.75",
        "sam_min_mask_pixels": "64",
        "sam_max_mask_area_ratio": "0.50",
    } == {
        name: argument.default_value[0].perform(LaunchContext())
        for name, argument in arguments.items()
        if name
        in {
            "grounding_box_threshold",
            "grounding_text_threshold",
            "grounding_duplicate_iou",
            "grounding_max_candidates",
            "sam_mask_quality_threshold",
            "sam_min_mask_pixels",
            "sam_max_mask_area_ratio",
        }
    }
    assert {
        "perception_model_root",
        "perception_model_manifest_sha256",
        "grounding_box_threshold",
        "grounding_text_threshold",
        "grounding_duplicate_iou",
        "grounding_max_candidates",
        "sam_mask_quality_threshold",
        "sam_min_mask_pixels",
        "sam_max_mask_area_ratio",
    } <= arguments.keys()


def test_mujoco_launch_declares_and_renders_selected_initial_keyframe() -> None:
    description = build_launch_description(backend="mujoco", pick_place=False)
    declared = _declared(description)
    assert "mujoco_initial_keyframe" in declared

    rendered = launch_composition._render_mujoco_robot_description(
        PACKAGE_ROOT,
        str(PACKAGE_ROOT / "assets/mujoco/scene.xml"),
        headless=False,
        initial_keyframe="cup_test_left_5cm",
    )
    assert '<param name="initial_keyframe">cup_test_left_5cm</param>' in rendered


def test_mujoco_launch_accepts_v5_multi_object_acceptance_keyframes() -> None:
    scene = PACKAGE_ROOT / "assets/mujoco/v5_multi_object_scene.xml"

    for keyframe in ("v5_no_cup", "v5_two_cups", "v5_cup_near_bottle"):
        rendered = launch_composition._render_mujoco_robot_description(
            PACKAGE_ROOT,
            str(scene),
            headless=True,
            sensor_rendering=True,
            initial_keyframe=keyframe,
        )
        assert f'<param name="initial_keyframe">{keyframe}</param>' in rendered


def test_fixed_mujoco_composition_still_selects_only_the_fixed_workflow() -> None:
    context = LaunchContext()
    context.launch_configurations.update(
        {
            "mujoco_scene": str(PACKAGE_ROOT / "assets/mujoco/scene.xml"),
            "mujoco_initial_keyframe": "task_start",
            "headless": "true",
            "readiness_timeout_s": "90.0",
            "evidence_file": "/tmp/fixed-regression.json",
        }
    )

    actions = launch_composition._mujoco_execute_actions(
        context,
        PACKAGE_ROOT,
        SimpleNamespace(path=PACKAGE_ROOT / "config/motion_policy.yaml"),
        "fixed-session",
        include_workflow=True,
    )
    scene_setup = next(
        action for action in actions if getattr(action, "node_executable", None) == "scene_setup"
    )
    event = ProcessExited(
        action=scene_setup,
        name="scene_setup",
        cmd=["scene_setup"],
        cwd=None,
        env=None,
        pid=202,
        returncode=0,
    )
    gated_actions = []
    for action in actions:
        if not isinstance(action, RegisterEventHandler):
            continue
        handler = action.event_handler
        if handler.matches(event):
            gated_actions.extend(handler.handle(event, context) or [])
    executables = [getattr(action, "node_executable", None) for action in gated_actions]

    assert executables.count("fixed_cup_pick_place") == 1
    assert "dynamic_cup_pick_place" not in executables
    assert "rgbd_cup_pose" not in executables


def test_fixed_mujoco_composition_preserves_simulator_exit_shutdown() -> None:
    context = LaunchContext()
    context.launch_configurations.update(
        {
            "mujoco_scene": str(PACKAGE_ROOT / "assets/mujoco/scene.xml"),
            "mujoco_initial_keyframe": "task_start",
            "headless": "true",
            "readiness_timeout_s": "90.0",
            "evidence_file": "/tmp/fixed-simulator-shutdown.json",
        }
    )
    actions = launch_composition._mujoco_execute_actions(
        context,
        PACKAGE_ROOT,
        SimpleNamespace(path=PACKAGE_ROOT / "config/motion_policy.yaml"),
        "fixed-session",
        include_workflow=True,
    )
    simulator = next(
        action
        for action in actions
        if getattr(action, "node_executable", None) == "ros2_control_node"
    )
    event = ProcessExited(
        action=simulator,
        name="ros2_control_node",
        cmd=["ros2_control_node"],
        cwd=None,
        env=None,
        pid=203,
        returncode=0,
    )
    emitted = []
    for action in actions:
        if isinstance(action, RegisterEventHandler) and action.event_handler.matches(event):
            emitted.extend(action.event_handler.handle(event, context) or [])

    shutdowns = [action for action in emitted if isinstance(action, Shutdown)]
    assert len(shutdowns) == 1
    assert shutdowns[0].event.reason == "MuJoCo runtime exited"
