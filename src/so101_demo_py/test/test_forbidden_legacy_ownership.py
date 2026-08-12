"""Legacy packages may retain forwarding surfaces, never runtime ownership."""

from __future__ import annotations

from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_TOP_LEVEL = {
    "launch",
    "package.xml",
    "resource",
    "setup.cfg",
    "setup.py",
    "so101_mujoco_demo_py",
    "src",
}
ALLOWED_PYTHON_FILES = {"__init__.py", "forwarder.py"}


@pytest.mark.parametrize("package", ["so101_mujoco_demo_py", "so101_gazebo_demo_py"])
def test_legacy_packages_own_no_runtime_assets_or_tests(package):
    root = SOURCE_ROOT / package
    forbidden = sorted(path.name for path in root.iterdir() if path.name not in ALLOWED_TOP_LEVEL)
    assert forbidden == []


@pytest.mark.parametrize(
    "python_root",
    [
        SOURCE_ROOT / "so101_mujoco_demo_py/so101_mujoco_demo_py",
        SOURCE_ROOT / "so101_gazebo_demo_py/src",
    ],
)
def test_legacy_python_tree_contains_only_forwarder(python_root):
    owned = sorted(
        str(path.relative_to(python_root))
        for path in python_root.rglob("*.py")
        if "__pycache__" not in path.parts and path.name not in ALLOWED_PYTHON_FILES
    )
    assert owned == []


def test_unified_package_never_imports_legacy_packages():
    unified = SOURCE_ROOT / "so101_demo_py/src"
    offenders = []
    for path in unified.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "from so101_mujoco_demo_py" in text or "from so101_gazebo_demo_py" in text:
            offenders.append(str(path.relative_to(unified)))
        if "import so101_mujoco_demo_py" in text or "import so101_gazebo_demo_py" in text:
            offenders.append(str(path.relative_to(unified)))
    assert offenders == []


def test_teleop_mujoco_profile_names_unified_runtime_owner():
    profile = SOURCE_ROOT / "so101_teleop/config/backends/mujoco_py.yaml"
    text = profile.read_text(encoding="utf-8")

    assert "so101_mujoco_demo_py" not in text
    assert "owner_package: so101_demo_py" in text
