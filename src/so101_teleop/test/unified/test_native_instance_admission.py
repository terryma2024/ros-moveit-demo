"""Admission of a native ACT instance: one worker, alone on the host, and nothing else may start beside it.

A native instance has no isolation: it shares the Host's loopback and shared memory on the fixed ROS domain with anything
else on that domain. Admission therefore refuses a native instance unless it is the only ACT instance (container slot or
native pick-place child) on the host, and refuses every container instance while one is admitted. Real: admission, the SQLite
store, the slot registry and the closed payload schema. Controlled: the campaign files and the GPU inventory (the container
collection fixtures).
"""

from dataclasses import asdict, replace

import pytest

from test_container_collection_admission import assert_nothing_acquired, fixture, terminated_services
from so101_teleop.unified.bridge import ActChildLaunch
from so101_teleop.unified.worker_slots import ActWorkerSlot


def native(spec):
    return replace(spec, payload=dict(spec.payload, instance_launcher='native'))


def second(spec, *, campaign='campaign-2', launcher):
    """A second collection start for the next execution generation."""
    generation = spec.execution_generation + 1
    slot = ActWorkerSlot(campaign_id=campaign, worker_id='w00', execution_generation=generation)
    return replace(spec, command_id='collection-'+campaign, execution_generation=generation,
        payload=dict(spec.payload, campaign_id=campaign, worker_slots=[asdict(slot)], instance_launcher=launcher))


def test_a_native_single_worker_is_admitted_and_recorded_as_native(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(native(spec), allow_existing=False)
        assert context.worker_count == 1 and workload.slot_registry.slots() == (slot,)
        assert workload.slot_registry.native_campaign_ids() == {slot.campaign_id}
        assert store._query_one('SELECT * FROM gpu_workload_leases') is not None
    finally:
        store.close()


def test_a_container_campaign_is_not_recorded_as_native(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        workload.start(spec, allow_existing=False)
        assert workload.slot_registry.native_campaign_ids() == set()
    finally:
        store.close()


@pytest.mark.parametrize('payload_edit', ['missing', 'unknown'])
def test_the_launcher_is_a_closed_required_payload_field(tmp_path, payload_edit):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        payload = dict(spec.payload)
        if payload_edit == 'missing':
            del payload['instance_launcher']
            expected = 'CAMPAIGN_START_SCHEMA'
        else:
            payload['instance_launcher'] = 'docker'
            expected = 'INSTANCE_LAUNCHER_INVALID'
        with pytest.raises(ValueError, match=expected):
            workload.start(replace(spec, payload=payload), allow_existing=False)
        assert_nothing_acquired(workload, store)
    finally:
        store.close()


def test_a_native_instance_with_two_workers_is_refused_before_any_resource(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        slots = [asdict(replace(slot, worker_id=f'w{index:02d}')) for index in range(2)]
        payload = dict(spec.payload, worker_count=2, worker_slots=slots, instance_launcher='native')
        with pytest.raises(ValueError, match='NATIVE_INSTANCE_SINGLE_WORKER_ONLY'):
            workload.start(replace(spec, payload=payload), allow_existing=False)
        assert_nothing_acquired(workload, store)
        # the same two workers are not refused for the launcher: the container rules apply to them as before
        container = dict(payload, instance_launcher='container')
        with pytest.raises(ValueError) as refused:
            workload.start(replace(spec, payload=container), allow_existing=False)
        assert 'NATIVE_INSTANCE' not in str(refused.value)
    finally:
        store.close()


def test_the_slot_registry_itself_refuses_a_native_batch_of_two(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        slots = (slot, replace(slot, worker_id='w01'))
        with pytest.raises(ValueError, match='NATIVE_INSTANCE_SINGLE_WORKER_ONLY'):
            workload.slot_registry.validate(slots, launcher='native')
        workload.slot_registry.validate(slots, launcher='container')
        with pytest.raises(ValueError, match='WORKER_SLOT_INVALID'):
            workload.slot_registry.validate((slot,), launcher='remote')
    finally:
        store.close()


def test_a_second_native_instance_is_refused_while_one_is_admitted(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        workload.start(native(spec), allow_existing=False)
        with pytest.raises(ValueError, match='NATIVE_INSTANCE_EXCLUSIVE'):
            workload.start(second(spec, launcher='native'), allow_existing=False)
        assert workload.slot_registry.slots() == (slot,)
    finally:
        store.close()


def test_a_container_instance_is_refused_while_a_native_instance_is_admitted(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        workload.start(native(spec), allow_existing=False)
        with pytest.raises(ValueError, match='NATIVE_INSTANCE_EXCLUSIVE'):
            workload.start(second(spec, launcher='container'), allow_existing=False)
        assert workload.slot_registry.slots() == (slot,)
    finally:
        store.close()


def test_a_native_instance_is_refused_while_a_container_slot_is_active(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        workload.start(spec, allow_existing=False)
        with pytest.raises(ValueError, match='NATIVE_INSTANCE_EXCLUSIVE'):
            workload.start(second(spec, launcher='native'), allow_existing=False)
        assert workload.slot_registry.slots() == (slot,)
    finally:
        store.close()


def test_a_native_instance_is_refused_while_a_native_pick_place_child_holds_the_domain(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        child = ActChildLaunch(campaign_id='pick-place', worker_id='w00', execution_generation=7, ros_domain_id=181,
            namespace='/pick', controller_name='pick/arm_controller', mujoco_session_id='pick-session',
            socket_root='/tmp/so101-pick')
        with workload.child_registry.reserve_many((child,)):
            with pytest.raises(ValueError, match='NATIVE_INSTANCE_EXCLUSIVE'):
                workload.start(native(spec), allow_existing=False)
            assert workload.slot_registry.slots() == ()
            assert store._query_one('SELECT * FROM gpu_workload_leases') is None
    finally:
        store.close()


def test_a_native_instance_is_admitted_again_after_the_first_is_settled(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(native(spec), allow_existing=False)
        terminated_services(paths, inspect)
        workload.finish(context, cleanup_confirmed=True)
        assert workload.slot_registry.slots() == () and workload.slot_registry.native_campaign_ids() == {slot.campaign_id}
        # the settled campaign no longer holds the host
        assert workload.slot_registry.slots(active=False) == (slot,)
        again = workload.start(second(spec, launcher='native'), allow_existing=False)
        assert again.campaign_id == 'campaign-2' and len(workload.slot_registry.slots()) == 1
    finally:
        store.close()


def test_finish_does_not_settle_a_native_instance_whose_stop_is_unproven(tmp_path):
    from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(native(spec), allow_existing=False)
        terminated_services(paths, inspect)
        owned = paths['run']/'wave-0'/'w00'/'g1'
        owned.mkdir(parents=True)
        registry = ContainerLaunchRegistry(paths['host']/'launches.sqlite3', create=False)
        registry.register(ContainerLaunch(launch_id='wave-0-w00-g1', role='shard', worker_id='w00', wave_id='wave-0',
            launch_generation=1, container_name=None, image_digest=None, owned_root=str(owned),
            session_id='act-session-w00-g1', launcher='native'))
        registry.close()
        with pytest.raises(ValueError, match='ACT_CONTAINER_CLEANUP_NOT_CONFIRMED'):
            workload.finish(context, cleanup_confirmed=True)
        assert workload.slot_registry.slots() == (slot,)
        assert store._query_one('SELECT * FROM gpu_workload_leases') is not None
    finally:
        store.close()
