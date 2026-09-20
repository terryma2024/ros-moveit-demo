"""Bridge ownership tests: fixed launch, exact identity, real child, no ROS in the web process."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from so101_teleop.owned_group import terminate_group
from so101_teleop.unified.arbiter import GlobalMutationArbiter
from so101_teleop.unified.bridge import (
    BridgeClient,
    BridgeLaunch,
    BridgeProcessOwner,
    identity_for,
    identity_matches,
)
from so101_teleop.unified.contracts import (
    Domain,
    MutationError,
    OperationSpec,
    OwnerKey,
    PendingChildKey,
    RevokeTarget,
)
from so101_teleop.unified.goals import GoalRegistry
from so101_teleop.unified.intent_store import IntentStore
from so101_teleop.unified.ipc import IpcRequest
from so101_teleop.unified.safety import SafetyAuthority, SafetyLane, SafetyLimits

HELPER_PATH = Path(__file__).parents[1] / "e2e/noros_child_helper.py"
SERVICE_EPOCH = "e1"
RUNTIME_ID = "R1"
SERVICE_TOKEN = "bridge-test-token"


class HelperLaunch(BridgeLaunch):
    """Test-owned launch that runs the no-ROS helper instead of the ROS child module."""

    def argv(self) -> list[str]:
        return [
            str(self.ros_python),
            str(HELPER_PATH),
            "--socket-root",
            str(self.socket_root),
            "--runtime-id",
            self.runtime_id,
            "--service-epoch",
            SERVICE_EPOCH,
            "--service-token",
            SERVICE_TOKEN,
            "--started-ticks",
            "1",
        ]


def socket_root(tmp_path: Path) -> Path:
    base = os.environ.get("SO101_IPC_SOCKET_BASE") or tempfile.gettempdir()
    Path(base).mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="so101bridge-", dir=base))


class Rig:
    def __init__(self, tmp_path: Path, launch_class: type[HelperLaunch] = HelperLaunch) -> None:
        self.root = socket_root(tmp_path)
        self.store = IntentStore.open(tmp_path / "state")
        self.arbiter = GlobalMutationArbiter(self.store, clock_ns=lambda: 1)
        self.lane = SafetyLane(
            GoalRegistry(), self.arbiter, limits=SafetyLimits(0.5, 0.5, 4), authorize=lambda a, k: None
        )
        self.launch = launch_class(
            ros_python=Path(sys.executable),
            install_prefix=Path(sys.prefix),
            runtime_id=RUNTIME_ID,
            environment=dict(os.environ),
            socket_root=self.root,
        )
        self.owner_process = BridgeProcessOwner(self.launch, self.arbiter, self.lane)

    def client(self, owner: OwnerKey | None) -> BridgeClient:
        normal, safety = self.owner_process.socket_paths()
        return BridgeClient(
            normal_socket=normal,
            safety_socket=safety,
            service_epoch=SERVICE_EPOCH,
            runtime_id=RUNTIME_ID,
            service_token=SERVICE_TOKEN,
            owner=owner,
            timeout_s=2.0,
        )

    async def close(self) -> None:
        """Close the rig without leaving the child it started behind.

        Two tests in this file never call ``stop_owned`` (one asserts a refusal before any stop, one
        kills the leader itself), and both leaked a live child on every run. The rig owns the
        process, so its close is where that has to end - not in each test's own finally.
        """
        owner = self.owner_process
        handle = owner.process
        pgid = owner.owner.pgid if owner.owner is not None else (handle.pid if handle else None)
        if handle is not None and handle.poll() is None:
            if owner.owner is not None and identity_matches(owner.owner):
                with contextlib.suppress(Exception):
                    await owner.stop_owned()
            # A successful stop clears the owner's process and owner fields, so never re-read them.
            if handle.poll() is None and pgid is not None:
                terminate_group(pgid=pgid, leader_pid=handle.pid, timeout_s=1.0)
                with contextlib.suppress(Exception):
                    handle.wait(timeout=5)
        await self.lane.close()
        self.store.close()
        shutil.rmtree(self.root, ignore_errors=True)


def test_launch_argv_is_fixed_and_refuses_unusable_paths(tmp_path):
    launch = BridgeLaunch(
        ros_python=Path(sys.executable),
        install_prefix=Path(sys.prefix),
        runtime_id="R1",
        environment={},
        socket_root=tmp_path / "sockets",
    )
    assert launch.argv() == [
        str(sys.executable),
        "-m",
        "so101_teleop.unified.ros_child",
        "--socket-root",
        str(tmp_path / "sockets"),
        "--runtime-id",
        "R1",
    ]
    with pytest.raises(MutationError, match="BRIDGE_ROS_PYTHON_MISSING"):
        BridgeLaunch(Path("/nonexistent/python"), Path(sys.prefix), "R1", {}, tmp_path)
    with pytest.raises(MutationError, match="BRIDGE_INSTALL_PREFIX_MISSING"):
        BridgeLaunch(Path(sys.executable), Path("/nonexistent/prefix"), "R1", {}, tmp_path)
    with pytest.raises(MutationError, match="BRIDGE_RUNTIME_ID_MISSING"):
        BridgeLaunch(Path(sys.executable), Path(sys.prefix), "", {}, tmp_path)


def test_owner_starts_a_real_child_serves_observe_then_stops_it(tmp_path):
    async def run():
        rig = Rig(tmp_path)
        try:
            owner = await rig.owner_process.start()
            assert owner.pid > 0 and owner.pgid > 0 and owner.started_ticks > 0
            assert rig.owner_process.ready()
            client = rig.client(owner)
            reply = await client.call(
                IpcRequest(
                    version=1,
                    operation="observe",
                    command_id="read-1",
                    deadline_ns=time.monotonic_ns() + 10**9,
                    service_epoch=SERVICE_EPOCH,
                    runtime_id=RUNTIME_ID,
                    service_token=SERVICE_TOKEN,
                )
            )
            assert reply.accepted and reply.result["runtime_id"] == RUNTIME_ID
            await rig.owner_process.stop_owned()
            assert not rig.owner_process.ready()
        finally:
            await rig.close()

    asyncio.run(run())


def test_identity_is_recomputed_from_the_live_process(tmp_path):
    async def run():
        rig = Rig(tmp_path)
        try:
            owner = await rig.owner_process.start()
            live = identity_for(owner.pid, rig.launch.argv(), rig.launch.environment)
            assert live.started_ticks == owner.started_ticks
            assert live.argv_sha256 == owner.argv_sha256
            drifted = OwnerKey(
                pid=owner.pid,
                pgid=owner.pgid,
                started_ticks=owner.started_ticks + 1,
                argv_sha256=owner.argv_sha256,
                environment_sha256=owner.environment_sha256,
            )
            rig.owner_process.owner = drifted
            with pytest.raises(MutationError, match="OWNER_IDENTITY_DRIFT"):
                await rig.owner_process.stop_owned()
            assert rig.owner_process.process.poll() is None, "a drifted owner must not be signalled"
            os.kill(owner.pid, signal.SIGTERM)
            rig.owner_process.process.wait(timeout=5)
        finally:
            await rig.close()

    asyncio.run(run())


def test_child_crash_makes_the_bridge_unready(tmp_path):
    async def run():
        rig = Rig(tmp_path)
        try:
            owner = await rig.owner_process.start()
            assert rig.owner_process.ready()
            os.kill(owner.pid, signal.SIGKILL)
            rig.owner_process.process.wait(timeout=5)
            for _ in range(100):
                if not rig.owner_process.ready():
                    break
                await asyncio.sleep(0.02)
            assert not rig.owner_process.ready()
            client = rig.client(owner)
            with pytest.raises(MutationError, match="IPC_CONNECT_FAILED"):
                await client.call(
                    IpcRequest(
                        version=1,
                        operation="observe",
                        command_id="read-2",
                        deadline_ns=time.monotonic_ns() + 10**9,
                        service_epoch=SERVICE_EPOCH,
                        runtime_id=RUNTIME_ID,
                        service_token=SERVICE_TOKEN,
                    )
                )
        finally:
            await rig.close()

    asyncio.run(run())


def test_safety_cancel_reaches_the_child_without_the_normal_channel(tmp_path):
    async def run():
        rig = Rig(tmp_path)
        try:
            owner = await rig.owner_process.start()
            client = rig.client(owner)
            parent = rig.arbiter.begin(
                OperationSpec("all-1", Domain.TELEOP, "execute_all", {}, RUNTIME_ID, 1, 10**18)
            )
            token = rig.arbiter.prepare_child(parent.operation_id, "arm")
            intent = rig.arbiter.cancel_parent(parent.operation_id)
            target = intent.targets[0]
            assert target.key.child_id == "arm"
            receipt = await client.revoke(
                target, SafetyAuthority("watchdog", Domain.TELEOP, SERVICE_EPOCH, 1, None)
            )
            assert receipt.linearized and not receipt.submitted
        finally:
            await rig.close()

    asyncio.run(run())


def test_client_refuses_to_cancel_without_the_exact_owner(tmp_path):
    async def run():
        rig = Rig(tmp_path)
        try:
            await rig.owner_process.start()
            client = rig.client(None)
            target = RevokeTarget(
                PendingChildKey("op", "arm", RUNTIME_ID, 1), revocation_revision=1
            )
            with pytest.raises(MutationError, match="BRIDGE_OWNER_UNKNOWN"):
                await client.revoke(
                    target, SafetyAuthority("watchdog", Domain.TELEOP, SERVICE_EPOCH, 1, None)
                )
        finally:
            await rig.close()

    asyncio.run(run())


def test_ros_import_is_child_only():
    program = (
        "import sys; import so101_teleop.unified.ipc, so101_teleop.unified.bridge,"
        " so101_teleop.unified.child_runtime, so101_teleop.unified.arbiter,"
        " so101_teleop.unified.instances, so101_teleop.unified.safety;"
        " assert 'rclpy' not in sys.modules, sorted(m for m in sys.modules if 'rclpy' in m);"
        " print('WEB_IMPORT_ROS_FREE')"
    )
    completed = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    assert "WEB_IMPORT_ROS_FREE" in completed.stdout
