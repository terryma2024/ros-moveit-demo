"""Host ownership of one native ACT instance: a Host process group running the same instance program a container runs.

`NativeInstanceOwner` has the surface of `ContainerShardOwner` (`start`, `check_health`, `control_client`, `close`,
`prove_stopped`, `instance_exit`, `observe_exit`), so the campaign owner, the wave coordinator, the task adapter and the wave
verifier use it unchanged. It differs where a container's isolation did the work:

* the instance is started in a session of its own, so it leads a process group, and it is identified by its kernel process
  identity (`NativeOwnerKey`), registered durably before it can do anything;
* the instance's environment is the fixed instance identity (domain 181, no namespace, localhost-only discovery, the instance
  marker) on top of the Host's, and nothing else on the Host may share that domain (admission enforces it);
* it is stopped with SIGTERM to the registered leader only, so the instance program retires itself and writes its own stop
  receipt; a stop is proven by that receipt plus the Host observation of `native_stop` (leader gone, group empty, no process
  still carrying the instance marker, Host ROS graph clear). Anything the instance left behind is terminated, recorded in
  `native-leftovers.json`, and makes that stop unconfirmed for good: only the instance's own retirement confirms a stop.
"""

import asyncio
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from so101_demo.act.parallel_collection_contracts import read_document
from so101_demo.runtime.act_instance.identity import (
    INSTANCE_OUTPUT_ENV, INSTANCE_ROOT_ENV, instance_environment)
from so101_demo.runtime.container_campaign.instance_owner_common import (
    check_runtime_ready, load_instance_spec, read_instance_exit)
from so101_demo.runtime.container_campaign.launch import ShardLaunchArgs, instance_private_environment
from so101_demo.runtime.container_campaign.native_stop import leader_state, observe_native_exit, stop_descendants
from so101_demo.runtime.container_campaign.process_identity import (
    NATIVE_LEADER_GONE, NativeOwnerKey, pid_namespace_inode, read_process_owner)
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.service_owner import _write
from so101_teleop.unified.contracts import AdmittedCampaignContext
from so101_teleop.unified.native_bridge import NativeBridgeProcessOwner


#: Variables of the Host environment an instance must not inherit: its identity is the fixed one, set explicitly below.
_NOT_INHERITED = frozenset({"ROS_NAMESPACE", "ROS_DOMAIN_ID", INSTANCE_ROOT_ENV, INSTANCE_OUTPUT_ENV, "CUDA_VISIBLE_DEVICES",
                            "SO101_MUJOCO_SESSION_ID", "GZ_PARTITION"})


def native_instance_environment(base, *, owned_root, session_id, gpu_uuid):
    """The environment of a native instance: the Host's, with the fixed instance identity and private locations on top.

    It mirrors the container launch: the same private temp, cache and log locations, the fixed ROS identity, and the instance
    marker the container shell sets only after it starts (here set from the start, so that the instance process itself and
    every descendant carry it). The selected GPU is the only CUDA device the instance sees."""
    environment = {name: value for name, value in base.items() if name not in _NOT_INHERITED}
    for entry in (*instance_private_environment(Path(owned_root)), *instance_environment(mujoco_session_id=session_id)):
        name, _, value = entry.partition("=")
        environment[name] = value
    environment[INSTANCE_ROOT_ENV] = str(owned_root)
    environment[INSTANCE_OUTPUT_ENV] = str(Path(owned_root) / "output")
    environment["CUDA_VISIBLE_DEVICES"] = gpu_uuid
    return environment


class NativeInstanceOwner:
    def __init__(self, *, admitted_context, launch, entry, paths, registry, service_token, startup_timeout_s,
                 status_timeout_s, max_frame_bytes, stop_timeout_s, install_prefix, ros2_executable, teacher_socket, command,
                 base_environment, graph_probe, popen=subprocess.Popen, monotonic_ns=time.monotonic_ns):
        if (type(admitted_context) is not AdmittedCampaignContext
                or type(launch) is not ContainerLaunch or launch.role != 'shard' or launch.launcher != 'native'
                or type(entry) is not ShardLaunchArgs or type(registry) is not ContainerLaunchRegistry
                or str(paths['run']) != admitted_context.evidence_root
                or Path(launch.owned_root).resolve(strict=True) != Path(launch.owned_root)
                or not Path(launch.owned_root).is_relative_to(paths['run'])
                or entry.mujoco_session_id != launch.session_id
                or type(service_token) is not str or re.fullmatch(r'[0-9a-f]{64}', service_token) is None
                or type(max_frame_bytes) is not int or max_frame_bytes <= 0
                or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in
                       (startup_timeout_s, status_timeout_s, stop_timeout_s))
                or not Path(install_prefix).is_absolute() or not Path(ros2_executable).is_absolute()
                or not Path(teacher_socket).is_absolute()
                or type(command) is not list or not command or any(type(item) is not str for item in command)
                or not callable(graph_probe) or not callable(popen)):
            raise ValueError('SHARD_OWNER_CONFIG_INVALID')
        self.context, self.launch, self.entry, self.registry = admitted_context, launch, entry, registry
        self.root = Path(launch.owned_root)
        self.spec = load_instance_spec(entry.spec, admitted_context=admitted_context, launch=launch,
            service_token=service_token)
        self.spec_sha256 = hashlib.sha256(entry.spec.read_bytes()).hexdigest()
        self.install_prefix, self._teacher_socket = Path(install_prefix), Path(teacher_socket)
        self.ros2_executable = Path(ros2_executable)
        self.argv = [*command, '--spec', str(entry.spec), '--install-prefix', str(self.install_prefix),
                     '--ros2', str(self.ros2_executable)]
        self.environment = native_instance_environment(base_environment, owned_root=self.root,
            session_id=launch.session_id, gpu_uuid=admitted_context.physical_gpu_uuid)
        self.token, self.startup_budget, self.status_budget, self.stop_budget = (
            service_token, startup_timeout_s, status_timeout_s, stop_timeout_s)
        self.max_bytes, self.graph_probe, self.popen, self.clock = max_frame_bytes, graph_probe, popen, monotonic_ns
        self.process, self.owner, self.bridge, self._log = None, None, None, None
        self._registered, self._closing, self._runtime_ready = False, False, False
        self._start_task = self._close_task = None
        self._startup_done = asyncio.Event()

    @property
    def teacher_socket(self):
        """The Teacher socket as the instance reaches it: the Host path of the same socket the container mounts."""
        return self._teacher_socket

    def observe_exit(self):
        """One fresh Host observation of the registered instance's exit, the document `registry.prove_terminated` judges."""
        if self.owner is None:
            raise ValueError('LAUNCH_OWNER_UNKNOWN')
        if self.process is not None:
            self.process.poll()         # reap our child so that a finished instance is not left as a zombie
        return observe_native_exit(self.owner, self.root, graph_probe=self.graph_probe)

    def _state(self):
        return leader_state(self.owner)

    async def start(self):
        if self._start_task is not None or self._closing:
            raise ValueError('SHARD_OWNER_ALREADY_STARTED')
        self._start_task = asyncio.create_task(self._start())
        try:
            return await asyncio.shield(self._start_task)
        except BaseException:
            await self.close()
            raise

    async def _start(self):
        try:
            deadline = min(self.clock()+int(self.startup_budget*1e9), int(self.context.deadline_monotonic_s*1e9))
            if self.clock() >= deadline:
                raise ValueError('SHARD_START_DEADLINE_EXPIRED')
            from so101_demo.runtime.act_instance.spec import load_spec
            if (hashlib.sha256(self.entry.spec.read_bytes()).hexdigest() != self.spec_sha256
                    or load_spec(self.entry.spec)[0] != self.spec):
                raise ValueError('SHARD_SPEC_CHANGED')
            # A cached exit cannot authorize reuse of the slot: read the exact predecessor's exit again first.
            for previous in self.registry.records():
                item = previous['launch']
                if item['role'] == 'shard' and item['worker_id'] == self.launch.worker_id:
                    if previous['owner'] is None:
                        raise ValueError('LAUNCH_OWNER_UNKNOWN')
                    if item.get('launcher', 'container') != 'native':
                        raise ValueError('LAUNCH_COLLISION: foreign launcher')
                    observed = await asyncio.to_thread(observe_native_exit, NativeOwnerKey(**previous['owner']),
                        Path(item['owned_root']), graph_probe=self.graph_probe)
                    self.registry.prove_terminated(item['launch_id'], observed)
            self.registry.register(self.launch)
            self._registered = True
            _write(self.root/'launch-argv.json', dict(argv=self.argv, launcher='native',
                environment_sha256=hashlib.sha256(json.dumps(self.environment, sort_keys=True).encode()).hexdigest(),
                fixed_environment={name: self.environment[name] for name in (
                    'ROS_DOMAIN_ID', 'ROS_LOCALHOST_ONLY', 'ROS_AUTOMATIC_DISCOVERY_RANGE', 'MUJOCO_GL',
                    INSTANCE_ROOT_ENV, INSTANCE_OUTPUT_ENV, 'CUDA_VISIBLE_DEVICES')}))
            fd = os.open(self.root/'native-instance.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            self._log = os.fdopen(fd, 'wb')
            try:
                self.process = self.popen(self.argv, env=self.environment, cwd=self.root, shell=False,
                    start_new_session=True, stdin=subprocess.DEVNULL, stdout=self._log, stderr=subprocess.STDOUT)
            except OSError as error:
                raise ValueError('SHARD_NATIVE_LAUNCH_FAILED') from error
            process = await self._identity(self.process.pid)
            self.owner = NativeOwnerKey.from_process(process, launch_generation=self.launch.launch_generation)
            self.registry.bind_native(self.launch.launch_id, self.owner)
            control = self.root/'control'
            await self._wait_file(control/'child-ready.json', deadline)
            self.bridge = NativeBridgeProcessOwner(native_owner=self.owner, control_socket_root=control,
                runtime_id=self.spec['runtime_id'], service_epoch=self.context.service_epoch,
                campaign_id=self.context.campaign_id, worker_id=self.launch.worker_id,
                execution_generation=self.context.execution_generation, session_id=self.launch.session_id)
            binding = self.bridge.accept_ready(read_document(control/'child-ready.json'))
            self.registry.bind_child(self.launch.launch_id, binding)
            await self._wait_file(self.root/'runtime-ready.json', deadline)
            await self._wait_file(self.root/'stack-readiness.json', deadline)
            check_runtime_ready(self.root, generation=self.launch.launch_generation, process=binding.process)
            _write(self.root/'native-instance-provenance.json', dict(schema_version=1, kind='ACT_NATIVE_INSTANCE_PROVENANCE',
                install_prefix=str(self.install_prefix), argv=self.argv, spec_sha256=self.spec_sha256,
                process_owner=asdict(self.owner.process_key()),
                host_pid_namespace_inode=pid_namespace_inode()))
            await self._ensure_alive(deadline)
            self._runtime_ready = True
            return binding
        finally:
            self._startup_done.set()

    async def _identity(self, pid):
        """The kernel identity of the process just spawned, after it has exec'd; retried only while it is incomplete."""
        until = time.monotonic()+2.
        while True:
            try:
                return await asyncio.to_thread(read_process_owner, pid)
            except (OSError, RuntimeError, ValueError) as error:
                if self.process.poll() is not None:
                    raise ValueError('SHARD_NATIVE_EXITED_BEFORE_IDENTITY') from error
                if time.monotonic() >= until:
                    raise ValueError('SHARD_NATIVE_IDENTITY_UNAVAILABLE') from error
                await asyncio.sleep(.01)

    async def _ensure_alive(self, deadline):
        if self._closing or self.clock() >= deadline:
            raise ValueError('SHARD_START_FENCED')
        if self.owner is None or await asyncio.to_thread(self._state) != 'live' or self.process.poll() is not None:
            raise ValueError('SHARD_NATIVE_NOT_RUNNING')
        return True

    async def _wait_file(self, path, deadline):
        while not path.exists():
            await self._ensure_alive(deadline)
            await asyncio.sleep(.05)
        await self._ensure_alive(deadline)

    async def check_health(self):
        if not self._runtime_ready or self.bridge is None:
            raise ValueError('SHARD_RUNTIME_NOT_READY')
        await self._ensure_alive(int(self.context.deadline_monotonic_s*1e9))
        if not await asyncio.to_thread(self.bridge.ready):
            raise ValueError('SHARD_RUNTIME_NOT_READY')
        return True

    def control_client(self):
        from so101_demo.runtime.container_campaign.control_client import ContainerControlClient
        # Status polling starts with the child binding, while the native stack is still starting.
        if self.bridge is None or self.bridge.binding is None or self._closing:
            raise ValueError('SHARD_RUNTIME_NOT_READY')
        return ContainerControlClient(binding=self.bridge.binding, context=self.context,
            runtime_id=self.spec['runtime_id'], service_token=self.token, max_bytes=self.max_bytes,
            ready_probe=self.bridge.ready)

    async def close(self):
        self._closing = True
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close())
        return await asyncio.shield(self._close_task)

    async def _close(self):
        if self._start_task is not None:
            await self._startup_done.wait()
        errors, signalled = [], []
        if self._registered:
            try:
                if self.owner is None:
                    # spawned but never identified: it is ours, so it must not outlive us, but it cannot be proven stopped
                    if self.process is not None and self.process.poll() is None:
                        await asyncio.to_thread(self._kill_unidentified)
                    raise ValueError('LAUNCH_OWNER_UNKNOWN')
                state = await asyncio.to_thread(self._state)
                if state == 'live':
                    # Signal only the exact registered leader. The instance program's SIGTERM path is idempotent with a
                    # terminate already running, so a failed or slow RPC cannot leave it running.
                    os.kill(self.owner.pid, signal.SIGTERM)
                deadline = self.clock()+int(self.stop_budget*1e9)
                while await asyncio.to_thread(self._state) not in NATIVE_LEADER_GONE:
                    if self.clock() >= deadline:
                        raise ValueError('SHARD_NATIVE_EXIT_UNCONFIRMED')
                    await asyncio.sleep(.05)
                    self.process.poll()
                self.process.poll()
                signalled = await asyncio.to_thread(stop_descendants, self.owner, self.root, timeout_s=3.)
                if signalled:
                    # What had to be terminated was not stopped by the instance's own retirement: the stop is not confirmed,
                    # and no later observation may confirm it.
                    _write(self.root/'native-leftovers.json', dict(signalled_groups=signalled))
                observed = await asyncio.to_thread(self.observe_exit)
                _write(self.root/'final-exit.json', observed)
                self._require_no_leftovers()
                self.registry.prove_terminated(self.launch.launch_id, observed)
            except Exception as error:
                errors.append(dict(type=type(error).__name__, reason=str(error)))
        if self._log is not None:
            self._log.close()
        result = dict(terminated=not errors, launch_id=self.launch.launch_id, errors=errors)
        _write(self.root/'host-cleanup.json', result | dict(signalled_groups=signalled))
        return result

    def _require_no_leftovers(self):
        if (self.root/'native-leftovers.json').exists():
            raise ValueError('SHARD_NATIVE_LEFTOVERS_TERMINATED')

    def _kill_unidentified(self):
        from so101_teleop.owned_group import terminate_group

        if os.getpgid(self.process.pid) == self.process.pid:
            terminate_group(pgid=self.process.pid, leader_pid=self.process.pid, timeout_s=3.)
        self.process.poll()

    async def prove_stopped(self):
        """Re-read the exact registered instance and its original stop evidence; sends no signal."""
        errors = []
        try:
            if not self._registered or self.owner is None:
                raise ValueError('LAUNCH_OWNER_UNKNOWN')
            observed = await asyncio.to_thread(self.observe_exit)
            self._require_no_leftovers()
            self.registry.prove_terminated(self.launch.launch_id, observed)
            if not (self.root/'late-exit-proof.json').exists():
                _write(self.root/'late-exit-proof.json', observed)
        except Exception as error:
            errors.append(dict(type=type(error).__name__, reason=str(error)))
        return dict(terminated=not errors, launch_id=self.launch.launch_id, errors=errors)

    def instance_exit(self):
        """The child's own exit record, or None when it is absent or not a closed, valid record."""
        return read_instance_exit(self.root)
