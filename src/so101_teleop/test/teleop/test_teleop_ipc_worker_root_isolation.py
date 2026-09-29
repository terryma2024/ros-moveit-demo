"""The IPC worker root must be unique per PROCESS, not only per xdist worker.

`conftest.pytest_configure` gives each xdist worker its own socket root under `SO101_IPC_SOCKET_BASE`, which is what keeps
one worker's socket processes outside another's cleanup scope. But `colcon test` launches this package's ~30 registered
pytest processes with ONE inherited base, and `<base>/<worker>` is the same path in every one of them - so the second
process to reach `gw0` collides:

    INTERNALERROR> FileExistsError: [Errno 17] File exists: '/tmp/s101-v3-ipc-943257/gw0'

That is what the first real eight-worker teleop gate did (CP-1606). The root therefore has to carry something that
differs between processes as well as between workers, and this test pins that property without launching any stack.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

CONFTEST = Path(__file__).resolve().parent / "conftest.py"


def _configure(monkeypatch, base: Path, *, worker: str, pid: int) -> Path:
    """Run the conftest's `pytest_configure` as one process would, and return the root it chose."""

    spec = importlib.util.spec_from_file_location("teleop_conftest_under_test", CONFTEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("PYTEST_XDIST_WORKER", worker)
    monkeypatch.setenv("SO101_IPC_SOCKET_BASE", str(base))
    monkeypatch.setattr(os, "getpid", lambda: pid, raising=False)
    module.pytest_configure(None)
    return Path(os.environ["SO101_IPC_SOCKET_BASE"])


def test_two_processes_sharing_one_base_do_not_collide(tmp_path, monkeypatch):
    """The scenario `colcon test -n 8` creates: one base, many pytest processes, the same worker name."""

    first = _configure(monkeypatch, tmp_path, worker="gw0", pid=1001)
    second = _configure(monkeypatch, tmp_path, worker="gw0", pid=1002)
    assert first != second, (
        f"two processes picked the same socket root {first}: the second one's mkdir raises FileExistsError "
        "and pytest aborts with INTERNALERROR")
    assert first.is_dir() and second.is_dir()
