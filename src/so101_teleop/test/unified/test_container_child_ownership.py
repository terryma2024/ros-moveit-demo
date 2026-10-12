"""Real control sockets bind container generation and local PID namespace identity."""

import asyncio
from dataclasses import asdict
import importlib
import json
import os
from types import SimpleNamespace as NS

from so101_teleop.unified.child_runtime import ChildRuntime
from so101_teleop.unified.contracts import OwnerKey


def fixture(tmp_path):
    from so101_demo.runtime.container_campaign.heartbeat import OwnerHeartbeatMonitor
    from so101_demo.runtime.container_campaign.process_identity import read_process_owner
    module = importlib.import_module("so101_teleop.unified.child_runtime")
    now = NS(ns=100_000_000)
    monitor = OwnerHeartbeatMonitor(generation=7, timeout_ns=100_000_000, monotonic_ns=lambda: now.ns)
    async def stop_act(_reason):
        return True
    runtime = ChildRuntime(NS(stop_act=stop_act), owner=OwnerKey(1, 1, 1, "a"*64, "b"*64),
        service_epoch="epoch", runtime_id="runtime", normal_queue_limit=2,
        act_campaign_id="campaign", act_worker_id="worker", act_generation=3)
    process = read_process_owner(os.getpid())
    server = module.ContainerChildIpcServer(runtime, socket_root=tmp_path / "control",
        owner=runtime.owner, service_epoch="epoch", service_token="private-token",
        owner_monitor=monitor, process_owner=process)
    return now, monitor, runtime, process, server


async def connect(server):
    from so101_demo.runtime.parallel_ipc.frames import transport_address
    return await asyncio.open_unix_connection(transport_address(server.normal_socket, server.socket_parent_fd))


async def heartbeat(writer, reader, sequence=1, **changes):
    writer.write(json.dumps(dict(kind="owner_heartbeat", generation=7,
        sequence=sequence, sent_monotonic_ns=1) | changes).encode() + b"\n")
    await writer.drain()
    return json.loads(await reader.readline())


def test_actual_ready_uses_inner_key_and_leaves_receipts_on_close(tmp_path):
    async def run():
        _now, _monitor, _runtime, process, server = fixture(tmp_path)
        await server.start()
        path = server.socket_root / "child-ready.json"
        try:
            ready = json.loads(path.read_text())
            assert ready["kind"] == "container_child_ready" and ready["generation"] == 7
            assert ready["execution_generation"] == 3  # launch generation is a different scope
            assert ready["process_owner"] == asdict(process)
            assert "pid" not in ready and ready["pid_namespace_inode"] == os.stat("/proc/self/ns/pid").st_ino
        finally:
            await server.close()
        assert path.is_file() and server.normal_socket.exists()
    asyncio.run(run())


def test_owned_heartbeat_disconnect_fences_runtime_and_old_generation_cannot_refresh(tmp_path):
    async def run():
        now, monitor, runtime, _process, server = fixture(tmp_path)
        await server.start()
        reader, writer = await connect(server)
        try:
            bad = await heartbeat(writer, reader, generation=6)
            assert bad["accepted"] is False
            reply = await heartbeat(writer, reader)
            assert reply["accepted"] is True
            assert reply["result"] == {"kind": "owner_heartbeat_ack", "generation": 7, "sequence": 1}
            now.ns += 50_000_000
            rollback = await heartbeat(writer, reader)
            assert rollback["accepted"] is False
            writer.close()
            await writer.wait_closed()
            await asyncio.wait_for(runtime.web_dead_latch.wait(), 1.)
            assert monitor.reason == "OWNER_CONNECTION_LOST"
        finally:
            await server.close()
    asyncio.run(run())


def test_only_one_heartbeat_connection_can_own_generation(tmp_path):
    async def run():
        _now, monitor, runtime, _process, server = fixture(tmp_path)
        await server.start()
        reader, writer = await connect(server)
        other_reader, other_writer = await connect(server)
        try:
            assert (await heartbeat(writer, reader))["accepted"] is True
            denied = await heartbeat(other_writer, other_reader, 2)
            assert denied["accepted"] is False
            other_writer.close()
            await other_writer.wait_closed()
            await asyncio.sleep(0)
            assert not monitor.expired and not runtime.web_dead
        finally:
            writer.close()
            await writer.wait_closed()
            await server.close()
    asyncio.run(run())


def test_actual_host_heartbeat_channel_keeps_owner_alive_and_disconnects_without_retry(tmp_path):
    async def run():
        module = importlib.import_module("so101_demo.runtime.container_campaign.heartbeat")
        now, monitor, runtime, _process, server = fixture(tmp_path)
        await server.start()
        channel = module.OwnerHeartbeatChannel(socket_path=server.normal_socket,
            generation=7, timeout_ns=100_000_000, max_bytes=64*1024)
        try:
            await channel.start()
            now.ns += 20_000_000
            await channel.send_once()
            assert not monitor.expired and not runtime.web_dead and channel.error is None
        finally:
            await channel.close()
            await asyncio.wait_for(runtime.web_dead_latch.wait(), 1.)
            await server.close()
    asyncio.run(run())


def test_failed_heartbeat_start_is_fenced_and_never_reconnects(tmp_path):
    async def run():
        import pytest
        from so101_demo.runtime.container_campaign.heartbeat import OwnerHeartbeatChannel
        _now, _monitor, _runtime, _process, server = fixture(tmp_path)
        await server.start()
        channel = OwnerHeartbeatChannel(socket_path=server.normal_socket,
            generation=6, timeout_ns=100_000_000, max_bytes=64*1024)
        try:
            with pytest.raises(ValueError, match="OWNER_HEARTBEAT_ACK_INVALID"):
                await channel.start()
            assert channel.error is not None
            with pytest.raises(ValueError, match="OWNER_HEARTBEAT_ALREADY_STARTED"):
                await channel.start()
        finally:
            await channel.close()
            await server.close()
    asyncio.run(run())


def test_container_watchdog_uses_receive_deadline_and_never_host_pid_probe(tmp_path, monkeypatch):
    async def run():
        from so101_teleop.unified import ros_child
        now, monitor, runtime, _process, server = fixture(tmp_path)
        monkeypatch.setenv("SO101_CHILD_WEB_PID", "1")
        monkeypatch.setattr(os, "kill", lambda *_args: (_ for _ in ()).throw(AssertionError("Host PID probed")))
        now.ns += monitor.timeout_ns
        await asyncio.wait_for(ros_child.container_watchdog(runtime, owner_monitor=monitor), 1.)
        assert runtime.web_dead
        await server.close()
    asyncio.run(run())


def test_host_container_owner_binds_ready_without_comparing_host_and_inner_pids(tmp_path):
    from so101_demo.runtime.container_campaign.process_identity import ContainerOwnerKey
    module = importlib.import_module("so101_teleop.unified.bridge")
    key = ContainerOwnerKey("a"*64, "2026-10-12T01:02:03Z", "sha256:"+"b"*64, 7)
    observed = {"Id": key.container_id, "Image": key.image_digest,
        "State": {"StartedAt": key.docker_started_at, "Pid": 501, "Running": True,
                  "Restarting": False, "Status": "running"}}
    owner = module.ContainerBridgeProcessOwner(container_owner=key, control_socket_root=tmp_path,
        runtime_id="runtime", service_epoch="epoch", campaign_id="campaign", worker_id="worker",
        execution_generation=3, inspect_container=lambda _id: observed,
        namespace_reader=lambda _pid: 200)
    ready = {"schema_version": 1, "kind": "container_child_ready", "generation": 7,
        "process_owner": {"pid": 1, "pgid": 1, "started_ticks": 99,
                          "argv_sha256": "c"*64, "environment_sha256": "d"*64},
        "pid_namespace_inode": 200, "service_epoch": "epoch", "runtime_id": "runtime",
        "campaign_id": "campaign", "worker_id": "worker", "execution_generation": 3,
        "normal_socket": "/act/control/normal.sock", "safety_socket": "/act/control/safety.sock"}
    binding = owner.accept_ready(ready)
    assert binding.process.pid == 1 and owner.ready()
    observed["State"]["Running"] = False
    observed["State"].update(Pid=0, Status="exited")
    assert owner.ready() is False
    receipt = dict(schema_version=1, kind="shard_stop_receipt", generation=7,
        process_owner=ready["process_owner"], pid_namespace_inode=200, goals_stopped=True,
        controllers_stopped=True, ros_children_exited=True, ros_graph_empty=True, forced=False)
    assert owner.stopped(receipt) is True
    observed["State"]["StartedAt"] = "2026-10-12T01:03:00Z"
    assert owner.stopped(receipt) is False
