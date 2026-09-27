"""A private per-run file carries the broker peer and controller capability."""

import os
from pathlib import Path
import select
import stat
import subprocess
import sys

import pytest


pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="controller peer identity uses Linux procfs")


def _private_directory(tmp_path):
    parent = tmp_path / "reservation"
    parent.mkdir(mode=0o700)
    return parent


def _start_ticks(pid):
    content = Path(f"/proc/{pid}/stat").read_text()
    return int(content[content.rfind(")") + 2:].split()[19])


def test_provision_has_exact_role_session_peer_and_private_capability(tmp_path):
    from so101_demo.adapters.act.controller_reservation_provision import (
        write_controller_reservation_provision,
    )

    parent = _private_directory(tmp_path)
    arm = parent / "arm.provision"
    gripper = parent / "gripper.provision"
    arm_key = write_controller_reservation_provision(
        arm, role="arm", session_id="session-17")
    gripper_key = write_controller_reservation_provision(
        gripper, role="gripper", session_id="session-17")

    assert len(arm_key) == len(gripper_key) == 32
    assert any(arm_key) and any(gripper_key) and arm_key != gripper_key
    for role, file, key in ((1, arm, arm_key), (2, gripper, gripper_key)):
        data = file.read_bytes()
        assert len(data) == 56 + len(b"session-17")
        assert data[:8] == b"SOPR" + bytes((1, role, len(b"session-17"), 0))
        assert int.from_bytes(data[8:12], "big") == os.geteuid()
        assert int.from_bytes(data[12:16], "big") == os.getpid()
        assert int.from_bytes(data[16:24], "big") == _start_ticks(os.getpid())
        assert data[24:56] == key
        assert data[56:] == b"session-17"
        assert stat.S_IMODE(file.stat().st_mode) == 0o600
        assert file.stat().st_nlink == 1
    assert sorted(file.name for file in parent.iterdir()) == [
        "arm.provision", "gripper.provision"]


def test_provision_refuses_overwrite_invalid_scope_and_symlink(tmp_path):
    from so101_demo.adapters.act.controller_reservation_provision import (
        write_controller_reservation_provision,
    )

    parent = _private_directory(tmp_path)
    file = parent / "arm.provision"
    write_controller_reservation_provision(file, role="arm", session_id="session-17")
    original = file.read_bytes()
    with pytest.raises(FileExistsError):
        write_controller_reservation_provision(file, role="arm", session_id="session-17")
    assert file.read_bytes() == original
    with pytest.raises(ValueError):
        write_controller_reservation_provision(parent / "bad.provision",
                                               role="neck", session_id="session-17")
    with pytest.raises(ValueError):
        write_controller_reservation_provision(parent / "bad.provision",
                                               role="arm", session_id="bad/session")
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(PermissionError):
        write_controller_reservation_provision(public / "arm.provision",
                                               role="arm", session_id="session-17")
    alias = tmp_path / "alias"
    alias.symlink_to(parent, target_is_directory=True)
    with pytest.raises(PermissionError):
        write_controller_reservation_provision(alias / "arm.provision",
                                               role="arm", session_id="session-17")


def test_provision_file_is_private_under_restrictive_umask(tmp_path):
    from so101_demo.adapters.act.controller_reservation_provision import (
        write_controller_reservation_provision,
    )

    file = _private_directory(tmp_path) / "arm.provision"
    previous_umask = os.umask(0o777)
    try:
        write_controller_reservation_provision(file, role="arm", session_id="session-17")
    finally:
        os.umask(previous_umask)
    assert stat.S_IMODE(file.stat().st_mode) == 0o600


def test_capability_is_absent_from_writer_argv_environment_and_output(tmp_path):
    parent = _private_directory(tmp_path)
    file = parent / "arm.provision"
    script = (
        "import sys; from pathlib import Path; "
        "from so101_demo.adapters.act.controller_reservation_provision "
        "import write_controller_reservation_provision; "
        "write_controller_reservation_provision(Path(sys.argv[1]), "
        "role='arm', session_id='session-17'); "
        "sys.stdout.write('READY\\n'); sys.stdout.flush(); sys.stdin.readline()"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(file)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    try:
        ready = select.poll()
        ready.register(process.stdout, select.POLLIN | select.POLLHUP)
        assert ready.poll(2000)
        assert process.stdout.readline() == "READY\n"
        capability = file.read_bytes()[24:56]
        assert len(capability) == 32 and any(capability)
        command = Path(f"/proc/{process.pid}/cmdline").read_bytes()
        environment = Path(f"/proc/{process.pid}/environ").read_bytes()
        assert capability.hex().encode() not in command + environment
        assert capability not in command + environment
        process.stdin.write("done\n")
        process.stdin.flush()
        assert process.wait(timeout=2) == 0
        assert process.stderr.read() == ""
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=2)
