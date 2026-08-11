from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = PROJECT_ROOT / "src/so101_mujoco_demo_py"
SUBMODULE = PROJECT_ROOT / "third_party/mujoco_ros2_control"
INSTALLER = PROJECT_ROOT / "scripts/install-mujoco-ros2-control.zsh"
LOCK = PACKAGE_ROOT / "config/dependency-lock.yaml"
OFFICIAL_BASE = "35ba8174b62d9560093614f981a3d4b978a96036"
APPROVED_ORIGIN = "git@gitee.com:zjumty/mujoco_ros2_control.git"
APPROVED_TAG = "so101-0.0.3-r1"


def run(*command: str | Path, cwd: Path = PROJECT_ROOT, env=None):
    return subprocess.run(
        [str(part) for part in command],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


def test_fork_submodule_has_approved_origin_base_tag_and_clean_status() -> None:
    assert (
        run("git", "-C", SUBMODULE, "remote", "get-url", "origin").stdout.strip() == APPROVED_ORIGIN
    )
    assert (
        run("git", "-C", SUBMODULE, "merge-base", "--is-ancestor", OFFICIAL_BASE, "HEAD").returncode
        == 0
    )
    head = run("git", "-C", SUBMODULE, "rev-parse", "HEAD").stdout.strip()
    assert run("git", "-C", SUBMODULE, "rev-list", "-n", "1", APPROVED_TAG).stdout.strip() == head
    assert (
        run("git", "-C", SUBMODULE, "status", "--porcelain", "--untracked-files=all").stdout == ""
    )
    assert (
        run(
            "git",
            "config",
            "-f",
            PROJECT_ROOT / ".gitmodules",
            "--get",
            "submodule.third_party/mujoco_ros2_control.url",
        ).stdout.strip()
        == APPROVED_ORIGIN
    )


def test_installer_has_no_destructive_or_underlay_install_commands() -> None:
    script = INSTALLER.read_text(encoding="utf-8")
    assert "git reset" not in script
    assert "git clean" not in script
    assert "--install-base /opt/ros/jazzy" not in script
    assert "/data/work/ws_mujoco_ros2_control_003" not in script
    assert "/data/work/ws_mujoco_ros2_control_fork" not in script
    assert "SO101_WORKSPACE_DIR" in script
    assert "setup.bash" not in script


def test_installer_disables_nounset_while_sourcing_generated_ros_setups() -> None:
    script = INSTALLER.read_text(encoding="utf-8")
    assert "source_setup()" in script
    assert 'set +u\n  source "$1"\n  set -u' in script


def prepare_installer_fixture(tmp_path: Path, checkout_ref: str) -> tuple[Path, Path]:
    project = tmp_path / "project"
    scripts = project / "scripts"
    config = project / "src/so101_mujoco_demo_py/config"
    checkout = project / "third_party/mujoco_ros2_control"
    scripts.mkdir(parents=True)
    config.mkdir(parents=True)
    checkout.parent.mkdir(parents=True)
    shutil.copy2(INSTALLER, scripts / INSTALLER.name)
    shutil.copy2(LOCK, config / LOCK.name)
    (project / ".gitmodules").write_text(
        '[submodule "third_party/mujoco_ros2_control"]\n'
        "\tpath = third_party/mujoco_ros2_control\n"
        f"\turl = {APPROVED_ORIGIN}\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "clone", "--quiet", "--shared", str(SUBMODULE), str(checkout)], check=True
    )
    subprocess.run(["git", "-C", str(checkout), "checkout", "--quiet", checkout_ref], check=True)
    subprocess.run(
        ["git", "-C", str(checkout), "remote", "set-url", "origin", APPROVED_ORIGIN], check=True
    )
    return project, checkout


def installer_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "colcon-called"
    fake_colcon = fake_bin / "colcon"
    fake_colcon.write_text(
        f'#!/usr/bin/env zsh\nprint -r -- "$*" >> {marker}\nexit 7\n',
        encoding="utf-8",
    )
    fake_colcon.chmod(0o755)
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    return environment, marker


@pytest.mark.parametrize("source_state", ["dirty", "wrong-commit"])
def test_installer_rejects_invalid_source_before_colcon(tmp_path: Path, source_state: str) -> None:
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    checkout_ref = (
        lock["fork"]["commit"] if source_state == "dirty" else f"{lock['fork']['commit']}^"
    )
    project, checkout = prepare_installer_fixture(tmp_path, checkout_ref)
    if source_state == "dirty":
        (checkout / "unexpected.txt").write_text("dirty\n", encoding="utf-8")
    environment, marker = installer_environment(tmp_path)

    result = run(project / "scripts" / INSTALLER.name, cwd=project, env=environment)

    assert result.returncode != 0
    assert not marker.exists()
    assert source_state.split("-")[0] in result.stderr.lower()


def test_installer_clean_qualified_source_reaches_colcon(tmp_path: Path) -> None:
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    project, _ = prepare_installer_fixture(tmp_path, lock["fork"]["commit"])
    environment, marker = installer_environment(tmp_path)

    result = run(project / "scripts" / INSTALLER.name, cwd=project, env=environment)

    assert result.returncode == 7
    assert marker.is_file()


def test_installer_derives_overlay_from_workspace_environment(tmp_path: Path) -> None:
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    project, _ = prepare_installer_fixture(tmp_path, lock["fork"]["commit"])
    environment, marker = installer_environment(tmp_path)
    workspace = tmp_path / "custom-workspace"
    environment["SO101_WORKSPACE_DIR"] = str(workspace)

    result = run(project / "scripts" / INSTALLER.name, cwd=project, env=environment)

    assert result.returncode == 7
    invocation = marker.read_text(encoding="utf-8")
    fork_workspace = workspace / "ws_mujoco_ros2_control_fork"
    assert f"--build-base {fork_workspace / 'build'}" in invocation
    assert f"--install-base {fork_workspace / 'install'}" in invocation
    assert f"--log-base {fork_workspace / 'log'}" in invocation


def test_installer_defaults_workspace_to_checkout_parent(tmp_path: Path) -> None:
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    project, _ = prepare_installer_fixture(tmp_path, lock["fork"]["commit"])
    environment, marker = installer_environment(tmp_path)
    environment.pop("SO101_WORKSPACE_DIR", None)

    result = run(project / "scripts" / INSTALLER.name, cwd=project, env=environment)

    assert result.returncode == 7
    invocation = marker.read_text(encoding="utf-8")
    fork_workspace = project.parent / "ws_mujoco_ros2_control_fork"
    assert f"--install-base {fork_workspace / 'install'}" in invocation
