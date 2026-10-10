"""The AF_UNIX boundary uses the platform transport without truncating paths."""

import os
from pathlib import Path
import socket
import sys
import tempfile

import pytest


def deep_root(tmp_path, *, name="d" * 80, nested="e" * 40):
    root = tmp_path / name / nested
    root.mkdir(parents=True, mode=0o700)
    return root


def test_transport_basename_budget_and_exact_kernel_size(tmp_path):
    from so101_demo.runtime.parallel_ipc import (
        IpcError, UNIX_SOCKADDR_CAPACITY_BYTES, require_transport_basename,
        transport_address)
    root = deep_root(tmp_path)
    assert len(os.fsencode(root / "s")) > 107
    if sys.platform == "darwin":
        with pytest.raises(IpcError, match="UNIX_SOCKET_PATH_TOO_LONG"):
            require_transport_basename(root / "s")
        return
    require_transport_basename(root / "s")
    for bad in ("x" * 200 + ".sock", "x" * 83 + ".sock"):
        with pytest.raises(IpcError, match="UNIX_SOCKET_PATH_TOO_LONG"):
            require_transport_basename(root / bad)
    with pytest.raises(IpcError, match="UNIX_SOCKET_BASENAME_INVALID"):
        require_transport_basename(root / "..")
    # The exact encoded sockaddr address including the terminating NUL is bounded.
    address = transport_address(root / ("b" * 91), 0)
    assert len(os.fsencode(address)) + 1 == UNIX_SOCKADDR_CAPACITY_BYTES
    with pytest.raises(IpcError, match="UNIX_SOCKET_PATH_TOO_LONG"):
        transport_address(root / ("b" * 92), 0)
    with pytest.raises(IpcError, match="UNIX_TRANSPORT_DESCRIPTOR"):
        transport_address(root / "s", -1)


def test_long_durable_root_binds_connects_and_keeps_canonical_path(tmp_path):
    from so101_demo.runtime.parallel_ipc import IpcError, transport_address
    root = deep_root(tmp_path)
    path = root / "control.sock"
    assert len(os.fsencode(path)) > 107
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if sys.platform == "darwin":
            with pytest.raises(IpcError, match="UNIX_SOCKET_PATH_TOO_LONG"):
                transport_address(path, parent_fd)
            return
        listener.bind(transport_address(path, parent_fd))
    finally:
        os.close(parent_fd)
        if sys.platform == "darwin":
            listener.close()
    try:
        listener.listen(1)
        listener.settimeout(5.0)
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(5.0)
        client_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            client.connect(transport_address(path, client_fd))
        finally:
            os.close(client_fd)
        client.sendall(b"ping")
        connection, _ = listener.accept()
        with connection:
            assert connection.recv(4) == b"ping"
            connection.sendall(b"pong")
        assert client.recv(4) == b"pong"
        client.close()
        # Canonical durable path, ownership and mode remain the audited identity.
        assert path.is_absolute() and path.exists()
        assert os.stat(path).st_uid == os.getuid()
        assert len(os.fsencode(path)) > 107
    finally:
        listener.close()


def test_missing_proc_transport_fails_closed(tmp_path, monkeypatch):
    from so101_demo.runtime import parallel_ipc
    from so101_demo.runtime.parallel_ipc import IpcError, require_transport_basename
    monkeypatch.setattr(parallel_ipc, "_PROC_FD_ROOT", tmp_path / "missing-proc")
    if sys.platform == "darwin":
        require_transport_basename(tmp_path / "control.sock")
        return
    with pytest.raises(IpcError, match="UNIX_TRANSPORT_UNAVAILABLE"):
        require_transport_basename(tmp_path / "control.sock")


def test_symlinked_parent_is_still_rejected(tmp_path):
    from so101_demo.runtime.parallel_ipc import IpcError, transport_address
    real = deep_root(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(real)
    path = alias / "control.sock"
    with pytest.raises(OSError):
        os.open(alias, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    parent_fd = os.open(real, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if sys.platform == "darwin":
            with pytest.raises(IpcError, match="UNIX_TRANSPORT_PARENT"):
                transport_address(path, parent_fd)
            return
        address = transport_address(path, parent_fd)
        assert address == f"/proc/self/fd/{parent_fd}/control.sock"
    finally:
        os.close(parent_fd)


def test_failed_bind_leaves_no_socket_and_no_fd_leak(tmp_path):
    from so101_demo.runtime.parallel_ipc import transport_address
    with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
        root = Path(directory)
        path = root / "control.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        address = transport_address(path, parent_fd)
        listener.bind(address)
        try:
            duplicate = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            with pytest.raises(OSError):
                duplicate.bind(address)
            duplicate.close()
            assert path.exists()
        finally:
            listener.close()
            os.close(parent_fd)
