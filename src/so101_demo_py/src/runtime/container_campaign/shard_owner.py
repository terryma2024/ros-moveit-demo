"""Host ownership of one private shard, with durable intent and original stop proof."""

import asyncio
import functools
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

from so101_demo.act.parallel_collection_contracts import read_document
from so101_demo.runtime.container_campaign.instance_owner_common import (
    check_runtime_ready, load_instance_spec, read_instance_exit)
from so101_demo.runtime.container_campaign.launch import ShardLaunchArgs, build_container_argv
from so101_demo.runtime.container_campaign.paths import CONTAINER_TEACHER_SOCKET
from so101_demo.runtime.container_campaign.docker_inspect import bounded_docker_inspect
from so101_demo.runtime.container_campaign.process_identity import container_key_from_inspect
from so101_demo.runtime.container_campaign.provenance import read_container_provenance
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.service_owner import _docker, _write
from so101_teleop.unified.bridge import ContainerBridgeProcessOwner
from so101_teleop.unified.contracts import AdmittedCampaignContext


def read_container_namespace(pid):
    """Read the exact Docker init namespace, repeating only a metadata denial."""
    if type(pid) is not int or pid <= 0:
        raise ValueError('SHARD_HOST_INIT_PID_INVALID')
    try:
        return os.stat(f'/proc/{pid}/ns/pid').st_ino
    except PermissionError:
        value = subprocess.check_output(['sudo','-n','/usr/bin/python3','-c',
            'import os,sys; print(os.stat("/proc/"+sys.argv[1]+"/ns/pid").st_ino)',str(pid)],
            text=True,timeout=10)
        inode = int(value.strip())
        if inode <= 0:
            raise ValueError('SHARD_HOST_NAMESPACE_INVALID')
        return inode


class ContainerShardOwner:
    def __init__(self, *, admitted_context, launch, entry, images, paths, registry,
                 approved_inputs, config_paths, service_token, startup_timeout_s,
                 status_timeout_s, max_frame_bytes, stop_timeout_s,
                 docker_runner=_docker, namespace_reader=read_container_namespace,
                 monotonic_ns=time.monotonic_ns, mount_build=None, cpuset_cpus=None):
        if (type(admitted_context) is not AdmittedCampaignContext
                or type(launch) is not ContainerLaunch or launch.role != 'shard'
                or type(entry) is not ShardLaunchArgs or type(registry) is not ContainerLaunchRegistry
                or str(paths['run']) != admitted_context.evidence_root
                or Path(launch.owned_root).resolve(strict=True) != Path(launch.owned_root)
                or not Path(launch.owned_root).is_relative_to(paths['run'])
                or entry.mujoco_session_id != launch.session_id
                or type(service_token) is not str or re.fullmatch(r'[0-9a-f]{64}',service_token) is None
                or type(max_frame_bytes) is not int or max_frame_bytes <= 0
                or any(type(v) not in (int,float) or not math.isfinite(v) or v <= 0 for v in
                       (startup_timeout_s,status_timeout_s,stop_timeout_s))):
            raise ValueError('SHARD_OWNER_CONFIG_INVALID')
        self.context,self.launch,self.entry,self.registry = admitted_context,launch,entry,registry
        self.root = Path(launch.owned_root)
        self.spec = load_instance_spec(entry.spec,admitted_context=admitted_context,launch=launch,
            service_token=service_token)
        self.spec_sha256 = hashlib.sha256(entry.spec.read_bytes()).hexdigest()
        self.argv = build_container_argv(role='shard',image=images,gpu_uuid=admitted_context.physical_gpu_uuid,
            host_paths=dict(owned_root=self.root,approved_inputs=approved_inputs,config_paths=config_paths,
                socket_roots=paths['socket_roots']|{'control':self.root/'control'},entry=entry),
            container_name=launch.container_name,uid=os.getuid(),gid=os.getgid(),mount_build=mount_build,
            cpuset_cpus=cpuset_cpus)
        self.mount_build = mount_build
        if images['shard']['digest'] != launch.image_digest:
            raise ValueError('SHARD_OWNER_CONFIG_INVALID')
        self.image = dict(images['shard'])
        self.token,self.startup_budget,self.status_budget,self.stop_budget = (
            service_token,startup_timeout_s,status_timeout_s,stop_timeout_s)
        self.max_bytes,self.docker,self.namespace_reader,self.clock = (
            max_frame_bytes,docker_runner,namespace_reader,monotonic_ns)
        self.owner,self.bridge = None,None
        self._registered,self._closing,self._runtime_ready = False,False,False
        self._start_task = self._close_task = None
        self._startup_done = asyncio.Event()

    @property
    def teacher_socket(self):
        """The Teacher socket as the instance reaches it: the fixed mount `build_role_mounts` gives every shard."""
        return CONTAINER_TEACHER_SOCKET

    def observe_exit(self):
        """One fresh reading of the registered container, the exit document `registry.prove_terminated` judges."""
        return self.inspect(self.owner.container_id)

    def inspect(self,container_id):
        result = bounded_docker_inspect(self.docker,['docker','inspect',container_id])
        if result.returncode != 0:
            raise ValueError('SHARD_CONTAINER_INSPECT_FAILED')
        documents = json.loads(result.stdout)
        if type(documents) is not list or len(documents) != 1:
            raise ValueError('SHARD_CONTAINER_INSPECT_FAILED')
        return documents[0]

    async def _observe(self):
        if self.owner is None:
            raise ValueError('LAUNCH_OWNER_UNKNOWN')
        observed = await asyncio.to_thread(self.inspect,self.owner.container_id)
        if container_key_from_inspect(observed,launch_generation=self.launch.launch_generation) != self.owner:
            raise ValueError('SHARD_CONTAINER_IDENTITY_CHANGED')
        return observed

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
            deadline = min(self.clock()+int(self.startup_budget*1e9),
                           int(self.context.deadline_monotonic_s*1e9))
            if self.clock() >= deadline:
                raise ValueError('SHARD_START_DEADLINE_EXPIRED')
            from so101_demo.runtime.act_instance.spec import load_spec
            if (hashlib.sha256(self.entry.spec.read_bytes()).hexdigest() != self.spec_sha256
                    or load_spec(self.entry.spec)[0] != self.spec):
                raise ValueError('SHARD_SPEC_CHANGED')
            # A cached exit cannot authorize reuse after a manual restart or
            # Docker identity change. Read the exact predecessor again before
            # creating the next generation's durable intent.
            for previous in self.registry.records():
                item=previous['launch']
                if item['role']=='shard' and item['worker_id']==self.launch.worker_id:
                    if previous['owner'] is None:
                        raise ValueError('LAUNCH_OWNER_UNKNOWN')
                    observed=await asyncio.to_thread(self.inspect,previous['owner']['container_id'])
                    self.registry.prove_terminated(item['launch_id'],observed)
            self.registry.register(self.launch)
            self._registered = True
            _write(self.root/'launch-argv.json',self.argv)
            result = await asyncio.to_thread(self.docker,self.argv)
            _write(self.root/'launch-result.json',dict(exit_code=result.returncode,
                   stdout=result.stdout,stderr=result.stderr))
            if result.returncode != 0 or re.fullmatch(r'[0-9a-f]{64}',result.stdout.strip()) is None:
                raise ValueError('SHARD_CONTAINER_LAUNCH_FAILED')
            cid = result.stdout.strip()
            first = await asyncio.to_thread(self.inspect,cid)
            owner = container_key_from_inspect(first,launch_generation=self.launch.launch_generation)
            if first.get('Name') != '/'+self.launch.container_name:
                raise ValueError('SHARD_CONTAINER_IDENTITY_CHANGED')
            self.registry.bind_container(self.launch.launch_id,owner)
            self.owner = owner
            control = self.root/'control'
            await self._wait_file(control/'child-ready.json',deadline)
            self.bridge = ContainerBridgeProcessOwner(container_owner=owner,control_socket_root=control,
                runtime_id=self.spec['runtime_id'],
                service_epoch=self.context.service_epoch,campaign_id=self.context.campaign_id,
                worker_id=self.launch.worker_id,execution_generation=self.context.execution_generation,
                session_id=self.launch.session_id,inspect_container=self.inspect,
                namespace_reader=self.namespace_reader)
            binding = self.bridge.accept_ready(read_document(control/'child-ready.json'))
            self.registry.bind_child(self.launch.launch_id,binding)
            await self._wait_file(self.root/'runtime-ready.json',deadline)
            await self._wait_file(self.root/'stack-readiness.json',deadline)
            check_runtime_ready(self.root,generation=self.launch.launch_generation,process=binding.process)
            actual = await asyncio.to_thread(functools.partial(read_container_provenance,cid,docker_runner=self.docker,
                **({} if self.mount_build is None else dict(mount_role='shard',install_root=str(self.mount_build.install)))))
            if (actual['image_digest'] != self.image['digest'] or any(
                    actual['provenance'][name] != self.image[name]
                    for name in ('package_source_sha256','install_sha256'))
                    or (self.mount_build is not None and actual['provenance']['git_commit'] != self.mount_build.commit)):
                raise ValueError('SHARD_IMAGE_PROVENANCE_CHANGED')
            if self.mount_build is not None:
                actual = dict(actual,mount_build=self.mount_build.document())
            _write(self.root/'actual-container-provenance.json',actual)
            await self._ensure_alive(deadline)
            self._runtime_ready = True
            return binding
        finally:
            self._startup_done.set()

    async def _ensure_alive(self,deadline):
        if self._closing or self.clock() >= deadline:
            raise ValueError('SHARD_START_FENCED')
        observed = await self._observe()
        if (observed['State']['Running'] is not True or observed['State']['Restarting'] is not False
                or observed['State'].get('OOMKilled') is True):
            raise ValueError('SHARD_CONTAINER_NOT_RUNNING')
        return True

    async def _wait_file(self,path,deadline):
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
        return ContainerControlClient(binding=self.bridge.binding,context=self.context,
            runtime_id=self.spec['runtime_id'],service_token=self.token,max_bytes=self.max_bytes,
            ready_probe=self.bridge.ready)

    async def close(self):
        self._closing = True
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close())
        return await asyncio.shield(self._close_task)

    async def _close(self):
        if self._start_task is not None:
            await self._startup_done.wait()
        errors = []
        if self._registered:
            try:
                if self.owner is None:
                    raise ValueError('LAUNCH_OWNER_UNKNOWN')
                observed = await self._observe()
                if observed['State']['Running'] is True:
                    # Signal only the exact registered owner. The child's SIGTERM path is idempotent with
                    # an already running terminate, so a failed or slow RPC cannot leave it running.
                    result = await asyncio.to_thread(self.docker,
                        ['docker','kill','--signal','TERM',self.owner.container_id])
                    if result.returncode != 0:
                        observed = await self._observe()
                        if observed['State']['Running'] is True:
                            raise ValueError('SHARD_CONTAINER_SIGNAL_FAILED')
                deadline = self.clock()+int(self.stop_budget*1e9)
                while observed['State']['Running'] is True:
                    if self.clock() >= deadline:
                        raise ValueError('SHARD_CONTAINER_EXIT_UNCONFIRMED')
                    await asyncio.sleep(.05)
                    observed = await self._observe()
                _write(self.root/'final-inspect.json',observed)
                self.registry.prove_terminated(self.launch.launch_id,observed)
            except Exception as error:
                errors.append(dict(type=type(error).__name__,reason=str(error)))
        result = dict(terminated=not errors,launch_id=self.launch.launch_id,errors=errors)
        _write(self.root/'host-cleanup.json',result)
        return result

    async def prove_stopped(self):
        """Re-read the exact registered container and the child's original stop evidence; sends no signal."""
        errors = []
        try:
            if not self._registered or self.owner is None:
                raise ValueError('LAUNCH_OWNER_UNKNOWN')
            observed = await self._observe()
            self.registry.prove_terminated(self.launch.launch_id,observed)
            if not (self.root/'late-exit-proof.json').exists():
                _write(self.root/'late-exit-proof.json',observed)
        except Exception as error:
            errors.append(dict(type=type(error).__name__,reason=str(error)))
        return dict(terminated=not errors,launch_id=self.launch.launch_id,errors=errors)

    def instance_exit(self):
        """The child's own exit record, or None when it is absent or not a closed, valid record."""
        return read_instance_exit(self.root)
