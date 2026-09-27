"""A broker and a later or earlier controller locate one private run directory."""

import os
from pathlib import Path
import stat

import pytest

from so101_teleop.unified.controller_reservation_paths import (
    controller_reservation_directory,
    controller_reservation_root,
    prepare_controller_reservation_directory,
)


def test_stable_per_session_paths_fit_linux_socket_limit():
    root = Path(os.environ["TMPDIR"]).parents[2]
    first = controller_reservation_directory(root, "session_A")
    assert first == controller_reservation_directory(root, "session_A")
    assert first != controller_reservation_directory(root, "session_B")
    assert first.parent == root / "ipc"
    assert first.name.isalnum() and len(first.name) == 16
    assert len(os.fsencode(first / "gripper.sock")) <= 107


def test_prepare_creates_only_private_directories(tmp_path):
    root = tmp_path / "evidence"
    root.mkdir(mode=0o700)
    directory = prepare_controller_reservation_directory(root, "session_A")
    assert directory == controller_reservation_directory(root, "session_A")
    for item in (directory.parent, directory):
        info = item.lstat()
        assert stat.S_ISDIR(info.st_mode)
        assert stat.S_IMODE(info.st_mode) == 0o700
        assert info.st_uid == os.geteuid()
    assert prepare_controller_reservation_directory(root, "session_A") == directory


def test_invalid_root_session_or_directory_fails_closed(tmp_path):
    root = tmp_path / "evidence"
    root.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises((ValueError, PermissionError)):
        prepare_controller_reservation_directory(alias, "session_A")
    with pytest.raises(ValueError):
        controller_reservation_directory(root, "bad/session")
    ipc = root / "ipc"
    ipc.mkdir(mode=0o755)
    with pytest.raises(PermissionError):
        prepare_controller_reservation_directory(root, "session_A")


def test_nested_campaign_uses_registered_short_root_for_socket_path():
    task_root = Path(os.environ["TMPDIR"]).parents[2]
    campaign_root = task_root / "diagnostics" / "deep-campaign" / "admitted"
    assert len(os.fsencode(controller_reservation_directory(
        campaign_root, "session_A") / "gripper.sock")) > 107
    selected = controller_reservation_root(
        campaign_root, {"SO101_ACT_RESERVATION_ROOT": str(task_root)})
    assert selected == task_root
    assert len(os.fsencode(controller_reservation_directory(
        selected, "session_A") / "gripper.sock")) <= 107
    with pytest.raises(ValueError, match="CONTROLLER_RESERVATION_ROOT_INVALID"):
        controller_reservation_root(
            campaign_root, {"SO101_ACT_RESERVATION_ROOT": "/tmp/outside"})
