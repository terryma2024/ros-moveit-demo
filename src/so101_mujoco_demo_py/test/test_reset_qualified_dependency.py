from __future__ import annotations

import hashlib
import os
import shutil
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


def test_patch_is_minimal_and_adds_compatible_reset_pause_snapshot_hooks() -> None:
    patch = PATCH_PATH.read_text(encoding="utf-8")
    assert "virtual void on_reset() {}" in patch
    assert "virtual void on_pause(bool paused)" in patch
    assert (
        "virtual void on_state_snapshot(const mjModel* model, const mjData* data, bool paused)"
        in patch
    )
    assert "reset_simulation_state" in patch
    assert "plugin->on_reset()" in patch
    assert "plugin->on_pause(request->paused)" in patch
    assert "refs/heads/main" not in patch
    assert "origin/main" not in patch
    changed = [line for line in patch.splitlines() if line.startswith("+++ b/")]
    assert changed
    assert set(changed) == {
        "+++ b/mujoco_ros2_control/src/mujoco_system_interface.cpp",
        "+++ b/mujoco_ros2_control/tests/test_headless_init.cpp",
        "+++ b/mujoco_ros2_control_plugins/include/mujoco_ros2_control_plugins/"
        "mujoco_ros2_control_plugins_base.hpp",
    }


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


def test_build_script_does_not_reapply_an_exact_already_applied_patch(tmp_path: Path) -> None:
    dependency_root = tmp_path / "dependency"
    source = dependency_root / "src" / "mujoco_ros2_control"
    subprocess.run(
        ["git", "clone", "--shared", str(Path(_lock()["source_checkout"])), str(source)],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "-C", str(source), "checkout", "--detach", COMMIT], check=True)
    subprocess.run(["git", "-C", str(source), "remote", "set-url", "origin", UPSTREAM], check=True)
    subprocess.run(
        ["git", "-C", str(source), "apply", "--unidiff-zero", str(PATCH_PATH)], check=True
    )

    package_root = tmp_path / "package"
    scripts = package_root / "scripts"
    patches = package_root / "patches"
    scripts.mkdir(parents=True)
    patches.mkdir()
    copied_script = scripts / BUILD_PATH.name
    script = BUILD_PATH.read_text(encoding="utf-8").replace(
        'dependency_root="/data/work/ws_mujoco_ros2_control_003"',
        f'dependency_root="{dependency_root}"',
    )
    copied_script.write_text(script, encoding="utf-8")
    copied_script.chmod(0o755)
    shutil.copy2(PATCH_PATH, patches / PATCH_PATH.name)
    install = dependency_root / "install"
    install.mkdir(parents=True)
    (install / "setup.bash").write_text("true\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_colcon = fake_bin / "colcon"
    fake_colcon.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_colcon.chmod(0o755)
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

    result = subprocess.run(
        [str(copied_script)], check=False, capture_output=True, text=True, env=environment
    )

    assert result.returncode == 0, result.stderr
    observed = subprocess.run(
        ["git", "-C", str(source), "diff", "HEAD", "--binary", "--unified=0"],
        check=True,
        capture_output=True,
    ).stdout
    assert (
        hashlib.sha256(observed).hexdigest() == hashlib.sha256(PATCH_PATH.read_bytes()).hexdigest()
    )


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


def test_patch_replays_authoritative_pause_hook_on_every_success_path() -> None:
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
        subprocess.run(["git", "apply", "--unidiff-zero", str(PATCH_PATH)], cwd=root, check=True)
        base = (
            root / "mujoco_ros2_control_plugins/include/mujoco_ros2_control_plugins/"
            "mujoco_ros2_control_plugins_base.hpp"
        ).read_text(encoding="utf-8")
        implementation = (root / "mujoco_ros2_control/src/mujoco_system_interface.cpp").read_text(
            encoding="utf-8"
        )
        callback = implementation.split(
            "void MujocoSystemInterface::set_pause_callback", maxsplit=1
        )[1].split("void MujocoSystemInterface::step_simulation_callback", maxsplit=1)[0]
        hook = "plugin->on_pause(request->paused);"
        snapshot = "plugin->on_state_snapshot(mj_model_, mj_data_, true);"
        assert "virtual void on_pause(bool paused)" in base
        assert (
            "virtual void on_state_snapshot(const mjModel* model, const mjData* data, bool paused)"
            in base
        )
        assert callback.count(hook) == 2
        assert callback.count(snapshot) == 2
        assert "plugin->update" not in callback
        idempotent = callback.split("if (currently_paused == request->paused)", maxsplit=1)[1]
        idempotent_body, changed_body = idempotent.split(
            "sim_->run = !request->paused;", maxsplit=1
        )
        assert idempotent_body.index(hook) < idempotent_body.index("response->success = true;")
        assert idempotent_body.index(hook) < idempotent_body.index(snapshot)
        assert idempotent_body.index(hook) < idempotent_body.index("return;")
        assert changed_body.index(hook) < changed_body.index("response->message =")
        assert changed_body.index(hook) < changed_body.index(snapshot)
        failure_body = callback.split("if (sim_ == nullptr", maxsplit=1)[1].split(
            "const std::unique_lock", maxsplit=1
        )[0]
        assert hook not in failure_body
        assert snapshot not in failure_body
        assert callback.index("const std::unique_lock<std::recursive_mutex> lock(*sim_mutex_);") < (
            callback.index(snapshot)
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
