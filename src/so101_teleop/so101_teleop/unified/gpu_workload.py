"""Durable physical-GPU ownership for admitted ACT campaigns.

Only the campaign owner calls this arbiter. Workers receive a frozen environment and do
not read the lease or resolve GPU selectors while running.
"""

from __future__ import annotations

from dataclasses import astuple, dataclass
from typing import Callable, Sequence

from .intent_store import IntentStore


def resolve_physical_gpu(selector: str, visible_physical_uuids: Sequence[str]) -> str:
    """Resolve a configured selector against one unambiguous physical inventory."""
    visible = tuple(visible_physical_uuids)
    if not visible or any(not isinstance(item, str) or not item.startswith("GPU-") for item in visible):
        raise ValueError("GPU_INVENTORY_INVALID")
    if len(set(visible)) != len(visible):
        raise ValueError("GPU_SELECTOR_AMBIGUOUS")
    if selector.startswith("INDEX:"):
        index_text = selector.removeprefix("INDEX:")
        if not index_text.isdecimal() or str(int(index_text)) != index_text:
            raise ValueError("GPU_SELECTOR_INVALID")
        index = int(index_text)
        if index >= len(visible):
            raise ValueError("GPU_SELECTOR_UNKNOWN")
        return visible[index]
    if selector.startswith("UUID:"):
        uuid = selector.removeprefix("UUID:")
        if uuid not in visible:
            raise ValueError("GPU_SELECTOR_UNKNOWN")
        return uuid
    raise ValueError("GPU_SELECTOR_INVALID")


@dataclass(frozen=True)
class GpuLeaseRequest:
    stable_host_id: str
    physical_gpu_uuid: str
    operation_id: str
    service_epoch: str
    owner_pid: int
    owner_started_ticks: int
    workload: str
    execution_generation: int
    deadline_ns: int

    def __post_init__(self) -> None:
        for name in ("stable_host_id", "physical_gpu_uuid", "operation_id", "service_epoch", "workload"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"GPU_LEASE_IDENTITY_INVALID: {name}")
        if not self.physical_gpu_uuid.startswith("GPU-"):
            raise ValueError("GPU_PHYSICAL_UUID_INVALID")
        for name in ("owner_pid", "owner_started_ticks", "deadline_ns"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"GPU_LEASE_VALUE_INVALID: {name}")
        if type(self.execution_generation) is not int or self.execution_generation < 0:
            raise ValueError("GPU_LEASE_GENERATION_INVALID")


class ActGpuWorkloadArbiter:
    def __init__(self, store: IntentStore, *, clock_ns: Callable[[], int]) -> None:
        self.store = store
        self.clock_ns = clock_ns

    @staticmethod
    def _owner_matches(row, request: GpuLeaseRequest) -> bool:
        return tuple(row) == astuple(request)

    def _row(self, request: GpuLeaseRequest):
        return self.store._query_one(
            "SELECT * FROM gpu_workload_leases WHERE stable_host_id=? AND physical_gpu_uuid=?",
            (request.stable_host_id, request.physical_gpu_uuid),
        )

    def acquire(self, request: GpuLeaseRequest) -> GpuLeaseRequest:
        if request.deadline_ns <= self.clock_ns():
            raise ValueError("GPU_LEASE_DEADLINE_EXPIRED")
        with self.store.immediate_transaction():
            row = self._row(request)
            if row is not None:
                if self._owner_matches(row, request):
                    return request
                raise ValueError("GPU_WORKLOAD_BUSY")
            self.store._connection.execute(
                "INSERT INTO gpu_workload_leases VALUES (?,?,?,?,?,?,?,?,?)", astuple(request)
            )
        return request

    def renew(self, request: GpuLeaseRequest, *, new_deadline_ns: int) -> GpuLeaseRequest:
        with self.store.immediate_transaction():
            row = self._row(request)
            if row is None or not self._owner_matches(row, request):
                raise ValueError("GPU_LEASE_OWNER_MISMATCH")
            if request.deadline_ns <= self.clock_ns():
                raise ValueError("GPU_LEASE_EXPIRED")
            if type(new_deadline_ns) is not int or new_deadline_ns <= max(request.deadline_ns, self.clock_ns()):
                raise ValueError("GPU_LEASE_RENEWAL_INVALID")
            self.store._connection.execute(
                "UPDATE gpu_workload_leases SET deadline_ns=? WHERE stable_host_id=? AND physical_gpu_uuid=?",
                (new_deadline_ns, request.stable_host_id, request.physical_gpu_uuid),
            )
        return GpuLeaseRequest(*astuple(request)[:-1], new_deadline_ns)

    def release(self, request: GpuLeaseRequest) -> None:
        with self.store.immediate_transaction():
            row = self._row(request)
            if row is None or not self._owner_matches(row, request):
                raise ValueError("GPU_LEASE_OWNER_MISMATCH")
            self.store._connection.execute(
                "DELETE FROM gpu_workload_leases WHERE stable_host_id=? AND physical_gpu_uuid=?",
                (request.stable_host_id, request.physical_gpu_uuid),
            )
