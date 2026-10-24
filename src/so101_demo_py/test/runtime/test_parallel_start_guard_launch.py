"""The installed retired-measurement entry and the TextAgent launch resource.

Both are discovered through the installed prefix. The TextAgent launch resource is verified with `ros2 launch ... --show-args`, which
proves discovery only, not physical success."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from paths import REPOSITORY

WORKTREE = REPOSITORY


def _installed_prefix() -> Path:
    """The demo package prefix: an explicit copy (base/so101_demo_py) or the active overlay."""

    explicit = os.environ.get("SO101_E2E_INSTALL_PREFIX")
    if explicit:
        base = Path(explicit).resolve()
        return (base / "so101_demo_py").resolve() if (base / "so101_demo_py").is_dir() else base
    from ament_index_python.packages import get_package_prefix

    return Path(get_package_prefix("so101_demo_py")).resolve()


def _copy_base() -> Path | None:
    """The copied install base when one was named explicitly, else None (overlay mode)."""

    explicit = os.environ.get("SO101_E2E_INSTALL_PREFIX")
    if not explicit:
        return None
    base = Path(explicit).resolve()
    return base if (base / "so101_demo_py").is_dir() else base.parent


def _entry_environment(prefix: Path, task_root: Path | None = None) -> dict[str, str]:
    """The runtime environment of the entry: install prefix plus the shared guard root.

    ``SO101_TASK_ROOT`` is the design's own requirement (the guard's lock and cleanup state
    live in one task-owned directory shared by CLI and Web), so it is part of the runtime
    environment rather than a metadata gate.
    """

    environment = dict(os.environ)
    environment.update({
        "SO101_E2E_INSTALL_PREFIX": str(prefix),
        "PYTHONNOUSERSITE": "1",
        "SO101_DISABLE_KIMI_EDITABLE_FINDER": "1",
    })
    if os.environ.get("SO101_E2E_INSTALL_PREFIX"):
        # An explicit copied prefix must supply the modules too, not just the console script.
        base = _copy_base() or prefix
        sites = [base / "so101_demo_py/lib/python3.12/site-packages",
                 base / "so101_teleop/lib/python3.12/site-packages"]
        inherited = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(site) for site in sites] + ([inherited] if inherited else []))
        prefixes = [base / "so101_demo_py", base / "so101_teleop",
                    base / "so101_mujoco_support"]
        existing = environment.get("AMENT_PREFIX_PATH", "")
        environment["AMENT_PREFIX_PATH"] = os.pathsep.join(
            [str(item) for item in prefixes] + ([existing] if existing else []))
    if task_root is not None:
        environment["SO101_TASK_ROOT"] = str(task_root)
        environment["ROS_HOME"] = str(task_root / "ros-home")
        environment["ROS_LOG_DIR"] = str(task_root / "ros-home/log")
    else:
        environment.pop("SO101_TASK_ROOT", None)
    return environment


def test_retired_measurement_entry_reports_retirement(tmp_path) -> None:
    """The old console script still exists but measures nothing."""

    prefix = _installed_prefix()
    entry = prefix / "lib/so101_demo_py/so101_measure_parallel_resources"
    completed = subprocess.run([sys.executable, str(entry)], capture_output=True, text=True,
                               timeout=60, env=_entry_environment(prefix, tmp_path))
    combined = completed.stdout + completed.stderr
    assert completed.returncode == 2, combined
    lines = completed.stdout.strip().splitlines()
    assert lines, f"the retired entry printed nothing on stdout: {combined!r}"
    payload = json.loads(lines[-1])
    assert payload["error"] == "MEASUREMENT_ENTRY_RETIRED"
    assert payload["authorizes_execution"] is False


def test_installed_text_agent_launch_resource_is_discoverable(tmp_path) -> None:
    """The installed launch resource is found by the standard ROS lookup (not physical proof)."""

    prefix = _installed_prefix()
    completed = subprocess.run(
        ["ros2", "launch", "so101_demo_py", "so101_mujoco_text_pick_agent.launch.py",
         "--show-args"],
        capture_output=True, text=True, timeout=180, cwd=str(tmp_path),
        env=_entry_environment(prefix, tmp_path / "task-root"))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "instruction" in completed.stdout
    assert (prefix / "share/so101_demo_py/launch"
            / "so101_mujoco_text_pick_agent.launch.py").exists()

