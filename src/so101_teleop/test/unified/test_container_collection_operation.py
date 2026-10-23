"""Pure startup composition returns the real SQLite admission operation."""

from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
import hashlib
import json

import pytest

from test_container_collection_admission import fixture as admission_fixture
from so101_teleop.unified.contracts import Domain, OperationSpec


def fixture(tmp_path,monkeypatch):
    import ament_index_python.packages as packages
    paths,slot,spec,store,workload,inspect = admission_fixture(tmp_path)
    share = Path(__file__).resolve().parents[3]/'so101_demo_py'
    original = packages.get_package_share_directory
    monkeypatch.setattr(packages,'get_package_share_directory',lambda name:
        str(share) if name == 'so101_demo_py' else original(name))
    collection = Path(spec.payload['collection_config_path'])
    collection.write_bytes((share/'config/act/parallel_collection.yaml').read_bytes())
    collection_sha = hashlib.sha256(collection.read_bytes()).hexdigest()
    manifest = Path(spec.payload['manifest_path'])
    document = json.loads(manifest.read_bytes())
    document['controlled_identity']['collection_config_sha256'] = collection_sha
    manifest.write_text(json.dumps(document))
    spec = replace(spec,payload=spec.payload|dict(collection_config_sha256=collection_sha,
        manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest()))
    return paths,slot,spec,store,workload,inspect


def prepare(module,args,workload,spec):
    """The caller passes the fingerprint it took from the frozen inputs; here it is the fixture's controlled value."""
    return module.prepare_collection_operation(args,services=SimpleNamespace(act_workload=workload,act_error=None),
        contact_policy_fingerprint=spec.payload['contact_policy_fingerprint'])


def arguments(spec):
    p = spec.payload
    return SimpleNamespace(campaign_id=p['campaign_id'],manifest=Path(p['manifest_path']),
        source=Path(p['source_path']),
        runtime_config=Path(p['runtime_config_path']),collection_config=Path(p['collection_config_path']),
        campaign_config=Path(p['campaign_config_path']),root=Path(p['evidence_root']),
        qualification=True,qualification_report=None,worker_count=1)


@pytest.mark.parametrize('worker_count',[1,2])
def test_preparation_has_no_resource_or_file_effect_and_actual_admission_persists_generation(tmp_path,monkeypatch,worker_count):
    import so101_demo.runtime.act_fixed_collection_composition as module
    paths,slot,spec,store,workload,inspect = fixture(tmp_path,monkeypatch)
    # Only the installed package-share lookup is replaced. The actual closed
    # collection/runtime loaders and real SQLite admission both run.
    services = SimpleNamespace(act_workload=workload,act_error=None)
    args = arguments(spec)
    args.worker_count = worker_count
    document = json.loads(args.manifest.read_bytes())
    document['worker_count'] = worker_count
    args.manifest.write_text(json.dumps(document))
    before = tuple(paths['run'].rglob('*'))
    try:
        prepared = module.prepare_collection_operation(args,services=services,
            contact_policy_fingerprint=spec.payload['contact_policy_fingerprint'])
        assert type(prepared) is OperationSpec and prepared.domain is Domain.VALIDATION
        assert prepared.execution_generation == 1
        assert prepared.runtime_id == workload.runtime_id
        assert prepared.payload['service_epoch'] == workload.service_epoch
        assert prepared.payload['resource_binding_id'] == workload.resource_binding_id
        assert 'children' not in prepared.payload
        assert store.execution_generation(Domain.VALIDATION) == 0
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        assert workload.slot_registry.slots() == ()
        assert before == tuple(paths['run'].rglob('*'))
        context = workload.start(prepared,allow_existing=False)
        assert context.execution_generation == store.execution_generation(Domain.VALIDATION) == 1
        assert workload.slot_registry.slots()[0].execution_generation == 1
        assert len(workload.slot_registry.slots()) == worker_count
    finally:
        store.close()


@pytest.mark.parametrize('problem',['workers','root','old_contract','formal_no_report'])
def test_preparation_refuses_invalid_inputs_without_allocating_generation(tmp_path,monkeypatch,problem):
    import so101_demo.runtime.act_fixed_collection_composition as module
    paths,slot,spec,store,workload,inspect = fixture(tmp_path,monkeypatch)
    args = arguments(spec)
    if problem == 'workers': args.worker_count = 4
    elif problem == 'root': args.root = tmp_path
    elif problem == 'old_contract': args.manifest.write_text('{"kind":"SINGLE_WORKER"}')
    else: args.qualification=False; args.worker_count=8
    try:
        with pytest.raises(ValueError):
            prepare(module,args,workload,spec)
        assert store.execution_generation(Domain.VALIDATION) == 0
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        assert workload.slot_registry.slots() == ()
    finally:
        store.close()


@pytest.mark.parametrize('failure',['generation_advanced','parent_write'])
def test_generation_conflict_or_failed_admission_never_leaks_gpu_or_slots(tmp_path,monkeypatch,failure):
    import so101_demo.runtime.act_fixed_collection_composition as module
    paths,slot,spec,store,workload,inspect = fixture(tmp_path,monkeypatch)
    try:
        prepared = prepare(module,arguments(spec),workload,spec)
        if failure == 'generation_advanced':
            with store.immediate_transaction():
                store.bump_execution_generation_locked(Domain.VALIDATION)
            expected = 'ACT_CONTAINER_GENERATION_STALE'
        else:
            def fail_parent(*args,**kwargs):
                raise ValueError('PARENT_WRITE_FAILED')
            monkeypatch.setattr(store,'insert_parent',fail_parent)
            expected = 'PARENT_WRITE_FAILED'
        with pytest.raises(ValueError,match=expected):
            workload.start(prepared,allow_existing=False)
        assert store.execution_generation(Domain.VALIDATION) == (1 if failure == 'generation_advanced' else 0)
        assert workload.slot_registry.slots() == ()
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        assert store._query_one('SELECT * FROM act_campaign_contexts') is None
    finally:
        store.close()


def test_prepare_takes_fingerprint_from_frozen_inputs(tmp_path,monkeypatch):
    """The arguments name no proposal, receipt or report; the fingerprint is the caller's explicit value (the later CLI stage
    passes `campaign_binding(...)['contact_policy_fingerprint']`) and nothing is read to derive it."""
    import so101_demo.runtime.act_fixed_collection_composition as module
    paths,slot,spec,store,workload,inspect = fixture(tmp_path,monkeypatch)
    args = arguments(spec)
    for removed in ('policy','activation_receipt','calibration'):
        assert not hasattr(args,removed)
    services = SimpleNamespace(act_workload=workload,act_error=None)
    try:
        fingerprint = 'a'*64
        assert fingerprint != spec.payload['contact_policy_fingerprint']
        prepared = module.prepare_collection_operation(args,services=services,contact_policy_fingerprint=fingerprint)
        assert prepared.payload['contact_policy_fingerprint'] == fingerprint
        for invalid in ('A'*64,'a'*63,'',None,123):
            with pytest.raises(ValueError,match='COLLECTION_POLICY_INVALID'):
                module.prepare_collection_operation(args,services=services,contact_policy_fingerprint=invalid)
        with pytest.raises(TypeError):
            module.prepare_collection_operation(args,services=services)
        assert store.execution_generation(Domain.VALIDATION) == 0
        # the value is the business identity: the run contract's controlled identity must carry the same one
        with pytest.raises(ValueError,match='COLLECTION_RUN_CONTRACT_BINDING_MISMATCH'):
            workload.start(prepared,allow_existing=False)
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
    finally:
        store.close()


def test_prepare_payload_matches_reduced_closed_key_set(tmp_path,monkeypatch):
    import so101_demo.runtime.act_fixed_collection_composition as module
    from so101_teleop.unified.admission import _COLLECTION_PAYLOAD_KEYS
    paths,slot,spec,store,workload,inspect = fixture(tmp_path,monkeypatch)
    try:
        payload = prepare(module,arguments(spec),workload,spec).payload
        assert set(payload) == _COLLECTION_PAYLOAD_KEYS
        assert not {'proposal_path','activation_receipt_path','calibration_report_path','calibration_report_sha256',
                    'children'} & set(payload)
        assert {'contact_policy_fingerprint','worker_slots','campaign_config_path','campaign_config_sha256',
                'registered_evidence_root','runtime_config_path','runtime_config_sha256'} <= set(payload)
    finally:
        store.close()


def formal_arguments(spec, report):
    """A formal-plane argument set: eight workers, the formal scene list as the manifest, the report named by `qualification_report`."""
    args = arguments(spec)
    args.qualification, args.worker_count, args.qualification_report = False, 8, report
    args.manifest = Path(spec.payload['manifest_path']).parent/'formal-scenes.json'
    args.manifest.write_text(json.dumps({'scenarios': [{'scene_id': 'formal-00', 'split': 'validation'}]}))
    return args


def test_qualification_payload_carries_neither_receipt_key_value(tmp_path,monkeypatch):
    import so101_demo.runtime.act_fixed_collection_composition as module
    paths,slot,spec,store,workload,inspect = fixture(tmp_path,monkeypatch)
    try:
        payload = prepare(module,arguments(spec),workload,spec).payload
        assert payload['qualification_receipt_path'] is None and payload['qualification_receipt_sha256'] is None
    finally:
        store.close()


def test_formal_payload_carries_the_report_path_and_its_sha256(tmp_path,monkeypatch):
    import so101_demo.runtime.act_fixed_collection_composition as module
    from so101_teleop.unified.admission import _COLLECTION_PAYLOAD_KEYS
    paths,slot,spec,store,workload,inspect = fixture(tmp_path,monkeypatch)
    report = tmp_path/'report-bytes.json'
    report.write_bytes(b'{"controlled": "report bytes, hashed and never parsed here"}')
    try:
        payload = prepare(module,formal_arguments(spec,report),workload,spec).payload
        assert set(payload) == _COLLECTION_PAYLOAD_KEYS and payload['worker_count'] == 8
        assert payload['qualification_mode'] is False
        assert payload['qualification_receipt_path'] == str(report)
        assert payload['qualification_receipt_sha256'] == hashlib.sha256(report.read_bytes()).hexdigest()
    finally:
        store.close()


@pytest.mark.parametrize('problem',['absent','directory','symlink'])
def test_formal_report_must_be_a_regular_file_before_admission(tmp_path,monkeypatch,problem):
    import so101_demo.runtime.act_fixed_collection_composition as module
    paths,slot,spec,store,workload,inspect = fixture(tmp_path,monkeypatch)
    target = tmp_path/'real-report.json'
    target.write_bytes(b'{}')
    report = tmp_path/'report-under-test.json'
    if problem == 'directory': report.mkdir()
    elif problem == 'symlink': report.symlink_to(target)
    try:
        with pytest.raises(ValueError,match='FIXED_COLLECTION_INPUT_UNREADABLE'):
            prepare(module,formal_arguments(spec,report),workload,spec)
        assert store.execution_generation(Domain.VALIDATION) == 0
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        assert workload.slot_registry.slots() == ()
    finally:
        store.close()


def test_qualification_run_naming_a_report_is_refused(tmp_path,monkeypatch):
    import so101_demo.runtime.act_fixed_collection_composition as module
    paths,slot,spec,store,workload,inspect = fixture(tmp_path,monkeypatch)
    args = arguments(spec)
    args.qualification_report = tmp_path/'report.json'
    args.qualification_report.write_bytes(b'{}')
    try:
        with pytest.raises(ValueError,match='COLLECTION_RUN_CONTRACT_MISMATCH'):
            prepare(module,args,workload,spec)
    finally:
        store.close()


def test_eight_worker_preparation_needs_none_of_the_scheduling_limits_in_the_campaign_config(tmp_path,monkeypatch):
    import so101_demo.runtime.act_fixed_collection_composition as module
    paths,slot,spec,store,workload,inspect = fixture(tmp_path,monkeypatch)
    report = tmp_path/'report-bytes.json'
    report.write_bytes(b'{}')
    config = Path(spec.payload['campaign_config_path'])
    document = json.loads(config.read_bytes())
    limits = ('max_concurrent_recordings','max_tasks_in_flight','min_assignment_gap_s')
    assert document['max_concurrent_recordings'] == 4 and document['min_assignment_gap_s'] == 60
    try:
        digests = set()
        for kept in (limits, limits[:1], limits[2:], ()):   # every combination of presence is admissible, each its own hash
            variant = {name:value for name,value in document.items() if name not in limits or name in kept}
            if 'max_tasks_in_flight' in kept:
                variant['max_tasks_in_flight'] = 5
            config.write_text(json.dumps(variant))
            payload = prepare(module,formal_arguments(spec,report),workload,spec).payload
            assert payload['worker_count'] == 8 and payload['campaign_config_sha256'] == hashlib.sha256(config.read_bytes()).hexdigest()
            digests.add(payload['campaign_config_sha256'])
        assert len(digests) == 4
        config.write_text(json.dumps(document))
        args = arguments(spec)   # one worker
        assert prepare(module,args,workload,spec).payload['worker_count'] == 1
        assert store.execution_generation(Domain.VALIDATION) == 0
    finally:
        store.close()


def test_phase_limits_that_exceed_the_batch_total_are_refused_before_admission(tmp_path,monkeypatch):
    """`collect_timeout_s + process_timeout_s` (and each alone, and the reserve) must fit `batch_hard_timeout_s`."""
    import so101_demo.runtime.act_fixed_collection_composition as module
    paths,slot,spec,store,workload,inspect = fixture(tmp_path,monkeypatch)
    args = arguments(spec)
    services = SimpleNamespace(act_workload=workload,act_error=None)
    config_path = args.campaign_config
    original = json.loads(config_path.read_bytes())
    try:
        for extra in (dict(collect_timeout_s=86400,process_timeout_s=86400),dict(collect_timeout_s=86400),
                      dict(process_timeout_s=86400),dict(processing_reserve_s=86400)):
            config_path.write_text(json.dumps(original|extra))
            with pytest.raises(ValueError,match='CAMPAIGN_PHASE_LIMITS_EXCEED_TOTAL'):
                module.prepare_collection_operation(args,services=services,
                    contact_policy_fingerprint=spec.payload['contact_policy_fingerprint'])
        assert store.execution_generation(Domain.VALIDATION) == 0
    finally:
        store.close()


def test_qualification_retry_is_refused_without_allocating_any_resources(tmp_path,monkeypatch):
    import so101_demo.runtime.act_fixed_collection_composition as module
    paths,slot,spec,store,workload,inspect = fixture(tmp_path,monkeypatch)
    args = arguments(spec)
    document = json.loads(args.campaign_config.read_bytes())
    args.campaign_config.write_text(json.dumps(document | dict(retry_invalid_max_rounds=1)))
    try:
        with pytest.raises(ValueError,match='COLLECTION_RETRY_QUALIFICATION_FORBIDDEN'):
            prepared = prepare(module,args,workload,spec)
            workload.start(prepared,allow_existing=False)
        assert store.execution_generation(Domain.VALIDATION) == 0
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        assert workload.slot_registry.slots() == ()
    finally:
        store.close()


def _prepared_with_total(tmp_path,monkeypatch,total):
    tmp_path.mkdir(exist_ok=True)
    """The fixture's start arguments under a campaign config that carries `batch_hard_timeout_s=total` (absent when None)."""
    paths,slot,spec,store,workload,inspect = fixture(tmp_path,monkeypatch)
    args = arguments(spec)
    document = json.loads(args.campaign_config.read_bytes())
    if total is not None:
        args.campaign_config.write_text(json.dumps(document|dict(batch_hard_timeout_s=total)))
    return store,workload,spec,args


def _deadline_seconds(prepared,workload):
    return (prepared.deadline_ns-workload.clock_ns())/1e9


def test_campaign_config_total_is_the_deadline_and_absent_keeps_the_runtime_yaml(tmp_path,monkeypatch):
    import so101_demo.runtime.act_fixed_collection_composition as module
    store,workload,spec,args = _prepared_with_total(tmp_path/'absent',monkeypatch,None)
    try:
        assert 8990 < _deadline_seconds(prepare(module,args,workload,spec),workload) <= 9000   # parallel_batch_act_offline.yaml
    finally:
        store.close()
    store,workload,spec,args = _prepared_with_total(tmp_path/'present',monkeypatch,4000)
    try:
        assert 3990 < _deadline_seconds(prepare(module,args,workload,spec),workload) <= 4000
    finally:
        store.close()


def test_phase_limits_are_checked_against_the_campaign_config_total(tmp_path,monkeypatch):
    import so101_demo.runtime.act_fixed_collection_composition as module
    store,workload,spec,args = _prepared_with_total(tmp_path,monkeypatch,None)
    document = json.loads(args.campaign_config.read_bytes())
    try:
        # 2500 + 2000 fits the 9000 s yaml total but not a 4000 s campaign total
        args.campaign_config.write_text(json.dumps(document|dict(collect_timeout_s=2500,process_timeout_s=2000)))
        assert prepare(module,args,workload,spec).payload['worker_count'] == 1
        args.campaign_config.write_text(json.dumps(document|dict(
            batch_hard_timeout_s=4000,collect_timeout_s=2500,process_timeout_s=2000)))
        with pytest.raises(ValueError,match='CAMPAIGN_PHASE_LIMITS_EXCEED_TOTAL'):
            prepare(module,args,workload,spec)
        assert store.execution_generation(Domain.VALIDATION) == 0
    finally:
        store.close()


def test_campaign_config_total_out_of_range_is_refused_by_the_loader(tmp_path,monkeypatch):
    import so101_demo.runtime.act_fixed_collection_composition as module
    store,workload,spec,args = _prepared_with_total(tmp_path,monkeypatch,None)
    document = json.loads(args.campaign_config.read_bytes())
    try:
        for bad in (1799,14401):
            args.campaign_config.write_text(json.dumps(document|dict(batch_hard_timeout_s=bad)))
            with pytest.raises(ValueError,match='CAMPAIGN_CONFIG_INVALID'):
                prepare(module,args,workload,spec)
    finally:
        store.close()


def test_the_controlled_identity_ignores_the_campaign_config_total(tmp_path,monkeypatch):
    import so101_demo.runtime.act_fixed_collection_composition as module
    from so101_demo.runtime.inference.config import load_campaign_config
    from so101_teleop.unified.admission import _collection_identity
    identities,hashes = [],[]
    for name,total in (('absent',None),('four',4000),('twelve',12000)):
        store,workload,spec,args = _prepared_with_total(tmp_path/name,monkeypatch,total)
        try:
            payload = prepare(module,args,workload,spec).payload
            identity = _collection_identity(payload,load_campaign_config(args.campaign_config,roles=('teacher',)))
            identity.pop('mount_build')                   # each fixture mounts its own tmp tree; the total is what is compared
            identities.append(identity)
            hashes.append(payload['campaign_config_sha256'])
        finally:
            store.close()
    assert identities[0] == identities[1] == identities[2] and len(set(hashes)) == 3


def test_the_controlled_identity_carries_the_rig_only_when_the_campaign_config_names_one():
    from so101_teleop.unified.admission import _collection_identity
    payload = {name: str(index) * 64 for index, name in enumerate(
        ('source_sha256', 'runtime_config_sha256', 'collection_config_sha256', 'contact_policy_fingerprint'))}
    image = {'digest': 'sha256:' + 'a' * 64, 'package_source_sha256': 'b' * 64, 'install_sha256': 'c' * 64}
    config = {'gpu_uuid': 'GPU-28221cec-9d21-7753-fd5a-da645740df19', 'teacher_service': {'image': image}, 'shard_image': image,
              'mount_build': {'commit': 'a' * 40, 'root': '/mount/' + 'a' * 12}}
    assert 'rig_profile_sha256' not in _collection_identity(payload, config)
    named = _collection_identity(payload, dict(config, rig_profile_sha256='9' * 64))
    assert named['rig_profile_sha256'] == '9' * 64
    assert {key: value for key, value in named.items() if key != 'rig_profile_sha256'} == _collection_identity(payload, config)
