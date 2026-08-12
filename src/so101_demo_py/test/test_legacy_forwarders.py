"""Compatibility-window contracts for the two deprecated demo packages."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[2]


def _load(path: Path, name: str):
    pick_place = SimpleNamespace(main=lambda _arguments: 0)
    qualification = SimpleNamespace(main=lambda: 0)
    scene_setup = SimpleNamespace(main=lambda: 0)
    modules = {
        "so101_demo": ModuleType("so101_demo"),
        "so101_demo.cli": ModuleType("so101_demo.cli"),
        "so101_demo.backends": ModuleType("so101_demo.backends"),
        "so101_demo.backends.mujoco": ModuleType("so101_demo.backends.mujoco"),
        "so101_demo.backends.mujoco.qualified_phases": ModuleType(
            "so101_demo.backends.mujoco.qualified_phases"
        ),
    }
    modules["so101_demo.cli"].pick_place = pick_place
    modules["so101_demo.cli"].qualification = qualification
    modules["so101_demo.backends.mujoco.qualified_phases"].scene_setup = scene_setup
    sys.modules.update(modules)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("path", "backend"),
    [
        (
            SOURCE_ROOT / "so101_mujoco_demo_py/so101_mujoco_demo_py/forwarder.py",
            "mujoco",
        ),
        (SOURCE_ROOT / "so101_gazebo_demo_py/src/forwarder.py", "gazebo"),
    ],
)
def test_old_entry_forwards_to_unified_cli_once(path, backend, monkeypatch):
    module = _load(path, f"legacy_{backend}_forwarder")
    received: list[list[str]] = []
    monkeypatch.setattr(module.pick_place, "main", lambda argv: received.append(argv) or 0)

    with pytest.warns(DeprecationWarning, match="use so101_demo_py") as warnings:
        assert module.main(["--mode", "dry_run", "--session-id", "compat"]) == 0

    assert len(warnings) == 1
    assert received == [
        ["--backend", backend, "--mode", "dry_run", "--session-id", "compat"]
    ]


def test_gazebo_unmappable_argument_is_rejected():
    module = _load(
        SOURCE_ROOT / "so101_gazebo_demo_py/src/forwarder.py",
        "legacy_gazebo_rejection",
    )

    with pytest.raises(SystemExit, match="cannot map legacy argument --live-runtime"):
        module.main(["--live-runtime"])


@pytest.mark.parametrize(
    ("package", "old_name", "new_name"),
    [
        ("so101_mujoco_demo_py", "so101_mujoco.launch.py", "so101_mujoco.launch.py"),
        (
            "so101_mujoco_demo_py",
            "so101_pick_place.launch.py",
            "so101_mujoco_pick_place.launch.py",
        ),
        ("so101_gazebo_demo_py", "so101_gazebo.launch.py", "so101_gazebo.launch.py"),
        (
            "so101_gazebo_demo_py",
            "so101_pick_place.launch.py",
            "so101_gazebo_pick_place.launch.py",
        ),
    ],
)
def test_old_launch_includes_unified_launcher(package, old_name, new_name):
    text = (SOURCE_ROOT / package / "launch" / old_name).read_text(encoding="utf-8")
    assert 'get_package_share_directory("so101_demo_py")' in text
    assert new_name in text
    assert "IncludeLaunchDescription" in text
