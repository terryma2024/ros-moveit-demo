"""Composing exact W2: two slots, a resolved manifest, and a host that can honour the claim.

Task 10 of the macOS MPS / private IPC plan. The composition has to satisfy three things at once:
v3 must still load and behave exactly as before, v4 must be reachable on the host that can run it,
and an exact-W2 campaign must always present two slots even when it has one point.
"""

import sys
from pathlib import Path

import pytest
import yaml

from so101_demo.parallel_batch.contracts import (
    AcceleratorKind,
    ContractError,
    IpcTransport,
    ParallelRuntimeConfigV3,
    ParallelRuntimeConfigV4,
)
from so101_demo.parallel_batch.w2_composition import (
    EXACT_W2_WORKERS,
    CompositionError,
    W2CampaignPlan,
    assert_no_host_platform_calls,
    compose_w2_campaign,
    exact_w2_slots,
    load_execution_config,
    load_execution_config_for_schema,
)

PACKAGE = Path(__file__).resolve().parents[1]
V3_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v3.yaml"
V4_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v4_macos_mps_w2.yaml"
V1_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v1.yaml"


# --------------------------------------------------------------------------------------
# the loader keeps v3 intact and adds v4
# --------------------------------------------------------------------------------------


def test_v3_still_loads_through_the_widened_loader():
    """Widening the gate for v4 must not change the v3 result at all."""

    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v3

    through_new = load_execution_config(V3_CONFIG)
    through_old = load_parallel_runtime_config_v3(V3_CONFIG)
    assert isinstance(through_new, ParallelRuntimeConfigV3)
    assert through_new == through_old


def test_v4_loads_and_v1_v2_are_still_refused_for_execution(tmp_path):
    """New execution accepts v3 and v4 only."""

    loaded = load_execution_config(V4_CONFIG)
    assert isinstance(loaded, ParallelRuntimeConfigV4)
    assert loaded.schema_version == 4
    for legacy in (V1_CONFIG, PACKAGE / "config/mujoco/parallel_batch_v2.yaml"):
        with pytest.raises(ContractError, match="CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION"):
            load_execution_config(legacy)

    unknown = tmp_path / "v9.yaml"
    unknown.write_text(yaml.safe_dump({"schema_version": 9}))
    with pytest.raises(ContractError, match="CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION"):
        load_execution_config(unknown)


def test_the_mps_combination_is_refused_on_a_host_that_cannot_run_it():
    """A Darwin v4 document on a non-Darwin host is a refusal, not a silent CPU attempt."""

    assert isinstance(load_execution_config_for_schema(V4_CONFIG, platform="darwin"),
                      ParallelRuntimeConfigV4)
    with pytest.raises(CompositionError, match="PLATFORM_HOST_MISMATCH"):
        load_execution_config_for_schema(V4_CONFIG, platform="linux")


def test_the_linux_combination_is_refused_on_darwin(tmp_path):
    """The retained Linux v4 combination is loadable but not executable here."""

    document = yaml.safe_load(V4_CONFIG.read_text())
    document["accelerator"] = {"kind": "cuda", "selector": "INDEX:0"}
    document["requested_device"] = "cuda"
    document["ipc_transport"] = "proc_fd_unix"
    document["mujoco_gl"] = "egl"
    document["mps_process_memory_fraction"] = None
    document["start_guard"].pop("mps_minimum_headroom_bytes")
    path = tmp_path / "v4-linux.yaml"
    path.write_text(yaml.safe_dump(document))

    loaded = load_execution_config(path)
    assert isinstance(loaded, ParallelRuntimeConfigV4)
    assert loaded.accelerator.kind is AcceleratorKind.CUDA
    with pytest.raises(CompositionError, match="PLATFORM_HOST_MISMATCH"):
        load_execution_config_for_schema(path, platform="darwin")
    assert isinstance(load_execution_config_for_schema(path, platform="linux"),
                      ParallelRuntimeConfigV4)


def test_a_v3_document_is_host_agnostic():
    """The v3 path never consults the host, so its behaviour is unchanged everywhere."""

    for host in ("darwin", "linux", "win32"):
        assert isinstance(load_execution_config_for_schema(V3_CONFIG, platform=host),
                          ParallelRuntimeConfigV3)


# --------------------------------------------------------------------------------------
# exact W2 slots
# --------------------------------------------------------------------------------------


def test_two_slots_exist_even_for_a_single_point():
    """Exact W2 means two slots; a short campaign leaves a slot idle, it does not become W1."""

    slots = exact_w2_slots(("p1",))
    assert slots.slot_ids == ("slot-0", "slot-1")
    assert slots.assigned_points == (("slot-0", "p1"), ("slot-1", None))
    assert slots.idle_slots == ("slot-1",)
    assert len(slots.slot_ids) == EXACT_W2_WORKERS


def test_two_slots_are_filled_in_order_for_a_longer_campaign():
    slots = exact_w2_slots(("p1", "p2", "p3"))
    assert slots.assigned_points == (("slot-0", "p1"), ("slot-1", "p2"))
    assert slots.idle_slots == ()
    assert slots.to_document()["slot_ids"] == ["slot-0", "slot-1"]


def test_no_points_at_all_still_yields_two_idle_slots():
    slots = exact_w2_slots(())
    assert slots.idle_slots == ("slot-0", "slot-1")


# --------------------------------------------------------------------------------------
# the resolved plan
# --------------------------------------------------------------------------------------


def _darwin_plan(tmp_path, **overrides):
    config = load_execution_config(V4_CONFIG)
    arguments = {
        "config": config,
        "config_path": V4_CONFIG,
        "campaign_id": "b-campaign-1",
        "batch_id": "batch-1",
        "selected_point_ids": ("p1", "p2"),
        "evidence_root": tmp_path,
        "broker_pid": 4242,
        "broker_birth_identity": 99,
    }
    arguments.update(overrides)
    return compose_w2_campaign(**arguments)


def test_the_plan_resolves_every_platform_value(tmp_path):
    """The manifest records resolved values: no `auto`, and the real platform combination."""

    plan = _darwin_plan(tmp_path)
    assert isinstance(plan, W2CampaignPlan)
    document = plan.to_document()
    assert document["schema_version"] == 4
    assert document["accelerator"] == "mps"
    assert document["accelerator_selector"] == "default"
    assert document["requested_device"] == "mps"
    assert document["allow_cpu_fallback"] is False
    assert document["ipc_transport"] == "darwin_private_path_unix"
    assert document["mujoco_gl"] == "cgl"
    assert document["worker_count"] == 2
    assert "auto" not in set(str(value) for value in document.values())
    assert document["mps_process_memory_fraction"] == 0.8
    assert document["mps_minimum_headroom_bytes"] == 1 << 30
    assert document["max_input_snapshot_bytes"] == 64 * 1024 * 1024
    assert document["broker_max_frame_bytes"] == 8388608
    assert document["start_guard_timeout_s"] == 2.0
    assert document["ros_domain_ids"] == [181, 182]


def test_the_manifest_records_identity_provenance_and_paths(tmp_path):
    """Broker identity, model provenance, snapshot root and supervisor receipt are all present."""

    plan = _darwin_plan(tmp_path)
    document = plan.to_document()
    assert document["broker_pid"] == 4242
    assert document["broker_birth_identity"] == 99
    provenance = document["model_provenance"]
    assert provenance["yolo_model_id"] == "plastic-cup-yolo11n-seg-v1"
    assert len(provenance["yolo_weights_sha256"]) == 64
    assert len(provenance["grounded_sam_manifest_sha256"]) == 64
    assert provenance["yolo_imgsz"] == 640
    assert document["snapshot_root"] == str(tmp_path / "inference-inputs")
    assert document["supervisor_receipt_path"] == str(
        tmp_path / "supervisor" / "owner-receipt.json")
    assert document["config_sha256"] == plan.config_sha256
    assert len(plan.config_sha256) == 64


def test_the_plan_carries_both_slots_and_their_assignments(tmp_path):
    plan = _darwin_plan(tmp_path, selected_point_ids=("p1",))
    document = plan.to_document()
    assert document["slots"]["slot_ids"] == ["slot-0", "slot-1"]
    assert document["slots"]["idle_slots"] == ["slot-1"]
    assert document["slots"]["assigned_points"] == [
        {"slot_id": "slot-0", "point_id": "p1"},
        {"slot_id": "slot-1", "point_id": None},
    ]


def test_the_plan_refuses_a_worker_count_that_is_not_two(tmp_path):
    """A fourth platform claim cannot be composed from the exact-W2 helper."""

    config = load_execution_config(V4_CONFIG)
    object.__setattr__(config, "worker_count", 4)
    with pytest.raises(CompositionError, match="PLATFORM_WORKER_COUNT_UNSUPPORTED"):
        compose_w2_campaign(config=config, config_path=V4_CONFIG, campaign_id="b",
                            batch_id="batch", selected_point_ids=("p1",),
                            evidence_root=tmp_path)
    assert EXACT_W2_WORKERS == 2


def test_the_plan_refuses_a_relative_evidence_root(tmp_path):
    config = load_execution_config(V4_CONFIG)
    with pytest.raises(CompositionError, match="EVIDENCE_ROOT"):
        compose_w2_campaign(config=config, config_path=V4_CONFIG, campaign_id="b",
                            batch_id="batch", selected_point_ids=("p1",),
                            evidence_root=Path("relative/root"))


def test_the_plan_refuses_a_missing_campaign_id(tmp_path):
    config = load_execution_config(V4_CONFIG)
    with pytest.raises(CompositionError, match="CAMPAIGN_ID"):
        compose_w2_campaign(config=config, config_path=V4_CONFIG, campaign_id="",
                            batch_id="batch", selected_point_ids=("p1",),
                            evidence_root=tmp_path)


def test_a_v3_plan_resolves_the_linux_combination(tmp_path):
    """v3 composes to the frozen Linux combination, with no MPS field anywhere."""

    plan = _darwin_plan(tmp_path, config=load_execution_config(V3_CONFIG),
                        config_path=V3_CONFIG)
    document = plan.to_document()
    assert document["schema_version"] == 3
    assert document["accelerator"] == "cuda"
    assert document["accelerator_selector"] == "INDEX:0"
    assert document["ipc_transport"] == str(IpcTransport.PROC_FD_UNIX)
    assert document["mujoco_gl"] == "egl"
    assert document["worker_count"] == 2
    assert document["mps_minimum_headroom_bytes"] is None
    assert document["mps_process_memory_fraction"] is None


# --------------------------------------------------------------------------------------
# platform-boundary assertions
# --------------------------------------------------------------------------------------


def test_the_darwin_plan_never_claims_an_nvml_or_proc_fd_dependency(tmp_path):
    """The host-boundary check accepts the real Darwin plan."""

    assert_no_host_platform_calls(_darwin_plan(tmp_path))


def test_the_platform_boundary_check_rejects_a_mixed_plan(tmp_path):
    """A plan mixing MPS with the Linux transport (or the reverse) is refused."""

    plan = _darwin_plan(tmp_path)
    import dataclasses

    mixed = dataclasses.replace(plan, ipc_transport=str(IpcTransport.PROC_FD_UNIX))
    with pytest.raises(CompositionError, match="PLATFORM_COMBINATION"):
        assert_no_host_platform_calls(mixed)

    mixed = dataclasses.replace(plan, mujoco_gl="egl")
    with pytest.raises(CompositionError, match="PLATFORM_COMBINATION"):
        assert_no_host_platform_calls(mixed)

    mixed = dataclasses.replace(plan, mps_minimum_headroom_bytes=None)
    with pytest.raises(CompositionError, match="PLATFORM_COMBINATION"):
        assert_no_host_platform_calls(mixed)


def test_the_plan_is_json_serializable_for_the_manifest(tmp_path):
    """A manifest projection must survive JSON, which is how it is written to disk."""

    import json

    document = _darwin_plan(tmp_path).to_document()
    encoded = json.dumps(document, sort_keys=True)
    assert json.loads(encoded)["worker_count"] == 2


def test_the_host_this_gate_runs_on_matches_the_documented_platform():
    """On this Mac the Darwin document must be the executable one."""

    if sys.platform == "darwin":
        assert isinstance(load_execution_config_for_schema(V4_CONFIG),
                          ParallelRuntimeConfigV4)
    else:
        pytest.skip("this assertion is about the Darwin host this task runs on")
