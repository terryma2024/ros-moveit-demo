"""Logical slot reservations persist without inventing session/socket launches."""

from dataclasses import asdict, replace
import importlib

import pytest

from so101_teleop.unified.intent_store import IntentStore


def slot(worker='w00', domain=181, campaign='campaign'):
    mod = importlib.import_module('so101_teleop.unified.worker_slots')
    namespace = '/act/'+campaign+'/'+worker
    return mod.ActWorkerSlot(campaign_id=campaign, worker_id=worker, execution_generation=1,
                            ros_domain_id=domain, namespace=namespace,
                            controller_name=namespace+'/arm_controller')


def test_persistent_slots_are_logical_and_exact_release_is_atomic(tmp_path):
    mod = importlib.import_module('so101_teleop.unified.worker_slots')
    store = IntentStore.open(tmp_path/'state')
    slots = (slot(), slot('w01',182))
    try:
        registry = mod.ActWorkerSlotRegistry(store)
        with registry.reserve_many(slots):
            assert registry.slots() == slots
        assert not {'socket_root','mujoco_session_id'} & set(asdict(slots[0]))
        with pytest.raises(ValueError, match='SLOT_RELEASE_REQUIRES_TRANSACTION'):
            registry.release_many_locked(slots)
        with pytest.raises(ValueError, match='SLOT_RELEASE_MISMATCH'):
            with store.immediate_transaction():
                registry.release_many_locked((replace(slots[0], ros_domain_id=180),slots[1]))
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
            with registry.reserve_many((slot('w01',182),)):
                raise RuntimeError('admission rejected before context')
        assert registry.slots() == (original,)
        with pytest.raises(ValueError, match='ROS_DOMAIN_SHARED'):
            with registry.reserve_many((slot('w00',181,'foreign'),)):
                pytest.fail('colliding slot reserved')
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


@pytest.mark.parametrize('problem', ['namespace','controller','worker','generation','domain'])
def test_slots_refuse_unbound_resource_fields(problem):
    original = slot()
    changes = {'namespace':{'namespace':'/'}, 'controller':{'controller_name':'foreign'},
               'worker':{'worker_id':'worker'}, 'generation':{'execution_generation':True},
               'domain':{'ros_domain_id':True}}
    with pytest.raises(ValueError, match='WORKER_SLOT_INVALID'):
        replace(original,**changes[problem])
