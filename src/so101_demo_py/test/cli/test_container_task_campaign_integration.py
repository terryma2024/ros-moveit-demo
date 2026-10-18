"""The collection CLI builds the real four-operation container campaign owner from its arguments.

REAL in every test here: argument parsing, `compose_services` (so the real `UnifiedWorkloadService`, `IntentStore` SQLite
admission, GPU lease and persistent slot registry), `make_campaign_paths`, the formal `freeze_inputs` through
`freeze_campaign_inputs`/`write_case_scopes`/`campaign_binding`, `prepare_collection_operation`, `load_campaign_config`,
`build_container_campaign_owner` with `ContainerLaunchRegistry`, `ContainerServiceOwner`, `ContainerShardLauncher`,
`ContainerShardOwner` (its whole start: durable intent, Docker identity binding, ready handshake, image provenance read, and its
whole close), `ConcurrentCollectionCoordinator`, `InstanceDispatch`, `ContainerTaskControl`, `ContainerTaskJournal`, the Host task
input writer, `read_container_task_result`, `ContainerCampaignOwner`, and `finish`.

CONTROLLED (passed through `CollectionEdges`, the CLI's only test seam, whose production defaults are the real probes):
the Docker executor (a scripted daemon that answers `run`/`inspect`/`exec`/`kill` and, for a shard `run`, writes the ready files a
shard would write), the NVML inventory, the host id, the installed-profile probe, the Teacher socket query, the container
namespace reader, and the container itself behind its control socket: a scripted instance that answers the four operations and
writes a real `task-result.json`. The ContainerControlClient socket transport and the in-container server are NOT exercised
here (see test_container_task_e2e.py); the shard's `control_client()` is still called, so its readiness checks run.
Test-local patches (not CLI seams): the installed package-share lookup, the execution-snapshot source root (as in
test_case_inputs.py), a recorder around `ContainerCampaignOwner`, a spy around `finish`, and - in the success tests only - the
wave verifier's readback, because the scripted container writes no committed episode; one test runs the real verifier and asserts
that it refuses exactly that.

Planes: the QUALIFICATION plane (W1 with the functional contract; W8 with the gate contract, whose `qualification_run_id` is the
`--run-id`) and the FORMAL plane. The formal plane is run to completion once, over a report that the real builder wrote from a
40-scene qualification run of the same registered evidence root (the world module of the qualification tests; its episode bytes,
QC recomputation and frozen-input reader are controlled and its rule files are TEST-ONLY), and admission verifies that report with
the real verifier; every other formal case fails closed. All approvals, scenes and images are synthetic; none of this is
container, physical or qualification evidence.
"""

import asyncio
from dataclasses import asdict
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import threading
from types import SimpleNamespace

import pytest

from paths import PACKAGE_ROOT, REPOSITORY
from so101_demo.act.diagnostic_episode_inputs import DEVELOPMENT_RUNTIME_FILE, resource_policy_identity
from so101_demo.cli import act_collect_parallel as cli
from so101_demo.cli.act_collect_parallel import CollectionEdges, main
from so101_demo.cli.mujoco_batch.request import _load_runtime_config
from so101_demo.runtime import act_fixed_collection_composition as composition
from so101_demo.runtime.container_campaign import result_verifier
from so101_demo.runtime.container_campaign.process_identity import pid_namespace_inode, read_process_owner
from so101_demo.runtime.container_campaign.provenance import freeze_image, verify_image_freeze
from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.task_contracts import InstanceStatus, TaskSpec, TaskStatus
from so101_demo.runtime.container_campaign.task_control import ContainerTaskControl
from so101_demo.runtime.container_campaign.task_results import reserve_task_output, write_task_result
from so101_demo.runtime.parallel_ipc.frames import canonical_json
from test_act_diagnostic_episode_scope import _write_registry
from collection_qualification_world import build_world, install_controlled_world
from collection_quality_rules import write_synthetic_rules
from so101_demo.act.parallel_qualification_verifier import build_collection_qualification_report
from test_case_inputs import bound_registry, policies
from so101_teleop.unified.contracts import Domain

GPU = 'GPU-28221cec-9d21-7753-fd5a-da645740df19'
DISK_FLOOR = 53687091200
CONTAINER_NAMESPACE = pid_namespace_inode() + 1
STOP_EVIDENCE_LOCK = threading.Lock()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return dict(path=str(path), sha256=sha(path))


def scene_rows(prefix, count, seed):
    return [dict(scene_id=f'{prefix}-{index:02d}', seed=seed + index, split='validation',
                 xy=[0.20 + 0.005 * index, 0.10], cup_position_world_m=[0.20 + 0.005 * index, 0.10, 0.165])
            for index in range(count)]


def write_json(path, document):
    path.write_text(json.dumps(document))
    return path


@pytest.fixture(scope='module')
def shared(tmp_path_factory):
    """Module-wide synthetic inputs: one candidate registry (real execution snapshot probe) and one image freeze."""
    from so101_demo.act import execution_snapshot

    base = tmp_path_factory.mktemp('cli-campaign').resolve()
    probe = execution_snapshot.freeze_execution_snapshot(REPOSITORY, base / 'probe')
    scene_bytes = (base / 'probe' / probe['scene_path']).read_bytes()
    runtime_bytes = (PACKAGE_ROOT / 'config/mujoco/parallel_batch_act_offline.yaml').read_bytes()
    collection_bytes = (PACKAGE_ROOT / 'config/act/parallel_collection.yaml').read_bytes()
    registry = bound_registry(base, probe, scene_bytes, runtime_config=runtime_bytes, collection_config=collection_bytes)
    # the real runtime file carries no hard stops: the freeze reads them from the development runtime document of the
    # registry's source root, so the synthetic source root carries a copy of the repository's
    development = Path(registry['source_root']) / DEVELOPMENT_RUNTIME_FILE
    development.parent.mkdir(parents=True)
    development.write_bytes(policies()['runtime_policy'].read_bytes())
    registry['roles']['resource_thresholds']['identity'] = resource_policy_identity(
        runtime_bytes, collection_bytes, development_runtime=development)
    candidates = _write_registry(base, registry)
    proposal = json.loads(Path(registry['roles']['contact_proposal']['selected']['path']).read_bytes())
    source, install = base / 'image-source', base / 'image-install'
    source.mkdir()
    install.mkdir()
    (source / '.image-git.json').write_text(json.dumps(dict(git_commit='1' * 40, submodules={})))
    (install / 'installed.py').write_text('installed')
    runtime = dict(interpreter='/act/venv/bin/python', dependencies={'numpy': '1.26.4'},
        module_origins={'so101_demo': '/act/install/lib/so101_demo/__init__.py'},
        package_prefixes={'so101_demo_py': '/act/install'})
    manifest = freeze_image(source_root=source, install_root=install, git_commit='1' * 40, submodules={}, runtime=runtime)
    report = verify_image_freeze(manifest, source_root=source, install_root=install, runtime=runtime)
    teacher_image = dict(digest='sha256:' + 'b' * 64, package_source_sha256=report['package_source_sha256'],
                         install_sha256=report['install_sha256'])
    return SimpleNamespace(base=base, candidates=candidates, fingerprint=proposal['policy_fingerprint'],
        runtime_bytes=runtime_bytes, collection_bytes=collection_bytes, report=report, teacher_image=teacher_image,
        shard_image=dict(teacher_image, digest='sha256:' + 'd' * 64))


def controlled_stop_evidence(spec, namespace_inode):
    """What a shard leaves in its owned root when told to stop: `shard-stop.json` and `retirement/*`.

    REAL: `NativeShardRetirement` and its evidence writers (which the Host's `read_shard_stop_evidence` then validates).
    CONTROLLED: the ROS cancel/status ports (as in test_controller_stop.py) and the native stack stop; the container's PID
    namespace number is the controlled one the ready document carried."""
    import time as _time

    from so101_demo.runtime.container_campaign import controller_stop, retirement
    from so101_teleop.unified.act_stack import ActStackLaunch, ActStackProcessOwner
    from so101_teleop.unified.contracts import OwnerKey

    root = Path(spec['owned_root'])
    (root / 'stack').mkdir(mode=0o700)
    native = OwnerKey(501, 501, 100, 'a' * 64, 'b' * 64)
    clock = [1_000_000_000]

    class Future:
        def done(self):
            return True

        def result(self):
            return SimpleNamespace(return_code=0, goals_canceling=[])

    class Node:
        def __init__(self):
            self.callbacks = {}

        def create_subscription(self, _type, topic, callback, _qos):
            self.callbacks[topic] = callback
            return object()

        def create_client(self, _type, topic):
            return SimpleNamespace(wait_for_service=lambda **kwargs: True, call_async=lambda request: Future())

    class Owner:
        def __init__(self):
            self.node = Node()

        def spin_once(self, **kwargs):
            clock[0] += 10_000_000
            for callback in self.node.callbacks.values():
                callback(SimpleNamespace(status_list=[SimpleNamespace(status=4, goal_info=SimpleNamespace(
                    goal_id=SimpleNamespace(uuid=list(range(16))), stamp=SimpleNamespace(sec=1, nanosec=2)))]))

        def close(self):
            pass

    class Stack(ActStackProcessOwner):
        async def stop(self, **kwargs):
            (root / 'stack' / 'cleanup-receipt.json').write_bytes(canonical_json(dict(schema_version=1,
                leader_pid=native.pid, pgid=native.pgid, started_ticks=native.started_ticks, argv_sha256=native.argv_sha256,
                session_id=spec['simulation_session_id'], ros_domain_id=181, group_clear=True,
                graph_clear=True, physical_stop_confirmed=True, parent_exited=False, term_sent=True, kill_sent=False,
                finished_at_monotonic_ns=_time.monotonic_ns())))
            self.process = self.owner = None

    with STOP_EVIDENCE_LOCK, pytest.MonkeyPatch.context() as patch:    # the patches are process-global: one shard at a time
        patch.setattr(controller_stop, '_open_owner', lambda: Owner())
        patch.setattr(controller_stop, '_ros_types', lambda: (object, SimpleNamespace(Request=lambda: object()), object()))
        patch.setattr(retirement, 'pid_namespace_inode', lambda: namespace_inode)
        observation = controller_stop.observe_act_controller_stop(timeout_s=0.1,
                                                                  monotonic_ns=lambda: clock[0])
        launch = ActStackLaunch(ros2_executable=Path('/usr/bin/true'), session_id=spec['simulation_session_id'],
                                evidence_root=root / 'stack', ros_domain_id=181, environment={})
        stack = Stack(launch, ready_probe=lambda: True, stop_probe=lambda: True, graph_clear_probe=lambda: True)
        stack.owner, stack.process = native, SimpleNamespace(pid=501)
        asyncio.run(retirement.NativeShardRetirement(process_owner=read_process_owner(os.getpid()),
            launch_generation=spec['launch_generation'], evidence_root=root, stack=stack,
            goal_stop_budget_s=5, stack_stop_budget_s=15, goal_stop_probe=lambda **kwargs: observation).retire(fenced=True))


class Docker:
    """Controlled Docker daemon. `run` creates a running container; for a shard it also writes the ready files."""

    def __init__(self):
        self.calls = []
        self.containers = {}
        self.names = {}
        self.fail_kill = set()
        self.refuse_run = None
        self.specs = {}

    def __call__(self, argv):
        self.calls.append(list(argv))
        if argv[:2] == ['docker', 'run']:
            return self._run(argv)
        if argv[:2] == ['docker', 'inspect']:
            return SimpleNamespace(returncode=0, stdout=json.dumps([self.containers[argv[2]]]), stderr='')
        if argv[:2] == ['docker', 'exec']:
            return SimpleNamespace(returncode=0, stdout=json.dumps(self.report), stderr='')
        if argv[:2] == ['docker', 'kill']:
            cid = argv[4]
            if cid in self.fail_kill:
                return SimpleNamespace(returncode=1, stdout='', stderr='injected kill failure')
            if cid in self.specs and self.containers[cid]['State']['Running']:
                controlled_stop_evidence(self.specs[cid], CONTAINER_NAMESPACE)    # the shard retires itself, then exits
            self.containers[cid]['State'].update(Running=False, Pid=0, Status='exited')
            return SimpleNamespace(returncode=0, stdout=cid + '\n', stderr='')
        pytest.fail(f'unexpected Docker command {argv}')

    def _run(self, argv):
        name = argv[argv.index('--name') + 1]
        shard = 'campaign_shard' in argv
        if self.refuse_run is not None and self.refuse_run(argv):
            return SimpleNamespace(returncode=1, stdout='', stderr='injected launch failure')
        cid = hashlib.sha256(name.encode()).hexdigest()
        digest = self.shard_digest if shard else self.teacher_digest
        self.containers[cid] = dict(Id=cid, Image=digest, Name='/' + name,
            State=dict(StartedAt='2026-10-12T01:02:03.123Z', Running=True, Restarting=False,
                       Pid=500 + len(self.containers), Status='running', ExitCode=0))
        self.names[name] = cid
        if shard:
            self.specs[cid] = json.loads(Path(argv[argv.index('--spec') + 1]).read_bytes())
            self._ready_files(self.specs[cid])
        return SimpleNamespace(returncode=0, stdout=cid + '\n', stderr='')

    @staticmethod
    def _ready_files(spec):
        """What a started shard leaves for its owner: the child-ready binding and the runtime/stack readiness files."""
        root = Path(spec['owned_root'])
        process = asdict(read_process_owner(os.getpid()))
        (root / 'control' / 'child-ready.json').write_bytes(canonical_json(dict(schema_version=1,
            kind='container_child_ready', generation=spec['launch_generation'], process_owner=process,
            pid_namespace_inode=CONTAINER_NAMESPACE, service_epoch=spec['service_epoch'], runtime_id=spec['runtime_id'],
            campaign_id=spec['campaign_id'], worker_id=spec['worker_id'],
            execution_generation=spec['execution_generation'], normal_socket='/act/control/normal.sock',
            safety_socket='/act/control/safety.sock')))
        stack = root / 'stack-readiness.json'
        stack.write_bytes(b'{"stack":"controlled"}\n')
        (root / 'runtime-ready.json').write_bytes(canonical_json(dict(schema_version=2, kind='ACT_SHARD_RUNTIME_READY',
            generation=spec['launch_generation'], process_owner=process,
            readiness_sha256=hashlib.sha256(stack.read_bytes()).hexdigest())))

    def runs(self, shard):
        return [call for call in self.calls if call[:2] == ['docker', 'run'] and ('campaign_shard' in call) == shard]

    def kills(self):
        return [call for call in self.calls if call[:2] == ['docker', 'kill']]


class ScriptedContainer:
    """Controlled instance behind the control socket: the four operations, with a real `task-result.json` per task."""

    def __init__(self, shard, log, polls_to_finish):
        self.shard, self.log, self.polls_to_finish = shard, log, polls_to_finish
        self.instance_id = shard.launch.launch_id
        self.tasks = {}

    async def call_task(self, packet):
        operation, payload = packet.operation, packet.payload
        self.log.append((self.instance_id, operation, payload.get('task_id')))
        if operation == 'assign_task':
            task = TaskSpec.model_validate(payload)
            document = json.loads(Path(task.inputs_ref.path).read_bytes())
            self.tasks[task.task_id] = dict(polls=0, document=document)
            self.log.append((self.instance_id, 'task_document', document))
            return TaskStatus(task_id=task.task_id, state='ACCEPTED').model_dump()
        if operation == 'get_status':
            task_id = payload['task_id']
            if task_id is None:
                return InstanceStatus(instance_id=self.instance_id, state='READY').model_dump()
            entry = self.tasks[task_id]
            entry['polls'] += 1
            if entry['polls'] < self.polls_to_finish:
                return InstanceStatus(instance_id=self.instance_id, state='BUSY',
                    task=TaskStatus(task_id=task_id, state='RUNNING')).model_dump()
            output = self.shard.root / 'output'
            if not (output / 'tasks' / task_id / 'task-result.json').exists():
                reserve_task_output(output, task_id)
                write_task_result(output, task_id, dict(teacher_task_result='PASS'))
            return InstanceStatus(instance_id=self.instance_id, state='READY',
                task=TaskStatus(task_id=task_id, state='SUCCEEDED')).model_dump()
        return InstanceStatus(instance_id=self.instance_id, state='TERMINATED').model_dump()


class World:
    pass


def make_world(tmp_path, shared, monkeypatch, *, plane, polls_to_finish=1, qualified=False):
    """A synthetic campaign for `plane` in ('W1', 'W8', 'FORMAL', 'SPOT'); returns everything the CLI is given and the doubles.

    `qualified` (FORMAL only) replaces the synthetic report file by a real report of a qualification run built under the same
    registered evidence root, with this world's controlled identity and this world's formal scene list as the gate's."""
    import ament_index_python.packages as packages
    from so101_demo.act import execution_snapshot

    world = World()
    root = tmp_path.resolve()
    world.root, world.plane, world.spot_check = root, plane, plane == 'SPOT'
    original = packages.get_package_share_directory
    monkeypatch.setattr(packages, 'get_package_share_directory',
                        lambda name: str(PACKAGE_ROOT) if name == 'so101_demo_py' else original(name))
    snapshot = execution_snapshot.freeze_execution_snapshot
    monkeypatch.setattr(execution_snapshot, 'freeze_execution_snapshot', lambda _root, output: snapshot(REPOSITORY, output))
    evidence = root / 'evidence'
    evidence.mkdir()
    inputs = root / 'inputs'
    inputs.mkdir()
    world.evidence, world.inputs = evidence, inputs
    world.source = write_json(inputs / 'source.json', dict(artifact='source'))
    world.runtime = inputs / 'runtime.yaml'
    world.runtime.write_bytes(shared.runtime_bytes)
    world.collection = inputs / 'collection.yaml'
    world.collection.write_bytes(shared.collection_bytes)
    weights = inputs / 'teacher.pt'
    weights.write_bytes(b'teacher-weights')
    service = dict(image=dict(shared.teacher_image), model=dict(model_id=_load_runtime_config(world.runtime).yolo_model_id,
        weights=ref(weights), classes={'0': 'plastic_cup'}, score_threshold=.25), instances=3, torch_threads=1,
        torch_interop_threads=1, max_inflight_requests=8, max_frame_bytes=2**20, max_image_height=480,
        max_image_width=640, queue_timeout_s=.75, inference_timeout_s=1.25)
    world.service = service
    identity = dict(source_sha256=sha(world.source), runtime_config_sha256=sha(world.runtime),
        collection_config_sha256=sha(world.collection), contact_policy_fingerprint=shared.fingerprint, gpu_uuid=GPU,
        image_source_install=dict(inference=shared.teacher_image, shard=shared.shard_image))
    qualification_contract = None
    if plane == 'W1':
        world.scenes = write_json(inputs / 'functional-scenes.json', dict(scenarios=scene_rows('functional', 8, 100)))
        world.manifest = write_json(inputs / 'functional-run.json', dict(schema_version=1,
            kind='ACT_COLLECTION_FUNCTIONAL_RUN', run_id='functional-run', worker_count=1,
            controlled_identity=identity, scene_manifest=ref(world.scenes)))
        world.worker_count, world.qualification, world.scene_ids = 1, True, [row['scene_id'] for row in scene_rows('functional', 8, 100)]
    elif plane == 'W8':
        world.scenes = write_json(inputs / 'qualification-scenes.json', dict(scenarios=scene_rows('load', 40, 200)))
        functional = write_json(inputs / 'functional-scenes.json', dict(scenarios=scene_rows('functional', 8, 100)))
        formal = write_json(inputs / 'formal-scenes.json', dict(scenarios=scene_rows('formal', 3, 300)))
        # TEST-ONLY synthetic rule files: the pass counts are not approved values (collection_quality_rules.py)
        rules = write_synthetic_rules(inputs)
        world.manifest = write_json(inputs / 'gate.json', dict(schema_version=1, kind='ACT_PARALLEL_COLLECTION_GATE',
            qualification_run_id='run-one', worker_count=8, scene_manifest=ref(world.scenes),
            functional_manifest=ref(functional), formal_split_manifest=ref(formal), controlled_identity=identity,
            quality_rules=rules))
        qualification_contract = ref(world.manifest)
        world.worker_count, world.qualification, world.scene_ids = 8, True, [row['scene_id'] for row in scene_rows('load', 40, 200)]
    elif plane == 'SPOT':
        world.scenes = write_json(inputs / 'spot-scenes.json', dict(scenarios=scene_rows('spot', 1, 400)))
        world.manifest = write_json(inputs / 'spot-run.json', dict(schema_version=1, kind='ACT_COLLECTION_SPOT_CHECK_RUN',
            run_id='spot-run', worker_count=1, controlled_identity=identity, scene_manifest=ref(world.scenes),
            collection_mode='preselected_target_diagnostic', spot_check='nominal'))
        world.worker_count, world.qualification, world.scene_ids = 1, True, ['spot-00']
    else:
        world.scenes = world.manifest = write_json(inputs / 'formal-scenes.json', dict(scenarios=scene_rows('formal', 3, 300)))
        world.worker_count, world.qualification, world.scene_ids = 8, False, [row['scene_id'] for row in scene_rows('formal', 3, 300)]
    world.report = write_json(inputs / 'qualification-report.json', dict(status='SYNTHETIC_NOT_A_QUALIFICATION'))
    if qualified:
        assert plane == 'FORMAL'
        install_controlled_world(monkeypatch)
        (root / 'qualification').mkdir()
        qualification = build_world(root / 'qualification', evidence_root=evidence, images=(shared.teacher_image, shared.shard_image),
            source_bytes=world.source.read_bytes(), runtime_bytes=shared.runtime_bytes, collection_bytes=shared.collection_bytes,
            fingerprint=shared.fingerprint, formal_scenes=world.scenes)
        world.report = build_collection_qualification_report(qualification.run, contract=qualification.contract_path)
        world.qualification_world = qualification
    world.campaign = dict(schema_version=1, kind='ACT_CONTAINER_CAMPAIGN', evidence_root=str(evidence),
        controlled_runtime=ref(world.runtime), head_service=service, teacher_service=service,
        shard_image=dict(shared.shard_image), gpu_uuid=GPU, qualification_contract=qualification_contract,
        **(dict(max_concurrent_recordings=4, min_assignment_gap_s=.05) if plane in ('W8', 'FORMAL') else {}))
    world.campaign_path = write_json(inputs / 'campaign.json', world.campaign)
    world.docker = Docker()
    world.docker.report, world.docker.teacher_digest, world.docker.shard_digest = (
        shared.report, shared.teacher_image['digest'], shared.shard_image['digest'])
    world.log = []
    world.controls = {}

    def control_factory(shard):
        container = world.controls.setdefault(shard.launch.launch_id, ScriptedContainer(shard, world.log, polls_to_finish))
        real_client = shard.control_client

        def client():
            real_client()    # the real readiness checks run; only the socket transport is replaced
            return container
        shard.control_client = client
        return ContainerTaskControl(owner=shard)

    def service_query(client, kind, request_id, timeout_s):
        settings = world.service
        if kind == 'service_health':
            return dict(schema_version=1, kind=kind, request_id=request_id, service_generation=client.generation,
                        available=True, reason='')
        return dict(schema_version=1, kind='service_ready', request_id=request_id, service_generation=client.generation,
            image_digest=shared.teacher_image['digest'], package_source_sha256=shared.teacher_image['package_source_sha256'],
            model_id=settings['model']['model_id'], weights_sha256=settings['model']['weights']['sha256'],
            service_config_sha256=hashlib.sha256(canonical_json(settings)).hexdigest(), gpu_uuid=GPU,
            configured_instances=3, loaded_instances=3, ready=True)

    world.environment = {'SO101_UNIFIED_EVIDENCE_ROOT': str(evidence), 'SO101_ACT_GPU_SELECTOR': 'INDEX:0',
                         'SO101_ACT_RESOURCE_BINDING_ID': 'binding-1'}
    world.edges = CollectionEdges(environment=world.environment, act_inventory=lambda: (GPU,),
        act_host_id=lambda: 'ai-station-test', calibration_identity_probe=lambda: ('a' * 40, 'b' * 64),
        docker_runner=world.docker, service_query=service_query, namespace_reader=lambda pid: CONTAINER_NAMESPACE,
        control_factory=control_factory)
    world.shared = shared
    return world


def argv_for(world, **overrides):
    values = {'campaign-id': 'campaign-one', 'run-id': 'run-one', 'worker-count': str(world.worker_count),
              'manifest': str(world.manifest), 'source': str(world.source), 'collection-config': str(world.collection),
              'runtime-config': str(world.runtime), 'campaign-config': str(world.campaign_path),
              'input-candidates': str(world.shared.candidates),
              'teacher-endpoint': str(policies()['teacher_endpoint']),
              'teacher-execution-policy': str(policies()['teacher_execution_policy']),
              'episode-recorder-policy': str(policies()['episode_recorder_policy']),
              'runtime-policy': str(policies()['runtime_policy'])}
    if not world.qualification:
        values['qualification-report'] = str(world.report)
    values.update({name.replace('_', '-'): value for name, value in overrides.items()})
    argv = []
    for name, value in values.items():
        if value is not None:
            argv += ['--' + name, value]
    if world.spot_check:
        return argv + ['--spot-check']
    return argv + (['--qualification'] if world.qualification else [])


class Spies:
    """Wrappers that record and delegate; none of them replaces an admission, owner or verifier decision."""

    def __init__(self, monkeypatch):
        from so101_teleop.unified.admission import UnifiedWorkloadService

        self.services, self.owners, self.finishes = [], [], []
        real_compose = cli.compose_services

        def compose(*args, **kwargs):
            services = real_compose(*args, **kwargs)
            self.services.append(services)
            return services
        monkeypatch.setattr(cli, 'compose_services', compose)
        real_owner = composition.ContainerCampaignOwner
        spies = self

        class RecordingOwner(real_owner):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                spies.owners.append(self)
        monkeypatch.setattr(composition, 'ContainerCampaignOwner', RecordingOwner)
        real_finish = UnifiedWorkloadService.finish

        def finish(service, context, *, cleanup_confirmed):
            self.finishes.append((context, cleanup_confirmed))
            return real_finish(service, context, cleanup_confirmed=cleanup_confirmed)
        monkeypatch.setattr(UnifiedWorkloadService, 'finish', finish)

    @property
    def workload(self):
        return self.services[-1].act_workload

    def lease(self):
        return self.workload.arbiter.store._query_one('SELECT * FROM gpu_workload_leases')

    def active_slots(self):
        return self.workload.slot_registry.slots()


def controlled_verifier(monkeypatch):
    """The wave readback is controlled: the scripted container commits no episode for the real verifier to find."""
    seen = []

    def verify_wave(self, plan, outcome, shards):
        seen.append(dict(qualification=self.qualification, case_inputs=self.case_inputs, plan=plan, outcome=outcome))
        rows = [dict(row, proof=dict(task_id=row['task_id'], worker_id=row['worker_id'], location=row['location'],
                                     **{name: 'controlled' for name in result_verifier._TASK_DATA[:-3]},
                                     export_eligible=False, result_sha256='0' * 64, task_result_sha256='0' * 64),
                     registration='controlled', owner_root='controlled', scope_path='controlled', inputs_manifest='controlled')
                for row in outcome['case_results']]
        return dict(wave_index=plan['wave_index'], scene_count=len(plan['scene_ids']),
                    coordinator_root=outcome['coordinator_root'], case_results=rows)
    monkeypatch.setattr(result_verifier.ContainerWaveResultVerifier, 'verify_wave', verify_wave)
    return seen


def run(world, capsys, **overrides):
    capsys.readouterr()
    code = main(argv_for(world, **overrides), edges=world.edges)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---- the real chain, W1 -----------------------------------------------------------------------------------------------


def test_real_cli_builds_four_operation_owner(tmp_path, shared, monkeypatch, capsys):
    """W1 (qualification plane): admission through finish. Real/controlled boundaries are in the module docstring."""
    world = make_world(tmp_path, shared, monkeypatch, plane='W1', polls_to_finish=2)
    spies = Spies(monkeypatch)
    verified = controlled_verifier(monkeypatch)
    code, out, err = run(world, capsys)
    assert code == 0, err
    summary = json.loads(out.strip().splitlines()[-1])
    assert summary['plane'] == 'qualification' and summary['scene_count'] == 8 and summary['waves'] == 1
    run_root = world.evidence / 'run-one'
    (owner,) = spies.owners
    # the owner is the real one, built from Teacher only, with the derived timeouts and the frozen disk floor
    runtime = _load_runtime_config(PACKAGE_ROOT / 'config/mujoco/parallel_batch_act_offline.yaml')
    assert owner.services.roles == ('teacher',) and owner.services.head_descriptor is None
    assert owner.services.startup_timeout_s == runtime.initializing_hard_timeout_s == 180.
    assert owner.services.receive_budget_s == world.service['queue_timeout_s'] + world.service['inference_timeout_s'] == 2.
    assert owner.services.stop_timeout_s == runtime.worker_recovery_timeout_s == 120.
    assert owner.approved_disk_floor_bytes == DISK_FLOOR and owner.qualification is True
    binding = json.loads((run_root / 'inputs/frozen/inputs-manifest.json').read_bytes())['scene_manifest']
    frozen_scenes = run_root / 'inputs/frozen/scene_manifest/scenes.json'
    assert binding['sha256'] == sha(frozen_scenes) == sha(world.scenes)
    assert owner.coordinator.scene_manifest == ref(frozen_scenes)
    assert owner.coordinator.max_recording_shards is None   # one shard: the campaign config states no cap
    assert owner.coordinator.max_tasks_in_flight is None and owner.coordinator.min_assignment_gap_s is None
    assert sorted(owner.coordinator.case_inputs) == sorted(world.scene_ids)
    # Teacher service started once; one shard; both stopped through the original owners
    assert len(world.docker.runs(shard=False)) == 1 and len(world.docker.runs(shard=True)) == 1
    assert len(world.docker.kills()) == 2
    # four operations reached the instance; one task per scene was assigned and collected from its own result file
    operations = [entry[1] for entry in world.log if entry[1] != 'task_document']
    assert operations.count('assign_task') == 8 and operations.count('terminate') == 1 and operations.count('get_status') >= 16
    documents = [entry[2] for entry in world.log if entry[1] == 'task_document']
    assert sorted(document['scene_id'] for document in documents) == sorted(world.scene_ids)
    for document in documents:
        assert document['scene_manifest'] == ref(frozen_scenes)
        assert document['inputs_manifest'] == ref(run_root / 'inputs/frozen/inputs-manifest.json')
        assert document['scope'] == ref(run_root / 'inputs/scopes' / (document['scene_id'] + '.json'))
        assert set(document['teacher']) and 'head' not in document
        task_id = document['task_id']
        assert (run_root / 'wave-0/w00/g1/output/tasks' / task_id / 'task-result.json').is_file()
        assert (run_root / 'host/wave-0/task-journal' / task_id / 'collected.json').is_file()
    # the verifier is the real class built with the qualification flag and the same per-scene inputs (its readback is controlled)
    assert len(verified) == 1 and verified[0]['qualification'] is True and verified[0]['case_inputs'] == owner.coordinator.case_inputs
    cleanup = json.loads((run_root / 'host/campaign-cleanup.json').read_bytes())
    assert cleanup['terminated'] is True
    # finish ran once, after the original-owner proof, and released the lease and the slot
    assert len(spies.finishes) == 1 and spies.finishes[0][1] is True
    assert spies.lease() is None and spies.active_slots() == ()
    assert len(spies.workload.slot_registry.slots(active=False)) == 1
    assert (run_root / 'host/teacher-ready.json').is_file() and (run_root / 'collection-index.json').is_file()


def test_real_wave_verifier_refuses_unregistered_scripted_results_and_run_still_settles(tmp_path, shared, monkeypatch, capsys):
    """The real verifier is reached and refuses results with no committed episode behind them; cleanup is still confirmed."""
    world = make_world(tmp_path, shared, monkeypatch, plane='W1')
    spies = Spies(monkeypatch)
    code, out, err = run(world, capsys)
    assert code == 1 and 'CONTAINER_WAVE_COMMIT_READBACK_INVALID' in err
    assert not (world.evidence / 'run-one/collection-index.json').exists()
    assert len(spies.finishes) == 1 and spies.lease() is None and spies.active_slots() == ()


# ---- refusals before any spawn ----------------------------------------------------------------------------------------


def corrupt(path):
    path.write_text('not json')
    return str(path)


BAD_INPUTS = [
    ('worker_count_not_allowed', 'W1', lambda w: dict(worker_count='4'), 'COLLECTION_WORKER_COUNT_INVALID', False),
    ('contract_worker_count_differs', 'W1', lambda w: dict(worker_count='2'), 'COLLECTION_RUN_CONTRACT_MISMATCH', False),
    ('formal_needs_eight', 'FORMAL', lambda w: dict(worker_count='2'), 'COLLECTION_WORKER_COUNT_INVALID', False),
    ('missing_manifest', 'W1', lambda w: dict(manifest=str(w.inputs / 'absent.json')), 'FIXED_COLLECTION_INPUT_UNREADABLE', False),
    ('manifest_not_a_contract', 'W1', lambda w: dict(manifest=corrupt(w.inputs / 'garbage.json')), 'COLLECTION_MANIFEST_INVALID', False),
    ('campaign_id', 'W1', lambda w: dict(campaign_id='../escape'), 'COLLECTION_CAMPAIGN_ID_INVALID', False),
    ('run_id', 'W1', lambda w: dict(run_id='a/b'), 'CAMPAIGN_RUN_ID_INVALID', False),
    ('run_exists', 'W1', lambda w: (w.evidence / 'run-one').mkdir() or {}, 'CAMPAIGN_RUN_EXISTS', True),
    ('runtime_config_not_campaigns', 'W1', lambda w: dict(runtime_config=str(w.source)), 'CAMPAIGN_CONFIG_BINDING_MISMATCH', True),
    ('unfreezable_candidates', 'W1', lambda w: dict(input_candidates=corrupt(w.inputs / 'candidates.json')), 'CASE_INPUTS_FREEZE_REFUSED', True),
    ('unreadable_policy', 'W1', lambda w: dict(teacher_endpoint=str(w.inputs / 'absent.yaml')), 'FIXED_COLLECTION_INPUT_UNREADABLE', False),
    ('formal_without_report', 'FORMAL', lambda w: dict(qualification_report=None), 'EIGHT_WORKER_QUALIFICATION_REQUIRED', False),
    ('formal_report_absent', 'FORMAL', lambda w: dict(qualification_report=str(w.inputs / 'absent-report.json')),
     'FIXED_COLLECTION_INPUT_UNREADABLE', False),
    ('formal_report_is_a_directory', 'FORMAL', lambda w: dict(qualification_report=str(w.inputs)),
     'FIXED_COLLECTION_INPUT_UNREADABLE', False),
    ('gate_names_another_run_id', 'W8', lambda w: dict(run_id='another-run'), 'QUALIFICATION_RUN_ID_MISMATCH', False),
    ('qualification_with_report', 'W1', lambda w: dict(qualification_report=str(w.report)), 'COLLECTION_RUN_CONTRACT_MISMATCH', False),
]


@pytest.mark.parametrize('name,plane,change,code_expected,run_root_exists', BAD_INPUTS, ids=[item[0] for item in BAD_INPUTS])
def test_bad_input_refused_before_any_spawn(tmp_path, shared, monkeypatch, capsys, name, plane, change, code_expected,
                                            run_root_exists):
    """Qualification (W1) or formal plane; every refusal precedes admission, any Docker call and any lease or slot."""
    world = make_world(tmp_path, shared, monkeypatch, plane=plane)
    spies = Spies(monkeypatch)
    code, out, err = run(world, capsys, **change(world))
    assert code == 2 and code_expected in err
    assert world.docker.calls == [] and out == ''
    assert spies.finishes == [] and spies.owners == []
    if spies.services:
        assert spies.lease() is None and spies.active_slots() == ()
        assert spies.workload.arbiter.store.execution_generation(Domain.VALIDATION) == 0
    else:    # refused before the services were even composed: the unified store was never opened
        assert not (world.evidence / 'unified').exists()
    run_root = world.evidence / 'run-one'
    assert not (run_root / 'host/launches.sqlite3').exists()
    assert run_root.exists() is run_root_exists


def test_formal_plane_refuses_a_report_that_is_not_a_run_report_at_admission(tmp_path, shared, monkeypatch, capsys):
    """FORMAL plane: a file that is no run's qualification report is refused by the real verifier and nothing starts."""
    world = make_world(tmp_path, shared, monkeypatch, plane='FORMAL')
    spies = Spies(monkeypatch)
    code, out, err = run(world, capsys)
    assert code == 1 and 'EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID' in err
    assert world.docker.calls == [] and spies.owners == [] and spies.finishes == []
    assert spies.lease() is None and spies.active_slots() == ()


def test_formal_plane_runs_over_a_real_exact_eight_qualification(tmp_path, shared, monkeypatch, capsys):
    """FORMAL plane through `main()`: admission verifies a report built by the real builder, then the formal campaign runs and settles."""
    world = make_world(tmp_path, shared, monkeypatch, plane='FORMAL', qualified=True)
    spies = Spies(monkeypatch)
    controlled_verifier(monkeypatch)
    assert world.report.is_relative_to(world.qualification_world.run) and world.report.parent.parent.name == 'run-1'
    code, out, err = run(world, capsys)
    assert code == 0, err
    summary = json.loads(out.strip().splitlines()[-1])
    assert summary['plane'] == 'formal' and summary['scene_count'] == 3
    (owner,) = spies.owners
    assert owner.qualification is False
    assert len(world.docker.runs(shard=False)) == 1 and len(world.docker.runs(shard=True)) >= 1
    assert len(spies.finishes) == 1 and spies.finishes[0][1] is True
    assert spies.lease() is None and spies.active_slots() == ()
    admitted = spies.finishes[0][0]
    assert admitted.workload_kind == 'act_collection_start' and admitted.worker_count == 8


def test_formal_plane_refuses_a_scene_list_that_is_not_the_gates(tmp_path, shared, monkeypatch, capsys):
    """The real report is valid, but the formal list given to the CLI is not the gate's: refused at admission, nothing starts."""
    world = make_world(tmp_path, shared, monkeypatch, plane='FORMAL', qualified=True)
    spies = Spies(monkeypatch)
    other = write_json(world.inputs / 'other-formal-scenes.json', dict(scenarios=scene_rows('elsewhere', 3, 400)))
    code, out, err = run(world, capsys, manifest=str(other))
    assert code == 1 and 'EIGHT_WORKER_QUALIFICATION_MISMATCH' in err
    assert world.docker.calls == [] and spies.owners == [] and spies.finishes == []
    assert spies.lease() is None and spies.active_slots() == ()


# ---- settlement -------------------------------------------------------------------------------------------------------


def test_owner_build_failure_after_admission_still_settles(tmp_path, shared, monkeypatch, capsys):
    """Admitted, then the owner cannot be built. The registry already exists (it is created first), nothing was launched, and
    the CLI asks `finish` to settle. CURRENT FINDING: `finish` refuses with ACT_CONTAINER_CLEANUP_NOT_CONFIRMED because
    `ContainerLaunchRegistry.all_terminated` is False for a registry with no launches, so the lease and the slot stay held;
    the CLI exits non-zero naming that code. Admission is not changed by this stage."""
    world = make_world(tmp_path, shared, monkeypatch, plane='W1')
    spies = Spies(monkeypatch)

    def refuse(**kwargs):
        raise ValueError('INJECTED_COORDINATOR_FAILURE')
    monkeypatch.setattr(composition, 'ConcurrentCollectionCoordinator', refuse)
    code, out, err = run(world, capsys)
    assert code == 1 and 'INJECTED_COORDINATOR_FAILURE' in err
    assert world.docker.calls == [] and spies.owners == []
    registry_path = world.evidence / 'run-one/host/launches.sqlite3'
    registry = ContainerLaunchRegistry(registry_path, create=False)
    try:
        assert registry.records() == ()
    finally:
        registry.close()
    assert len(spies.finishes) == 1 and spies.finishes[0][1] is True
    assert 'ACT_CONTAINER_CLEANUP_NOT_CONFIRMED' in err
    assert spies.lease() is not None and len(spies.active_slots()) == 1


def test_unconfirmed_cleanup_never_calls_finish(tmp_path, shared, monkeypatch, capsys):
    """The run completes but the Teacher container cannot be signalled: cleanup is unconfirmed, so finish is never called."""
    world = make_world(tmp_path, shared, monkeypatch, plane='W1')
    spies = Spies(monkeypatch)
    controlled_verifier(monkeypatch)
    world.docker.fail_kill.add(hashlib.sha256(b'so101-run-one-teacher-g1').hexdigest())
    code, out, err = run(world, capsys)
    assert code == 1 and 'CAMPAIGN_CLEANUP_UNCONFIRMED' in err
    cleanup = json.loads((world.evidence / 'run-one/host/campaign-cleanup.json').read_bytes())
    assert cleanup['terminated'] is False and cleanup['services']['terminated'] is False
    assert spies.finishes == []
    assert spies.lease() is not None and len(spies.active_slots()) == 1
    assert (world.evidence / 'run-one/collection-index.json').is_file()


def test_two_waves_start_teacher_once(tmp_path, shared, monkeypatch, capsys):
    """W8 gate contract on the qualification plane: 40 scenes in two waves of 20, eight shards each, one Teacher."""
    world = make_world(tmp_path, shared, monkeypatch, plane='W8')
    spies = Spies(monkeypatch)
    verified = controlled_verifier(monkeypatch)
    code, out, err = run(world, capsys)
    assert code == 0, err
    run_root = world.evidence / 'run-one'
    assert len(world.docker.runs(shard=False)) == 1 and len(world.docker.runs(shard=True)) == 16
    assert len(world.docker.kills()) == 17
    index = json.loads((run_root / 'campaign-index.json').read_bytes())
    assert [len(wave['scene_ids']) for wave in index['waves']] == [20, 20]
    assert [item['plan']['wave_index'] for item in verified] == [0, 1]
    assert all(item['qualification'] is True and item['plan']['assignment'] is not None for item in verified)
    shards = [entry for entry in world.log if entry[1] == 'assign_task']
    assert len(shards) == 40 and sorted({entry[0] for entry in shards}) == sorted(
        f'wave-{wave}-w{worker:02d}-g{wave + 1}' for wave in (0, 1) for worker in range(8))
    (owner,) = spies.owners
    assert owner.coordinator.scene_manifest == ref(run_root / 'inputs/frozen/scene_manifest/scenes.json')
    assert owner.coordinator.max_recording_shards == 4   # the hashed campaign config's cap reaches the wave coordinator
    assert owner.coordinator.max_tasks_in_flight is None and owner.coordinator.min_assignment_gap_s == .05   # a short gap: this plane runs on the real clock
    assert spies.lease() is None and spies.active_slots() == () and len(spies.finishes) == 1


def test_a_campaign_completed_with_task_faults_settles_and_exits_non_zero_with_a_distinct_reason(tmp_path, shared, monkeypatch, capsys):
    world = make_world(tmp_path, shared, monkeypatch, plane='W1')
    spies = Spies(monkeypatch)
    controlled_verifier(monkeypatch)
    faults = [dict(scene_id='scene-01', reason='CONTAINER_TASK_FAILED: boom')]
    real_run = composition.ContainerCampaignOwner.run

    async def finished(self, manifest):
        return dict(await real_run(self, manifest), task_faults=faults)   # a real run, as if one scene had faulted
    monkeypatch.setattr(composition.ContainerCampaignOwner, 'run', finished)
    code, out, err = run(world, capsys)
    assert code == 1 and 'CAMPAIGN_COMPLETED_WITH_FAULTS' in err and 'CAMPAIGN_RUN_FAILED' not in err
    assert json.loads(out)['task_faults'] == faults
    assert len(spies.finishes) == 1 and spies.finishes[0][1] is True, 'the run still settled: a fault is not a cleanup failure'


@pytest.mark.parametrize('retry_status,expected_rc', [('COMPLETE', 0), ('ABORTED', 1)])
def test_retry_summary_reports_recovery_and_aborted_infrastructure_is_nonzero(tmp_path, shared, monkeypatch, capsys,
                                                                           retry_status, expected_rc):
    world = make_world(tmp_path, shared, monkeypatch, plane='W1')
    Spies(monkeypatch)
    controlled_verifier(monkeypatch)
    real_run = composition.ContainerCampaignOwner.run

    async def finished(self, manifest):
        return dict(await real_run(self, manifest), retry=dict(rounds_run=1, recovered=2, status=retry_status,
                                                               reason='RETRY_INFRA' if retry_status == 'ABORTED' else None))

    monkeypatch.setattr(composition.ContainerCampaignOwner, 'run', finished)
    code, out, err = run(world, capsys)
    assert code == expected_rc
    assert json.loads(out)['retry_rounds'] == 1 and json.loads(out)['recovered'] == 2
    if retry_status == 'ABORTED':
        assert 'CAMPAIGN_RETRY_ABORTED' in err


def test_disk_floor_comes_from_frozen_inputs(tmp_path, shared, monkeypatch, capsys):
    """The owner's disk floor is the frozen runtime policy's, whatever that is; the command line has no such option."""
    world = make_world(tmp_path, shared, monkeypatch, plane='W1')
    spies = Spies(monkeypatch)
    policy = tmp_path / 'runtime-policy.yaml'
    text = policies()['runtime_policy'].read_text()
    assert str(DISK_FLOOR) in text
    policy.write_text(text.replace(str(DISK_FLOOR), str(DISK_FLOOR + 1048576)))

    async def stop_early(self, manifest):
        raise RuntimeError('STOP_EARLY_FOR_TEST')
    monkeypatch.setattr(composition.ContainerCampaignOwner, 'run', stop_early)
    code, out, err = run(world, capsys, runtime_policy=str(policy))
    assert code == 1 and 'STOP_EARLY_FOR_TEST' in err
    (owner,) = spies.owners
    assert owner.approved_disk_floor_bytes == DISK_FLOOR + 1048576
    frozen = json.loads((world.evidence / 'run-one/inputs/frozen/inputs-manifest.json').read_bytes())
    assert frozen['runtime_policy']['hard_stops']['disk_free_min_bytes'] == DISK_FLOOR + 1048576
    for option in ('--disk-floor', '--approved-disk-floor-bytes', '--disk-free-min-bytes'):
        with pytest.raises(SystemExit):
            main(argv_for(world) + [option, '1'], edges=world.edges)


def test_cli_has_no_resume_or_factory_seams(tmp_path, shared, monkeypatch):
    assert list(inspect.signature(main).parameters) == ['argv', 'edges']
    assert not hasattr(cli, '_context_from_service') and not hasattr(cli, '_service')
    assert not hasattr(composition, 'build_fixed_collection_spec')
    options = {option for action in cli._parser()._actions for option in action.option_strings}
    assert not options & {'--resume', '--calibration', '--policy', '--activation-receipt', '--split-manifest',
                          '--root', '--qualification-contract'}
    world = make_world(tmp_path, shared, monkeypatch, plane='W1')
    for option in ('--resume', '--calibration', '--policy', '--activation-receipt', '--split-manifest'):
        with pytest.raises(SystemExit):
            main(argv_for(world) + [option, 'x'], edges=world.edges)
    for name in ('service_factory', 'context_factory'):
        with pytest.raises(TypeError):
            main(argv_for(world), edges=world.edges, **{name: lambda *args: None})
    assert world.docker.calls == []


# ---- the spot-check plane ---------------------------------------------------------------------------------------------------


def test_real_cli_runs_a_spot_check_in_the_diagnostic_mode(tmp_path, shared, monkeypatch, capsys):
    """`--spot-check`: one worker, one scene, the diagnostic frozen mode end to end. Real/controlled boundaries as in W1."""
    world = make_world(tmp_path, shared, monkeypatch, plane='SPOT', polls_to_finish=2)
    spies = Spies(monkeypatch)
    verified = controlled_verifier(monkeypatch)
    code, out, err = run(world, capsys)
    assert code == 0, err
    summary = json.loads(out.strip().splitlines()[-1])
    assert summary['plane'] == 'spot_check' and summary['scene_count'] == 1 and summary['waves'] == 1
    run_root = world.evidence / 'run-one'
    frozen = json.loads((run_root / 'inputs/frozen/inputs-manifest.json').read_bytes())
    assert frozen['mode'] == 'preselected_target_diagnostic' and frozen['scene_manifest']['scene_count'] == 1
    scope = json.loads((run_root / 'inputs/scopes/spot-00.json').read_bytes())
    assert scope['mode'] == 'preselected_target_diagnostic' and scope['scene_id'] == 'spot-00'
    (owner,) = spies.owners
    assert owner.qualification is True and owner.coordinator.collection_mode == 'preselected_target_diagnostic'
    assert len(verified) == 1 and verified[0]['qualification'] is True
    assert verified[0]['plan'] == dict(wave_index=0, scene_ids=['spot-00'], assignment=None, plane='spot_check')
    documents = [entry[2] for entry in world.log if entry[1] == 'task_document']
    assert [(item['scene_id'], item['collection_mode']) for item in documents] == [('spot-00', 'preselected_target_diagnostic')]
    index = json.loads((run_root / 'collection-index.json').read_bytes())
    assert index['qualification'] is True and index['committed_episodes'] == []
    assert len(world.docker.runs(shard=False)) == 1 and len(world.docker.runs(shard=True)) == 1
    assert len(spies.finishes) == 1 and spies.finishes[0][1] is True and spies.lease() is None and spies.active_slots() == ()


def test_the_other_planes_write_the_formal_collection_mode(tmp_path, shared, monkeypatch, capsys):
    world = make_world(tmp_path, shared, monkeypatch, plane='W1', polls_to_finish=2)
    spies = Spies(monkeypatch)
    controlled_verifier(monkeypatch)
    code, _out, err = run(world, capsys)
    assert code == 0, err
    assert spies.owners[0].coordinator.collection_mode == 'formal'
    assert {entry[2]['collection_mode'] for entry in world.log if entry[1] == 'task_document'} == {'formal'}
    assert json.loads((world.evidence / 'run-one/inputs/frozen/inputs-manifest.json').read_bytes())['mode'] == 'formal'


SPOT_REFUSALS = [
    ('spot_check_with_qualification', {}, lambda argv: argv + ['--qualification']),
    ('spot_check_with_two_workers', {'worker_count': '2'}, lambda argv: argv),
    ('spot_check_with_eight_workers', {'worker_count': '8'}, lambda argv: argv),
    ('spot_check_with_a_report', {'qualification_report': 'REPORT'}, lambda argv: argv),
]


@pytest.mark.parametrize('name,overrides,edit', SPOT_REFUSALS, ids=[item[0] for item in SPOT_REFUSALS])
def test_a_malformed_spot_check_invocation_is_refused_before_anything_is_written(tmp_path, shared, monkeypatch, capsys, name,
                                                                                 overrides, edit):
    world = make_world(tmp_path, shared, monkeypatch, plane='SPOT')
    overrides = {key: str(world.report) if value == 'REPORT' else value for key, value in overrides.items()}
    capsys.readouterr()
    code = main(edit(argv_for(world, **overrides)), edges=world.edges)
    assert code == 2 and 'REFUSED' in capsys.readouterr().err
    assert not (world.evidence / 'run-one').exists()


def test_the_qualification_flag_refuses_a_spot_check_contract_and_the_spot_check_flag_refuses_any_other(tmp_path, shared,
                                                                                                         monkeypatch, capsys):
    spot = make_world(tmp_path / 'spot', shared, monkeypatch, plane='SPOT') if (tmp_path / 'spot').mkdir() is None else None
    capsys.readouterr()
    argv = [item for item in argv_for(spot) if item != '--spot-check'] + ['--qualification']
    assert main(argv, edges=spot.edges) == 2
    assert 'COLLECTION_RUN_CONTRACT_MISMATCH' in capsys.readouterr().err
    functional = make_world(tmp_path / 'functional', shared, monkeypatch, plane='W1') if (tmp_path / 'functional').mkdir() is None else None
    argv = [item for item in argv_for(functional) if item != '--qualification'] + ['--spot-check']
    assert main(argv, edges=functional.edges) == 2
    assert 'COLLECTION_RUN_CONTRACT_MISMATCH' in capsys.readouterr().err
    assert not (functional.evidence / 'run-one').exists() and not (spot.evidence / 'run-one').exists()


def test_the_composition_refuses_a_spot_check_that_is_not_a_qualification_mode_single_worker_run(tmp_path, shared, monkeypatch):
    world = make_world(tmp_path, shared, monkeypatch, plane='SPOT')
    arguments = SimpleNamespace(campaign_id='campaign-one', manifest=world.manifest, source=world.source,
        runtime_config=world.runtime, collection_config=world.collection, campaign_config=world.campaign_path, root=tmp_path,
        qualification=False, spot_check=True, qualification_report=None, worker_count=1, instance_launcher='container')
    with pytest.raises(ValueError, match='COLLECTION_RUN_CONTRACT_MISMATCH'):
        composition.prepare_collection_operation(arguments, services=SimpleNamespace(act_workload=None),
                                                 contact_policy_fingerprint='a' * 64)
    arguments.qualification, arguments.worker_count = True, 2
    with pytest.raises(ValueError, match='COLLECTION_WORKER_COUNT_INVALID'):
        composition.prepare_collection_operation(arguments, services=SimpleNamespace(act_workload=None),
                                                 contact_policy_fingerprint='a' * 64)
