"""SQLite collection admission/finish use slots and independent launch readback."""

from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path

import pytest

from test_act_campaign_admission import _write_policy, _start_spec, _service
from so101_demo.runtime.container_campaign.paths import make_campaign_paths
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.process_identity import ContainerOwnerKey
from so101_teleop.unified.intent_store import IntentStore
from so101_teleop.unified.worker_slots import ActWorkerSlot

GPU = 'GPU-28221cec-9d21-7753-fd5a-da645740df19'


def fixture(tmp_path):
    paths = make_campaign_paths(tmp_path, 'campaign')
    root = paths['run']
    fingerprint, proposal, activation, receipt = _write_policy(root)
    activation.write_text(json.dumps(receipt))
    base = _start_spec(root, fingerprint, proposal, activation, calibration_status='QUALIFIED')
    runtime = json.loads(Path(base.payload['runtime_config_path']).read_text())
    detector = runtime['head_search']['detector']
    image = dict(digest='sha256:'+'b'*64, package_source_sha256='c'*64, install_sha256='d'*64)
    model = dict(model_id=detector['model_id'], weights=dict(path=detector['weights_path'],
        sha256=detector['weights_sha256']), classes={'0':'plastic_cup'}, score_threshold=.25)
    service = dict(image=image, model=model, instances=1, torch_threads=detector['torch_threads'],
        torch_interop_threads=detector['torch_interop_threads'], max_inflight_requests=8,
        max_frame_bytes=8388608, max_image_height=480, max_image_width=640,
        queue_timeout_s=10., inference_timeout_s=20.)
    campaign = dict(schema_version=1, kind='ACT_CONTAINER_CAMPAIGN', evidence_root=str(tmp_path),
        controlled_runtime=dict(path=base.payload['runtime_config_path'], sha256=base.payload['runtime_config_sha256']),
        head_service=service, teacher_service=service, shard_image=image, gpu_uuid=GPU, qualification_contract=None)
    config_path = root/'campaign.json'
    config_path.write_text(json.dumps(campaign))
    slot = ActWorkerSlot(campaign_id=base.payload['campaign_id'], worker_id='w00',
        execution_generation=base.execution_generation, ros_domain_id=181, namespace='/act/campaign/w00',
        controller_name='/act/campaign/w00/arm_controller')
    payload = {name:value for name,value in base.payload.items()
               if name not in {'children','preparation_receipt_path','preparation_receipt_sha256'}}
    payload.update(worker_slots=[asdict(slot)], qualification_mode=True,
        registered_evidence_root=str(tmp_path), campaign_config_path=str(config_path),
        campaign_config_sha256=hashlib.sha256(config_path.read_bytes()).hexdigest())
    scenes_path = root/'functional-scenes.json'
    scenes_path.write_text(json.dumps({'scenarios':[{'scene_id':f'functional-{i:02d}','split':'validation'}
                                                 for i in range(8)]}))
    controlled = {name:payload[name] for name in ('source_sha256','runtime_config_sha256',
                  'collection_config_sha256','contact_policy_fingerprint')}
    controlled.update(gpu_uuid=GPU,image_source_install=dict(inference=image,shard=image))
    functional_path = root/'functional-run.json'
    functional_path.write_text(json.dumps(dict(schema_version=1,kind='ACT_COLLECTION_FUNCTIONAL_RUN',
        run_id='functional-run',worker_count=1,controlled_identity=controlled,
        scene_manifest=dict(path=str(scenes_path),sha256=hashlib.sha256(scenes_path.read_bytes()).hexdigest()))))
    payload.update(manifest_path=str(functional_path),manifest_sha256=hashlib.sha256(functional_path.read_bytes()).hexdigest())
    spec = replace(base, kind='act_collection_start', payload=payload)
    store = IntentStore.open(tmp_path/'state')
    workload = _service(store)
    workload.visible_physical_uuids = (GPU,)
    workload.root_registration = dict(path=str(tmp_path), uid=os.getuid(), gid=os.getgid())
    inspect = {}
    workload.container_inspect = lambda cid: inspect[cid]
    return paths, slot, spec, store, workload, inspect


def terminated_services(paths, inspect):
    registry = ContainerLaunchRegistry(paths['host']/'launches.sqlite3')
    for role, character in [('head','1'),('teacher','2')]:
        launch = ContainerLaunch(launch_id=role+'-g1', role=role, worker_id=None, wave_id=None,
            launch_generation=1, container_name='so101-'+role, image_digest='sha256:'+'b'*64,
            owned_root=str(paths['services'][role]))
        owner = ContainerOwnerKey(character*64,'2026-10-12T01:02:03.123Z','sha256:'+'b'*64,1)
        registry.register(launch)
        registry.bind_container(launch.launch_id,owner)
        inspect[owner.container_id] = dict(Id=owner.container_id, Image=owner.image_digest,
            State=dict(StartedAt=owner.docker_started_at, Running=False, Restarting=False,
                       Pid=0, Status='exited', ExitCode=0))
        registry.prove_terminated(launch.launch_id,inspect[owner.container_id])
    registry.close()


def test_admission_freezes_persistent_slots_and_finish_checks_actual_containers(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(spec, allow_existing=False)
        assert workload.slot_registry.slots() == (slot,)
        assert workload.child_registry.launches() == ()
        expected = hashlib.sha256(json.dumps([asdict(slot)],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        assert context.domain_session_map_sha256 == expected
        with pytest.raises(ValueError, match='ACT_CONTAINER_CLEANUP_NOT_CONFIRMED'):
            workload.finish(context,cleanup_confirmed=True)
        assert workload.slot_registry.slots() == (slot,)
        assert store._query_one('SELECT * FROM gpu_workload_leases') is not None
        terminated_services(paths,inspect)
        projection = workload.finish(context,cleanup_confirmed=True)
        assert workload.slot_registry.slots() == ()
        assert workload.slot_registry.slots(active=False) == (slot,)
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        assert workload.finish(context,cleanup_confirmed=True) == projection
    finally:
        store.close()


def test_cached_exit_does_not_release_active_container_or_logical_slots(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(spec,allow_existing=False)
        terminated_services(paths,inspect)
        inspect['1'*64]['State'].update(Running=True,Pid=123,Status='running')
        with pytest.raises(ValueError, match='ACT_CONTAINER_CLEANUP_NOT_CONFIRMED'):
            workload.finish(context,cleanup_confirmed=True)
        assert workload.slot_registry.slots() == (slot,)
        assert store._query_one('SELECT * FROM gpu_workload_leases') is not None
    finally:
        store.close()


def test_campaign_config_replaced_between_hash_and_parse_is_refused(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    original = workload._verify_artifact
    def replace_after_read(path, digest, **kwargs):
        result = original(path,digest,**kwargs)
        if path == spec.payload['campaign_config_path']:
            document = json.loads(Path(path).read_text())
            document['teacher_service']['instances'] = 2
            Path(path).write_text(json.dumps(document))
        return result
    workload._verify_artifact = replace_after_read
    try:
        with pytest.raises(ValueError, match='CAMPAIGN_CONFIG_INVALID'):
            workload.start(spec,allow_existing=False)
        assert workload.slot_registry.slots() == ()
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
    finally:
        store.close()


def test_collection_cannot_use_existing_context_admission_mode(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        with pytest.raises(ValueError, match='ACT_CONTAINER_NEW_CAMPAIGN_REQUIRED'):
            workload.start(spec)
        assert workload.slot_registry.slots() == ()
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
    finally:
        store.close()


def test_corrupt_launch_registry_keeps_resources_fenced(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(spec,allow_existing=False)
        (paths['host']/'launches.sqlite3').write_bytes(b'not a SQLite database')
        with pytest.raises(ValueError, match='ACT_CONTAINER_CLEANUP_NOT_CONFIRMED'):
            workload.finish(context,cleanup_confirmed=True)
        assert workload.slot_registry.slots() == (slot,)
        assert store._query_one('SELECT * FROM gpu_workload_leases') is not None
    finally:
        store.close()


@pytest.mark.parametrize('problem',['old_children','unknown','root','config_hash','gpu','slot_count','resume',
                                  'old_manifest','manifest_identity','manifest_workers'])
def test_closed_container_start_refuses_before_resources(tmp_path,problem):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    payload = dict(spec.payload)
    if problem == 'old_children':
        payload['children'] = payload.pop('worker_slots')
    elif problem == 'unknown': payload['allow_resume'] = True
    elif problem == 'root': payload['registered_evidence_root'] = str(paths['run'])
    elif problem == 'config_hash': payload['campaign_config_sha256'] = 'f'*64
    elif problem == 'gpu': workload.visible_physical_uuids = ('GPU-foreign',)
    elif problem == 'slot_count': payload['worker_slots'] = []
    elif problem == 'resume': spec = replace(spec,kind='act_collection_resume')
    elif problem in ('old_manifest','manifest_identity','manifest_workers'):
        path = Path(payload['manifest_path'])
        document = json.loads(path.read_text())
        if problem == 'old_manifest': document = {'kind':'SINGLE_WORKER','scenarios':[{}]*8}
        elif problem == 'manifest_identity': document['controlled_identity']['source_sha256'] = '0'*64
        else: document['worker_count'] = 2
        path.write_text(json.dumps(document))
        payload['manifest_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        with pytest.raises(ValueError):
            workload.start(replace(spec,payload=payload),allow_existing=False)
        assert workload.slot_registry.slots() == ()
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        assert store._query_one('SELECT * FROM act_campaign_contexts') is None
    finally:
        store.close()
