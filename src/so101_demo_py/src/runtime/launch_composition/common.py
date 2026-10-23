"""Launch constants, owned directories and small helpers shared by the launch builders."""

from __future__ import annotations

from math import isfinite
import os
from pathlib import Path
import re
import shutil
import stat

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch.actions import (
    EmitEvent,
    OpaqueFunction,
)
from launch.events import Shutdown as ShutdownEvent
from launch.substitutions import LaunchConfiguration

COMMON_ARGUMENTS = {
    "run_mode",
    "execute",
    "headless",
    "policy_id",
    "session_id",
    "evidence_file",
    "readiness_timeout_s",
}


_CONTROLLERS = ("joint_state_broadcaster", "arm_controller", "gripper_controller")


MUJOCO_CUP_KEYFRAMES = (
    "task_start",
    "cup_test_forward_5cm",
    "cup_test_left_5cm",
    "cup_test_right_5cm",
    "no_cup",
    "two_cups",
    "cup_near_bottle",
)


_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _advance_on_success(event, action, operation: str):
    if event.returncode == 0:
        return [action]
    return [
        EmitEvent(
            event=ShutdownEvent(reason=f"{operation} failed with exit code {event.returncode}")
        )
    ]


def _raise_launch_failure(_context, message: str):
    raise RuntimeError(message)


def _terminal_launch_actions(reason: str, *, failed: bool):
    actions = [EmitEvent(event=ShutdownEvent(reason=reason))]
    if failed:
        actions.append(OpaqueFunction(function=_raise_launch_failure, args=[reason]))
    return actions


def _positive_finite_launch_value(context, name: str) -> str:
    value = LaunchConfiguration(name).perform(context)
    try:
        parsed = float(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be finite and positive") from error
    if not isfinite(parsed) or parsed <= 0.0:
        raise RuntimeError(f"{name} must be finite and positive")
    return value


def _owned_directory(path: Path, label: str) -> Path:
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError(f"{label} must not be a symlink: {path}")
    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"{label} must be a directory: {path}")
    if metadata.st_uid != os.geteuid():
        raise RuntimeError(f"{label} must be owned by the current user: {path}")
    return path.resolve(strict=True)


def _exclusive_owned_directory(path: Path, label: str) -> Path:
    try:
        path.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError as error:
        raise RuntimeError(f"{label} already exists: {path}") from error
    return _owned_directory(path, label)


def installed_executable(name: str) -> Path:
    """Functional discovery of one installed console script; metadata cannot block it.

    Ament's index is consulted first, then the share directory layout, then PATH. Only
    a genuinely unavailable executable raises here.
    """

    candidates: list[Path] = []
    try:
        candidates.append(Path(get_package_prefix("so101_demo_py")) / "lib/so101_demo_py" / name)
    except (LookupError, OSError, RuntimeError):
        pass
    try:
        share = Path(get_package_share_directory("so101_demo_py"))
        candidates.append(share.parents[1] / "lib/so101_demo_py" / name)
    except (LookupError, OSError, RuntimeError):
        pass
    located = shutil.which(name)
    if located:
        candidates.append(Path(located))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"installed executable is unavailable: {name}")
