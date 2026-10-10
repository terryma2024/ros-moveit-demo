"""The campaign owner has one durable lease for one physical GPU."""

from __future__ import annotations

import pytest

from so101_teleop.unified.gpu_workload import (
    ActGpuWorkloadArbiter,
    GpuLeaseRequest,
    resolve_physical_gpu,
)
from so101_teleop.unified.intent_store import IntentStore


def request(operation_id: str = "op-1", *, generation: int = 3, deadline_ns: int = 10_000) -> GpuLeaseRequest:
    return GpuLeaseRequest(
        stable_host_id="ai-station-1",
        physical_gpu_uuid="GPU-physical-a",
        operation_id=operation_id,
        service_epoch="epoch-1",
        owner_pid=111,
        owner_started_ticks=222,
        workload="act-task8",
        execution_generation=generation,
        deadline_ns=deadline_ns,
    )


def test_index_and_uuid_select_the_same_physical_gpu():
    visible = ("GPU-physical-a", "GPU-physical-b")
    assert resolve_physical_gpu("INDEX:1", visible) == "GPU-physical-b"
    assert resolve_physical_gpu("UUID:GPU-physical-b", visible) == "GPU-physical-b"
    with pytest.raises(ValueError, match="GPU_SELECTOR_AMBIGUOUS"):
        resolve_physical_gpu("INDEX:0", ("GPU-physical-a", "GPU-physical-a"))
    with pytest.raises(ValueError, match="GPU_SELECTOR_UNKNOWN"):
        resolve_physical_gpu("UUID:GPU-foreign", visible)


def test_lease_survives_service_restart_and_blocks_other_owner(tmp_path):
    root = tmp_path / "intents"
    store = IntentStore.open(root)
    first = ActGpuWorkloadArbiter(store, clock_ns=lambda: 1)
    lease = first.acquire(request())
    assert lease.physical_gpu_uuid == "GPU-physical-a"
    store.close()

    reopened = IntentStore.open(root)
    try:
        second = ActGpuWorkloadArbiter(reopened, clock_ns=lambda: 2)
        with pytest.raises(ValueError, match="GPU_WORKLOAD_BUSY"):
            second.acquire(request("op-2"))
        with pytest.raises(ValueError, match="GPU_LEASE_OWNER_MISMATCH"):
            second.release(request("op-2"))
        second.release(request())
        assert second.acquire(request("op-2")).operation_id == "op-2"
    finally:
        reopened.close()


def test_expired_lease_is_not_silently_reassigned(tmp_path):
    store = IntentStore.open(tmp_path / "intents")
    try:
        arbiter = ActGpuWorkloadArbiter(store, clock_ns=lambda: 1)
        arbiter.acquire(request())
        later = ActGpuWorkloadArbiter(store, clock_ns=lambda: 20_000)
        with pytest.raises(ValueError, match="GPU_WORKLOAD_BUSY"):
            later.acquire(request("op-2", deadline_ns=30_000))
        with pytest.raises(ValueError, match="GPU_LEASE_EXPIRED"):
            later.renew(request(), new_deadline_ns=30_000)
    finally:
        store.close()
