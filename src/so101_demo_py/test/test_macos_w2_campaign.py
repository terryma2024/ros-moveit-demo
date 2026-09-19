"""The composed macOS MPS W2 campaign: pre-flight, one-time admission, recovery, cleanup.

The pieces from Tasks 3-9 were each tested alone. These tests cover the composition itself: that a
dirty host stops the campaign before anything is spawned, that every broker response is routed
through the one-time table, that a broker failure runs the closed rebuild, and that released
snapshots are reported rather than deleted.
"""

import time
from pathlib import Path

import numpy as np
import pytest

from so101_demo.parallel_batch.campaign_supervisor import CampaignSupervisor
from so101_demo.parallel_batch.inference_registry import InferenceRegistry
from so101_demo.parallel_batch.input_snapshot import SnapshotRegistry, SnapshotStore
from so101_demo.parallel_batch.macos_w2_campaign import (
    CampaignInventory,
    CampaignPorts,
    MacosW2Campaign,
    MacosW2CampaignError,
    read_inventory,
)
from so101_demo.parallel_batch.pool_recovery import INFRASTRUCTURE_FAILURE, RecoveryFacts
from so101_demo.parallel_batch.w2_composition import (
    W2CampaignPlan, compose_w2_campaign, load_execution_config)

PACKAGE = Path(__file__).resolve().parents[1]
V4_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v4_macos_mps_w2.yaml"

BROKER_PID = 7001
BROKER_BIRTH = 8001


def _plan(tmp_path):
    return compose_w2_campaign(
        config=load_execution_config(V4_CONFIG), config_path=V4_CONFIG,
        campaign_id="b-composed", batch_id="batch-composed",
        selected_point_ids=("p1", "p2"), evidence_root=tmp_path,
        broker_pid=BROKER_PID, broker_birth_identity=BROKER_BIRTH)


def _campaign(tmp_path, **port_overrides):
    plan = _plan(tmp_path)
    supervisor = CampaignSupervisor("b-composed", state_root=tmp_path / "supervisor")
    ports = CampaignPorts(model_factories={"yolo": lambda: object()}, **port_overrides)
    return MacosW2Campaign(plan=plan, address=object(), supervisor=supervisor, ports=ports)


# --------------------------------------------------------------------------------------
# pre-flight
# --------------------------------------------------------------------------------------


def test_a_clean_host_is_reported_clean(tmp_path):
    inventory = read_inventory(claim_path=tmp_path / "absent.lock",
                               ipc_base=tmp_path / "absent-ipc")
    assert isinstance(inventory, CampaignInventory)
    assert inventory.clean is True


def test_a_live_claim_makes_the_host_not_clean(tmp_path):
    """A held claim alone is enough to stop a new campaign."""

    claim = tmp_path / "campaign-claim.lock"
    claim.write_text("")
    ipc_base = tmp_path / "so101-ipc"
    (ipc_base / "b-live").mkdir(parents=True)
    (ipc_base / "b-live" / "broker.sock").write_text("")
    inventory = read_inventory(claim_path=claim, ipc_base=ipc_base)
    assert inventory.clean is False
    assert inventory.claim_held is True
    assert inventory.existing_campaign_dirs == (str(ipc_base / "b-live"),)


def test_the_pre_flight_never_signals_anything(tmp_path):
    """Reading the inventory reports owned processes; it does not stop them."""

    inventory = read_inventory(claim_path=tmp_path / "x", ipc_base=tmp_path)
    assert inventory.owned_processes == ()
    assert inventory.live_endpoints == ()


# --------------------------------------------------------------------------------------
# composition guards
# --------------------------------------------------------------------------------------


def test_the_composition_refuses_a_plan_that_is_not_mps(tmp_path):
    """A CUDA plan cannot be driven by the macOS composition."""

    from dataclasses import replace

    plan = replace(_plan(tmp_path), accelerator="cuda")
    supervisor = CampaignSupervisor("x", state_root=tmp_path / "sup")
    with pytest.raises(MacosW2CampaignError, match="PLAN_NOT_MPS"):
        MacosW2Campaign(plan=plan, address=object(), supervisor=supervisor,
                        ports=CampaignPorts(model_factories={}))


def test_the_composition_refuses_a_slot_count_that_is_not_two(tmp_path):
    from dataclasses import replace

    from so101_demo.parallel_batch.w2_composition import exact_w2_slots

    plan = replace(_plan(tmp_path), slots=exact_w2_slots(("p1", "p2", "p3")),
                   worker_count=3)
    supervisor = CampaignSupervisor("x", state_root=tmp_path / "sup")
    with pytest.raises(MacosW2CampaignError, match="SLOT_COUNT_MISMATCH"):
        MacosW2Campaign(plan=plan, address=object(), supervisor=supervisor,
                        ports=CampaignPorts(model_factories={}))


def test_a_mixed_platform_plan_is_refused_by_the_composition(tmp_path):
    """The host-boundary check runs at composition time, not only in a config test."""

    from dataclasses import replace

    from so101_demo.parallel_batch.w2_composition import CompositionError

    plan = replace(_plan(tmp_path), ipc_transport="proc_fd_unix")
    supervisor = CampaignSupervisor("x", state_root=tmp_path / "sup")
    with pytest.raises(CompositionError, match="PLATFORM_COMBINATION"):
        MacosW2Campaign(plan=plan, address=object(), supervisor=supervisor,
                        ports=CampaignPorts(model_factories={}))


# --------------------------------------------------------------------------------------
# one-time admission
# --------------------------------------------------------------------------------------


def test_every_broker_response_must_pass_the_one_time_table(tmp_path):
    """A response is admitted once, and a repeat is refused with its reason."""

    campaign = _campaign(tmp_path)
    campaign.request_binding(request_id="req-1", slot_id="slot-0", point_id="p1", attempt=1,
                            input_sha256="a" * 64, deadline_s=30.0, broker_pid=BROKER_PID,
                            broker_birth_identity=BROKER_BIRTH)
    first = campaign.admit_response("req-1", broker_pid=BROKER_PID,
                                   broker_birth_identity=BROKER_BIRTH,
                                   output_sha256="b" * 64)
    assert first.accepted is True
    second = campaign.admit_response("req-1", broker_pid=BROKER_PID,
                                    broker_birth_identity=BROKER_BIRTH)
    assert second.accepted is False
    assert second.reason == "REQUEST_ALREADY_CONSUMED"


def test_a_response_from_a_replaced_broker_identity_is_refused(tmp_path):
    campaign = _campaign(tmp_path)
    campaign.request_binding(request_id="req-2", slot_id="slot-0", point_id="p1", attempt=1,
                             input_sha256="a" * 64, deadline_s=30.0, broker_pid=BROKER_PID,
                             broker_birth_identity=BROKER_BIRTH)
    decision = campaign.admit_response("req-2", broker_pid=BROKER_PID,
                                       broker_birth_identity=BROKER_BIRTH + 1)
    assert decision.accepted is False
    assert decision.reason == "BROKER_IDENTITY_MISMATCH"


def test_an_unknown_request_is_refused_not_admitted(tmp_path):
    campaign = _campaign(tmp_path)
    decision = campaign.admit_response("never-registered", broker_pid=BROKER_PID,
                                       broker_birth_identity=BROKER_BIRTH)
    assert decision.accepted is False
    assert decision.reason == "REQUEST_UNKNOWN"


# --------------------------------------------------------------------------------------
# recovery and cleanup
# --------------------------------------------------------------------------------------


def test_the_composition_runs_the_closed_rebuild_sequence(tmp_path):
    """A broker failure produces the seven-step trace, and the request is removed first."""

    campaign = _campaign(tmp_path)
    campaign.supervisor.acquire_claim()
    campaign.request_binding(request_id="req-3", slot_id="slot-0", point_id="p1", attempt=1,
                             input_sha256="a" * 64, deadline_s=30.0, broker_pid=BROKER_PID,
                             broker_birth_identity=BROKER_BIRTH)
    facts = RecoveryFacts(
        campaign_id="b-composed", failed_request_id="req-3", point_id="p1", attempt=1,
        motion_in_flight=False, broker_pid=BROKER_PID, broker_birth_identity=BROKER_BIRTH)
    trace = campaign.rebuild_after_broker_failure(
        facts=facts,
        create_campaign_root=lambda: "b-newcampaign",
        spawn_broker=lambda path: path == "b-newcampaign",
        spawn_worker=lambda name, path: True,
        coordinator_decision=lambda payload: True,
        reap_owned_processes=lambda: (BROKER_PID,))
    assert trace[0] == "remove_active_request"
    assert trace[-1] == "coordinator_decision"
    assert campaign.registry.pending() == ()
    campaign.supervisor.release_claim()


def test_released_snapshots_are_reported_and_still_on_disk(tmp_path):
    """Cleanup releases snapshots as deletion candidates; it never unlinks them."""

    campaign = _campaign(tmp_path)
    descriptor = campaign.snapshots.register(
        request_id="req-4", slot="slot-0",
        array=np.zeros((4, 4, 3), dtype=np.uint8), frame_timestamp_ns=1)
    released = campaign.release_snapshots(reason="campaign finished")
    assert released == (descriptor.relative_path,)
    assert Path(campaign.plan.snapshot_root).joinpath(
        *descriptor.relative_path.split("/")).exists()
    assert [c.outcome for c in campaign.snapshots.pending_deletion_candidates()] == [
        "DELETION_CANDIDATE"]


def test_the_infrastructure_disposition_is_never_a_business_status(tmp_path):
    campaign = _campaign(tmp_path)
    document = campaign.infrastructure_failure_document(request_id="req-5", point_id="p2",
                                                        attempt=2)
    assert document["kind"] == INFRASTRUCTURE_FAILURE
    assert document["business_status"] is None
    assert document["campaign_id"] == "b-composed"


def test_an_empty_campaign_directory_is_residue_not_a_live_stack(tmp_path):
    """Only a campaign directory that still holds something counts as live.

    A run that stops before its cleanup leaves an empty directory behind. Treating that as a
    blocking condition would make one crashed run refuse every later campaign on the host.
    """

    from so101_demo.parallel_batch.macos_w2_campaign import read_inventory

    ipc_base = tmp_path / "so101-ipc"
    (ipc_base / "b-empty-residue").mkdir(parents=True)
    (ipc_base / "b-holds-a-socket").mkdir(parents=True)
    (ipc_base / "b-holds-a-socket" / "broker.sock").write_text("")

    inventory = read_inventory(claim_path=tmp_path / "no-claim", ipc_base=ipc_base)
    assert inventory.existing_campaign_dirs == (str(ipc_base / "b-holds-a-socket"),)
    assert inventory.clean is False

    (ipc_base / "b-holds-a-socket" / "broker.sock").unlink()
    after = read_inventory(claim_path=tmp_path / "no-claim", ipc_base=ipc_base)
    assert after.existing_campaign_dirs == ()
    assert after.clean is True
