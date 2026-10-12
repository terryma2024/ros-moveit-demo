"""SQLite collection admission/finish use slots and independent launch readback."""

from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path

import pytest

from test_act_campaign_admission import _write_policy, _start_spec, _service
from test_act_diagnostic_episode_admission import _diagnostic_spec
from so101_demo.runtime.container_campaign.paths import make_campaign_paths
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.process_identity import ContainerOwnerKey
from so101_teleop.unified.intent_store import IntentStore
from so101_teleop.unified.worker_slots import ActWorkerSlot

GPU = 'GPU-28221cec-9d21-7753-fd5a-da645740df19'


SHARE = Path(__file__).resolve().parents[3]/'so101_demo_py'
REMOVED_KEYS = ('proposal_path', 'activation_receipt_path', 'calibration_report_path', 'calibration_report_sha256')


def fixture(tmp_path):
    """A container-collection start spec with the real parallel-runtime YAML and no calibration report or receipt.

    Controlled: the source/collection/manifest scaffolding files (synthetic bytes written by `_start_spec` into a directory
    beside the run, never into it), the contact fingerprint string (a collection start carries it; the shard verifies it per
    task) and the teacher weights file. Real: the campaign-config loader, the payload schema, admission and its SQLite store."""
    paths = make_campaign_paths(tmp_path, 'campaign')
    root = paths['run']
    scaffold = tmp_path/'scaffold'
    scaffold.mkdir()
    fingerprint, proposal, activation, receipt = _write_policy(scaffold)
    base = replace(_start_spec(scaffold, fingerprint, proposal, activation), execution_generation=1)
    runtime = scaffold/'parallel_batch_act_offline.yaml'
    runtime.write_bytes((SHARE/'config/mujoco/parallel_batch_act_offline.yaml').read_bytes())
    runtime_sha = hashlib.sha256(runtime.read_bytes()).hexdigest()
    weights = scaffold/'teacher-weights.pt'
    weights.write_bytes(b'teacher-weights')
    image = dict(digest='sha256:'+'b'*64, package_source_sha256='c'*64, install_sha256='d'*64)
    model = dict(model_id='teacher-model', weights=dict(path=str(weights),
        sha256=hashlib.sha256(weights.read_bytes()).hexdigest()), classes={'0':'plastic_cup'}, score_threshold=.25)
    service = dict(image=image, model=model, instances=1, torch_threads=4, torch_interop_threads=2,
        max_inflight_requests=8, max_frame_bytes=8388608, max_image_height=480, max_image_width=640,
        queue_timeout_s=10., inference_timeout_s=20.)
    campaign = dict(schema_version=1, kind='ACT_CONTAINER_CAMPAIGN', evidence_root=str(tmp_path),
        controlled_runtime=dict(path=str(runtime), sha256=runtime_sha),
        head_service=service, teacher_service=service, shard_image=image, gpu_uuid=GPU, qualification_contract=None)
    config_path = root/'campaign.json'
    config_path.write_text(json.dumps(campaign))
    slot = ActWorkerSlot(campaign_id=base.payload['campaign_id'], worker_id='w00',
        execution_generation=base.execution_generation, ros_domain_id=181, namespace='/act/campaign/w00',
        controller_name='/act/campaign/w00/arm_controller')
    payload = {name:value for name,value in base.payload.items()
               if name not in {'children','preparation_receipt_path','preparation_receipt_sha256', *REMOVED_KEYS}}
    payload.update(worker_slots=[asdict(slot)], qualification_mode=True, evidence_root=str(root),
        runtime_config_path=str(runtime), runtime_config_sha256=runtime_sha,
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


def assert_nothing_acquired(service, store):
    assert service.slot_registry.slots() == () and service.child_registry.launches() == ()
    assert service.arbiter.is_idle()
    assert store._query_one('SELECT * FROM gpu_workload_leases') is None
    assert store._query_one('SELECT * FROM act_campaign_contexts') is None


def test_collection_admits_without_calibration_report_or_run_root_receipt(tmp_path):
    """CP-3609: a collection start names neither a calibration report nor a contact proposal/receipt, and the run root holds none."""
    from so101_teleop.unified.admission import _COLLECTION_PAYLOAD_KEYS
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        assert not set(REMOVED_KEYS) & set(spec.payload) and set(spec.payload) == _COLLECTION_PAYLOAD_KEYS
        names = sorted(path.name for path in paths['run'].rglob('*') if path.is_file())
        assert not [name for name in names if 'calibration' in name or 'activation' in name or 'proposal' in name]
        context = workload.start(spec, allow_existing=False)
        assert context.workload_kind == 'act_collection_start' and workload.slot_registry.slots() == (slot,)
        assert context.contact_policy_fingerprint == spec.payload['contact_policy_fingerprint']
        assert store._query_one('SELECT * FROM gpu_workload_leases') is not None
    finally:
        store.close()


@pytest.mark.parametrize('key', REMOVED_KEYS)
def test_collection_payload_carrying_removed_keys_is_schema_error(tmp_path, key):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        payload = dict(spec.payload, **{key: 'x' if key.endswith('path') else 'f'*64})
        with pytest.raises(ValueError, match='CAMPAIGN_START_SCHEMA'):
            workload.start(replace(spec, payload=payload), allow_existing=False)
        assert_nothing_acquired(workload, store)
    finally:
        store.close()


def test_collection_runtime_config_may_be_parallel_runtime_yaml(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        runtime = Path(spec.payload['runtime_config_path'])
        assert runtime.suffix == '.yaml' and runtime.read_bytes() == (SHARE/'config/mujoco/parallel_batch_act_offline.yaml').read_bytes()
        with pytest.raises(ValueError):
            json.loads(runtime.read_bytes())
        assert workload.start(spec, allow_existing=False).runtime_config_sha256 == hashlib.sha256(runtime.read_bytes()).hexdigest()
    finally:
        store.close()


def test_collection_still_checks_hashes_profile_probe_and_fingerprint_shape(tmp_path):
    """What admission keeps enforcing for collection once the two rules are gone."""
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        workload.calibration_identity_probe = lambda: (_ for _ in ()).throw(OSError('installed profile missing'))
        with pytest.raises(ValueError, match='CALIBRATION_REQUIRED'):
            workload.start(spec, allow_existing=False)
        assert_nothing_acquired(workload, store)
        workload.calibration_identity_probe = lambda: ('a'*40, 'b'*64)
        for name in ('source', 'runtime_config', 'collection_config', 'manifest'):
            with pytest.raises(ValueError, match='CAMPAIGN_ARTIFACT_HASH_MISMATCH|CAMPAIGN_CONFIG_BINDING_MISMATCH'):
                workload.start(replace(spec, payload=dict(spec.payload, **{name+'_sha256': 'e'*64})), allow_existing=False)
        assert_nothing_acquired(workload, store)
    finally:
        store.close()


def test_pick_place_still_requires_calibration_and_activation(tmp_path):
    """Pinned before the collection edit: pick-place validation keeps both rules and its full schema."""
    fingerprint, proposal_path, receipt_path, receipt = _write_policy(tmp_path)
    spec = _start_spec(tmp_path, fingerprint, proposal_path, receipt_path)
    cases = (('no_receipt_file', spec, 'POLICY_NOT_ACTIVATED'),
             ('no_calibration_pair', replace(spec, payload={key: value for key, value in spec.payload.items()
                 if key not in ('calibration_report_path', 'calibration_report_sha256')}), 'CALIBRATION_REQUIRED'),
             ('no_proposal_key', replace(spec, payload={key: value for key, value in spec.payload.items()
                 if key != 'proposal_path'}), 'CAMPAIGN_START_SCHEMA'),
             ('other_fingerprint', replace(spec, payload=dict(spec.payload, contact_policy_fingerprint='0'*64)),
              'PICK_PLACE_VALIDATION_MANIFEST_BINDING_MISMATCH'))
    for name, candidate, code in cases:
        store = IntentStore.open(tmp_path/('state-'+name))
        try:
            service = _service(store)
            with pytest.raises(ValueError, match=code):
                service.start(candidate)
            assert service.child_registry.launches() == () and service.arbiter.is_idle()
            assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        finally:
            store.close()
    receipt_path.write_text(json.dumps(receipt))
    stale = tmp_path/'foreign-root'
    stale.mkdir()
    receipt_path.write_text(json.dumps(dict(receipt, evidence_root=str(stale))))
    store = IntentStore.open(tmp_path/'state-foreign')
    try:
        with pytest.raises(ValueError, match='POLICY_NOT_ACTIVATED'):
            _service(store).start(spec)
    finally:
        store.close()
    receipt_path.write_text(json.dumps(receipt))
    store = IntentStore.open(tmp_path/'state-ok')
    try:
        assert _service(store).start(spec).workload_kind == 'pick_place_validation_phase'
    finally:
        store.close()


def test_diagnostic_admission_unchanged(tmp_path):
    """Pinned before the collection edit: the diagnostic kind keeps the report, proposal and receipt rules and their keys."""
    def drop(*keys):
        return lambda payload: [payload.pop(key) for key in keys]

    cases = (('no_proposal_key', drop('proposal_path'), 'CAMPAIGN_START_SCHEMA'),
             ('no_calibration_pair', drop('calibration_report_path', 'calibration_report_sha256'), 'CALIBRATION_REQUIRED'),
             ('other_fingerprint', lambda payload: payload.update(contact_policy_fingerprint='0'*64), 'POLICY_NOT_ACTIVATED'))
    for name, mutate, code in cases:
        store = IntentStore.open(tmp_path/('state-'+name))
        try:
            service = _service(store)
            with pytest.raises(ValueError, match=code):
                service.start(_diagnostic_spec(tmp_path, tag=name, payload_mutation=mutate))
            assert service.child_registry.launches() == () and service.arbiter.is_idle()
            assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        finally:
            store.close()
    store = IntentStore.open(tmp_path/'state-ok')
    try:
        assert _service(store).start(_diagnostic_spec(tmp_path, tag='ok')).workload_kind == 'act_diagnostic_episode'
    finally:
        store.close()
