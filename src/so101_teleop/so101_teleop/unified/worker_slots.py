"""Persistent logical Worker resources; session/socket instances live elsewhere."""

import contextlib
from dataclasses import asdict, dataclass
import fcntl
import json
import os
from pathlib import Path
import re

#: How an instance of a slot runs; only `native` has no isolation and so needs the host to itself.
LAUNCHERS = ('container', 'native')


@dataclass(frozen=True)
class ActWorkerSlot:
    """One logical worker of one campaign generation.

    A slot names an instance, not a ROS graph: every instance runs at the fixed identity of
    `so101_demo.runtime.act_instance.identity` and the container is its isolation, so a slot carries no domain,
    namespace or controller name that could collide.

    `wNN` is a collection shard. `pNN` is a phase-2 processor of the same campaign generation: it is admitted like a shard slot
    (reserved before launch, released with the campaign) and is not counted among the campaign's workers."""

    campaign_id: str
    worker_id: str
    execution_generation: int

    @property
    def is_processor(self):
        return self.worker_id.startswith('p')

    def __post_init__(self):
        if (type(self.campaign_id) is not str
                or re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', self.campaign_id) is None
                or type(self.worker_id) is not str or re.fullmatch(r'[wp][0-9]{2}', self.worker_id) is None
                or type(self.execution_generation) is not int or self.execution_generation < 0):
            raise ValueError('WORKER_SLOT_INVALID')


#: The ROS domain a native ACT instance runs on; the native batch worker uses the same one.
NATIVE_INSTANCE_ROS_DOMAIN_ID = 181


def batch_domain_claim_held(claim_root, domain_id=NATIVE_INSTANCE_ROS_DOMAIN_ID) -> bool:
    """True while a native batch (`so101_parallel_batch`) holds its flock on the claim file of ``domain_id``.

    A hand-launched batch worker runs on the same fixed domain as a native instance and is invisible to the ACT
    tables. The batch allocator takes ``LOCK_EX`` on ``domain-<id>.lock`` for the life of the batch and the kernel drops
    it when the process dies, so asking for the lock is exact: a stale file nobody holds reads as free. A claim
    directory or file that cannot be inspected fails closed.
    """
    path = Path(claim_root) / f'domain-{int(domain_id)}.lock'
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        except OSError:
            return True
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        return False
    finally:
        os.close(descriptor)


def default_batch_domain_claim_probe():
    """The installed probe: the batch allocator's own claim root for the current host."""
    from so101_demo.parallel_batch.resource_allocation.models import runtime_ipc_base

    return batch_domain_claim_held(runtime_ipc_base() / 'so101-parallel-domain-claims')


def _canonical(slot):
    return json.dumps(asdict(slot), sort_keys=True, separators=(',', ':'), allow_nan=False)


class ActWorkerSlotRegistry:
    def __init__(self, store, *, child_registry=None, batch_domain_claim_probe=None):
        self.store, self.child_registry = store, child_registry
        #: Callable returning True while a native batch worker holds the fixed ROS domain; None means "not asked".
        self.batch_domain_claim_probe = batch_domain_claim_probe

    def slots(self, *, active=True):
        if type(active) is not bool:
            raise ValueError('WORKER_SLOT_INVALID')
        with self.store._thread_lock:
            rows = self.store._query_all('SELECT slot_json FROM act_worker_slots WHERE active=? '
                                        'ORDER BY campaign_id, execution_generation, worker_id', (int(active),))
            return tuple(ActWorkerSlot(**json.loads(row['slot_json'])) for row in rows)

    def native_campaign_ids(self):
        """Campaign ids that are admitted with the native instance launcher (their admitted payload says so)."""
        with self.store._thread_lock:
            rows = self.store._query_all('SELECT c.campaign_id AS campaign_id, p.payload_json AS payload '
                'FROM act_campaign_contexts c JOIN parents p ON p.operation_id = c.operation_id')
        native = set()
        for row in rows:
            try:
                if json.loads(row['payload']).get('instance_launcher') == 'native':
                    native.add(row['campaign_id'])
            except (TypeError, ValueError, AttributeError):
                continue
        return native

    def _require_launcher_exclusivity(self, slots, launcher):
        """A native instance has no isolation and shares the fixed ROS domain with nothing else on the host.

        A native instance therefore needs a host with no other ACT instance and no native pick-place child; and while one is
        admitted no container instance may start either. Only the ACT tables are read."""
        if launcher not in LAUNCHERS:
            raise ValueError('WORKER_SLOT_INVALID')
        active = self.slots()
        if launcher == 'native':
            if len(slots) != 1:
                raise ValueError('NATIVE_INSTANCE_SINGLE_WORKER_ONLY')
            if active or (self.child_registry is not None and self.child_registry.launches()):
                raise ValueError('NATIVE_INSTANCE_EXCLUSIVE')
            if self.batch_domain_claim_probe is not None and self.batch_domain_claim_probe():
                raise ValueError('NATIVE_INSTANCE_BATCH_DOMAIN_CLAIMED')
        elif active and {slot.campaign_id for slot in active} & self.native_campaign_ids():
            raise ValueError('NATIVE_INSTANCE_EXCLUSIVE')

    def validate(self, slots, *, launcher='container'):
        if type(slots) is not tuple or not slots or any(type(slot) is not ActWorkerSlot for slot in slots):
            raise ValueError('WORKER_SLOT_INVALID')
        self._require_launcher_exclusivity(slots, launcher)
        existing = list(self.slots())
        if self.child_registry is not None:
            existing.extend(self.child_registry.launches())
        for slot in slots:
            for previous in existing:
                if (previous.campaign_id, previous.worker_id, previous.execution_generation) == (
                        slot.campaign_id, slot.worker_id, slot.execution_generation):
                    raise ValueError('DUPLICATE_WORKER_SLOT')
            existing.append(slot)

    @contextlib.contextmanager
    def reserve_many(self, slots, *, launcher='container'):
        # Commit the complete logical reservation before any GPU lease or spawn.
        # Holding this store's lock across admission prevents resource races.
        with self.store._thread_lock:
            with self.store.immediate_transaction():
                self.validate(slots, launcher=launcher)
                for slot in slots:
                    self.store._connection.execute('INSERT INTO act_worker_slots VALUES (?,?,?,?,1)',
                        (slot.campaign_id, slot.worker_id, slot.execution_generation, _canonical(slot)))
            try:
                yield
            except BaseException:
                with self.store.immediate_transaction():
                    for slot in slots:
                        self.store._connection.execute('DELETE FROM act_worker_slots WHERE campaign_id=? '
                            'AND worker_id=? AND execution_generation=? AND slot_json=? AND active=1',
                            (slot.campaign_id,slot.worker_id,slot.execution_generation,_canonical(slot)))
                raise

    def release_many_locked(self, slots):
        if not self.store._connection.in_transaction:
            raise ValueError('SLOT_RELEASE_REQUIRES_TRANSACTION')
        active = self.slots()
        if (type(slots) is not tuple or not slots or len(set(slots)) != len(slots)
                or any(slot not in active for slot in slots)):
            raise ValueError('SLOT_RELEASE_MISMATCH')
        for slot in slots:
            self.store._connection.execute('UPDATE act_worker_slots SET active=0 WHERE campaign_id=? '
                'AND worker_id=? AND execution_generation=? AND slot_json=? AND active=1',
                (slot.campaign_id,slot.worker_id,slot.execution_generation,_canonical(slot)))
