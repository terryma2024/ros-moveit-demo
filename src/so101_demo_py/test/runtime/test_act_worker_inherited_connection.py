"""The sole Worker's child must inherit the owned teacher connection explicitly."""

import os
import socket
import sys
from types import SimpleNamespace

import pytest

from so101_demo.runtime.parallel_worker_parts.process_tree import WorkerOwnedProcessTree


def test_owned_child_receives_exact_socket_fd_without_new_process_group(tmp_path):
    parent, inherited = socket.socketpair()
    parent.settimeout(5)
    tree = WorkerOwnedProcessTree(manifest_path=tmp_path / "owned.json")
    child = None
    try:
        program = ("import os,socket,sys; "
                   "s=socket.socket(fileno=int(sys.argv[1])); "
                   "s.sendall(str(os.getpgrp()).encode()); s.recv(1)")
        child = tree.start(SimpleNamespace(role="inherited-connection-probe",
            argv=(sys.executable, "-c", program, str(inherited.fileno()))),
            pass_fds=(inherited.fileno(),))
        assert int(parent.recv(100)) == os.getpgrp() == child.pgid
        assert tree.manifest.processes == (child,)
    finally:
        if child is not None:
            assert tree.stop(child) is True
        parent.close()
        inherited.close()
    assert tree.manifest.processes == ()


@pytest.mark.parametrize("fds", [(-1,), (True,), (1, 1), (999999,)])
def test_invalid_inherited_descriptors_refuse_before_start(fds):
    calls = []
    tree = WorkerOwnedProcessTree(popen=lambda *a, **k: calls.append((a, k)))
    with pytest.raises(ValueError, match="WORKER_INHERITED_FDS_INVALID"):
        tree.start(SimpleNamespace(role="invalid", argv=("must-not-start",)), pass_fds=fds)
    assert calls == [] and tree.manifest.processes == ()
