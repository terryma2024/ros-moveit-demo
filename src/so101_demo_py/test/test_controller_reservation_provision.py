"""A private per-run file carries the broker peer and controller capability."""

import os
from pathlib import Path
import select
import stat
import subprocess
import sys
import threading
from types import SimpleNamespace
import uuid

import pytest

from so101_teleop.unified.controller_reservation_paths import (
    controller_reservation_directory, prepare_controller_reservation_directory,
)


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
    neck = parent / "neck.provision"
    arm_key = write_controller_reservation_provision(
        arm, role="arm", session_id="session-17")
    gripper_key = write_controller_reservation_provision(
        gripper, role="gripper", session_id="session-17")
    neck_key = write_controller_reservation_provision(
        neck, role="neck", session_id="session-17")

    assert {len(key) for key in (arm_key, gripper_key, neck_key)} == {32}
    assert all(any(key) for key in (arm_key, gripper_key, neck_key))
    assert len({arm_key, gripper_key, neck_key}) == 3
    for role, file, key in ((1, arm, arm_key), (2, gripper, gripper_key),
                            (3, neck, neck_key)):
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
        "arm.provision", "gripper.provision", "neck.provision"]


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
                                               role="camera", session_id="session-17")
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


def test_provision_rolls_back_its_link_when_directory_sync_fails(tmp_path, monkeypatch):
    from so101_demo.adapters.act.controller_reservation_provision import (
        write_controller_reservation_provision,
    )

    parent = _private_directory(tmp_path)
    original = os.fsync

    def fail_directory_sync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("injected directory sync failure")
        return original(descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_sync)
    with pytest.raises(OSError, match="injected directory sync failure"):
        write_controller_reservation_provision(
            parent / "arm.provision", role="arm", session_id="session-17")
    assert list(parent.iterdir()) == []


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


def _provision_scope(tmp_path):
    task_root = Path(os.environ["TMPDIR"]).parents[2]
    root = task_root / f"p{uuid.uuid4().hex[:8]}"
    root.mkdir(mode=0o700)
    directory = controller_reservation_directory(root, "session-17")
    environment = {
        "SO101_ACT_RESERVATION_ROOT": str(root),
        "SO101_ACT_CONTROLLER_RESERVATION_DIR": str(directory),
        "SO101_SIMULATION_SESSION_ID": "session-17",
    }
    return root, directory, environment


def test_broker_provisions_three_roles_and_removes_only_its_files(tmp_path):
    from so101_demo.adapters.act.controller_reservation_provision import (
        ControllerReservationProvisions,
    )

    _, directory, environment = _provision_scope(tmp_path)
    provisions = ControllerReservationProvisions.publish(environment, "session-17")
    assert directory.stat().st_mode & 0o777 == 0o700
    assert set(provisions.capabilities) == {"arm", "gripper", "neck"}
    assert len(set(provisions.capabilities.values())) == 3
    for role in ("arm", "gripper", "neck"):
        file = directory / f"{role}.provision"
        assert file.stat().st_mode & 0o777 == 0o600
        assert file.read_bytes()[24:56] == provisions.capabilities[role]
    unrelated = directory / "keep.txt"
    unrelated.write_text("keep")
    provisions.close()
    provisions.close()
    assert sorted(path.name for path in directory.iterdir()) == ["keep.txt"]
    assert unrelated.read_text() == "keep"


def test_broker_provision_rejects_scope_drift_before_publication(tmp_path):
    from so101_demo.adapters.act.controller_reservation_provision import (
        ControllerReservationProvisions,
    )

    root, directory, environment = _provision_scope(tmp_path)
    for change in (
        {"SO101_ACT_RESERVATION_ROOT": str(tmp_path / "outside")},
        {"SO101_ACT_CONTROLLER_RESERVATION_DIR": str(root / "wrong")},
        {"SO101_SIMULATION_SESSION_ID": "other-session"},
    ):
        with pytest.raises(ValueError, match="CONTROLLER_RESERVATION_PROVISION_SCOPE_INVALID"):
            ControllerReservationProvisions.publish({**environment, **change}, "session-17")
    assert not directory.exists()


def test_broker_provision_rejects_overlong_socket_path_before_publication(tmp_path):
    from so101_demo.adapters.act.controller_reservation_provision import (
        ControllerReservationProvisions,
    )

    root = tmp_path / "long-root"
    root.mkdir(mode=0o700)
    directory = controller_reservation_directory(root, "session-17")
    assert len(os.fsencode(directory / "gripper.sock")) > 107
    with pytest.raises(ValueError, match="CONTROLLER_RESERVATION_SOCKET_PATH_TOO_LONG"):
        ControllerReservationProvisions.publish({
            "SO101_ACT_RESERVATION_ROOT": str(root),
            "SO101_ACT_CONTROLLER_RESERVATION_DIR": str(directory),
            "SO101_SIMULATION_SESSION_ID": "session-17",
        }, "session-17")
    assert not directory.exists()


def test_broker_provision_partial_collision_keeps_existing_file(tmp_path):
    from so101_demo.adapters.act.controller_reservation_provision import (
        ControllerReservationProvisions,
    )

    root, directory, environment = _provision_scope(tmp_path)
    prepare_controller_reservation_directory(root, "session-17")
    existing = directory / "gripper.provision"
    existing.write_bytes(b"existing")
    original_inode = existing.stat().st_ino
    with pytest.raises(FileExistsError):
        ControllerReservationProvisions.publish(environment, "session-17")
    assert sorted(path.name for path in directory.iterdir()) == ["gripper.provision"]
    assert existing.stat().st_ino == original_inode
    assert existing.read_bytes() == b"existing"


def test_neck_provision_collision_rolls_back_other_new_roles(tmp_path):
    from so101_demo.adapters.act.controller_reservation_provision import (
        ControllerReservationProvisions,
    )

    root, directory, environment = _provision_scope(tmp_path)
    prepare_controller_reservation_directory(root, "session-17")
    existing = directory / "neck.provision"
    existing.write_bytes(b"existing")
    original_inode = existing.stat().st_ino
    with pytest.raises(FileExistsError):
        ControllerReservationProvisions.publish(environment, "session-17")
    assert sorted(path.name for path in directory.iterdir()) == ["neck.provision"]
    assert existing.stat().st_ino == original_inode
    assert existing.read_bytes() == b"existing"


@pytest.mark.parametrize("start_fails", (False, True))
def test_standalone_broker_publishes_before_service_and_cleans_on_exit(
        tmp_path, monkeypatch, start_fails):
    import rclpy
    from rclpy import executors
    from so101_demo.adapters.act import domain_authority, ros_broker
    from so101_demo.cli import act_command_broker as cli

    root, directory, environment = _provision_scope(tmp_path)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    short_root = Path(os.environ["TMPDIR"]).parents[2] / f"broker-{uuid.uuid4().hex[:6]}"
    short_root.mkdir(mode=0o700)
    socket_path = short_root / "broker.sock"
    seen = []

    class Authority:
        kernel_name = "test-kernel"
        domain = 1

        def __init__(self, domain):
            self.domain = domain

        def acquire(self):
            return self

        def close(self):
            seen.append("authority_closed")

    class Node:
        def destroy_node(self):
            seen.append("node_destroyed")

    class Executor:
        def add_node(self, node):
            pass

        def spin(self):
            pass

        def shutdown(self):
            seen.append("executor_stopped")

    class Driver:
        unknown_goal_seen = False

        def __init__(self, *args, **kwargs):
            pass

        def stopped(self):
            return True

        def diagnostics(self):
            return {}

    class Broker:
        def __init__(self, driver, *, ownership, simulation_session_id, reservation_port):
            self.ownership = SimpleNamespace(state="IDLE")
            self.audit = []
            self.prefix_executor = None
            self.reservation_port = reservation_port

        def tick(self):
            pass

    class Server:
        def __init__(self, broker, endpoint, *, parent_pid):
            self._stop = threading.Event()
            self.broker = broker

        def start(self):
            assert sorted(path.name for path in directory.iterdir()) == [
                "arm.provision", "gripper.provision", "neck.provision"]
            assert set(self.broker.reservation_port._paths) == {"arm", "gripper", "neck"}
            for role in ("arm", "gripper", "neck"):
                assert self.broker.reservation_port._paths[role] == directory / f"{role}.sock"
                assert self.broker.reservation_port._capabilities[role] == (
                    directory / f"{role}.provision").read_bytes()[24:56]
            seen.append("server_started")
            if start_fails:
                raise RuntimeError("injected server startup failure")
            self._stop.set()

        def close(self):
            seen.append("server_closed")

    monkeypatch.setattr(domain_authority, "DomainAuthority", Authority)
    monkeypatch.setattr(rclpy, "init", lambda: None)
    monkeypatch.setattr(rclpy, "create_node", lambda *args, **kwargs: Node())
    monkeypatch.setattr(rclpy, "shutdown", lambda: seen.append("rclpy_stopped"))
    monkeypatch.setattr(executors, "SingleThreadedExecutor", Executor)
    monkeypatch.setattr(ros_broker, "RosBrokerDriver", Driver)
    monkeypatch.setattr(cli, "CommandBroker", Broker)
    monkeypatch.setattr(cli, "UnixBrokerServer", Server)
    arguments = [
        "--socket", str(socket_path), "--session-id", "session-17",
        "--parent-pid", str(os.getpid()), "--lease-timeout-s", "1",
        "--calibration-mode", "--stop-velocity-rad-s", "0.01", "--max-age-s", "0.1",
    ]
    if start_fails:
        with pytest.raises(RuntimeError, match="injected server startup failure"):
            cli.main(arguments)
    else:
        assert cli.main(arguments) == 0
    assert seen.index("server_started") < seen.index("server_closed")
    assert list(directory.iterdir()) == []
    assert "capability" not in socket_path.with_name("broker-runtime.json").read_text()
