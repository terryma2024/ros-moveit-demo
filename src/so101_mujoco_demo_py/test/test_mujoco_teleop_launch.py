import importlib.util
from pathlib import Path

from launch.actions import IncludeLaunchDescription

PACKAGE = Path(__file__).resolve().parents[1]
LAUNCH = PACKAGE / "launch/so101_mujoco_teleop.launch.py"


def load_module():
    spec = importlib.util.spec_from_file_location("so101_mujoco_teleop_launch", LAUNCH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_integrated_launch_owns_runtime_and_teleop_with_one_session(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(
        module,
        "get_package_share_directory",
        lambda package: str(PACKAGE if package == "so101_mujoco_demo_py" else PACKAGE),
    )

    description = module.generate_launch_description()
    includes = [
        action for action in description.entities if isinstance(action, IncludeLaunchDescription)
    ]

    assert len(includes) == 2
    source = LAUNCH.read_text(encoding="utf-8")
    assert '"launch_workflow": "false"' in source
    assert '"backend": "mujoco_py"' in source
    assert source.count('session_id = LaunchConfiguration("simulation_session_id")') == 1
