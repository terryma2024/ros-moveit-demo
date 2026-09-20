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


def test_campaign_ports_expose_the_worker_simulation_seams() -> None:
    """The simulation driver plugs in through `CampaignPorts`, not through the campaign body.

    Both seams default to `None`, which is what keeps every earlier campaign - the IPC-only Worker -
    working unchanged; a caller that supplies them gets a Worker that owns a station and talks to
    the shared Broker through the v4 port.
    """

    from so101_demo.parallel_batch.macos_w2_campaign import CampaignPorts

    default = CampaignPorts(model_factories={})
    assert default.worker_station is None
    assert default.worker_broker is None
    assert default.stop_worker("w1") is True
    assert default.cancel_goals() is True
    assert default.confirm_absence() is True

    station = lambda resources: ("station", resources)  # noqa: E731 - the seam is the subject
    broker = lambda *args, **kwargs: ("broker", args, kwargs)
    supplied = CampaignPorts(model_factories={}, worker_station=station, worker_broker=broker)
    assert supplied.worker_station is station
    assert supplied.worker_broker is broker


def test_worker_leases_and_bindings_use_the_ids_the_worker_derives(tmp_path: Path) -> None:
    """The admission gate must bind the ids the Worker will actually request with.

    The Worker's port derives `{attempt_id}-{model_id}`, so anything else in the table is a parallel
    vocabulary that would refuse real inference. The lease document is also what tells the Worker
    which identity it owns, so the two sides cannot drift.
    """

    import json

    from so101_demo.cli.macos_w2_campaign import bind_worker_requests, build_worker_leases
    from so101_demo.parallel_batch.w2_composition import exact_w2_slots

    class _Plan:
        slots = exact_w2_slots(("p1", "p2"))

    leases = build_worker_leases(
        plan=_Plan(), batch_id="b1", evidence_root=tmp_path, input_sha256="a" * 64
    )

    assert sorted(leases) == ["w1", "w2"]
    document = leases["w1"]
    assert document["attempt_ids"] == ["w1-att-00", "w1-att-01", "w1-att-02"]
    assert document["slot_id"] == "slot-0" and leases["w2"]["slot_id"] == "slot-1"
    assert document["point_id"] == "p1" and leases["w2"]["point_id"] == "p2"
    assert Path(document["snapshot_path"]).is_file()
    on_disk = json.loads(Path(document["lease_path"]).read_text())
    assert on_disk["attempt_ids"] == document["attempt_ids"]
    assert on_disk["model_id"] == "yolo"
    # the fault-injection switches must travel with the lease, or a probe would silently do nothing
    assert on_disk["deadline_s"] == 240.0
    assert on_disk["tamper_input_sha256"] is False

    tuned = build_worker_leases(plan=_Plan(), batch_id="b1", evidence_root=tmp_path,
                                input_sha256="a" * 64, deadline_s=4.0, tamper_input_sha256=True)
    tuned_disk = json.loads(Path(tuned["w1"]["lease_path"]).read_text())
    assert tuned_disk["deadline_s"] == 4.0 and tuned_disk["tamper_input_sha256"] is True

    class _Ready:
        broker_pid = 4242
        broker_birth_identity = 17

    class _Campaign:
        def __init__(self):
            self.bindings = []

        def request_binding(self, **kwargs):
            self.bindings.append(kwargs)

    campaign = _Campaign()
    bind_worker_requests(campaign, leases, ready=_Ready())

    bound = sorted(binding["request_id"] for binding in campaign.bindings)
    assert bound == ["w1-att-00-yolo", "w1-att-01-yolo", "w1-att-02-yolo",
                     "w2-att-00-yolo", "w2-att-01-yolo", "w2-att-02-yolo"]
    assert all(binding["broker_pid"] == 4242 for binding in campaign.bindings)
    assert all(binding["input_sha256"] == "a" * 64 for binding in campaign.bindings)


def test_admission_rule_refuses_unknown_duplicate_and_tampered_requests() -> None:
    """The campaign's admission rule, tested without a socket.

    Order matters and is asserted: an unimplemented operation is refused first, a repeated id is
    refused before it can consume the table twice, and an inference whose declared digest is not the
    bound one is refused - including when the digest is unreadable, which must never count as a match.
    """

    import json

    from so101_demo.cli.macos_w2_campaign import IMPLEMENTED_OPERATIONS, admission_decision

    bound = "a" * 64
    good = json.dumps({"input_sha256": bound})
    consumed = {"w1-att-00-yolo"}

    assert admission_decision(
        operation="broker.infer", request_id="w1-att-01-yolo", serialized_request=good,
        consumed_ids=consumed, bound_digest=bound) is None

    unknown = admission_decision(
        operation="coordinator.cancel_request", request_id="x", serialized_request=good,
        consumed_ids=set(), bound_digest=bound)
    assert unknown["error"]["code"] == "UNKNOWN_OPERATION"
    assert "coordinator.cancel_request" not in IMPLEMENTED_OPERATIONS

    cancelled = admission_decision(
        operation="broker.infer", request_id="w2-att-00-yolo", serialized_request=good,
        consumed_ids=set(), bound_digest=bound, cancelled_ids={"w2-att-00-yolo"})
    assert cancelled["error"]["code"] == "CANCELLED"
    # cancellation is refused whether or not the id was ever consumed
    cancelled_after_use = admission_decision(
        operation="broker.infer", request_id="w2-att-00-yolo", serialized_request=good,
        consumed_ids={"w2-att-00-yolo"}, bound_digest=bound,
        cancelled_ids={"w2-att-00-yolo"})
    assert cancelled_after_use["error"]["code"] == "CANCELLED"

    duplicate = admission_decision(
        operation="broker.infer", request_id="w1-att-00-yolo", serialized_request=good,
        consumed_ids=consumed, bound_digest=bound)
    assert duplicate["error"]["code"] == "DUPLICATE_REQUEST"

    for tampered in (json.dumps({"input_sha256": "0" * 64}), None, "not json", {}, b"\xff\xfe"):
        refusal = admission_decision(
            operation="broker.infer", request_id="w1-att-02-yolo", serialized_request=tampered,
            consumed_ids=set(), bound_digest=bound)
        assert refusal["error"]["code"] == "SNAPSHOT_MISMATCH", tampered


def test_per_slot_summary_reads_a_synthetic_evidence_tree(tmp_path: Path) -> None:
    """The per-slot summary is the campaign's own statement about what each slot did.

    It must count executed points from their manifests, keep the failure codes, stay quiet rather
    than raise when a directory or a file is unreadable, and report zeros for a slot that produced
    nothing - the last case is a fact the run has to record, not a reason to lose it.
    """

    import json

    from so101_demo.cli.macos_w2_campaign import summarize_per_slot_pick_place

    def write(path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))

    root = tmp_path
    base = root / "w1-station/pick/batches/b1/points"
    write(base / "01-task_start/dynamic/dynamic-execute-manifest.json",
          {"current_state": "DONE", "failure": None,
           "final_samples": [{"simulation_step": 33, "table_contact": True,
                              "maximum_normal_force_n": 0.233}]})
    write(base / "02-failed/dynamic/dynamic-execute-manifest.json",
          {"current_state": "DONE", "failure": {"code": "X"}, "final_samples": []})
    write(base / "01-task_start/point-result.json", {"status": "FAILED",
                                                     "failure_code": "TERMINAL_CAPTURE_FAILED"})
    (base / "01-task_start/broken.json").write_text("{not json")

    summary = summarize_per_slot_pick_place(evidence_root=root)

    w1 = summary["w1"]
    assert w1["manifests"] == 2 and w1["point_results"] == 1
    assert w1["executed_points"] == ["01-task_start"]
    assert w1["failure_codes"] == ["TERMINAL_CAPTURE_FAILED"]
    contact = w1["contacts"][0]
    assert contact["point"] == "01-task_start" and contact["simulation_step"] == 33
    assert contact["table_contact"] is True and contact["max_normal_force_n"] == 0.233
    # the plan's named items travel too, and a manifest that does not carry them reads as None
    # rather than raising - the summary must survive an older or partial evidence file
    assert contact["planning_scene_readback"] is None
    assert contact["release_marker_sequence"] is None
    assert contact["final_cup_position_world_m"] is None
    # a slot with nothing on disk is reported, not omitted and not an exception
    assert summary["w2"]["manifests"] == 0 and summary["w2"]["executed_points"] == []


def test_campaign_verdict_requires_the_happy_path_and_no_refusals() -> None:
    """PASS is the happy path only: any refusal - even a deliberate probe - reads INCOMPLETE."""

    from so101_demo.cli.macos_w2_campaign import campaign_status

    good = dict(cleanup_complete=True, results=[{}, {}],
                workers=[{"status": "ACTIVE"}, {"status": "ACTIVE"}],
                served={"count": 6, "devices": ["mps"]}, refused=[])
    assert campaign_status(**good) == "W2_CAMPAIGN_PASS"

    for change in (
        {"cleanup_complete": False},
        {"results": [{}]},
        {"workers": [{"status": "ACTIVE"}, {"status": "STOPPED"}]},
        {"served": {"count": 5, "devices": ["mps"]}},
        {"served": {"count": 6, "devices": []}},
        {"served": {"count": 6, "devices": ["cpu"]}},
        {"refused": [{"reason": "DUPLICATE_REQUEST"}]},
    ):
        assert campaign_status(**{**good, **change}) == "W2_CAMPAIGN_INCOMPLETE", change
