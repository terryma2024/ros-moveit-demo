"""SQLite collection admission/finish use slots and independent launch readback."""

from dataclasses import asdict, replace
import hashlib
import itertools
import json
import os
from pathlib import Path
import sys
import time

import pytest

from teleop_paths import DEMO_TEST_IMPORT_PATH

# the qualification world builder lives in the demo package's test/support, with the fixtures it imports
for _candidate in DEMO_TEST_IMPORT_PATH:
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from test_act_campaign_admission import _write_policy, _start_spec, _service
from so101_demo.runtime.container_campaign.paths import make_campaign_paths
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.process_identity import ContainerOwnerKey
from so101_teleop.unified.contracts import Domain, OperationSpec
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
        head_service=service, teacher_service=service, shard_image=image, gpu_uuid=GPU, qualification_contract=None,
        max_concurrent_recordings=4)
    config_path = root/'campaign.json'
    config_path.write_text(json.dumps(campaign))
    slot = ActWorkerSlot(campaign_id=base.payload['campaign_id'], worker_id='w00',
        execution_generation=base.execution_generation)
    payload = {name:value for name,value in base.payload.items()
               if name not in {'children','preparation_receipt_path','preparation_receipt_sha256', *REMOVED_KEYS}}
    payload.update(worker_slots=[asdict(slot)], qualification_mode=True, qualification_receipt_sha256=None, evidence_root=str(root),
        instance_launcher='container',
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


def test_the_diagnostic_episode_kind_is_no_longer_admitted(tmp_path):
    """The old native `act_diagnostic_episode run` is removed with its admission kind: the kind is unknown, nothing is acquired."""
    fingerprint, proposal_path, receipt_path, receipt = _write_policy(tmp_path)
    receipt_path.write_text(json.dumps(receipt))
    spec = replace(_start_spec(tmp_path, fingerprint, proposal_path, receipt_path), kind='act_diagnostic_episode')
    store = IntentStore.open(tmp_path/'state-removed')
    try:
        service = _service(store)
        with pytest.raises(ValueError, match='UNKNOWN_OPERATION'):
            service.start(spec)
        assert service.child_registry.launches() == () and service.arbiter.is_idle()
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
    finally:
        store.close()
    from so101_teleop.unified import admission
    assert not hasattr(admission, '_DIAGNOSTIC_PAYLOAD_KEYS') and 'act_diagnostic_episode' not in admission._ACT_START_KINDS


def test_only_the_collection_payload_carries_the_report_hash(tmp_path):
    """Pinned before the formal-collection edit: pick-place validation keeps its key set; the hash is collection-only."""
    from so101_teleop.unified import admission
    key = 'qualification_receipt_sha256'
    assert key in admission._COLLECTION_PAYLOAD_KEYS
    for name in ('_ACT_PAYLOAD_KEYS', '_PICK_PLACE_VALIDATION_PAYLOAD_KEYS'):
        assert key not in getattr(admission, name)
    fingerprint, proposal_path, receipt_path, receipt = _write_policy(tmp_path)
    receipt_path.write_text(json.dumps(receipt))
    pick_place = _start_spec(tmp_path, fingerprint, proposal_path, receipt_path)
    cases = (('pick_place', pick_place),)
    for name, spec in cases:
        store = IntentStore.open(tmp_path/('state-'+name))
        try:
            service = _service(store)
            with pytest.raises(ValueError, match='CAMPAIGN_START_SCHEMA'):
                service.start(replace(spec, payload=dict(spec.payload, **{key: 'f'*64})))
            assert service.child_registry.launches() == () and service.arbiter.is_idle()
            assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        finally:
            store.close()


def test_qualification_mode_carrying_a_report_hash_or_path_is_refused(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        for change in (dict(qualification_receipt_sha256='f'*64), dict(qualification_receipt_path=str(tmp_path/'any.json'))):
            with pytest.raises(ValueError, match='QUALIFICATION_RECEIPT_UNEXPECTED'):
                workload.start(replace(spec, payload=dict(spec.payload, **change)), allow_existing=False)
            assert_nothing_acquired(workload, store)
            assert store.execution_generation(Domain.VALIDATION) == 0
    finally:
        store.close()


# ---- formal collection: admission verifies an exact-eight qualification report built by the real builder --------------------
#
# REAL: the qualification run on disk (the world builder drives the production producers, see collection_qualification_world.py),
# the report written by `build_collection_qualification_report`, the verifier `verify_collection_qualification` run by admission
# itself, the campaign-config loader, `UnifiedWorkloadService.start()` with its SQLite store, slot registry and GPU arbiter.
# CONTROLLED: what the world module labels controlled (episode bytes, the QC recomputation, Docker and provenance documents, the
# frozen-inputs reader) and the TEST-ONLY synthetic rule files, whose pass counts are not approved values. None of it is physical,
# Teacher, container or qualification evidence.

REPORT_RUNS = itertools.count()


@pytest.fixture(scope='module')
def qualified_world(tmp_path_factory):
    from collection_qualification_world import build_world, install_controlled_world
    from so101_demo.act.parallel_qualification_verifier import build_collection_qualification_report

    patch = pytest.MonkeyPatch()
    install_controlled_world(patch)
    try:
        world = build_world(tmp_path_factory.mktemp('qualification-world'))
        build_collection_qualification_report(world.run, contract=world.contract_path)
    finally:
        patch.undo()
    return world


def sha_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def formal_start(world, tmp_path, monkeypatch, *, config_edit=None, payload_edit=None, copy_report_into_run=False):
    """A formal start spec over `world`'s report, with its own run under the same registered root and its own store.

    The formal campaign config is the qualification world's with `qualification_contract` null (a formal campaign names no gate
    contract); `config_edit` and `payload_edit` mutate the config dict and the payload dict before they are hashed/frozen."""
    from collection_qualification_world import install_controlled_world

    install_controlled_world(monkeypatch)
    paths = make_campaign_paths(world.root, f'formal-{next(REPORT_RUNS)}')
    inputs = tmp_path/'formal-inputs'
    inputs.mkdir()
    campaign = json.loads(world.campaign_path.read_bytes())
    campaign['qualification_contract'] = None
    if config_edit is not None:
        config_edit(campaign, inputs)
    config_path = inputs/'campaign.json'
    config_path.write_text(json.dumps(campaign))
    report = world.report_path
    if copy_report_into_run:
        report = paths['host']/'qualification-report.json'
        report.write_bytes(world.report_path.read_bytes())
    slots = [asdict(ActWorkerSlot(campaign_id='campaign-1', worker_id=f'w{index:02d}', execution_generation=1))
        for index in range(8)]
    payload = dict(campaign_id='campaign-1', backend='mujoco', worker_count=8,
        contact_policy_fingerprint=world.identity['contact_policy_fingerprint'], evidence_root=str(paths['run']),
        service_epoch='epoch-1', resource_binding_id='binding-1', qualification_mode=False,
        qualification_receipt_path=str(report), qualification_receipt_sha256=sha_of(report), worker_slots=slots,
        registered_evidence_root=str(world.root), campaign_config_path=str(config_path),
        campaign_config_sha256=sha_of(config_path), instance_launcher='container')
    for name, path in (('source', world.inputs/'source.tar'), ('manifest', world.formal), ('runtime_config', world.runtime),
                       ('collection_config', world.collection)):
        payload[name+'_path'], payload[name+'_sha256'] = str(path), sha_of(path)
    if payload_edit is not None:
        payload_edit(payload, inputs)
    spec = OperationSpec(command_id='formal-1', domain=Domain.VALIDATION, kind='act_collection_start', payload=payload,
        runtime_id='runtime-1', execution_generation=1, deadline_ns=time.monotonic_ns()+10**12)
    store = IntentStore.open(tmp_path/'state')
    workload = _service(store)
    workload.visible_physical_uuids = (GPU,)
    workload.root_registration = dict(path=str(world.root), uid=os.getuid(), gid=os.getgid())
    return paths, spec, store, workload


def test_formal_admits_after_exact_eight_qualification(qualified_world, tmp_path, monkeypatch):
    paths, spec, store, workload = formal_start(qualified_world, tmp_path, monkeypatch)
    try:
        assert not qualified_world.run.is_relative_to(paths['run']) and not paths['run'].is_relative_to(qualified_world.run)
        started = time.monotonic()
        context = workload.start(spec, allow_existing=False)
        print(f'ADMISSION_VERIFICATION_SECONDS={time.monotonic()-started:.1f}')
        assert context.workload_kind == 'act_collection_start' and len(workload.slot_registry.slots()) == 8
        assert store._query_one('SELECT * FROM gpu_workload_leases') is not None
        assert store.execution_generation(Domain.VALIDATION) == 1
    finally:
        store.close()


def test_formal_admits_when_teacher_weights_and_instance_count_differ(qualified_world, tmp_path, monkeypatch):
    """The Teacher's weights, classes, threshold and instance count are not part of the qualified identity (spec section 7)."""
    def other_teacher(campaign, inputs):
        weights = inputs/'other-teacher.pt'
        weights.write_bytes(b'other-teacher-weights')
        teacher = campaign['teacher_service']
        teacher['model'] = dict(teacher['model'], model_id='other-model', score_threshold=.5,
            weights=dict(path=str(weights), sha256=sha_of(weights)))
        teacher['instances'] = 1
        assert teacher['instances'] != qualified_world.service['instances']
    paths, spec, store, workload = formal_start(qualified_world, tmp_path, monkeypatch, config_edit=other_teacher)
    try:
        assert workload.start(spec, allow_existing=False).workload_kind == 'act_collection_start'
        assert len(workload.slot_registry.slots()) == 8
    finally:
        store.close()


def assert_formal_refused(workload, store, spec, code):
    with pytest.raises(ValueError, match=code) as raised:
        workload.start(spec, allow_existing=False)
    assert_nothing_acquired(workload, store)
    assert store.execution_generation(Domain.VALIDATION) == 0
    return raised


def test_report_under_the_current_run_root_is_refused(qualified_world, tmp_path, monkeypatch):
    paths, spec, store, workload = formal_start(qualified_world, tmp_path, monkeypatch, copy_report_into_run=True)
    try:
        assert Path(spec.payload['qualification_receipt_path']).is_relative_to(paths['run'])
        assert_formal_refused(workload, store, spec, 'EIGHT_WORKER_QUALIFICATION_MISMATCH')
    finally:
        store.close()


def test_report_hash_that_is_not_the_reports_is_refused(qualified_world, tmp_path, monkeypatch):
    paths, spec, store, workload = formal_start(qualified_world, tmp_path, monkeypatch,
        payload_edit=lambda payload, inputs: payload.update(qualification_receipt_sha256='f'*64))
    try:
        assert_formal_refused(workload, store, spec, 'EIGHT_WORKER_QUALIFICATION_MISMATCH')
    finally:
        store.close()


def test_formal_scene_list_that_is_not_the_gates_is_refused(qualified_world, tmp_path, monkeypatch):
    def other_list(payload, inputs):
        scenes = inputs/'other-formal-scenes.json'
        scenes.write_text(json.dumps({'scenarios': [{'scene_id': 'elsewhere-00', 'seed': 1, 'split': 'validation'}]}))
        payload.update(manifest_path=str(scenes), manifest_sha256=sha_of(scenes))
    paths, spec, store, workload = formal_start(qualified_world, tmp_path, monkeypatch, payload_edit=other_list)
    try:
        assert_formal_refused(workload, store, spec, 'EIGHT_WORKER_QUALIFICATION_MISMATCH')
    finally:
        store.close()


def test_campaign_config_naming_a_gate_contract_is_refused(qualified_world, tmp_path, monkeypatch):
    def names_gate(campaign, inputs):
        campaign['qualification_contract'] = dict(path=str(qualified_world.contract_path),
                                                  sha256=sha_of(qualified_world.contract_path))
    paths, spec, store, workload = formal_start(qualified_world, tmp_path, monkeypatch, config_edit=names_gate)
    try:
        assert_formal_refused(workload, store, spec, 'EIGHT_WORKER_QUALIFICATION_MISMATCH')
    finally:
        store.close()


@pytest.mark.parametrize('missing', ['path', 'sha256'])
def test_formal_without_report_path_or_hash_is_required(qualified_world, tmp_path, monkeypatch, missing):
    paths, spec, store, workload = formal_start(qualified_world, tmp_path, monkeypatch,
        payload_edit=lambda payload, inputs: payload.update({'qualification_receipt_'+missing: None}))
    try:
        assert_formal_refused(workload, store, spec, 'EIGHT_WORKER_QUALIFICATION_REQUIRED')
    finally:
        store.close()


IDENTITY_CHANGES = ('source_sha256', 'runtime_config_sha256', 'collection_config_sha256', 'contact_policy_fingerprint',
                    'inference_image', 'shard_image', 'gpu_uuid')


@pytest.mark.parametrize('key', IDENTITY_CHANGES)
def test_identity_that_differs_from_the_qualified_one_is_refused(qualified_world, tmp_path, monkeypatch, key):
    """Each controlled-identity key, changed on the formal side only, refuses the same report; the run holds the originals."""
    def different_file(name, suffix):
        def edit(payload, inputs):
            other = inputs/f'other-{name}{suffix}'
            other.write_bytes(Path(payload[name+'_path']).read_bytes()+b'# another file\n')
            payload.update({name+'_path': str(other), name+'_sha256': sha_of(other)})
            if name == 'runtime_config':    # the campaign config binds the runtime file too
                config = json.loads(Path(payload['campaign_config_path']).read_bytes())
                config['controlled_runtime'] = dict(path=str(other), sha256=sha_of(other))
                Path(payload['campaign_config_path']).write_text(json.dumps(config))
                payload['campaign_config_sha256'] = sha_of(payload['campaign_config_path'])
        return edit
    payload_edit = config_edit = None
    if key == 'source_sha256': payload_edit = different_file('source', '.tar')
    elif key == 'runtime_config_sha256': payload_edit = different_file('runtime_config', '.yaml')
    elif key == 'collection_config_sha256': payload_edit = different_file('collection_config', '.yaml')
    elif key == 'contact_policy_fingerprint': payload_edit = lambda payload, inputs: payload.update(contact_policy_fingerprint='f'*64)
    elif key == 'inference_image':
        # the loader requires the Head's image to equal the Teacher's, so both change
        config_edit = lambda campaign, inputs: [campaign[role]['image'].update(install_sha256='9'*64)
                                                for role in ('head_service', 'teacher_service')]
    elif key == 'shard_image':
        config_edit = lambda campaign, inputs: campaign['shard_image'].update(digest='sha256:'+'9'*64)
    else:
        config_edit = lambda campaign, inputs: campaign.update(gpu_uuid='GPU-00000000-0000-0000-0000-000000000000')
    paths, spec, store, workload = formal_start(qualified_world, tmp_path, monkeypatch, config_edit=config_edit,
                                                payload_edit=payload_edit)
    try:
        raised = assert_formal_refused(workload, store, spec, 'EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID')
        assert 'COLLECTION_QUALIFICATION_IDENTITY_MISMATCH' in str(raised.value.__cause__)
    finally:
        store.close()


def test_legacy_pass_receipt_in_a_sibling_run_is_refused_as_invalid_evidence(qualified_world, tmp_path, monkeypatch):
    legacy = make_campaign_paths(qualified_world.root, f'legacy-{next(REPORT_RUNS)}')['host']/'qualification-report.json'
    legacy.write_text(json.dumps(dict(status='PASSED', worker_count=8)))
    paths, spec, store, workload = formal_start(qualified_world, tmp_path, monkeypatch, payload_edit=lambda payload, inputs:
        payload.update(qualification_receipt_path=str(legacy), qualification_receipt_sha256=sha_of(legacy)))
    try:
        assert_formal_refused(workload, store, spec, 'EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID')
    finally:
        store.close()
