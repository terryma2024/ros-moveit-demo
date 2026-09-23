"""Make package-local Teleop contract tests independent of colcon shell inheritance.

The second fixture here is a net, not a mechanism: tests that spawn helpers own their cleanup, and
several of them failed to do it - this task's orphan inventory grew every time a test errored before
its ``finally``. The fixture closes whatever a test left behind, and it decides what to close from
evidence rather than from a list a failing test never got to build: it takes the pids whose command
line names that test's own temporary directory, re-reads each one's argv exactly, and terminates the
group of every match. That is the ownership rule the production stop path uses, so the net cannot
reach a process that was not started for this run.
"""

import os
from pathlib import Path
import subprocess
import sys

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from so101_teleop.owned_group import terminate_group  # noqa: E402
from so101_teleop.process_identity import (  # noqa: E402
    ProcessIdentityError,
    read_identity,
)


def pytest_configure(config) -> None:
    """Keep each xdist worker's socket processes outside every other worker's cleanup scope."""
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    base = os.environ.get("SO101_IPC_SOCKET_BASE")
    if not worker or not base:
        return
    worker_root = Path(base) / worker
    worker_root.mkdir(mode=0o700)
    if worker_root.stat().st_mode & 0o077:
        raise RuntimeError(f"IPC worker root is not private: {worker_root}")
    os.environ["SO101_IPC_SOCKET_BASE"] = str(worker_root)


def _groups_naming(marker: str) -> dict[int, int]:
    """Every process group holding a process whose argv really names ``marker``: pgid -> a pid."""
    listing = subprocess.run(
        ["ps", "-A", "-o", "pid=", "-o", "pgid=", "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if listing.returncode != 0:
        return {}
    groups: dict[int, int] = {}
    for line in listing.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        if marker not in parts[2]:
            continue
        pid = int(parts[0])
        try:
            identity = read_identity(pid)
        except ProcessIdentityError:
            continue
        if not any(marker in argument for argument in identity.argv):
            continue  # the ps text was not the argv this process is really running
        groups.setdefault(identity.pgid, pid)
    return groups


def _markers(tmp_path) -> tuple[str, ...]:
    """Evidence that a live process was started for this test.

    A bridge child names its socket root instead of the test's directory: ``Rig`` puts its sockets in
    the task's registered IPC root, deliberately outside ``tmp_path``. Both markers are therefore
    needed, and both are task-owned - one is this test's own directory, the other is the registered
    IPC root only this task's tests use.
    """
    markers = [str(tmp_path)]
    ipc_root = os.environ.get("SO101_IPC_SOCKET_BASE")
    if ipc_root:
        markers.append(str(ipc_root))
    return tuple(markers)


@pytest.fixture(autouse=True)
def _close_process_groups_this_test_left_behind(tmp_path):
    """Terminate, after every test, any group whose argv still names this test's own run."""
    yield
    seen: set[int] = set()
    for marker in _markers(tmp_path):
        for pgid, member_pid in _groups_naming(marker).items():
            if pgid in seen:
                continue
            seen.add(pgid)
            terminate_group(pgid=pgid, leader_pid=member_pid, timeout_s=1.0)
