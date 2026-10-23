"""Host stop path of one bound shard: real registry, real stop evidence, real owner and task adapter.

Controlled doubles: the Docker daemon (inspect/kill) and the native stack/ROS goal probe behind the child's own
`NativeShardRetirement`. Nothing here claims a container, GPU or physical stop.
"""

import asyncio
import json
import os
import threading
import time
from types import SimpleNamespace

import pytest

from test_controller_stop import run_probe
from test_shard_owner import fixture
from so101_demo.runtime.container_campaign.process_identity import (
    ContainerChildBinding, ContainerOwnerKey, pid_namespace_inode, read_process_owner,
)
from so101_demo.runtime.container_campaign.registry import ContainerLaunch
from so101_demo.runtime.container_campaign.retirement import NativeShardRetirement
from so101_demo.runtime.parallel_ipc.frames import canonical_json
from so101_teleop.unified.act_stack import ActStackLaunch, ActStackProcessOwner
from so101_teleop.unified.bridge import ContainerBridgeProcessOwner
from so101_teleop.unified.contracts import OwnerKey

STARTED_AT = '2026-10-12T01:02:03.123Z'


class DockerDouble:
    """Controlled Docker daemon: inspect plus `kill --signal TERM`; the exit is scripted by the test."""

    def __init__(self, key, name, *, exit_on_signal=True):
        self.key, self.name, self.exit_on_signal = key, name, exit_on_signal
        self.running, self.signals, self.started_at = True, [], key.docker_started_at

    def document(self):
        return dict(Id=self.key.container_id, Image=self.key.image_digest, Name='/'+self.name,
            State=dict(StartedAt=self.started_at, Running=self.running, Restarting=False,
                       Pid=100 if self.running else 0, Status='running' if self.running else 'exited', ExitCode=0))

    def __call__(self, argv):
        if argv[:2] == ['docker', 'inspect']:
            assert argv[2] == self.key.container_id
            return SimpleNamespace(returncode=0, stdout=json.dumps([self.document()]), stderr='')
        if argv[:2] == ['docker', 'kill']:
            assert argv == ['docker', 'kill', '--signal', 'TERM', self.key.container_id]
            self.signals.append(argv)
            if self.exit_on_signal:
                self.running = False
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        raise AssertionError(argv)


def write_stop_evidence(root, launch, monkeypatch):
    """The child's real NativeShardRetirement with a controlled ROS goal probe and native stack."""
    _, goals, _ = run_probe(monkeypatch)
    stack_root = root/'stack'
    stack_root.mkdir(mode=0o700)
    process = read_process_owner(os.getpid())
    native = OwnerKey(501, 501, 100, 'a'*64, 'b'*64)
    class Stack(ActStackProcessOwner):
        async def stop(self, **kwargs):
            (stack_root/'cleanup-receipt.json').write_bytes(canonical_json(dict(schema_version=1,
                leader_pid=native.pid, pgid=native.pgid, started_ticks=native.started_ticks,
                argv_sha256=native.argv_sha256, session_id=launch.session_id, ros_domain_id=181,
                group_clear=True, graph_clear=True, physical_stop_confirmed=True, parent_exited=False,
                term_sent=True, kill_sent=False, finished_at_monotonic_ns=time.monotonic_ns())))
            self.process = self.owner = None
    stack = Stack(ActStackLaunch(ros2_executable=__import__('pathlib').Path('/usr/bin/true'),
        session_id=launch.session_id, evidence_root=stack_root, ros_domain_id=181, environment={}),
        ready_probe=lambda: True, stop_probe=lambda: True, graph_clear_probe=lambda: True)
    stack.owner, stack.process = native, SimpleNamespace(pid=501)
    retirement = NativeShardRetirement(process_owner=process, launch_generation=launch.launch_generation,
        evidence_root=root, stack=stack, goal_stop_budget_s=5,
        stack_stop_budget_s=15, goal_stop_probe=lambda **kwargs: goals)
    # A separate thread keeps this usable from inside a running test loop.
    worker = threading.Thread(target=lambda: asyncio.run(retirement.retire(fenced=True)))
    worker.start()
    worker.join()
    return process


def bound_owner(tmp_path, *, evidence=None, exit_on_signal=True):
    """A registered shard whose container and child binding already exist, as after `_start` bound them."""
    owner, registry, calls, root = fixture(tmp_path, (0, ''))
    launch = owner.launch
    key = ContainerOwnerKey('f'*64, STARTED_AT, owner.image['digest'], launch.launch_generation)
    process = evidence() if evidence is not None else read_process_owner(os.getpid())
    registry.register(launch)
    registry.bind_container(launch.launch_id, key)
    binding = ContainerChildBinding(key, process, pid_namespace_inode(), str(root/'control/normal.sock'))
    registry.bind_child(launch.launch_id, binding)
    docker = DockerDouble(key, launch.container_name, exit_on_signal=exit_on_signal)
    owner.docker = docker
    owner.owner, owner._registered = key, True
    owner.bridge = ContainerBridgeProcessOwner(container_owner=key, control_socket_root=root/'control',
        runtime_id=owner.spec['runtime_id'], service_epoch=owner.context.service_epoch,
        campaign_id=owner.context.campaign_id, worker_id=launch.worker_id,
        execution_generation=owner.context.execution_generation,
        session_id=launch.session_id, inspect_container=owner.inspect,
        namespace_reader=lambda _pid: pid_namespace_inode())
    owner.bridge.binding = binding
    return owner, registry, root, docker


def next_generation(launch):
    __import__('pathlib').Path(launch.owned_root+'-next').mkdir(exist_ok=True)
    return ContainerLaunch(launch_id='measurement-w00-g2', role='shard', worker_id='w00', wave_id='measurement',
        launch_generation=2, container_name='so101-campaign-w00-g2', image_digest=launch.image_digest,
        owned_root=launch.owned_root+'-next',
        session_id='campaign-w00-g2')


def test_close_signals_bound_running_container(tmp_path, monkeypatch):
    owner, registry, root, docker = bound_owner(tmp_path)
    write_stop_evidence(root, owner.launch, monkeypatch)
    async def run():
        receipt = await owner.close()
        assert receipt == dict(terminated=True, launch_id=owner.launch.launch_id, errors=[])
        assert docker.signals == [['docker', 'kill', '--signal', 'TERM', 'f'*64]]
        assert registry.records()[0]['exit_inspect']['State']['Status'] == 'exited'
        assert json.loads((root/'host-cleanup.json').read_text())['terminated'] is True
        assert (await owner.close()) == receipt and len(docker.signals) == 1
    try:
        asyncio.run(run())
    finally:
        registry.close()


def test_changed_container_identity_is_never_signalled(tmp_path, monkeypatch):
    owner, registry, root, docker = bound_owner(tmp_path)
    write_stop_evidence(root, owner.launch, monkeypatch)
    docker.started_at = '2026-10-12T02:00:00.000Z'
    async def run():
        receipt = await owner.close()
        assert receipt['terminated'] is False and receipt['errors'][0]['reason'] == 'SHARD_CONTAINER_IDENTITY_CHANGED'
        assert docker.signals == []
    try:
        asyncio.run(run())
    finally:
        registry.close()


def test_signal_that_does_not_stop_the_container_is_unconfirmed(tmp_path, monkeypatch):
    owner, registry, root, docker = bound_owner(tmp_path, exit_on_signal=False)
    write_stop_evidence(root, owner.launch, monkeypatch)
    async def run():
        receipt = await owner.close()
        assert receipt['terminated'] is False and receipt['errors'][0]['reason'] == 'SHARD_CONTAINER_EXIT_UNCONFIRMED'
        assert len(docker.signals) == 1 and registry.records()[0]['exit_inspect'] is None
    try:
        asyncio.run(run())
    finally:
        registry.close()


def test_unproven_stop_keeps_slot_fenced(tmp_path):
    owner, registry, root, docker = bound_owner(tmp_path)
    async def run():
        # The container exits after the signal but the child left no native stop evidence: exit alone proves nothing.
        receipt = await owner.close()
        assert receipt['terminated'] is False and receipt['errors'][0]['reason'] == 'LAUNCH_STOP_UNCONFIRMED'
        assert registry.records()[0]['exit_inspect'] is None
        with pytest.raises(ValueError, match='LAUNCH_COLLISION: slot not retired'):
            registry.register(next_generation(owner.launch))
        assert len(registry.records()) == 1
    try:
        asyncio.run(run())
    finally:
        registry.close()


def test_prove_stopped_sends_no_signal_and_unfences_only_with_original_evidence(tmp_path, monkeypatch):
    owner, registry, root, docker = bound_owner(tmp_path, exit_on_signal=False)
    async def run():
        running = await owner.prove_stopped()
        assert running['terminated'] is False and running['errors'][0]['reason'] == 'LAUNCH_STOP_UNCONFIRMED'
        docker.running = False
        no_evidence = await owner.prove_stopped()
        assert no_evidence['terminated'] is False
        with pytest.raises(ValueError, match='LAUNCH_COLLISION: slot not retired'):
            registry.register(next_generation(owner.launch))
        write_stop_evidence(root, owner.launch, monkeypatch)
        proven = await owner.prove_stopped()
        assert proven == dict(terminated=True, launch_id=owner.launch.launch_id, errors=[])
        assert docker.signals == []
        registry.register(next_generation(owner.launch))
    try:
        asyncio.run(run())
    finally:
        registry.close()


def test_control_client_is_available_while_the_stack_is_still_starting(tmp_path):
    owner, registry, root, docker = bound_owner(tmp_path)
    try:
        assert owner._runtime_ready is False
        client = owner.control_client()
        assert client.binding is owner.bridge.binding and client.ready_probe() is True
        owner._closing = True
        with pytest.raises(ValueError, match='SHARD_RUNTIME_NOT_READY'):
            owner.control_client()
        assert not hasattr(owner.bridge, 'start_heartbeats') and not hasattr(owner, 'heartbeat_channel')
    finally:
        registry.close()


def test_no_exit_record_means_no_instance_exit(tmp_path):
    owner, registry, root, docker = bound_owner(tmp_path)
    try:
        assert owner.instance_exit() is None
        (root/'instance-exit.json').write_text(json.dumps(dict(schema_version=1, kind='ACT_SHARD_INSTANCE_EXIT',
            state='STOPPING', fault_reason='deadline', task=None, cleanup_confirmed=True, cleanup_errors=[])))
        assert owner.instance_exit()['fault_reason'] == 'deadline'
        (root/'instance-exit.json').write_text('{"fault_reason": "x"}')
        assert owner.instance_exit() is None
    finally:
        registry.close()


def test_late_exit_is_proven_on_repeated_terminate(tmp_path, monkeypatch):
    """Real task adapter over the real owner; the container ignores the first TERM and exits later."""
    from so101_demo.runtime.container_campaign.task_control import ContainerTaskControl
    owner, registry, root, docker = bound_owner(tmp_path, exit_on_signal=False)
    write_stop_evidence(root, owner.launch, monkeypatch)
    control = ContainerTaskControl(owner=owner)
    async def run():
        first = await control.terminate('CONTAINER_INSTANCE_EXECUTION_FAULT')
        assert first.state == 'STOPPING' and first.resources_released is False
        assert first.fault_reason == 'CONTAINER_INSTANCE_EXECUTION_FAULT' and len(docker.signals) == 1
        assert (await control.terminate('again')).resources_released is False
        docker.running = False
        released = await control.terminate('again')
        assert released.state == 'TERMINATED' and released.resources_released is True
        assert registry.records()[0]['exit_inspect'] is not None and len(docker.signals) == 1
        (root/'instance-exit.json').write_text('{}')  # a repeated call never re-reads or re-signals
        assert (await control.get_status()).resources_released is True
    try:
        asyncio.run(run())
    finally:
        registry.close()
