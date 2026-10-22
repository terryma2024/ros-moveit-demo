"""A staged collection admits once per stage; the first admission of a campaign id happens once.

Controlled: the fixture of `test_container_collection_admission` (synthetic scaffolding files, fake container inspect). Real:
admission, the SQLite store and the stage records of the run (`host/<stage>-complete.json`)."""

from dataclasses import asdict, replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_container_collection_admission import fixture, terminated_services
from so101_demo.runtime.container_campaign import container_receipts, stage_records
from so101_demo.runtime.container_campaign.process_identity import ContainerOwnerKey
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_teleop.unified.worker_slots import ActWorkerSlot

FIRST = 'collection-campaign-1'


def first_spec(spec):
    return replace(spec, command_id=FIRST)


def staged(spec, stage, generation):
    """The spec of a later stage: its own command id and generation, the slots of that generation, the rest as phase 1."""
    payload = dict(spec.payload)
    payload['worker_slots'] = [asdict(ActWorkerSlot(campaign_id=payload['campaign_id'], worker_id='w00',
                                                    execution_generation=generation))]
    return replace(spec, command_id=f'{FIRST}-{stage}', payload=payload, execution_generation=generation)


def logic(spec):
    return dict(path=spec.payload['campaign_config_path'], sha256=spec.payload['campaign_config_sha256'])


def settle_first(paths, inspect, workload, spec):
    context = workload.start(first_spec(spec), allow_existing=False)
    terminated_services(paths, inspect)
    workload.finish(context, cleanup_confirmed=True)
    return context


def record_phase1(paths, spec):
    stage_records.write_record(paths['host'], stage_records.PHASE1, dict(campaign_config=logic(spec)))


def test_the_first_admission_of_a_campaign_id_happens_once(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        settle_first(paths, inspect, workload, spec)
        again = replace(staged(spec, 'x', 2), command_id='second-start')
        with pytest.raises(ValueError, match='CAMPAIGN_FIRST_ADMISSION_REPEATED'):
            workload.start(again, allow_existing=False)
        assert workload.slot_registry.slots() == ()
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        assert store._query_one('SELECT COUNT(*) FROM act_campaign_contexts')[0] == 1
    finally:
        store.close()


def test_a_later_stage_is_admitted_on_the_same_run_after_the_stage_record_before_it(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        first = settle_first(paths, inspect, workload, spec)
        record_phase1(paths, spec)
        second = workload.start(staged(spec, 'phase2', 2), allow_existing=False)
        assert second.campaign_id == first.campaign_id and second.operation_id != first.operation_id
        assert second.execution_generation == 2 and second.evidence_root == first.evidence_root
        assert store._query_one('SELECT COUNT(*) FROM act_campaign_contexts')[0] == 2
        assert [item.execution_generation for item in workload.slot_registry.slots()] == [2]
    finally:
        store.close()


@pytest.mark.parametrize('stage', ['phase2', 'retry-1', 'finalize'])
def test_a_later_stage_without_a_first_admission_is_refused_before_any_resource(tmp_path, stage):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        with pytest.raises(ValueError, match='STAGE_FIRST_ADMISSION_MISSING'):
            workload.start(staged(spec, stage, 1), allow_existing=False)
        assert workload.slot_registry.slots() == ()
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        assert store._query_one('SELECT * FROM act_campaign_contexts') is None
    finally:
        store.close()


@pytest.mark.parametrize('stage,code', [('phase2', 'STAGE_PREVIOUS_RECORD_MISSING'),
                                         ('retry-1', 'STAGE_PREVIOUS_RECORD_MISSING'),
                                         ('finalize', 'STAGE_PREVIOUS_RECORD_MISSING')])
def test_a_later_stage_without_the_record_before_it_is_refused(tmp_path, stage, code):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        settle_first(paths, inspect, workload, spec)
        with pytest.raises(ValueError, match=code):
            workload.start(staged(spec, stage, 2), allow_existing=False)
        assert workload.slot_registry.slots() == ()
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        assert store._query_one('SELECT COUNT(*) FROM act_campaign_contexts')[0] == 1
    finally:
        store.close()


def test_a_stage_record_that_was_altered_is_refused(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        settle_first(paths, inspect, workload, spec)
        record_phase1(paths, spec)
        path = stage_records.record_path(paths['host'], stage_records.PHASE1)
        path.write_bytes(path.read_bytes().replace(b'phase1', b'phase9', 1))
        with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_INVALID'):
            workload.start(staged(spec, 'phase2', 2), allow_existing=False)
        assert store._query_one('SELECT COUNT(*) FROM act_campaign_contexts')[0] == 1
    finally:
        store.close()


def test_a_stage_record_naming_another_logic_document_is_refused(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        settle_first(paths, inspect, workload, spec)
        stage_records.write_record(paths['host'], stage_records.PHASE1,
                                   dict(campaign_config=dict(path='x', sha256='f' * 64)))
        with pytest.raises(ValueError, match='STAGE_LOGIC_DOCUMENT_CHANGED'):
            workload.start(staged(spec, 'phase2', 2), allow_existing=False)
    finally:
        store.close()


def test_a_stage_that_is_already_complete_is_refused(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        settle_first(paths, inspect, workload, spec)
        record_phase1(paths, spec)
        previous = stage_records.read_record(paths['host'], stage_records.PHASE1)
        stage_records.write_record(paths['host'], stage_records.PHASE2, dict(campaign_config=logic(spec)), previous=previous)
        with pytest.raises(ValueError, match='STAGE_ALREADY_COMPLETE'):
            workload.start(staged(spec, 'phase2', 2), allow_existing=False)
    finally:
        store.close()


@pytest.mark.parametrize('field', ['evidence_root', 'registered_evidence_root', 'campaign_config_sha256'])
def test_a_stage_that_names_another_run_than_the_first_admission_is_refused(tmp_path, field):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        settle_first(paths, inspect, workload, spec)
        record_phase1(paths, spec)
        later = staged(spec, 'phase2', 2)
        payload = dict(later.payload)
        other = tmp_path / 'other-run'
        payload[field] = 'f' * 64 if field == 'campaign_config_sha256' else str(other)
        with pytest.raises(ValueError):
            workload.start(replace(later, payload=payload), allow_existing=False)
        assert workload.slot_registry.slots() == ()
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        assert store._query_one('SELECT COUNT(*) FROM act_campaign_contexts')[0] == 1
    finally:
        store.close()


def test_the_run_root_refusal_carries_its_own_code(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        settle_first(paths, inspect, workload, spec)
        record_phase1(paths, spec)
        # the same campaign id under another run root: the stage cannot borrow the id of a run that is not its own
        other = Path(tmp_path) / 'run-b'
        other.mkdir()
        later = staged(spec, 'phase2', 2)
        payload = dict(later.payload, evidence_root=str(other))
        with pytest.raises(ValueError, match='STAGE_RUN_ROOT_MISMATCH'):
            workload.start(replace(later, payload=payload), allow_existing=False)
    finally:
        store.close()


def test_an_unknown_stage_name_is_refused(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        settle_first(paths, inspect, workload, spec)
        with pytest.raises(ValueError, match='STAGE_NAME_INVALID'):
            workload.start(staged(spec, 'whatever', 2), allow_existing=False)
    finally:
        store.close()


def receipt_and_remove(paths, inspect, stage=stage_records.PHASE1):
    """What the owner does at the end of a stage: receipt every container that was proven exited, then remove it."""
    registry = ContainerLaunchRegistry(paths['host'] / 'launches.sqlite3', create=False)
    try:
        entries = []
        for record in registry.records():
            entry = container_receipts.container_entry(record, inspect[record['owner']['container_id']])
            logs, digest = container_receipts.save_logs(paths['host'], stage, entry['container_name'],
                lambda argv: SimpleNamespace(returncode=0, stdout='t out', stderr='t err'), entry['container_id'])
            entries.append(dict(entry, logs_path=logs, logs_sha256=digest, removed=True, absent_after_removal=True))
    finally:
        registry.close()
    record = stage_records.read_record(paths['host'], stage)
    container_receipts.write_receipt(paths['host'], stage=stage, stage_record_sha256=record['sha256'], containers=entries)
    inspect.clear()


def test_a_stage_settles_on_its_receipt_when_its_containers_were_removed(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(first_spec(spec), allow_existing=False)
        terminated_services(paths, inspect)
        record_phase1(paths, spec)
        receipt_and_remove(paths, inspect)
        workload.finish(context, cleanup_confirmed=True)
        assert workload.slot_registry.slots() == () and store._query_one('SELECT * FROM gpu_workload_leases') is None
    finally:
        store.close()


def test_removed_containers_without_a_receipt_do_not_settle(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(first_spec(spec), allow_existing=False)
        terminated_services(paths, inspect)
        inspect.clear()
        with pytest.raises(ValueError, match='ACT_CONTAINER_CLEANUP_NOT_CONFIRMED'):
            workload.finish(context, cleanup_confirmed=True)
        assert store._query_one('SELECT * FROM gpu_workload_leases') is not None
    finally:
        store.close()


@pytest.mark.parametrize('damage', ['uncovered', 'altered', 'log missing', 'log altered'])
def test_a_receipt_that_does_not_hold_does_not_settle(tmp_path, damage):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(first_spec(spec), allow_existing=False)
        terminated_services(paths, inspect)
        record_phase1(paths, spec)
        receipt_and_remove(paths, inspect)
        path = container_receipts.receipt_files(paths['host'])[0][2]
        document = json.loads(path.read_bytes())
        logs = paths['host'] / document['containers'][0]['logs_path']
        if damage == 'uncovered':
            document['containers'].pop()
        elif damage == 'altered':
            document['containers'][0]['exit_code'] = 9
        elif damage == 'log missing':
            logs.unlink()
        else:
            logs.write_bytes(logs.read_bytes() + b'x')
        path.write_bytes(stage_records.canonical_json(document) + b'\n')
        with pytest.raises(ValueError, match='ACT_CONTAINER_CLEANUP_NOT_CONFIRMED'):
            workload.finish(context, cleanup_confirmed=True)
        assert store._query_one('SELECT * FROM gpu_workload_leases') is not None
    finally:
        store.close()


def terminated_processor(paths, inspect, root):
    """A phase-2 processor launch, proven exited like the services of `terminated_services`."""
    (root/'processing'/'p00'/'g1').mkdir(parents=True)
    registry = ContainerLaunchRegistry(paths['host']/'launches.sqlite3', create=False)
    launch = ContainerLaunch(launch_id='processing-p00-g1', role='processor', worker_id='p00', wave_id=None,
        launch_generation=1, container_name='so101-processor-p00', image_digest='sha256:'+'b'*64,
        owned_root=str(root/'processing'/'p00'/'g1'))
    owner = ContainerOwnerKey('3'*64, '2026-10-12T01:02:03.123Z', 'sha256:'+'b'*64, 1)
    registry.register(launch)
    registry.bind_container(launch.launch_id, owner)
    inspect[owner.container_id] = dict(Id=owner.container_id, Image=owner.image_digest,
        State=dict(StartedAt=owner.docker_started_at, Running=False, Restarting=False,
                   Pid=0, Status='exited', ExitCode=0, FinishedAt='2026-10-12T01:05:03.123Z'))
    registry.prove_terminated(launch.launch_id, inspect[owner.container_id])
    registry.close()


def release_processor_slots(store, campaign_id):
    """What the end of the phase-2 stage does to the processor slots: they are released with that stage's admission."""
    with store.immediate_transaction():
        store._connection.execute("UPDATE act_worker_slots SET active=0 WHERE campaign_id=? AND worker_id LIKE 'p%'",
                                  (campaign_id,))


def test_a_later_stage_settles_although_the_processor_slots_were_released_by_phase_2(tmp_path):
    """Phase 2 admits and releases the pNN slots; the finalize still settles the processor launches of the registry on their receipt."""
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(first_spec(spec), allow_existing=False)
        terminated_services(paths, inspect)
        terminated_processor(paths, inspect, paths['run'])
        workload.admit_processor_slots(context, (ActWorkerSlot(campaign_id=context.campaign_id, worker_id='p00',
                                                               execution_generation=context.execution_generation),))
        record_phase1(paths, spec)
        receipt_and_remove(paths, inspect)
        release_processor_slots(store, context.campaign_id)
        workload.finish(context, cleanup_confirmed=True)
        assert workload.slot_registry.slots() == () and store._query_one('SELECT * FROM gpu_workload_leases') is None
    finally:
        store.close()


def test_a_processor_launch_that_no_slot_ever_covered_does_not_settle(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(first_spec(spec), allow_existing=False)
        terminated_services(paths, inspect)
        terminated_processor(paths, inspect, paths['run'])
        record_phase1(paths, spec)
        receipt_and_remove(paths, inspect)
        with pytest.raises(ValueError, match='ACT_CONTAINER_CLEANUP_NOT_CONFIRMED'):
            workload.finish(context, cleanup_confirmed=True)
        assert store._query_one('SELECT * FROM gpu_workload_leases') is not None
    finally:
        store.close()
