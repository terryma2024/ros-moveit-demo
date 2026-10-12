"""Real service owner/registry with only Docker and inference external I/O replaced."""

import asyncio
import hashlib
import importlib
import json
import time
from types import SimpleNamespace

import pytest

from so101_demo.runtime.container_campaign.paths import make_campaign_paths
from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.provenance import freeze_image, verify_image_freeze
from so101_demo.runtime.parallel_ipc.frames import canonical_json
from so101_teleop.unified.contracts import AdmittedCampaignContext


def fixture(tmp_path, *, measurement=False, fail_teacher=False, refuse_stop=False, ready_drift=False):
    mod = importlib.import_module('so101_demo.runtime.container_campaign.service_owner')
    paths = make_campaign_paths(tmp_path, 'campaign')
    source, install = tmp_path/'source', tmp_path/'install'
    source.mkdir(); install.mkdir()
    (source/'.image-git.json').write_text(json.dumps(dict(git_commit='1'*40, submodules={})))
    (install/'installed.py').write_text('installed')
    runtime = dict(interpreter='/act/venv/bin/python', dependencies={'numpy':'1.26.4'},
        module_origins={'so101_demo':'/act/install/lib/so101_demo/__init__.py'},
        package_prefixes={'so101_demo_py':'/act/install'})
    manifest = freeze_image(source_root=source, install_root=install,
                           git_commit='1'*40, submodules={}, runtime=runtime)
    report = verify_image_freeze(manifest, source_root=source, install_root=install, runtime=runtime)
    image = dict(digest='sha256:'+'b'*64, package_source_sha256=report['package_source_sha256'],
                 install_sha256=report['install_sha256'])
    controlled = tmp_path/'runtime.json'
    controlled.write_text('{}')
    sha = hashlib.sha256(controlled.read_bytes()).hexdigest()
    config = dict(schema_version=1, kind='ACT_CONTAINER_CAMPAIGN', evidence_root=str(tmp_path),
        controlled_runtime=dict(path=str(controlled), sha256=sha), gpu_uuid='GPU-28221cec-9d21-7753-fd5a-da645740df19',
        shard_image=image, qualification_contract=None)
    for role in ('head','teacher'):
        weights = tmp_path/(role+'.pt')
        weights.write_bytes(role.encode())
        config[role+'_service'] = dict(image=image, model=dict(model_id=role,
            weights=dict(path=str(weights), sha256=hashlib.sha256(weights.read_bytes()).hexdigest()),
            classes={'0':'plastic_cup'}, score_threshold=.25), instances=3, torch_threads=1,
            torch_interop_threads=1, max_inflight_requests=8, max_frame_bytes=8388608,
            max_image_height=480, max_image_width=640, queue_timeout_s=10., inference_timeout_s=20.)
    if measurement:
        config['teacher_service']['model']['weights']['path'] = str(tmp_path/'unused-teacher.pt')
    context = AdmittedCampaignContext(campaign_id='campaign', operation_id='operation',
        workload_kind='act_calibration_measurement_start' if measurement else 'act_collection_start',
        service_epoch='epoch', execution_generation=1, stable_host_id='host',
        physical_gpu_uuid=config['gpu_uuid'], worker_count=1 if measurement else 8,
        source_sha256='a'*64, manifest_sha256='a'*64, runtime_config_sha256=sha,
        collection_config_sha256='a'*64, contact_policy_fingerprint='a'*64,
        domain_session_map_sha256='a'*64, resource_binding_id='binding', evidence_root=str(paths['run']),
        admitted_at_monotonic_s=1, deadline_monotonic_s=time.monotonic()+3600)
    descriptor = paths['run']/'head-descriptor.json'
    descriptor.write_text(json.dumps(dict(backend='yolo_seg', weights_path=config['head_service']['model']['weights']['path'],
        weights_sha256=config['head_service']['model']['weights']['sha256'], model_id='head', image_size_px=640,
        requested_device='cuda', allow_cpu_fallback=False, torch_threads=1, torch_interop_threads=1,
        torch_version='2.13.0+cu130', ultralytics_version='8.4.115')))
    registry = ContainerLaunchRegistry(paths['host']/'launches.sqlite3')
    calls, containers = [], {}

    def docker(argv):
        calls.append(argv)
        if argv[:2] == ['docker','run']:
            role = argv[argv.index('--role')+1]
            if role == 'teacher' and fail_teacher:
                return SimpleNamespace(returncode=1, stdout='', stderr='injected Docker launch failure')
            cid = ('1' if role == 'head' else '2')*64
            containers[cid] = dict(Id=cid, Image=image['digest'], Name='/'+argv[argv.index('--name')+1],
                State=dict(StartedAt='2026-10-12T01:02:03.123Z', Running=True, Restarting=False,
                           Pid=500, Status='running', ExitCode=0))
            return SimpleNamespace(returncode=0, stdout=cid+'\n', stderr='')
        if argv[:2] == ['docker','inspect']:
            return SimpleNamespace(returncode=0, stdout=json.dumps([containers[argv[2]]]), stderr='')
        if argv[:2] == ['docker','exec']:
            return SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr='')
        if argv[:2] == ['docker','kill']:
            assert argv[2:4] == ['--signal','TERM']
            if not refuse_stop:
                containers[argv[4]]['State'].update(Running=False, Pid=0, Status='exited')
            return SimpleNamespace(returncode=0, stdout=argv[4]+'\n', stderr='')
        pytest.fail(f'Unexpected external Docker command {argv}')

    def query(client, kind, request_id, timeout_s):
        role = 'head' if client.socket_path.parent.name == 'head' else 'teacher'
        settings = config[role+'_service']
        if kind == 'service_health':
            return dict(schema_version=1, kind=kind, request_id=request_id,
                        service_generation=client.generation, available=True, reason='')
        return dict(schema_version=1, kind='service_ready', request_id=request_id,
            service_generation=client.generation, image_digest=image['digest'],
            package_source_sha256=image['package_source_sha256'], model_id=role,
            weights_sha256=settings['model']['weights']['sha256'],
            service_config_sha256='f'*64 if ready_drift else hashlib.sha256(canonical_json(settings)).hexdigest(),
            gpu_uuid=config['gpu_uuid'], configured_instances=3, loaded_instances=3, ready=True)
    owner = mod.ContainerServiceOwner(admitted_context=context, config=config, paths=paths,
        roles=('head',) if measurement else ('head','teacher'), registry=registry,
        head_descriptor=descriptor, head_descriptor_sha256=hashlib.sha256(descriptor.read_bytes()).hexdigest(),
        startup_timeout_s=1., receive_budget_s=.1, stop_timeout_s=.1,
        docker_runner=docker, query=query)
    return owner, registry, calls, containers


def test_services_start_once_and_survive_borrowed_clients_until_owner_closes(tmp_path):
    owner, registry, calls, containers = fixture(tmp_path)
    async def run():
        endpoints = await owner.start()
        assert set(endpoints) == {'head','teacher'}
        assert endpoints['head'].client() is not endpoints['head'].client()
        assert len([argv for argv in calls if argv[:2] == ['docker','run']]) == 2
        assert all(item['State']['Running'] for item in containers.values())
        assert await owner.check_health() is True
        with pytest.raises(ValueError, match='SERVICE_OWNER_ALREADY_STARTED'):
            await owner.start()
        first, second = await asyncio.gather(owner.close(), owner.close())
        assert first == second and first['terminated'] is True
        assert len([argv for argv in calls if argv[:2] == ['docker','kill']]) == 2
        assert registry.all_terminated(owner.inspect_container)
    asyncio.run(run())
    registry.close()


def test_actual_service_exit_is_health_failure_before_any_new_dispatch(tmp_path):
    owner, registry, calls, containers = fixture(tmp_path)
    async def run():
        await owner.start()
        containers['2'*64]['State'].update(Running=False, Pid=0, Status='exited', ExitCode=1)
        with pytest.raises(ValueError, match='SERVICE_CONTAINER_NOT_RUNNING'):
            await owner.check_health()
        assert (await owner.close())['terminated'] is True
    asyncio.run(run())
    registry.close()


def test_measurement_only_launches_head_without_reading_unused_teacher_weights(tmp_path):
    owner, registry, calls, _ = fixture(tmp_path, measurement=True)
    async def run():
        assert set(await owner.start()) == {'head'}
        assert len([argv for argv in calls if argv[:2] == ['docker','run']]) == 1
        assert (await owner.close())['terminated'] is True
    asyncio.run(run())
    registry.close()


def test_partial_start_retires_known_container_and_unknown_intent_keeps_fence(tmp_path):
    owner, registry, calls, containers = fixture(tmp_path, fail_teacher=True)
    async def run():
        with pytest.raises(ValueError, match='SERVICE_OWNER_START_FAILED'):
            await owner.start()
        receipt = await owner.close()
        assert receipt['terminated'] is False
        assert not containers['1'*64]['State']['Running']
        assert not registry.all_terminated(owner.inspect_container)
    asyncio.run(run())
    registry.close()


def test_stop_timeout_never_forces_service_or_claims_exit(tmp_path):
    owner, registry, calls, containers = fixture(tmp_path, refuse_stop=True)
    async def run():
        await owner.start()
        assert (await owner.close())['terminated'] is False
        assert all(item['State']['Running'] for item in containers.values())
        assert not any('KILL' in argv or argv[:2] == ['docker','stop'] for argv in calls)
    asyncio.run(run())
    registry.close()


def test_ready_config_drift_fails_and_known_owned_launch_retires(tmp_path):
    owner, registry, calls, containers = fixture(tmp_path, ready_drift=True)
    async def run():
        with pytest.raises(ValueError, match='SERVICE_OWNER_START_FAILED'):
            await owner.start()
        assert (await owner.close())['terminated'] is True
        assert len(containers) == 1
    asyncio.run(run())
    registry.close()


def test_close_during_pending_docker_launch_waits_for_identity_and_single_cleanup(tmp_path):
    import threading
    owner, registry, calls, containers = fixture(tmp_path)
    original = owner.docker_runner
    entered, release = threading.Event(), threading.Event()
    def pending_launch(argv):
        if argv[:2] == ['docker','run']:
            entered.set()
            assert release.wait(2), 'test did not release its external Docker call'
        return original(argv)
    owner.docker_runner = pending_launch
    async def run():
        starting = asyncio.create_task(owner.start())
        while not entered.is_set():
            await asyncio.sleep(.001)
        closing = asyncio.create_task(owner.close())
        await asyncio.sleep(.01)
        assert not closing.done()
        release.set()
        with pytest.raises(ValueError, match='SERVICE_OWNER_START_FAILED'):
            await starting
        assert (await closing)['terminated'] is True
        assert len(containers) == 1
        assert len([argv for argv in calls if argv[:2] == ['docker','kill']]) == 1
    try:
        asyncio.run(run())
    finally:
        release.set()
        registry.close()
