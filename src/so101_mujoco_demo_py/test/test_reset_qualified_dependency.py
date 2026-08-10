from __future__ import annotations

import hashlib
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

import pytest
import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = PACKAGE_ROOT / "config" / "dependency-lock.yaml"
PATCH_PATH = PACKAGE_ROOT / "patches" / "mujoco_ros2_control-0.0.3-reset-hook.patch"
BUILD_PATH = PACKAGE_ROOT / "scripts" / "build_reset_qualified_overlay.sh"
CHECK_PATH = PACKAGE_ROOT / "scripts" / "check_reset_qualified_runtime.py"
UPSTREAM = "https://github.com/ros-controls/mujoco_ros2_control"
COMMIT = "35ba8174b62d9560093614f981a3d4b978a96036"
OVERLAY = "/data/work/ws_mujoco_ros2_control_003/install"


def _lock() -> dict:
    return yaml.safe_load(LOCK_PATH.read_text(encoding="utf-8"))


def test_lock_pins_reset_qualified_source_and_patch() -> None:
    lock = _lock()
    assert lock["provider"] == "patched_source"
    assert lock["release"] == "0.0.3"
    assert lock["upstream"]["url"] == UPSTREAM
    assert lock["upstream"]["tag"] == "0.0.3"
    assert lock["upstream"]["commit"] == COMMIT
    assert lock["prefix"] == OVERLAY
    assert lock["patch"]["path"] == str(PATCH_PATH.relative_to(PACKAGE_ROOT))
    assert lock["patch"]["sha256"] == hashlib.sha256(PATCH_PATH.read_bytes()).hexdigest()


def test_lock_declares_exact_prefix_and_source_order() -> None:
    lock = _lock()
    assert lock["source_order"] == [
        "/opt/ros/jazzy",
        OVERLAY,
        "project_install",
    ]
    assert lock["package_prefixes"] == {
        "mujoco_ros2_control": OVERLAY,
        "mujoco_ros2_control_msgs": OVERLAY,
        "mujoco_ros2_control_plugins": OVERLAY,
        "mujoco_vendor": "/opt/ros/jazzy",
    }
    assert lock["project_package_prefixes"] == {
        "so101_mujoco_support": str(PACKAGE_ROOT.parents[1] / "install/so101_mujoco_support"),
        "so101_mujoco_demo_py": str(PACKAGE_ROOT.parents[1] / "install/so101_mujoco_demo_py"),
    }


@pytest.mark.parametrize("path", [PATCH_PATH, BUILD_PATH, CHECK_PATH])
def test_replay_artifact_exists(path: Path) -> None:
    assert path.is_file(), path


def test_patch_is_minimal_and_adds_compatible_reset_hook() -> None:
    patch = PATCH_PATH.read_text(encoding="utf-8")
    assert "virtual void on_reset() {}" in patch
    assert "reset_simulation_state" in patch
    assert "plugin->on_reset()" in patch
    assert "main" not in patch
    changed = [line for line in patch.splitlines() if line.startswith("+++ b/")]
    assert changed
    assert all(
        path.endswith(("mujoco_ros2_control_plugins_base.hpp", "mujoco_system_interface.cpp"))
        for path in changed
    )


def test_build_script_is_pinned_and_never_overwrites_underlay() -> None:
    script = BUILD_PATH.read_text(encoding="utf-8")
    assert UPSTREAM in script
    assert COMMIT in script
    assert 'dependency_root="/data/work/ws_mujoco_ros2_control_003"' in script
    assert 'source_dir="${dependency_root}/src/mujoco_ros2_control"' in script
    assert f"--install-base {OVERLAY}" in script
    assert "git reset" not in script
    assert "git clean" not in script
    assert "main" not in script
    assert "--install-base /opt/ros/jazzy" not in script


def test_patch_replays_and_places_hook_only_after_successful_central_reset() -> None:
    source = Path(_lock()["source_checkout"])
    archive = subprocess.run(
        ["git", "-C", str(source), "archive", COMMIT],
        check=True,
        capture_output=True,
    ).stdout
    with tempfile.TemporaryDirectory() as raw_temp:
        root = Path(raw_temp)
        archive_path = root / "source.tar"
        archive_path.write_bytes(archive)
        with tarfile.open(archive_path) as stream:
            stream.extractall(root, filter="data")
        subprocess.run(
            ["git", "apply", "--unidiff-zero", "--check", str(PATCH_PATH)], cwd=root, check=True
        )
        subprocess.run(["git", "apply", "--unidiff-zero", str(PATCH_PATH)], cwd=root, check=True)
        implementation = (root / "mujoco_ros2_control/src/mujoco_system_interface.cpp").read_text(
            encoding="utf-8"
        )
        central = implementation.split(
            "void MujocoSystemInterface::reset_simulation_state", maxsplit=1
        )[1].split("void MujocoSystemInterface::reset_world_callback", maxsplit=1)[0]
        callback = implementation.split(
            "void MujocoSystemInterface::reset_world_callback", maxsplit=1
        )[1].split("void MujocoSystemInterface::set_pause_callback", maxsplit=1)[0]
        assert central.count("plugin->on_reset();") == 1
        assert central.index("plugin->on_reset();") > central.index(
            "joint.effort_interface.command_ = 0.0;"
        )
        assert callback.index("return;") < callback.index(
            "reset_simulation_state(fill_initial_state);"
        )
        assert callback.index("reset_simulation_state(fill_initial_state);") < callback.index(
            "response->success = true;"
        )


def test_runtime_checker_fails_without_qualified_environment() -> None:
    environment = dict(os.environ)
    environment["AMENT_PREFIX_PATH"] = "/opt/ros/jazzy"
    result = subprocess.run(
        ["python3", str(CHECK_PATH), "--lock", str(LOCK_PATH), "--check-only"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode != 0
    assert result.stdout or result.stderr
