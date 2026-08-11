from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SUBMODULE = PROJECT_ROOT / "third_party/mujoco_ros2_control"
OFFICIAL_BASE = "35ba8174b62d9560093614f981a3d4b978a96036"
APPROVED_ORIGIN = "git@gitee.com:zjumty/mujoco_ros2_control.git"


def test_fork_submodule_has_approved_origin_and_official_base() -> None:
    origin = subprocess.run(
        ["git", "-C", str(SUBMODULE), "remote", "get-url", "origin"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    assert origin == APPROVED_ORIGIN

    ancestry = subprocess.run(
        [
            "git",
            "-C",
            str(SUBMODULE),
            "merge-base",
            "--is-ancestor",
            OFFICIAL_BASE,
            "HEAD",
        ],
        check=False,
    )
    assert ancestry.returncode == 0
