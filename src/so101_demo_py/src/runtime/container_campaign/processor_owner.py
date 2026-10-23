"""Host ownership of one private processor container (phase 2), with durable intent and a container-exit stop proof.

It is modelled on `shard_owner.ContainerShardOwner` and reuses its Docker reads, close, stop proof and control client. What
differs is what a processor is: the shard image with the `campaign_processor` entrypoint, no GPU, no Teacher socket, no ROS
graph. Readiness is the program's own `processor-ready.json` (written once its control server accepts calls). The stop proof is the
exit inspect of the exact registered container: a processor has no shard stop receipt.
"""

import asyncio
import functools
import hashlib
import math
import os
from pathlib import Path
import re
import time

from so101_demo.act.parallel_collection_contracts import read_document
from so101_demo.runtime.act_processor.program import READY_KIND, READY_NAME
from so101_demo.runtime.act_processor.spec import load_processor_spec
from so101_demo.runtime.container_campaign.launch import ProcessorLaunchArgs, build_container_argv
from so101_demo.runtime.container_campaign.process_identity import container_key_from_inspect
from so101_demo.runtime.container_campaign.provenance import read_container_provenance
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.service_owner import _docker, _write
from so101_demo.runtime.container_campaign.shard_owner import ContainerShardOwner, read_container_namespace
from so101_teleop.unified.bridge import ContainerBridgeProcessOwner
from so101_teleop.unified.contracts import AdmittedCampaignContext
from dataclasses import asdict


def check_processor_ready(root, *, generation, process):
    """The processor's ready record names this generation and this process."""
    ready = read_document(Path(root) / READY_NAME)
    expected = dict(schema_version=1, kind=READY_KIND, generation=generation, process_owner=asdict(process))
    if set(ready) != set(expected) or any(
            ready[name] != value or type(ready[name]) is not type(value) for name, value in expected.items()):
        raise ValueError('PROCESSOR_RUNTIME_READINESS_INVALID')
    return ready


class ContainerProcessorOwner(ContainerShardOwner):
    """One processor container. `phase1_attempts` are the sealed attempt directories it may read (mounted read-only)."""

    def __init__(self, *, admitted_context, launch, entry, images, paths, registry, approved_inputs, config_paths,
                 phase1_attempts, service_token, startup_timeout_s, status_timeout_s, max_frame_bytes, stop_timeout_s,
                 docker_runner=_docker, namespace_reader=read_container_namespace, monotonic_ns=time.monotonic_ns,
                 mount_build=None, cpuset_cpus=None):
        run = Path(paths['run'])
        if (type(admitted_context) is not AdmittedCampaignContext
                or type(launch) is not ContainerLaunch or launch.role != 'processor'
                or type(entry) is not ProcessorLaunchArgs or type(registry) is not ContainerLaunchRegistry
                or type(phase1_attempts) is not tuple or str(run) != admitted_context.evidence_root
                or Path(launch.owned_root).resolve(strict=True) != Path(launch.owned_root)
                or not Path(launch.owned_root).is_relative_to(run / 'processing')
                or type(service_token) is not str or re.fullmatch(r'[0-9a-f]{64}', service_token) is None
                or type(max_frame_bytes) is not int or max_frame_bytes <= 0
                or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in
                       (startup_timeout_s, status_timeout_s, stop_timeout_s))):
            raise ValueError('PROCESSOR_OWNER_CONFIG_INVALID')
        self.context, self.launch, self.entry, self.registry = admitted_context, launch, entry, registry
        self.root = Path(launch.owned_root)
        self.spec, _runtime = load_processor_spec(entry.spec)
        expected = dict(campaign_id=admitted_context.campaign_id, processor_id=launch.worker_id,
                        launch_generation=launch.launch_generation, execution_generation=admitted_context.execution_generation,
                        service_epoch=admitted_context.service_epoch, service_token=service_token,
                        owned_root=str(self.root), processing_root=str(run / 'processing'))
        if (any(self.spec.get(name) != value or type(self.spec.get(name)) is not type(value) for name, value in expected.items())
                or self.spec['deadline_monotonic_s'] > admitted_context.deadline_monotonic_s):
            raise ValueError('PROCESSOR_SPEC_CONTEXT_MISMATCH')
        self.spec_sha256 = hashlib.sha256(entry.spec.read_bytes()).hexdigest()
        self.argv = build_container_argv(role='processor', image=images, gpu_uuid=None,
            host_paths=dict(owned_root=self.root, approved_inputs=approved_inputs, config_paths=config_paths,
                socket_roots={'control': self.root / 'control'}, entry=entry, phase1_attempts=phase1_attempts,
                processing_root=run / 'processing'),
            container_name=launch.container_name, uid=os.getuid(), gid=os.getgid(), mount_build=mount_build,
            cpuset_cpus=cpuset_cpus)
        self.mount_build = mount_build
        if images['shard']['digest'] != launch.image_digest:
            raise ValueError('PROCESSOR_OWNER_CONFIG_INVALID')
        self.image = dict(images['shard'])
        self.phase1_attempts = phase1_attempts
        self.token, self.startup_budget, self.status_budget, self.stop_budget = (
            service_token, startup_timeout_s, status_timeout_s, stop_timeout_s)
        self.max_bytes, self.docker, self.namespace_reader, self.clock = (
            max_frame_bytes, docker_runner, namespace_reader, monotonic_ns)
        self.owner, self.bridge = None, None
        self._registered, self._closing, self._runtime_ready = False, False, False
        self._start_task = self._close_task = None
        self._startup_done = asyncio.Event()

    @property
    def teacher_socket(self):
        """A processor reaches no Teacher."""
        return None

    async def _start(self):
        try:
            deadline = min(self.clock() + int(self.startup_budget * 1e9), int(self.context.deadline_monotonic_s * 1e9))
            if self.clock() >= deadline:
                raise ValueError('PROCESSOR_START_DEADLINE_EXPIRED')
            if (hashlib.sha256(self.entry.spec.read_bytes()).hexdigest() != self.spec_sha256
                    or load_processor_spec(self.entry.spec)[0] != self.spec):
                raise ValueError('PROCESSOR_SPEC_CHANGED')
            # Read the exact predecessor of this slot again before creating the next generation's durable intent.
            for previous in self.registry.records():
                item = previous['launch']
                if item['role'] == 'processor' and item['worker_id'] == self.launch.worker_id:
                    if previous['owner'] is None:
                        raise ValueError('LAUNCH_OWNER_UNKNOWN')
                    observed = await asyncio.to_thread(self.inspect, previous['owner']['container_id'])
                    self.registry.prove_terminated(item['launch_id'], observed)
            self.registry.register(self.launch)
            self._registered = True
            _write(self.root / 'launch-argv.json', self.argv)
            result = await asyncio.to_thread(self.docker, self.argv)
            _write(self.root / 'launch-result.json', dict(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
            if result.returncode != 0 or re.fullmatch(r'[0-9a-f]{64}', result.stdout.strip()) is None:
                raise ValueError('PROCESSOR_CONTAINER_LAUNCH_FAILED')
            cid = result.stdout.strip()
            first = await asyncio.to_thread(self.inspect, cid)
            owner = container_key_from_inspect(first, launch_generation=self.launch.launch_generation)
            if first.get('Name') != '/' + self.launch.container_name:
                raise ValueError('PROCESSOR_CONTAINER_IDENTITY_CHANGED')
            self.registry.bind_container(self.launch.launch_id, owner)
            self.owner = owner
            control = self.root / 'control'
            await self._wait_file(control / 'child-ready.json', deadline)
            self.bridge = ContainerBridgeProcessOwner(container_owner=owner, control_socket_root=control,
                runtime_id=self.spec['runtime_id'], service_epoch=self.context.service_epoch,
                campaign_id=self.context.campaign_id, worker_id=self.launch.worker_id,
                execution_generation=self.context.execution_generation, session_id=self.launch.launch_id,
                inspect_container=self.inspect, namespace_reader=self.namespace_reader)
            binding = self.bridge.accept_ready(read_document(control / 'child-ready.json'))
            self.registry.bind_child(self.launch.launch_id, binding)
            await self._wait_file(self.root / READY_NAME, deadline)
            check_processor_ready(self.root, generation=self.launch.launch_generation, process=binding.process)
            actual = await asyncio.to_thread(functools.partial(read_container_provenance, cid, docker_runner=self.docker,
                **({} if self.mount_build is None else dict(mount_role='shard', install_root=str(self.mount_build.install)))))
            if (actual['image_digest'] != self.image['digest'] or any(
                    actual['provenance'][name] != self.image[name] for name in ('package_source_sha256', 'install_sha256'))
                    or (self.mount_build is not None and actual['provenance']['git_commit'] != self.mount_build.commit)):
                raise ValueError('PROCESSOR_IMAGE_PROVENANCE_CHANGED')
            if self.mount_build is not None:
                actual = dict(actual, mount_build=self.mount_build.document())
            _write(self.root / 'actual-container-provenance.json', actual)
            await self._ensure_alive(deadline)
            self._runtime_ready = True
            return binding
        finally:
            self._startup_done.set()
