import ast
import subprocess
import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1] / "src" / "core"
FORBIDDEN_IMPORT_ROOTS = {"gazebo", "launch", "moveit", "mujoco", "rclpy", "ros_gz"}


def test_core_imports_no_ros_or_simulator_implementation() -> None:
    """Catch coupling the business model back to ROS, MoveIt, or a concrete simulator."""

    sources = sorted(CORE_ROOT.rglob("*.py"))
    assert sources
    violations: list[tuple[Path, str]] = []
    for source in sources:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = {node.module.split(".", 1)[0]}
            else:
                continue
            for root in roots & FORBIDDEN_IMPORT_ROOTS:
                violations.append((source.relative_to(CORE_ROOT), root))
    assert violations == []


def test_core_ports_and_ordinary_cli_do_not_eagerly_import_model_runtimes() -> None:
    """Catch making ordinary application imports require Torch or Transformers."""

    program = """
import sys
import so101_demo.core.detection
import so101_demo.ports.object_detector
import so101_demo.cli.rgbd_object_pose
heavy = {name.split('.', 1)[0] for name in sys.modules} & {'torch', 'transformers'}
assert not heavy, heavy
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
