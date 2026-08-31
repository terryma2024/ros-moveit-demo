import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace

from launch.actions import DeclareLaunchArgument, RegisterEventHandler, Shutdown
from launch.events.process import ProcessExited
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


def test_pick_place_toggle_changes_only_workflow_launch() -> None:
    stack = _declared(build_launch_description(backend="mujoco", pick_place=False))
    workflow = _declared(build_launch_description(backend="mujoco", pick_place=True))
    assert stack == workflow


def test_stack_launcher_does_not_embed_workflow_or_shutdown_handler() -> None:
    source = inspect.getsource(launch_composition._configured_actions)

    assert "include_workflow=pick_place" in source


def test_gazebo_workflow_is_event_gated_by_readiness_and_scene() -> None:
    source = inspect.getsource(launch_composition._gazebo_execute_actions)
    assert 'executable="motion_stack_ready"' in source
    assert 'executable="scene_setup"' in source
    assert 'executable="gazebo_execute"' in source
    assert source.count("OnProcessExit(") >= 3
    assert "TimerAction(period=12.0" not in source


def test_gazebo_stack_without_pick_place_has_no_workflow_gate() -> None:
    source = inspect.getsource(launch_composition._configured_actions)
    assert "include_workflow=pick_place" in source


def test_launch_source_reports_first_gazebo_phase_failure() -> None:
    source = inspect.getsource(launch_composition._gazebo_execute_actions)
    assert '"Gazebo readiness"' in source
    assert '"Gazebo Planning Scene setup"' in source
    assert "TimerAction(period=12.0" not in source


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
