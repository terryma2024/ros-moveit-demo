"""ACT admission composes on the existing unified store with physical GPU identity."""

from __future__ import annotations

import os
from types import SimpleNamespace

from so101_teleop.unified.compose import compose_domain_services, resolve_visible_physical_uuids


def configured():
    return {"SO101_ACT_GPU_SELECTOR": "INDEX:0",
            "SO101_ACT_RESOURCE_BINDING_ID": "binding-1",
            "SO101_UNIFIED_SERVICE_EPOCH": "epoch-1",
            "SO101_UNIFIED_RUNTIME_ID": "runtime-1"}


def test_act_composition_uses_same_store_and_kernel_owner(tmp_path):
    services = compose_domain_services(
        environment=configured(), evidence_root=tmp_path,
        act_inventory=lambda: ("GPU-physical-a",),
        act_host_id=lambda: "host-1",
        act_owner_identity=lambda: (os.getpid(), 123),
    )
    assert services.act_workload is not None
    assert services.act_workload.arbiter is services.arbiter
    assert services.act_workload.gpu_arbiter.store is services.store
    assert services.act_workload.owner_pid == os.getpid()
    assert services.act_workload.owner_started_ticks == 123
    assert services.act_workload.visible_physical_uuids == ("GPU-physical-a",)


def test_missing_or_ambiguous_act_mapping_never_exposes_admission(tmp_path):
    absent = compose_domain_services(environment={}, evidence_root=tmp_path / "absent")
    assert absent.act_workload is None
    ambiguous = compose_domain_services(
        environment=configured(), evidence_root=tmp_path / "ambiguous",
        act_inventory=lambda: ("GPU-physical-a", "GPU-physical-a"),
        act_host_id=lambda: "host-1",
        act_owner_identity=lambda: (os.getpid(), 123),
    )
    assert ambiguous.act_workload is None
    assert "GPU_SELECTOR_AMBIGUOUS" in ambiguous.act_error


def test_visible_index_mapping_preserves_cuda_order_and_rejects_mismatch():
    devices = (SimpleNamespace(index=0, uuid="GPU-a"),
               SimpleNamespace(index=1, uuid="GPU-b"))
    assert resolve_visible_physical_uuids(devices, {"CUDA_VISIBLE_DEVICES": "1,0"}) == (
        "GPU-b", "GPU-a")
    try:
        resolve_visible_physical_uuids(devices, {"CUDA_VISIBLE_DEVICES": "1",
                                                 "NVIDIA_VISIBLE_DEVICES": "0"})
    except ValueError as error:
        assert "GPU_MAPPING_AMBIGUOUS" in str(error)
    else:
        raise AssertionError("conflicting GPU visibility must fail closed")
