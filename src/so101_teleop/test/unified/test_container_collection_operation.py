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
        qualification=True,qualification_contract=None,worker_count=1)


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
