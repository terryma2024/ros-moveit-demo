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
    identity = module.ContainerChildIdentity(runtime_id="runtime", act_campaign_id="campaign",
        act_worker_id="worker", act_generation=3, normal_queue_limit=2)
    server = module.ContainerChildIpcServer(identity, socket_root=tmp_path / "control",
        owner=runtime.owner, service_epoch="epoch", service_token="private-token",
        task_port=NS(assign_task=stop_act, get_status=stop_act, terminate=stop_act), generation=7, close_timeout_s=1., process_owner=process)
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
        execution_generation=3, ros_namespace="/act/campaign/w00", session_id="session1", ros_domain_id=181,
        inspect_container=lambda _id: observed,
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
    (tmp_path.parent / "shard-stop.json").write_text(json.dumps(receipt))
    assert owner.stopped() is False
    write_stop_originals(tmp_path.parent, receipt)
    assert owner.stopped() is True
    observed["State"]["StartedAt"] = "2026-10-12T01:03:00Z"
    assert owner.stopped() is False


def write_stop_originals(root, receipt):
    """Explicit external ROS/native I/O fixture; no physical success claim."""
    import hashlib
    from so101_demo.runtime.parallel_ipc.frames import canonical_json

    namespace = "/act/campaign/w00"
    endpoints = dict(arm="/arm_controller/follow_joint_trajectory/_action",
        gripper="/gripper_controller/follow_joint_trajectory/_action",
        neck="/neck_controller/follow_joint_trajectory/_action", moveit="/execute_trajectory/_action")
    goals = canonical_json(dict(schema_version=1, kind="ACT_CONTROLLER_STOP_OBSERVATION",
        ros_namespace=namespace, started_monotonic_ns=100, completed_monotonic_ns=150,
        lanes={name:dict(action_prefix=namespace+prefix, cancel_sent_monotonic_ns=110,
            cancel_received_monotonic_ns=120, cancel_return_code=0, goals_canceling=[],
            status_received_monotonic_ns=130, statuses=[]) for name,prefix in endpoints.items()}))
    native_owner = dict(pid=2, pgid=2, started_ticks=200, argv_sha256="a"*64, environment_sha256="b"*64)
    native = canonical_json(dict(schema_version=1, leader_pid=2, pgid=2, started_ticks=200,
        argv_sha256="a"*64, session_id="session1", ros_domain_id=181,
        group_clear=True, graph_clear=True, physical_stop_confirmed=True,
        parent_exited=False, term_sent=True, kill_sent=False, finished_at_monotonic_ns=160))
    audit_root = root / "retirement"
    audit_root.mkdir()
    (audit_root / "controller-stop.json").write_bytes(goals)
    (audit_root / "stack-stop.json").write_bytes(native)
    (audit_root / "audit.json").write_bytes(canonical_json(dict(schema_version=1, kind="ACT_SHARD_STOP_AUDIT",
        generation=receipt["generation"], process_owner=receipt["process_owner"],
        pid_namespace_inode=receipt["pid_namespace_inode"], ros_namespace=namespace,
        session_id="session1", ros_domain_id=181, native_owner=native_owner,
        controller_stop_sha256=hashlib.sha256(goals).hexdigest(), native_stop_sha256=hashlib.sha256(native).hexdigest(), errors=[])))


class RecordingTaskPort:
    """Controlled double for the in-container executor; the server and frames are real."""

    def __init__(self):
        self.calls = []

    async def assign_task(self, task):
        from so101_demo.runtime.container_campaign.task_contracts import TaskStatus
        self.calls.append(("assign_task", task))
        return TaskStatus(task_id=task.task_id, state="ACCEPTED")

    async def get_status(self, task_id=None):
        from so101_demo.runtime.container_campaign.task_contracts import InstanceStatus
        self.calls.append(("get_status", task_id))
        if task_id == "missing":
            raise ValueError("TASK_ID_UNKNOWN")
        return InstanceStatus(instance_id="instance-01", state="READY")

    async def terminate(self, reason):
        from so101_demo.runtime.container_campaign.task_contracts import InstanceStatus
        self.calls.append(("terminate", reason))
        return InstanceStatus(instance_id="instance-01", state="STOPPING", fault_reason=reason)


def task_server(tmp_path, port, **changes):
    module = importlib.import_module("so101_teleop.unified.child_runtime")
    from so101_demo.runtime.container_campaign.process_identity import read_process_owner
    identity = module.ContainerChildIdentity(runtime_id="runtime", act_campaign_id="campaign",
        act_worker_id="worker", act_generation=3, normal_queue_limit=2)
    arguments = dict(socket_root=tmp_path / "control", owner=OwnerKey(1, 1, 1, "a"*64, "b"*64),
        service_epoch="epoch", service_token="private-token", max_bytes=4096, task_port=port,
        generation=7, close_timeout_s=1., process_owner=read_process_owner(os.getpid()))
    return module.ContainerChildIpcServer(identity, **(arguments | changes))


async def exchange(server, frame):
    reader, writer = await connect(server)
    try:
        writer.write(frame if isinstance(frame, bytes) else json.dumps(frame).encode() + b"\n")
        await writer.drain()
        return json.loads(await reader.readline())
    finally:
        writer.close()
        await writer.wait_closed()


def request(operation, payload, deadline_ns=None):
    import time
    return dict(operation=operation, payload=payload, deadline_ns=deadline_ns or time.monotonic_ns() + 5_000_000_000)


def test_task_request_reaches_executor_and_generic_rpc_refused(tmp_path):
    import time
    async def run():
        port = RecordingTaskPort()
        server = task_server(tmp_path, port)
        await server.start()
        try:
            spec = dict(task_id="task-001", inputs_ref=dict(path="/act/input/t.json", sha256="a"*64),
                        deadline_monotonic_s=time.monotonic() + 5)
            assigned = await exchange(server, request("assign_task", spec))
            assert assigned["accepted"] is True and assigned["result"] == dict(
                task_id="task-001", state="ACCEPTED", fault_reason=None)
            status = await exchange(server, request("get_status", dict(task_id=None)))
            assert status["result"]["state"] == "READY" and status["result"]["instance_id"] == "instance-01"
            stopped = await exchange(server, request("terminate", dict(reason="done")))
            assert stopped["result"]["state"] == "STOPPING" and stopped["result"]["fault_reason"] == "done"
            assert [name for name, _ in port.calls] == ["assign_task", "get_status", "terminate"]
            assert port.calls[0][1].task_id == "task-001"
            refused = await exchange(server, request("get_status", dict(task_id="missing")))
            assert refused["accepted"] is False and refused["code"] == "TASK_ID_UNKNOWN"
            before = len(port.calls)
            generic = [
                dict(version=1, operation="observe", command_id="c", deadline_ns=time.monotonic_ns() + 10**9,
                     service_epoch="epoch", runtime_id="runtime", service_token="private-token"),
                request("plan_joints", {}), request("cancel", {}), dict(kind="unknown_kind"), [1], request("observe", {}),
            ]
            for frame in generic:
                reply = await exchange(server, frame)
                assert reply["accepted"] is False and reply["code"] == "CONTAINER_OPERATION_NOT_ALLOWED", frame
            malformed = await exchange(server, b"not json\n")
            assert malformed["accepted"] is False and malformed["code"].startswith("CONTAINER_TASK_REJECTED")
            oversize = await exchange(server, request("get_status", dict(task_id="x"*5000)))
            assert oversize["accepted"] is False and oversize["code"] == "IPC_FRAME_TOO_LARGE"
            expired = await exchange(server, request("get_status", dict(task_id=None), deadline_ns=1))
            assert expired["accepted"] is False and "TASK_REQUEST_DEADLINE_EXPIRED" in expired["code"]
            assert len(port.calls) == before
            # The safety socket carries no task or goal authority in the container.
            reader, writer = await asyncio.open_unix_connection(
                __import__("so101_demo.runtime.parallel_ipc.frames", fromlist=["x"]).transport_address(
                    server.safety_socket, server.socket_parent_fd))
            writer.write(b"{}\n")
            await writer.drain()
            assert json.loads(await reader.readline())["code"] == "CONTAINER_OPERATION_NOT_ALLOWED"
            writer.close()
            await writer.wait_closed()
        finally:
            await server.close()
    asyncio.run(run())


def test_foreign_peer_is_refused_before_any_task_dispatch(tmp_path, monkeypatch):
    from so101_teleop.unified import child_runtime
    async def run():
        port = RecordingTaskPort()
        server = task_server(tmp_path, port)
        await server.start()
        try:
            monkeypatch.setattr(child_runtime, "peer_uid", lambda _sock: os.geteuid() + 1)
            reply = await exchange(server, request("get_status", dict(task_id=None)))
            assert reply == dict(accepted=False, code="IPC_PEER_REJECTED", ack=None, terminal=None, result=None)
            monkeypatch.setattr(child_runtime, "peer_uid", lambda _sock: None)
            assert (await exchange(server, request("get_status", dict(task_id=None))))["code"] == "IPC_PEER_REJECTED"
            assert port.calls == []
        finally:
            await server.close()
    asyncio.run(run())


def test_no_heartbeat_request_kind_on_container_socket(tmp_path):
    async def run():
        port = RecordingTaskPort()
        server = task_server(tmp_path, port)
        await server.start()
        try:
            reply = await exchange(server, dict(kind="owner_heartbeat", generation=7, sequence=1, sent_monotonic_ns=1))
            assert reply["accepted"] is False and reply["code"] == "CONTAINER_OPERATION_NOT_ALLOWED"
            assert port.calls == []
        finally:
            await server.close()
    asyncio.run(run())
    from so101_teleop.unified.child_runtime import ContainerChildIpcServer
    import inspect
    assert "heartbeat" not in inspect.signature(ContainerChildIpcServer.__init__).parameters
    assert not hasattr(ContainerChildIpcServer, "owner_monitor")
