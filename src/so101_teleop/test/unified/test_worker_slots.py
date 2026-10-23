"""Logical slot reservations persist without inventing session/socket launches."""

from dataclasses import asdict, replace
import importlib

import pytest

from so101_teleop.unified.intent_store import IntentStore


def slot(worker='w00', campaign='campaign', generation=1):
    mod = importlib.import_module('so101_teleop.unified.worker_slots')
    return mod.ActWorkerSlot(campaign_id=campaign, worker_id=worker, execution_generation=generation)


def test_persistent_slots_are_logical_and_exact_release_is_atomic(tmp_path):
    mod = importlib.import_module('so101_teleop.unified.worker_slots')
    store = IntentStore.open(tmp_path/'state')
    slots = (slot(), slot('w01'))
    try:
        registry = mod.ActWorkerSlotRegistry(store)
        with registry.reserve_many(slots):
            assert registry.slots() == slots
        assert not {'socket_root','mujoco_session_id'} & set(asdict(slots[0]))
        with pytest.raises(ValueError, match='SLOT_RELEASE_REQUIRES_TRANSACTION'):
            registry.release_many_locked(slots)
        with pytest.raises(ValueError, match='SLOT_RELEASE_MISMATCH'):
            with store.immediate_transaction():
                registry.release_many_locked((replace(slots[0], worker_id='w05'),slots[1]))
        assert registry.slots() == slots
        with store.immediate_transaction():
            registry.release_many_locked(slots)
        assert registry.slots() == ()
        assert registry.slots(active=False) == slots
    finally:
        store.close()


def test_reservation_failure_rolls_back_only_new_batch(tmp_path):
    mod = importlib.import_module('so101_teleop.unified.worker_slots')
    store = IntentStore.open(tmp_path/'state')
    try:
        registry = mod.ActWorkerSlotRegistry(store)
        original = slot()
        with registry.reserve_many((original,)):
            pass
        with pytest.raises(RuntimeError):
            with registry.reserve_many((slot('w01'),)):
                raise RuntimeError('admission rejected before context')
        assert registry.slots() == (original,)
        with pytest.raises(ValueError, match='DUPLICATE_WORKER_SLOT'):
            with registry.reserve_many((slot('w00'),)):
                pytest.fail('duplicate slot reserved')
    finally:
        store.close()


def test_old_owner_slots_reopen_as_fences_without_takeover(tmp_path):
    mod = importlib.import_module('so101_teleop.unified.worker_slots')
    store = IntentStore.open(tmp_path/'state')
    original = slot()
    with mod.ActWorkerSlotRegistry(store).reserve_many((original,)):
        pass
    store.close()
    store = IntentStore.open(tmp_path/'state')
    try:
        assert mod.ActWorkerSlotRegistry(store).slots() == (original,)
    finally:
        store.close()


@pytest.mark.parametrize('problem', ['worker','generation','campaign'])
def test_slots_refuse_malformed_identity_fields(problem):
    original = slot()
    changes = {'worker':{'worker_id':'worker'}, 'generation':{'execution_generation':True},
               'campaign':{'campaign_id':'../x'}}
    with pytest.raises(ValueError, match='WORKER_SLOT_INVALID'):
        replace(original,**changes[problem])


@pytest.mark.parametrize('extra', [{'ros_domain_id':181}, {'namespace':'/act/w00'}, {'controller_name':'/act/w00/arm_controller'}])
def test_a_slot_carries_no_ros_domain_namespace_or_controller(extra):
    mod = importlib.import_module('so101_teleop.unified.worker_slots')
    assert set(mod.ActWorkerSlot.__dataclass_fields__) == {'campaign_id','worker_id','execution_generation'}
    with pytest.raises(TypeError):
        mod.ActWorkerSlot(campaign_id='campaign', worker_id='w00', execution_generation=1, **extra)


def test_all_eight_slots_of_one_campaign_are_active_together(tmp_path):
    """One fixed identity means no per-slot resource to collide on: only the (campaign, worker, generation) key."""
    mod = importlib.import_module('so101_teleop.unified.worker_slots')
    store = IntentStore.open(tmp_path/'state')
    slots = tuple(slot(f'w{index:02d}') for index in range(8))
    try:
        registry = mod.ActWorkerSlotRegistry(store)
        with registry.reserve_many(slots):
            assert registry.slots() == slots
            with pytest.raises(ValueError, match='DUPLICATE_WORKER_SLOT'):
                with registry.reserve_many((slots[3],)):
                    pytest.fail('duplicate slot reserved')
            with registry.reserve_many((slot('w00', campaign='second'),)):    # another campaign, same worker id
                assert len(registry.slots()) == 9
    finally:
        store.close()
