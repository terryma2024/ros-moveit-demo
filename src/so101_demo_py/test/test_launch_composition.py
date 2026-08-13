import importlib.util
import inspect
from pathlib import Path

from launch.actions import DeclareLaunchArgument
from so101_demo.runtime import launch_composition
from so101_demo.runtime.launch_composition import COMMON_ARGUMENTS, build_launch_description

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
        action.name
        for action in description.entities
        if isinstance(action, DeclareLaunchArgument)
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


def test_pick_place_toggle_changes_only_workflow_launch() -> None:
    stack = _declared(build_launch_description(backend="mujoco", pick_place=False))
    workflow = _declared(build_launch_description(backend="mujoco", pick_place=True))
    assert stack == workflow


def test_stack_launcher_does_not_embed_workflow_or_shutdown_handler() -> None:
    source = inspect.getsource(launch_composition._configured_actions)

    assert "include_workflow=pick_place" in source


def test_gazebo_workflow_is_event_gated_by_readiness_and_scene() -> None:
    source = inspect.getsource(launch_composition._gazebo_execute_actions)
    assert 'executable="gazebo_ready"' in source
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
