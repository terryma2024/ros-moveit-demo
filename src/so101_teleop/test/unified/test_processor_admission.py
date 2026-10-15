"""Phase-2 processor slots: admitted like shard slots, released with the campaign, checked by the cleanup verification."""

from dataclasses import replace

import pytest

from test_container_collection_admission import fixture, terminated_services
from so101_demo.runtime.container_campaign.process_identity import ContainerOwnerKey
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_teleop.unified.worker_slots import ActWorkerSlot


def processor_slot(slot, index=0, **changes):
    return replace(slot, worker_id=f'p{index:02d}', **changes)


def settled_processor(paths, inspect, *, worker='p00', generation=1, owned=None, character='3'):
    root = owned or paths['run']/'processing'/worker/f'g{generation}'
    root.mkdir(parents=True, exist_ok=True)
    registry = ContainerLaunchRegistry(paths['host']/'launches.sqlite3', create=False)
    launch = ContainerLaunch(launch_id=f'processing-{worker}-g{generation}', role='processor', worker_id=worker,
        wave_id=None, launch_generation=generation, container_name=f'so101-act-{worker}-g{generation}',
        image_digest='sha256:'+'b'*64, owned_root=str(root))
    owner = ContainerOwnerKey(character*64, '2026-10-12T01:02:03.123Z', 'sha256:'+'b'*64, generation)
    registry.register(launch)
    registry.bind_container(launch.launch_id, owner)
    inspect[owner.container_id] = dict(Id=owner.container_id, Image=owner.image_digest,
        State=dict(StartedAt=owner.docker_started_at, Running=False, Restarting=False, Pid=0, Status='exited', ExitCode=0))
    registry.prove_terminated(launch.launch_id, inspect[owner.container_id])
    registry.close()


def test_processor_slots_are_the_same_logical_resource_as_shard_slots():
    slot = ActWorkerSlot(campaign_id='campaign', worker_id='p03', execution_generation=2)
    assert slot.is_processor and not ActWorkerSlot('campaign', 'w03', 2).is_processor
    for worker in ('q00', 'p0', 'p000', 'P00', 'pp0'):
        with pytest.raises(ValueError, match='WORKER_SLOT_INVALID'):
            ActWorkerSlot('campaign', worker, 2)


def test_admitted_campaign_reserves_processors_and_finish_releases_them_with_the_campaign(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(spec, allow_existing=False)
        processors = (processor_slot(slot, 0), processor_slot(slot, 1))
        assert workload.admit_processor_slots(context, processors) == processors
        assert workload.slot_registry.slots() == (*processors, slot)
        with pytest.raises(ValueError, match='DUPLICATE_WORKER_SLOT'):
            workload.admit_processor_slots(context, processors)
        terminated_services(paths, inspect)
        settled_processor(paths, inspect, worker='p00')
        settled_processor(paths, inspect, worker='p01', character='4')
        projection = workload.finish(context, cleanup_confirmed=True)
        assert workload.slot_registry.slots() == ()
        assert workload.slot_registry.slots(active=False) == (*processors, slot)
        assert store._query_one('SELECT * FROM gpu_workload_leases') is None
        assert workload.finish(context, cleanup_confirmed=True) == projection
    finally:
        store.close()


def test_a_running_processor_container_keeps_every_slot_and_the_lease(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(spec, allow_existing=False)
        processor = processor_slot(slot)
        workload.admit_processor_slots(context, (processor,))
        terminated_services(paths, inspect)
        settled_processor(paths, inspect)
        inspect['3'*64]['State'].update(Running=True, Pid=77, Status='running')
        with pytest.raises(ValueError, match='ACT_CONTAINER_CLEANUP_NOT_CONFIRMED'):
            workload.finish(context, cleanup_confirmed=True)
        assert workload.slot_registry.slots() == (processor, slot)
        assert store._query_one('SELECT * FROM gpu_workload_leases') is not None
    finally:
        store.close()


@pytest.mark.parametrize('problem', ['foreign_root', 'unslotted_processor'])
def test_cleanup_verification_refuses_a_processor_outside_its_slot_scope(tmp_path, problem):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(spec, allow_existing=False)
        workload.admit_processor_slots(context, (processor_slot(slot),))
        terminated_services(paths, inspect)
        if problem == 'foreign_root':
            settled_processor(paths, inspect, owned=paths['run']/'processing'/'p00'/'elsewhere')
        else:
            settled_processor(paths, inspect, worker='p05')
        with pytest.raises((ValueError, KeyError), match='ACT_CONTAINER_CLEANUP_NOT_CONFIRMED|CONTAINER_LAUNCH_RECORD_INVALID'):
            workload.finish(context, cleanup_confirmed=True)
        assert workload.slot_registry.slots() == (processor_slot(slot), slot)
    finally:
        store.close()


@pytest.mark.parametrize('problem', ['shard_slot', 'other_campaign', 'other_generation', 'gap', 'empty', 'not_tuple'])
def test_processor_slot_admission_refusals(tmp_path, problem):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(spec, allow_existing=False)
        slots = {'shard_slot': (replace(slot, worker_id='w01'),),
                 'other_campaign': (processor_slot(slot, campaign_id='other'),),
                 'other_generation': (processor_slot(slot, execution_generation=slot.execution_generation + 1),),
                 'gap': (processor_slot(slot, 1),), 'empty': (), 'not_tuple': [processor_slot(slot)]}[problem]
        with pytest.raises(ValueError, match='PROCESSOR_SLOT_INVALID'):
            workload.admit_processor_slots(context, slots)
        assert workload.slot_registry.slots() == (slot,)
    finally:
        store.close()


def test_processor_slots_need_the_admitted_context_and_an_active_campaign(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(spec, allow_existing=False)
        with pytest.raises(ValueError, match='CAMPAIGN_CONTEXT_MISMATCH'):
            workload.admit_processor_slots(replace(context, operation_id='forged'), (processor_slot(slot),))
        terminated_services(paths, inspect)
        workload.finish(context, cleanup_confirmed=True)
        with pytest.raises(ValueError, match='CAMPAIGN_NOT_ACTIVE'):
            workload.admit_processor_slots(context, (processor_slot(slot),))
        assert workload.slot_registry.slots() == ()
    finally:
        store.close()


# ---- native single worker: one processor beside the (already stopped) native shard --------------------------------------------


def native_spec(spec):
    return replace(spec, payload=dict(spec.payload, instance_launcher='native'))


def test_a_native_campaign_admits_exactly_one_processor_slot_and_nothing_else_changes(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(native_spec(spec), allow_existing=False)
        processor = processor_slot(slot)
        assert workload.admit_processor_slots(context, (processor,)) == (processor,)
        assert workload.slot_registry.slots() == (processor, slot)
        with pytest.raises(ValueError, match='PROCESSOR_SLOT_INVALID|NATIVE_INSTANCE_SINGLE_WORKER_ONLY|DUPLICATE_WORKER_SLOT|PROCESSOR_SLOT_NATIVE_SINGLE_ONLY'):
            workload.admit_processor_slots(context, (processor_slot(slot, 1),))
        assert workload.slot_registry.native_campaign_ids() == {slot.campaign_id}
    finally:
        store.close()


def test_two_processor_slots_are_refused_for_a_native_campaign_before_any_reservation(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(native_spec(spec), allow_existing=False)
        with pytest.raises(ValueError, match='PROCESSOR_SLOT_NATIVE_SINGLE_ONLY'):
            workload.admit_processor_slots(context, (processor_slot(slot, 0), processor_slot(slot, 1)))
        assert workload.slot_registry.slots() == (slot,)
    finally:
        store.close()


def test_finish_does_not_settle_a_native_processor_whose_stop_is_unproven(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(native_spec(spec), allow_existing=False)
        workload.admit_processor_slots(context, (processor_slot(slot),))
        terminated_services(paths, inspect)
        root = paths['run']/'processing'/'p00'/'g1'
        root.mkdir(parents=True)
        registry = ContainerLaunchRegistry(paths['host']/'launches.sqlite3', create=False)
        registry.register(ContainerLaunch(launch_id='processing-p00-g1', role='processor', worker_id='p00', wave_id=None, launch_generation=1,
            container_name=None, image_digest=None, owned_root=str(root), launcher='native'))
        registry.close()
        with pytest.raises(ValueError, match='ACT_CONTAINER_CLEANUP_NOT_CONFIRMED'):
            workload.finish(context, cleanup_confirmed=True)
        assert workload.slot_registry.slots() == (processor_slot(slot), slot)
    finally:
        store.close()
