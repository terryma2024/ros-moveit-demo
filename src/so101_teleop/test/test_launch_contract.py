import importlib.util
from pathlib import Path

from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.utilities import perform_substitutions
from launch_ros.actions import Node


PACKAGE = Path(__file__).resolve().parents[1]
LAUNCH = PACKAGE / "launch" / "so101_teleop.launch.py"


def load_launch_module():
    spec = importlib.util.spec_from_file_location("standalone_so101_teleop_launch", LAUNCH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_launch_requires_explicit_backend_and_defers_server_node():
    description = load_launch_module().generate_launch_description()
    arguments = {
        entity.name: entity
        for entity in description.entities
        if isinstance(entity, DeclareLaunchArgument)
    }

    assert arguments["backend"].default_value is None
    assert any(isinstance(entity, OpaqueFunction) for entity in description.entities)
    assert not any(isinstance(entity, Node) for entity in description.entities)


def test_launch_starts_new_package_and_freezes_backend_environment(monkeypatch, tmp_path):
    module = load_launch_module()
    source = tmp_path / "web"
    source.mkdir()
    (source / "package.json").write_text("{}")
    dist = source / "dist"
    dist.mkdir()
    monkeypatch.setattr(module, "ensure_web_bundle", lambda *_args: dist)
    context = LaunchContext()
    context.launch_configurations.update({
        "backend": "gazebo_cpp",
        "bind_address": "127.0.0.1",
        "port": "8000",
        "world_name": "world",
        "tcp_frame": "tcp",
        "simulation_session_id": "session-a",
        "gz_partition": "partition-a",
        "web_source_dir": str(source),
        "build_web_if_needed": "true",
    })

    nodes = module.launch_setup(context)

    assert len(nodes) == 1
    node = nodes[0]
    assert node.node_package == "so101_teleop"
    assert node.node_executable == "so101_teleop_server.py"
    process = vars(node)["_ExecuteLocal__process_description"]
    environment = {
        perform_substitutions(context, key): perform_substitutions(context, value)
        for key, value in vars(process)["_Executable__additional_env"]
    }
    assert environment["SO101_TELEOP_BACKEND"] == "gazebo_cpp"
    assert environment["SO101_TELEOP_WEB_ROOT"] == str(dist)
