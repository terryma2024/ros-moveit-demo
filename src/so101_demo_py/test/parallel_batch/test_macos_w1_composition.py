"""Composing W1: one slot, one Worker, one ROS domain, one approved profile.

Task 7 of the macOS service campaign closure plan. W1 is not a capacity calculation and not a
shrunken W2: the two W1 profiles exist because the platform claim is exactly one Worker for one
named batch kind, so the composition must produce one slot regardless of how many points were
selected, and it must never invent a budget, qualification or promotion field.
"""

import json
from pathlib import Path

import pytest

from so101_demo.parallel_batch.contracts import (
    AcceleratorKind,
    ContractError,
    IpcTransport,
    ParallelRuntimeConfigMacosMpsTwoWorker,
    ParallelRuntimeConfigMacosMpsSingleWorkerRetry,
    ParallelRuntimeConfigMacosMpsSingleWorkerFirstPass,
)
from so101_demo.parallel_batch.two_worker_composition import (
    CompositionError,
    compose_two_worker_campaign,
    load_execution_config,
    load_execution_config_for_schema,
)
from so101_demo.parallel_batch.single_worker_composition import (
    EXACT_SINGLE_WORKERS,
    MPS_SINGLE_WORKER_FIRST_PASS,
    MPS_SINGLE_WORKER_FULL_RESTART_RETRY,
    MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG_BASENAME,
    MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG_BASENAME,
    SingleWorkerCampaignPlan,
    assert_no_host_platform_calls,
    compose_single_worker_first_pass,
    compose_single_worker_retry,
    exact_single_worker_slots,
)
from paths import PACKAGE_ROOT

PACKAGE = PACKAGE_ROOT
MACOS_MPS_TWO_WORKER_CONFIG = PACKAGE / "config/mujoco/parallel_batch_macos_mps_two_worker.yaml"
MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG = PACKAGE / "config/mujoco/parallel_batch_macos_mps_single_worker_retry.yaml"
MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG = PACKAGE / "config/mujoco/parallel_batch_macos_mps_single_worker_first_pass.yaml"

BROKER_PID = 9101
BROKER_BIRTH = 9201


def _plan_for(compose, path, tmp_path, *, points=("p1",), name="w1"):
    return compose(
        config=load_execution_config(path), config_path=path,
        campaign_id=f"b-{name}", batch_id=f"batch-{name}", selected_point_ids=tuple(points),
        evidence_root=tmp_path, broker_pid=BROKER_PID, broker_birth_identity=BROKER_BIRTH)


# --------------------------------------------------------------------------------------
# the loader widens for v5/v6 without touching v3 or v4
# --------------------------------------------------------------------------------------


def test_single_worker_install_documents_load_through_the_execution_loader():
    """The installed W1 documents are reachable through the real execution gate."""

    assert isinstance(load_execution_config(MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG), ParallelRuntimeConfigMacosMpsSingleWorkerRetry)
    assert isinstance(load_execution_config(MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG), ParallelRuntimeConfigMacosMpsSingleWorkerFirstPass)
    assert isinstance(load_execution_config(MACOS_MPS_TWO_WORKER_CONFIG), ParallelRuntimeConfigMacosMpsTwoWorker)


def test_the_w1_documents_are_refused_on_a_host_that_cannot_run_mps():
    """A Linux host still refuses the MPS path, for v5/v6 exactly as for v4."""

    for path in (MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG, MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG):
        assert isinstance(load_execution_config_for_schema(path, platform="darwin"),
                          (ParallelRuntimeConfigMacosMpsSingleWorkerRetry, ParallelRuntimeConfigMacosMpsSingleWorkerFirstPass))
        with pytest.raises(CompositionError, match="PLATFORM_HOST_MISMATCH"):
            load_execution_config_for_schema(path, platform="linux")


def test_the_installed_basenames_are_the_ones_the_manifest_records():
    """The provenance basenames name the files that are actually installed."""

    assert MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG.name == MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG_BASENAME
    assert MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG.name == MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG_BASENAME
    assert MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG.is_file() and MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG.is_file()


# --------------------------------------------------------------------------------------
# one slot, one Worker, one ROS domain
# --------------------------------------------------------------------------------------


def test_the_one_w1_slot_is_capacity_only_and_assigns_no_point():
    """A W1 slot is a capacity statement; the queue decides which point it executes."""

    slots = exact_single_worker_slots()
    assert slots.slot_ids == ("slot-0",)
    assert slots.assigned_points == (("slot-0", None),)
    assert slots.idle_slots == ("slot-0",)
    document = slots.to_document()
    assert document["slot_ids"] == ["slot-0"]
    assert document["capacity_only"] is True


@pytest.mark.parametrize(
    "compose, path, profile, batch_kind",
    [
        (compose_single_worker_retry, MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG, MPS_SINGLE_WORKER_FULL_RESTART_RETRY, "FULL_RESTART_RETRY"),
        (compose_single_worker_first_pass, MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG, MPS_SINGLE_WORKER_FIRST_PASS, "FIRST_PASS"),
    ],
)
def test_each_w1_profile_composes_one_slot_one_worker_and_one_domain(
        compose, path, profile, batch_kind, tmp_path):
    """The plan is exactly one slot, one Worker and one ROS domain per profile."""

    plan = _plan_for(compose, path, tmp_path)

    assert isinstance(plan, SingleWorkerCampaignPlan)
    assert plan.worker_count == EXACT_SINGLE_WORKERS == 1
    assert plan.slots.slot_ids == ("slot-0",)
    assert plan.ros_domain_ids == (181,)
    assert len(plan.ros_domain_ids) == plan.worker_count == len(plan.slots.slot_ids)
    assert plan.execution_profile == profile
    assert plan.batch_kind == batch_kind
    assert plan.accelerator == "mps"
    assert plan.accelerator_selector == "default"
    assert plan.requested_device == "mps"
    assert plan.allow_cpu_fallback is False
    assert plan.ipc_transport == str(IpcTransport.DARWIN_PRIVATE_PATH_UNIX)
    assert plan.mujoco_gl == "cgl"
    assert plan.mps_minimum_headroom_bytes == 1 << 30
    assert plan.mps_process_memory_fraction == 0.8
    assert plan.broker_pid == BROKER_PID and plan.broker_birth_identity == BROKER_BIRTH


def test_the_manifest_records_the_route_and_the_resolved_platform_values(tmp_path):
    """The manifest carries the profile and the batch kind it admits, never `auto`."""

    plan = _plan_for(compose_single_worker_retry, MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG, tmp_path, points=("p1", "p2"))
    document = plan.to_document()

    assert document["execution_profile"] == MPS_SINGLE_WORKER_FULL_RESTART_RETRY
    assert document["batch_kind"] == "FULL_RESTART_RETRY"
    assert document["worker_count"] == 1
    assert document["ros_domain_ids"] == [181]
    assert document["slots"]["slot_ids"] == ["slot-0"]
    assert document["selected_point_ids"] == ["p1", "p2"]
    assert document["snapshot_root"] == str(tmp_path / "inference-inputs")
    assert document["supervisor_receipt_path"].endswith("owner-receipt.json")
    assert document["model_provenance"]["yolo_imgsz"] == 640
    assert "auto" not in {str(value) for value in document.values()}


def test_the_worker_count_never_follows_the_selected_point_count(tmp_path):
    """One point is not a W1 claim and four points do not make a W4 claim."""

    one = _plan_for(compose_single_worker_first_pass, MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG, tmp_path / "one", points=("p1",))
    four = _plan_for(compose_single_worker_first_pass, MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG, tmp_path / "four",
                     points=("p1", "p2", "p3", "p4"))

    assert (one.worker_count, four.worker_count) == (1, 1)
    assert one.slots.slot_ids == four.slots.slot_ids == ("slot-0",)
    assert one.execution_profile == four.execution_profile == MPS_SINGLE_WORKER_FIRST_PASS
    assert one.ros_domain_ids == four.ros_domain_ids == (181,)
    assert one.to_document()["batch_kind"] == four.to_document()["batch_kind"] == "FIRST_PASS"


def test_a_w1_plan_invents_no_budget_qualification_or_promotion_field(tmp_path):
    """A W1 composition is a routing fact plus provenance, never a capacity claim."""

    document = _plan_for(compose_single_worker_retry, MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG, tmp_path).to_document()
    forbidden = ("budget", "qualification", "promotion", "profile_sha256", "capacity",
                 "forecast", "max_points_per_worker")

    assert not [key for key in document if any(token in key for token in forbidden)]


def test_a_w1_plan_is_json_serializable(tmp_path):
    """The manifest must survive the JSON round trip the evidence files use."""

    document = _plan_for(compose_single_worker_first_pass, MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG, tmp_path).to_document()
    assert json.loads(json.dumps(document))["execution_profile"] == MPS_SINGLE_WORKER_FIRST_PASS


def test_a_w1_plan_never_claims_an_nvml_or_proc_fd_dependency(tmp_path):
    """The Darwin boundary check runs at composition time, not only in a config test."""

    plan = _plan_for(compose_single_worker_retry, MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG, tmp_path)
    assert_no_host_platform_calls(plan)

    from dataclasses import replace

    with pytest.raises(CompositionError, match="PLATFORM_COMBINATION"):
        assert_no_host_platform_calls(replace(plan, ipc_transport="proc_fd_unix"))
    with pytest.raises(CompositionError, match="PLATFORM_COMBINATION"):
        assert_no_host_platform_calls(replace(plan, accelerator="cuda"))
    with pytest.raises(CompositionError, match="PLATFORM_COMBINATION"):
        assert_no_host_platform_calls(replace(plan, mps_minimum_headroom_bytes=None))


# --------------------------------------------------------------------------------------
# cross-profile refusal
# --------------------------------------------------------------------------------------


def test_each_w1_composer_refuses_the_other_profile_document(tmp_path):
    """No cross-profile reuse: the retry composer takes v5 only, the first-pass composer v6."""

    with pytest.raises(CompositionError, match="CONFIG_SCHEMA_MISMATCH"):
        _plan_for(compose_single_worker_retry, MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG, tmp_path / "a")
    with pytest.raises(CompositionError, match="CONFIG_SCHEMA_MISMATCH"):
        _plan_for(compose_single_worker_first_pass, MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG, tmp_path / "b")
    with pytest.raises(CompositionError, match="CONFIG_SCHEMA_MISMATCH"):
        _plan_for(compose_single_worker_retry, MACOS_MPS_TWO_WORKER_CONFIG, tmp_path / "c")
    with pytest.raises(CompositionError, match="CONFIG_SCHEMA_MISMATCH"):
        _plan_for(compose_single_worker_first_pass, MACOS_MPS_TWO_WORKER_CONFIG, tmp_path / "d")


def test_exact_w2_refuses_a_w1_document(tmp_path):
    """The W2 composer is not a fallback for a W1 profile and vice versa."""

    for path in (MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG, MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG):
        with pytest.raises(CompositionError, match="CONFIG_SCHEMA_MISMATCH"):
            compose_two_worker_campaign(
                config=load_execution_config(path), config_path=path, campaign_id="b-w2",
                batch_id="batch-w2", selected_point_ids=("p1",), evidence_root=tmp_path)


def test_a_w1_composition_refuses_a_relative_evidence_root_and_a_missing_identity(tmp_path):
    """The same closed input rules as W2: absolute root, non-empty campaign identity."""

    config = load_execution_config(MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG)
    with pytest.raises(CompositionError, match="EVIDENCE_ROOT"):
        compose_single_worker_first_pass(
            config=config, config_path=MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG, campaign_id="b", batch_id="batch",
            selected_point_ids=("p1",), evidence_root=Path("relative"))
    with pytest.raises(CompositionError, match="CAMPAIGN_ID"):
        compose_single_worker_first_pass(
            config=config, config_path=MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG, campaign_id="", batch_id="batch",
            selected_point_ids=("p1",), evidence_root=tmp_path)


def test_a_w1_plan_cannot_carry_a_linux_transport(tmp_path):
    """A hand-made plan with a Linux transport is refused before anything reads it."""

    from dataclasses import replace

    config = load_execution_config(MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG)
    assert config.accelerator.kind is AcceleratorKind.MPS
    assert config.ipc_transport is IpcTransport.DARWIN_PRIVATE_PATH_UNIX

    plan = _plan_for(compose_single_worker_retry, MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG, tmp_path)
    with pytest.raises(CompositionError, match="PLATFORM_COMBINATION"):
        assert_no_host_platform_calls(replace(plan, accelerator="cuda"))
    with pytest.raises(CompositionError, match="PLATFORM_COMBINATION"):
        assert_no_host_platform_calls(
            replace(plan, ipc_transport=str(IpcTransport.PROC_FD_UNIX), mujoco_gl="egl"))
    with pytest.raises(ContractError):
        # the closed v5 contract refuses a CUDA document before any composition exists
        load_w1_config_with_cuda(tmp_path)


def load_w1_config_with_cuda(tmp_path):
    """A hand-written v5 document that claims the Linux combination."""

    import yaml

    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_macos_mps_single_worker_retry

    document = yaml.safe_load(MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG.read_text())
    document["accelerator"] = {"kind": "cuda", "selector": "INDEX:0"}
    document["requested_device"] = "cuda"
    document["ipc_transport"] = "proc_fd_unix"
    document["mujoco_gl"] = "egl"
    document["mps_process_memory_fraction"] = None
    document["start_guard"].pop("mps_minimum_headroom_bytes")
    path = tmp_path / "v5-linux.yaml"
    path.write_text(yaml.safe_dump(document))
    return load_parallel_runtime_config_macos_mps_single_worker_retry(path)
