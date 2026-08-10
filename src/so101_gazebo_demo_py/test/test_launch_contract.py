import importlib.util
from pathlib import Path

from launch import LaunchContext, LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.utilities import perform_substitutions
from launch_ros.actions import Node
from so101_gazebo_demo.gazebo.model_asset import materialize_prepared_model


PACKAGE = Path(__file__).parents[1]
LAUNCH_NAMES = (
    "so101_display.launch.py", "so101_controller.launch.py",
    "so101_gazebo.launch.py", "so101_move_group_headless.launch.py",
    "so101_moveit.launch.py",
)


def load(name: str) -> LaunchDescription:
    path = PACKAGE / "launch" / name
    spec = importlib.util.spec_from_file_location(name.replace(".", "_"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.generate_launch_description()
    assert isinstance(result, LaunchDescription)
    return result


def test_all_public_stack_launches_generate() -> None:
    for name in LAUNCH_NAMES:
        assert list(load(name).entities)


def test_gazebo_headless_default_is_false() -> None:
    arguments = {
        entity.name: perform_substitutions(LaunchContext(), entity.default_value)
        for entity in load("so101_gazebo.launch.py").entities
        if isinstance(entity, DeclareLaunchArgument)
    }
    assert arguments["headless"] == "false"
    assert arguments["controller_config"].endswith(
        "/config/so101_controllers_physical_outcome.yaml"
    )


def test_gazebo_spawn_uses_calibrated_collision_model() -> None:
    source = (PACKAGE / "launch" / "so101_gazebo.launch.py").read_text()
    assert " gazebo_collision_primitives:=true" in source
    prepared = (PACKAGE / "models" / "so101_prepared.sdf").read_text()
    assert 'optimization="convex_hull"' in prepared
    assert "@SO101_PACKAGE_SHARE@/config/so101_controllers.yaml" in prepared
    assert "model://so101_gazebo_demo_py/" in prepared
    assert "model://so101_gazebo_demo_cpp/" not in prepared
    assert "libso101_attachment_collision_system.so" not in prepared


def test_prepared_model_materialization_only_resolves_owned_share(tmp_path: Path) -> None:
    template = tmp_path / "template.sdf"
    output = tmp_path / "runtime.sdf"
    template.write_text(
        "<parameters>@SO101_PACKAGE_SHARE@/config/so101_controllers.yaml</parameters>"
    )
    materialize_prepared_model(
        template, Path("/owned/share/so101_gazebo_demo_py"), output,
        controller_config=Path("/safe/so101_controllers.yaml"),
    )
    assert output.read_text() == (
        "<parameters>/safe/so101_controllers.yaml</parameters>"
    )


def test_controller_launch_names_all_public_controllers() -> None:
    nodes = [entity for entity in load("so101_controller.launch.py").entities if isinstance(entity, Node)]
    arguments = {str(argument) for node in nodes for argument in (node._Node__arguments or [])}
    assert {"joint_state_broadcaster", "arm_controller", "gripper_controller"} <= arguments


def test_launches_use_only_new_package_assets() -> None:
    for name in LAUNCH_NAMES:
        text = (PACKAGE / "launch" / name).read_text()
        assert 'get_package_share_directory("so101_gazebo_demo_cpp")' not in text
        assert 'package_name="so101_gazebo_demo_cpp"' not in text
        assert "libso101_attachment_collision_system.so" not in text
