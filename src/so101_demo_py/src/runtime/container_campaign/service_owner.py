"""Host campaign-lifetime inference services, borrowed by cases and waves.

This consumes an admitted context. It performs local input/provenance checks,
not GPU or campaign authorization. Failed/unknown exits keep cleanup unconfirmed.
"""

import asyncio
import copy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
from types import SimpleNamespace

from so101_demo.runtime.container_campaign.launch import InferenceLaunchArgs, build_container_argv
from so101_demo.runtime.container_campaign.process_identity import ContainerOwnerKey, container_key_from_inspect
from so101_demo.runtime.container_campaign.provenance import read_container_provenance
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_demo.runtime.inference.client import InferenceClient
from so101_demo.runtime.inference.config import _service, calibration_runtime_hash, load_campaign_config
from so101_demo.runtime.inference.contract import validate_service_response
from so101_demo.runtime.parallel_ipc.frames import canonical_json
from so101_teleop.unified.contracts import AdmittedCampaignContext


def _docker(argv):
    return subprocess.run(argv, capture_output=True, text=True, timeout=30)


def _query(client, kind, request_id, timeout_s):
    return client.query(kind, request_id, timeout_s=timeout_s)


def _write(path, document):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(canonical_json(document)+b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


@dataclass(frozen=True, slots=True)
class ServiceEndpoint:
    role: str
    socket_path: Path
    service_generation: str
    max_frame_bytes: int

    def client(self):
        # Every local Worker owner gets its own one-pending-request client.
        return InferenceClient(socket_path=self.socket_path, service_generation=self.service_generation,
                               max_frame_bytes=self.max_frame_bytes)


class ContainerServiceOwner:
    def __init__(self, *, admitted_context, config, paths, roles, registry,
                 startup_timeout_s, receive_budget_s, stop_timeout_s, head_descriptor=None,
                 head_descriptor_sha256=None, docker_runner=_docker, query=_query,
                 monotonic_ns=time.monotonic_ns):
        # Measurement launches Head only, a validation kind Head and Teacher, and collection Teacher only (CP-3608 ruling 2:
        # collection does not run Head Search). The Head descriptor exists only for a launched Head.
        kind = getattr(admitted_context, 'workload_kind', None)
        required_roles = (('head',) if kind == 'act_calibration_measurement_start'
                          else ('teacher',) if kind == 'act_collection_start' else ('head', 'teacher'))
        allowed = {'act_calibration_measurement_start', 'act_collection_start',
                   'pick_place_validation_full', 'pick_place_validation_phase'}
        if (type(admitted_context) is not AdmittedCampaignContext
                or admitted_context.workload_kind not in allowed or roles != required_roles
                or type(registry) is not ContainerLaunchRegistry or registry.records()
                or any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
                       for value in (startup_timeout_s, receive_budget_s, stop_timeout_s))):
            raise ValueError('SERVICE_OWNER_CONFIG_INVALID')
        self.context = admitted_context
        self.config, self.paths, self.roles, self.registry = copy.deepcopy(config), paths, roles, registry
        if (admitted_context.campaign_config_path is None or admitted_context.campaign_config_sha256 is None
                or admitted_context.registered_evidence_root != config['evidence_root']
                or load_campaign_config(admitted_context.campaign_config_path, roles=roles,
                    expected_sha256=admitted_context.campaign_config_sha256) != self.config):
            raise ValueError('SERVICE_OWNER_CONTEXT_MISMATCH')
        if (str(paths['run']) != admitted_context.evidence_root
                or not paths['run'].is_relative_to(Path(config['evidence_root']))
                or config['gpu_uuid'] != admitted_context.physical_gpu_uuid
                or config['controlled_runtime']['sha256'] != admitted_context.runtime_config_sha256
                or calibration_runtime_hash(config['controlled_runtime']['path']) != admitted_context.runtime_config_sha256):
            raise ValueError('SERVICE_OWNER_CONTEXT_MISMATCH')
        for role in roles:
            _service(self.config[role+'_service'], role, readback=True)
        if self.config['head_service']['image'] != self.config['teacher_service']['image']:
            raise ValueError('SERVICE_OWNER_CONFIG_INVALID')
        if 'head' in roles:
            if (head_descriptor is None or head_descriptor_sha256 is None
                    or calibration_runtime_hash(head_descriptor) != head_descriptor_sha256):
                raise ValueError('SERVICE_OWNER_CONFIG_INVALID')
        elif head_descriptor is not None or head_descriptor_sha256 is not None:
            raise ValueError('SERVICE_OWNER_CONFIG_INVALID')
        self.head_descriptor = None if head_descriptor is None else Path(head_descriptor)
        self.head_descriptor_sha256 = head_descriptor_sha256
        self.startup_timeout_s, self.receive_budget_s, self.stop_timeout_s = (
            startup_timeout_s, receive_budget_s, stop_timeout_s)
        self.docker_runner, self.query, self.clock = docker_runner, query, monotonic_ns
        self._launch_ids, self._endpoints = [], {}
        self._start_task = self._close_task = None
        self._startup_done = asyncio.Event()
        self._closing = False

    def inspect_container(self, container_id):
        value = self.docker_runner(['docker', 'inspect', container_id])
        if value.returncode != 0:
            raise ValueError('SERVICE_CONTAINER_INSPECT_FAILED')
        documents = json.loads(value.stdout)
        if type(documents) is not list or len(documents) != 1:
            raise ValueError('SERVICE_CONTAINER_INSPECT_FAILED')
        return documents[0]

    async def start(self):
        if self._start_task is not None or self._closing:
            raise ValueError('SERVICE_OWNER_ALREADY_STARTED')
        self._start_task = asyncio.create_task(self._start())
        try:
            return await asyncio.shield(self._start_task)
        except BaseException as error:
            await self.close()
            if isinstance(error, asyncio.CancelledError):
                raise
            raise ValueError('SERVICE_OWNER_START_FAILED') from error

    async def _start(self):
        try:
            # Prepare and validate both fixed commands before the first spawn.
            deadline = min(self.clock()+int(self.startup_timeout_s*1e9),
                           int(self.context.deadline_monotonic_s*1e9))
            prepared = []
            for role in self.roles:
                settings = self.config[role+'_service']
                config_path = self.paths['run']/(role+'-service.json')
                _write(config_path, settings)
                owned = self.paths['services'][role]
                (owned/'tmp').mkdir(mode=0o700)
                generation = self.paths['run'].name+'-'+role+'-g1'
                entry = InferenceLaunchArgs(config=config_path, generation=generation,
                    startup_deadline_monotonic_ns=deadline, receive_budget_s=self.receive_budget_s,
                    head_descriptor=self.head_descriptor if role == 'head' else None,
                    head_descriptor_sha256=self.head_descriptor_sha256 if role == 'head' else None)
                from so101_demo.cli.campaign_inference import _inputs
                _inputs(SimpleNamespace(config=config_path, role=role, gpu_uuid=self.config['gpu_uuid'],
                    startup_deadline_monotonic_ns=deadline, head_descriptor=entry.head_descriptor,
                    head_descriptor_sha256=entry.head_descriptor_sha256))
                images = {name:self.config[name+'_service']['image'] for name in ('head','teacher')}
                images['shard'] = self.config['shard_image']
                argv = build_container_argv(role=role, image=images, gpu_uuid=self.config['gpu_uuid'],
                    host_paths=dict(owned_root=owned, approved_inputs=(Path(settings['model']['weights']['path']),),
                        socket_roots=self.paths['socket_roots'], config_paths=(config_path, self.head_descriptor)
                            if role == 'head' else (config_path,), entry=entry),
                    container_name='so101-'+generation, uid=os.getuid(), gid=os.getgid())
                prepared.append((role, generation, argv))
            for role, generation, argv in prepared:
                if self._closing or self.clock() >= deadline:
                    raise ValueError('SERVICE_OWNER_START_FENCED')
                settings = self.config[role+'_service']
                launch = ContainerLaunch(launch_id=role+'-g1', role=role, worker_id=None, wave_id=None,
                    launch_generation=1, container_name=argv[argv.index('--name')+1],
                    image_digest=settings['image']['digest'], owned_root=str(self.paths['services'][role]))
                self.registry.register(launch)
                self._launch_ids.append(launch.launch_id)
                _write(self.paths['host']/(role+'-launch-argv.json'), argv)
                result = await asyncio.to_thread(self.docker_runner, argv)
                _write(self.paths['host']/(role+'-launch-result.json'), dict(
                    exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
                if result.returncode != 0 or re.fullmatch(r'[0-9a-f]{64}', result.stdout.strip()) is None:
                    raise ValueError('SERVICE_CONTAINER_LAUNCH_FAILED')
                cid = result.stdout.strip()
                observed = await asyncio.to_thread(self.inspect_container, cid)
                owner = container_key_from_inspect(observed, launch_generation=1)
                if observed.get('Name') != '/'+launch.container_name:
                    raise ValueError('SERVICE_CONTAINER_IDENTITY_CHANGED')
                self.registry.bind_container(launch.launch_id, owner)
                endpoint = ServiceEndpoint(role, self.paths['socket_roots'][role]/'inference.sock',
                                           generation, settings['max_frame_bytes'])
                client = endpoint.client()
                sequence = 0
                while True:
                    if self._closing or self.clock() >= deadline:
                        raise ValueError('SERVICE_OWNER_START_FENCED')
                    observed = await asyncio.to_thread(self.inspect_container, cid)
                    if (container_key_from_inspect(observed, launch_generation=1) != owner
                            or observed['State']['Running'] is not True or observed['State']['Restarting'] is not False):
                        raise ValueError('SERVICE_CONTAINER_NOT_RUNNING')
                    sequence += 1
                    request_id = 'ready-'+str(sequence)
                    try:
                        ready = await asyncio.to_thread(self.query, client, 'service_ready', request_id,
                            min(self.receive_budget_s, (deadline-self.clock())/1e9))
                    except (OSError, TimeoutError):
                        await asyncio.sleep(.05)
                        continue
                    ready = validate_service_response(ready)
                    expected = dict(request_id=request_id, service_generation=generation,
                        image_digest=settings['image']['digest'], package_source_sha256=settings['image']['package_source_sha256'],
                        model_id=settings['model']['model_id'], weights_sha256=settings['model']['weights']['sha256'],
                        service_config_sha256=hashlib.sha256(canonical_json(settings)).hexdigest(),
                        gpu_uuid=self.config['gpu_uuid'], configured_instances=settings['instances'])
                    if any(ready[name] != value for name, value in expected.items()):
                        raise ValueError('SERVICE_READY_IDENTITY_MISMATCH')
                    if ready['ready'] is True and ready['loaded_instances'] == settings['instances']:
                        break
                    await asyncio.sleep(.05)
                actual = await asyncio.to_thread(read_container_provenance, cid, docker_runner=self.docker_runner)
                if (actual['image_digest'] != settings['image']['digest'] or any(
                        actual['provenance'][name] != settings['image'][name]
                        for name in ('package_source_sha256','install_sha256'))):
                    raise ValueError('SERVICE_IMAGE_PROVENANCE_MISMATCH')
                _write(self.paths['host']/(role+'-ready.json'), ready)
                _write(self.paths['host']/(role+'-provenance.json'), actual)
                self._endpoints[role] = endpoint
            return self._endpoints.copy()
        finally:
            self._startup_done.set()

    async def check_health(self):
        if (self._closing or self._start_task is None or not self._start_task.done()
                or self._start_task.cancelled() or self._start_task.exception() is not None
                or set(self._endpoints) != set(self.roles)):
            raise ValueError('SERVICE_OWNER_NOT_AVAILABLE')
        for role in self.roles:
            record = next(item for item in self.registry.records() if item['launch']['launch_id'] == role+'-g1')
            cid = record['owner']['container_id']
            observed = await asyncio.to_thread(self.inspect_container, cid)
            if (container_key_from_inspect(observed, launch_generation=1) != ContainerOwnerKey(**record['owner'])
                    or observed['State']['Running'] is not True or observed['State']['Restarting'] is not False):
                raise ValueError('SERVICE_CONTAINER_NOT_RUNNING')
            client = self._endpoints[role].client()
            request_id = 'health-'+str(self.clock())
            health = validate_service_response(await asyncio.to_thread(
                self.query, client, 'service_health', request_id, self.receive_budget_s))
            if (health['kind'] != 'service_health' or health['request_id'] != request_id
                    or health['service_generation'] != client.generation or health['available'] is not True):
                raise ValueError('SERVICE_OWNER_NOT_AVAILABLE')
        return True

    async def close(self):
        self._closing = True
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close())
        return await asyncio.shield(self._close_task)

    async def _close(self):
        if self._start_task is not None:
            await self._startup_done.wait()
        errors = {}
        for launch_id in reversed(self._launch_ids):
            record = next(item for item in self.registry.records() if item['launch']['launch_id'] == launch_id)
            try:
                if record['owner'] is None:
                    raise ValueError('LAUNCH_OWNER_UNKNOWN')
                cid = record['owner']['container_id']
                observed = await asyncio.to_thread(self.inspect_container, cid)
                if container_key_from_inspect(observed, launch_generation=1) != ContainerOwnerKey(**record['owner']):
                    raise ValueError('SERVICE_CONTAINER_IDENTITY_CHANGED')
                if observed['State']['Running'] is True:
                    result = await asyncio.to_thread(self.docker_runner, ['docker','kill','--signal','TERM',cid])
                    if result.returncode != 0:
                        raise ValueError('SERVICE_CONTAINER_SIGNAL_FAILED')
                deadline = self.clock()+int(self.stop_timeout_s*1e9)
                while observed['State']['Running'] is True:
                    if self.clock() >= deadline:
                        raise ValueError('SERVICE_CONTAINER_EXIT_UNCONFIRMED')
                    await asyncio.sleep(.05)
                    observed = await asyncio.to_thread(self.inspect_container, cid)
                self.registry.prove_terminated(launch_id, observed)
            except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
                errors[launch_id] = dict(type=type(error).__name__, reason=str(error))
        return dict(terminated=not errors, launch_ids=self._launch_ids.copy(), errors=errors)
