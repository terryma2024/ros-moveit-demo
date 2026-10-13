"""Persistent logical Worker resources; session/socket instances live elsewhere."""

import contextlib
from dataclasses import asdict, dataclass
import json
import re


@dataclass(frozen=True)
class ActWorkerSlot:
    """One logical worker of one campaign generation.

    A slot names an instance, not a ROS graph: every instance runs at the fixed identity of
    `so101_demo.runtime.act_instance.identity` and the container is its isolation, so a slot carries no domain,
    namespace or controller name that could collide."""

    campaign_id: str
    worker_id: str
    execution_generation: int

    def __post_init__(self):
        if (type(self.campaign_id) is not str
                or re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', self.campaign_id) is None
                or type(self.worker_id) is not str or re.fullmatch(r'w[0-9]{2}', self.worker_id) is None
                or type(self.execution_generation) is not int or self.execution_generation < 0):
            raise ValueError('WORKER_SLOT_INVALID')


def _canonical(slot):
    return json.dumps(asdict(slot), sort_keys=True, separators=(',', ':'), allow_nan=False)


class ActWorkerSlotRegistry:
    def __init__(self, store, *, child_registry=None):
        self.store, self.child_registry = store, child_registry

    def slots(self, *, active=True):
        if type(active) is not bool:
            raise ValueError('WORKER_SLOT_INVALID')
        with self.store._thread_lock:
            rows = self.store._query_all('SELECT slot_json FROM act_worker_slots WHERE active=? '
                                        'ORDER BY campaign_id, execution_generation, worker_id', (int(active),))
            return tuple(ActWorkerSlot(**json.loads(row['slot_json'])) for row in rows)

    def validate(self, slots):
        if type(slots) is not tuple or not slots or any(type(slot) is not ActWorkerSlot for slot in slots):
            raise ValueError('WORKER_SLOT_INVALID')
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
    def reserve_many(self, slots):
        # Commit the complete logical reservation before any GPU lease or spawn.
        # Holding this store's lock across admission prevents resource races.
        with self.store._thread_lock:
            with self.store.immediate_transaction():
                self.validate(slots)
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
