import importlib.util
from pathlib import Path

from launch.actions import DeclareLaunchArgument
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
