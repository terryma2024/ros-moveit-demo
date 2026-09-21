"""The composed macOS MPS W2 campaign: pre-flight, one-time admission, recovery, cleanup.

The pieces from Tasks 3-9 were each tested alone. These tests cover the composition itself: that a
dirty host stops the campaign before anything is spawned, that every broker response is routed
through the one-time table, that a broker failure runs the closed rebuild, and that released
snapshots are reported rather than deleted.
"""

import json
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

    plan = replace(_plan(tmp_path), slots=exact_w2_slots(), worker_count=3)
    supervisor = CampaignSupervisor("x", state_root=tmp_path / "sup")
    with pytest.raises(MacosW2CampaignError, match="SLOT_COUNT_MISMATCH"):
        MacosW2Campaign(plan=plan, address=object(), supervisor=supervisor,
                        ports=CampaignPorts(model_factories={}))


def test_the_two_slots_are_capacity_only_and_assign_no_points(tmp_path):
    """The slots exist because the platform claim is exact W2, not to hold the first two points.

    Point assignment belongs to the durable shared queue (`parallel_batch.queue`), which hands a
    Worker exactly one point per lease; a slot that already owned a point would make concurrent
    leasing impossible and would silently drop every selected point after the second.
    """

    from so101_demo.parallel_batch.w2_composition import exact_w2_slots

    slots = exact_w2_slots()

    assert slots.slot_ids == ("slot-0", "slot-1")
    assert slots.assigned_points == (("slot-0", None), ("slot-1", None))
    assert slots.idle_slots == ("slot-0", "slot-1")

    plan = _plan(tmp_path)
    assert plan.selected_point_ids == ("p1", "p2")
    assert plan.to_document()["selected_point_ids"] == ["p1", "p2"]
    assert [point for _slot, point in plan.slots.assigned_points] == [None, None]


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
        slots = exact_w2_slots()
        selected_point_ids = ("p1", "p2")

    leases = build_worker_leases(
        plan=_Plan(), batch_id="b1", evidence_root=tmp_path, input_sha256="a" * 64
    )

    assert sorted(leases) == ["w1", "w2"]
    document = leases["w1"]
    assert document["attempt_ids"] == ["w1-att-00", "w1-att-01", "w1-att-02"]
    assert document["slot_id"] == "slot-0" and leases["w2"]["slot_id"] == "slot-1"
    # The slot no longer owns a point: the queue decides which point a lease carries. Until the
    # Worker is wired to that queue (plan Task 3) the entry point keeps its explicit fallback, so
    # the lease still carries a *selected* id rather than an invented or unselected one.
    assert {lease["point_id"] for lease in leases.values()} <= set(_Plan.selected_point_ids)
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


def test_campaign_cli_exposes_the_fault_switches_with_safe_defaults() -> None:
    """The fault-injection switches are an interface: the runners pass them by name.

    A renamed or re-defaulted flag would silently turn a probe into a normal run - the failure mode
    this session hit twice - so the names and the off-by-default values are pinned here.
    """

    from so101_demo.cli.macos_w2_campaign import build_parser

    parser = build_parser()
    options = parser.parse_args([
        "--config", "/tmp/config.yaml", "--campaign-id", "c", "--batch-id", "b",
        "--evidence-root", "/tmp/evidence", "--yolo-weights", "/tmp/y.pt",
        "--grounded-root", "/tmp/g",
    ])

    assert options.duplicate_probe is False
    assert options.tamper_snapshot_sha is False
    assert options.cancel_second_worker_after_served == 0
    assert options.stall_serve_after == 0
    assert options.worker_deadline_s == 240.0
    assert options.crash_broker_after_served == 0

    armed = parser.parse_args([
        "--config", "/tmp/config.yaml", "--campaign-id", "c", "--batch-id", "b",
        "--evidence-root", "/tmp/evidence", "--yolo-weights", "/tmp/y.pt",
        "--grounded-root", "/tmp/g", "--duplicate-probe", "--tamper-snapshot-sha",
        "--cancel-second-worker-after-served", "4", "--stall-serve-after", "2",
        "--worker-deadline-s", "4",
    ])
    assert armed.duplicate_probe is True and armed.tamper_snapshot_sha is True
    assert armed.cancel_second_worker_after_served == 4
    assert armed.stall_serve_after == 2 and armed.worker_deadline_s == 4.0


def test_campaign_binds_the_selection_and_queue_it_executes(tmp_path):
    """Selection and queue are bound together, once, before any Worker can lease a point.

    Without this binding the campaign has no checked answer to "which points may run", and the
    queue is the only issuer of per-point leases (plan Task 2/3).
    """

    from so101_demo.parallel_batch.queue import DurablePointQueue
    from so101_demo.parallel_batch.selection import build_first_pass_selection
    from test_parallel_selection import (
        ANCHOR_IDS, CLOSURE_SHA, CONFIG_SHA, SAMPLE_IDS, _write_catalog)

    catalog = _write_catalog(tmp_path)
    binding = build_first_pass_selection(
        catalog_path=catalog, point_ids=ANCHOR_IDS + SAMPLE_IDS[:1],
        campaign_id="b-composed", batch_id="batch-composed",
        config_sha256=CONFIG_SHA, runtime_closure_sha256=CLOSURE_SHA)
    queue = DurablePointQueue(root=tmp_path / "queue", binding=binding)
    campaign = _campaign(tmp_path)

    campaign.bind_selection(binding=binding, queue=queue)

    assert campaign.selection_sha256 == binding.selection_sha256
    assert campaign.queue is queue
    with pytest.raises(MacosW2CampaignError, match="SELECTION_ALREADY_BOUND"):
        campaign.bind_selection(binding=binding, queue=queue)
    with pytest.raises(MacosW2CampaignError, match="SELECTION_TYPE"):
        _campaign(tmp_path / "second").bind_selection(binding=object(), queue=queue)
    with pytest.raises(MacosW2CampaignError, match="QUEUE_TYPE"):
        _campaign(tmp_path / "third").bind_selection(binding=binding, queue=object())


def test_campaign_journal_publishes_committed_watermarks(tmp_path):
    """The macOS campaign's standard events are durable *and* watermarked before they are ACKed."""

    from so101_demo.cli.macos_w2_campaign import (
        commit_campaign_terminal, open_campaign_journal)
    from so101_demo.parallel_batch.journal import (
        CoordinatorJournal, JournalCorruption)

    journal = open_campaign_journal(
        evidence_root=tmp_path, campaign_id="b-composed", batch_id="batch-composed")
    try:
        watermark = journal.read_watermark()
        assert watermark is not None and watermark.sequence == 1
        prefix = CoordinatorJournal.read_committed_prefix(tmp_path / "journal",
                                                          "batch-composed", watermark)
        assert [event.type for event in prefix.events] == ["CAMPAIGN_STARTED"]
        assert prefix.unconfirmed_durability is False

        commit_campaign_terminal(journal, outcome="W2_CAMPAIGN_PASS", cleanup_complete=True)
        final = journal.read_watermark()
        assert final.sequence == 3
        with pytest.raises(JournalCorruption):
            journal.append_committed("POINT_LEASED", "late-1", {"point_id": "p9"})
    finally:
        journal.close()

    replay = CoordinatorJournal.read_committed_prefix(
        tmp_path / "journal", "batch-composed", final)
    assert [event.type for event in replay.events] == [
        "CAMPAIGN_STARTED", "BATCH_TERMINAL", "CLEANUP_COMMITTED"]


# --------------------------------------------------------------------------------------
# Task 7: the typed route, the service adapter's dispatch, and the fresh pre-child guard
#
# The adapter is the seam the service launches. It accepts exactly the flags the supervisor
# sends - no more - so its dispatch key has to be derived from those flags plus the config
# document: (schema_version, execution_profile, batch_kind, worker_count). A key that is not
# in the closed table is refused by name; there is no generic `--batch-kind` fallback and no
# cross-profile reuse.
# --------------------------------------------------------------------------------------

V5_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v5_macos_mps_w1_retry.yaml"
V6_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v6_macos_mps_w1_first_pass.yaml"

ROUTES = (
    (V4_CONFIG, 2, "MPS_W2_FIRST_PASS", "FIRST_PASS",
     "so101_demo.cli.macos_w2_campaign"),
    (V5_CONFIG, 1, "MPS_W1_FULL_RESTART_RETRY", "FULL_RESTART_RETRY",
     "so101_demo.cli.macos_n1_retry"),
    (V6_CONFIG, 1, "MPS_W1_FIRST_PASS", "FIRST_PASS",
     "so101_demo.cli.macos_n1_first_pass"),
)


def _service_environment(tmp_path):
    return {
        "SO101_FIXED_CONTROL_CAMPAIGN_ID": "campaign-a",
        "SO101_FIXED_CONTROL_SOCKET": str(tmp_path / "control.sock"),
        "SO101_FIXED_CONTROL_TOKEN": "ab" * 32,
        "SO101_FIXED_CONTROL_EPOCH": "1",
    }


def _service_argv(tmp_path, *, config_path, worker_count, point_ids=("p1",)):
    """The argv the service's supervisor builds, with real files behind every path."""

    from so101_demo.cli import macos_service_campaign as adapter

    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    weights = tmp_path / "yolo.pt"
    weights.write_bytes(b"weights")
    grounded = tmp_path / "grounded"
    grounded.mkdir(parents=True, exist_ok=True)
    (grounded / "manifest.json").write_text('{"model": "grounded"}\n')
    points = tmp_path / "points.yaml"
    points.write_text("points: [p1, p2]\n")
    return adapter, [
        "--points", str(points), "--config", str(config_path), "--batch-id", "b001",
        "--worker-count", str(worker_count), "--evidence-root", str(tmp_path / "batch"),
        "--broker-image", "sha256:" + "a" * 64, "--yolo-weights", str(weights),
        "--yolo-weights-sha256", adapter._digest(weights),
        "--grounded-root", str(grounded),
        "--grounded-manifest-sha256", adapter._digest(grounded / "manifest.json"),
        "--run-mode", "execute",
        *[item for point in point_ids for item in ("--point-id", point)],
    ]


def test_the_service_adapter_dispatches_each_approved_route_to_one_module(tmp_path):
    """One line per approved combination; the module is selected, never guessed."""

    for config_path, worker_count, profile, batch_kind, module in ROUTES:
        adapter, argv = _service_argv(tmp_path / config_path.stem, config_path=config_path,
                                      worker_count=worker_count)
        arguments = adapter.build_parser().parse_args(argv)
        record = adapter.validate(arguments, environment=_service_environment(tmp_path))

        assert record["execution_profile"] == profile
        assert record["batch_kind"] == batch_kind
        assert record["worker_count"] == worker_count
        assert record["campaign_module"] == module
        assert record["schema_version"] in (4, 5, 6)


def test_the_service_adapter_refuses_a_key_outside_the_table(tmp_path):
    """A worker count, schema or profile the table does not name is refused by name."""

    from so101_demo.cli.macos_service_campaign import ServiceCampaignError

    environment = _service_environment(tmp_path)
    for config_path, worker_count, reason in (
        (V4_CONFIG, 1, "PLATFORM_WORKER_COUNT_UNSUPPORTED"),
        (V4_CONFIG, 4, "PLATFORM_WORKER_COUNT_UNSUPPORTED"),
        (V5_CONFIG, 2, "PLATFORM_WORKER_COUNT_UNSUPPORTED"),
        (V6_CONFIG, 8, "PLATFORM_WORKER_COUNT_UNSUPPORTED"),
    ):
        adapter, argv = _service_argv(tmp_path / f"{config_path.stem}-{worker_count}",
                                      config_path=config_path, worker_count=worker_count)
        with pytest.raises(ServiceCampaignError, match=reason):
            adapter.validate(adapter.build_parser().parse_args(argv), environment=environment)


def test_the_service_adapter_refuses_a_declared_batch_kind_or_profile_that_disagrees(tmp_path):
    """The request's own batch kind and profile, when declared, must match the document.

    A v5 document claiming first-pass, a v6 document claiming retry and a v4 document claiming W1
    are all refused here - the profile belongs to exactly one schema, and the batch kind to exactly
    one profile.
    """

    from so101_demo.cli.macos_service_campaign import (
        BATCH_KIND_VARIABLE,
        EXECUTION_PROFILE_VARIABLE,
        ServiceCampaignError,
    )

    for config_path, worker_count, overrides, reason in (
        (V5_CONFIG, 1, {BATCH_KIND_VARIABLE: "FIRST_PASS"}, "PROFILE_BATCH_KIND_MISMATCH"),
        (V6_CONFIG, 1, {BATCH_KIND_VARIABLE: "FULL_RESTART_RETRY"},
         "PROFILE_BATCH_KIND_MISMATCH"),
        (V6_CONFIG, 1, {EXECUTION_PROFILE_VARIABLE: "MPS_W1_FULL_RESTART_RETRY"},
         "PROFILE_SCHEMA_MISMATCH"),
        (V4_CONFIG, 2, {EXECUTION_PROFILE_VARIABLE: "MPS_W1_FIRST_PASS"},
         "PROFILE_SCHEMA_MISMATCH"),
        (V4_CONFIG, 2, {BATCH_KIND_VARIABLE: "ADAPTIVE_POOL"}, "ADAPTIVE_UNSUPPORTED_ON_MACOS"),
    ):
        adapter, argv = _service_argv(tmp_path / f"{config_path.stem}-{len(overrides)}",
                                      config_path=config_path, worker_count=worker_count)
        environment = {**_service_environment(tmp_path), **overrides}
        with pytest.raises(ServiceCampaignError, match=reason):
            adapter.validate(adapter.build_parser().parse_args(argv), environment=environment)


def test_the_service_adapter_has_no_generic_batch_kind_or_profile_flag(tmp_path):
    """The dispatch key cannot be overridden from the command line."""

    adapter, _ = _service_argv(tmp_path, config_path=V4_CONFIG, worker_count=2)
    accepted = {option for action in adapter.build_parser()._actions
                for option in action.option_strings}

    assert "--batch-kind" not in accepted
    assert "--execution-profile" not in accepted
    for flag in ("--batch-kind", "--execution-profile"):
        with pytest.raises(SystemExit):
            adapter.build_parser().parse_args([flag, "FIRST_PASS"])


def test_the_service_adapter_refuses_a_v3_document_and_a_missing_w1_config(tmp_path):
    """v3 is still not executable on this platform, and the W1 routes need their documents."""

    from so101_demo.cli.macos_service_campaign import ServiceCampaignError

    environment = _service_environment(tmp_path)
    adapter, argv = _service_argv(tmp_path / "v3", config_path=PACKAGE / "config/mujoco/parallel_batch_v3.yaml",
                                  worker_count=2)
    with pytest.raises(ServiceCampaignError, match="CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION"):
        adapter.validate(adapter.build_parser().parse_args(argv), environment=environment)


def test_the_adapter_runs_the_fresh_guard_before_it_creates_the_campaign_child(
        tmp_path, monkeypatch, capsys):
    """The campaign child is never created when the fresh admission refuses."""

    from so101_demo.cli import macos_service_campaign as adapter
    from so101_demo.parallel_batch.start_guard import FAIL, GuardCheck, GuardResult
    from so101_demo.parallel_batch.start_guard_probe import darwin_guard_scope

    created: list[str] = []

    class _NeverCalledCampaign:
        def __init__(self, *args, **kwargs) -> None:
            created.append("campaign-child")

    monkeypatch.setattr(adapter, "OwnedCampaign", _NeverCalledCampaign)

    observed: list[dict] = []

    def refusing_guard(*, policy, batch_id, worker_count, **kwargs):
        observed.append({"policy_floor": policy.mps_minimum_headroom_bytes,
                         "batch_id": batch_id, "worker_count": worker_count,
                         "children_at_call": list(created)})
        return GuardResult(
            scope=darwin_guard_scope(batch_id=batch_id, worker_count=worker_count),
            status=FAIL, started_monotonic_s=0.0, completed_monotonic_s=0.0,
            checks={"mps_accelerator": GuardCheck(FAIL, "MPS_HEADROOM_BELOW_MINIMUM",
                                                  1, 1 << 30, "bytes")},
            snapshot=None, cleanup_state="CLEAR")

    adapter, argv = _service_argv(tmp_path, config_path=V6_CONFIG, worker_count=1)
    code = adapter.main(argv, guard=refusing_guard, environment=_service_environment(tmp_path))

    assert code != 0
    assert created == [], "no campaign child may exist when the admission refuses"
    assert observed and observed[0]["children_at_call"] == []
    assert observed[0]["policy_floor"] == 1 << 30
    assert observed[0]["worker_count"] == 1
    document = json.loads(capsys.readouterr().out)
    assert document["status"] == "REFUSED"
    assert document["stage"] == "start_guard"
    assert document["refusal"] == "MPS_HEADROOM_BELOW_MINIMUM"


def test_the_adapter_guard_is_only_asked_once_per_campaign(tmp_path, monkeypatch):
    """One fresh check per campaign start, not one per request field."""

    from so101_demo.cli import macos_service_campaign as adapter
    from so101_demo.parallel_batch.start_guard import FAIL, GuardCheck, GuardResult
    from so101_demo.parallel_batch.start_guard_probe import darwin_guard_scope

    monkeypatch.setattr(adapter, "OwnedCampaign", lambda *a, **k: None)
    calls: list[int] = []

    def refusing_guard(*, policy, batch_id, worker_count, **kwargs):
        calls.append(worker_count)
        return GuardResult(
            scope=darwin_guard_scope(batch_id=batch_id, worker_count=worker_count),
            status=FAIL, started_monotonic_s=0.0, completed_monotonic_s=0.0,
            checks={"probe": GuardCheck(FAIL, "RAM_BELOW_MINIMUM", 1, 1 << 30, "bytes")},
            snapshot=None, cleanup_state="CLEAR")

    adapter, argv = _service_argv(tmp_path, config_path=V5_CONFIG, worker_count=1)
    adapter.main(argv, guard=refusing_guard, environment=_service_environment(tmp_path))
    assert calls == [1]


def test_the_composed_campaign_accepts_a_w1_plan(tmp_path):
    """One composition drives both W1 profiles: one slot, one Worker, one domain."""

    from so101_demo.parallel_batch.w1_composition import compose_w1_retry

    plan = compose_w1_retry(
        config=load_execution_config(V5_CONFIG), config_path=V5_CONFIG, campaign_id="b-w1",
        batch_id="batch-w1", selected_point_ids=("p1",), evidence_root=tmp_path)
    supervisor = CampaignSupervisor("b-w1", state_root=tmp_path / "supervisor")
    campaign = MacosW2Campaign(plan=plan, address=object(), supervisor=supervisor,
                               ports=CampaignPorts(model_factories={}))

    assert campaign.plan.worker_count == 1
    assert campaign.plan.slots.slot_ids == ("slot-0",)
    assert campaign.plan.execution_profile == "MPS_W1_FULL_RESTART_RETRY"


def test_the_n1_verdict_requires_the_single_worker_happy_path():
    """A W1 pass is one Worker, three served requests on MPS and nothing refused."""

    from so101_demo.cli.macos_n1_first_pass import campaign_status as n1_status

    good = dict(cleanup_complete=True, results=[{}], workers=[{"status": "ACTIVE"}],
                served={"count": 3, "devices": ["mps"]}, refused=[])
    assert n1_status(**good) == "N1_CAMPAIGN_PASS"
    for change in (
        {"cleanup_complete": False},
        {"results": []},
        {"results": [{}, {}]},
        {"workers": [{"status": "STOPPED"}]},
        {"served": {"count": 2, "devices": ["mps"]}},
        {"served": {"count": 3, "devices": []}},
        {"refused": [{"reason": "DUPLICATE_REQUEST"}]},
    ):
        assert n1_status(**{**good, **change}) == "N1_CAMPAIGN_INCOMPLETE", change
