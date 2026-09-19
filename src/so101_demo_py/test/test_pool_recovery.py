"""Whole-pool rebuild after a Broker failure: order, safety gates and the requeue decision.

Task 9 of the macOS MPS / private IPC plan. These tests drive the recovery through injected ports
that record their own call order, so the *sequence* is asserted rather than described, and each
safety gate gets its own refusal case.
"""

import pytest

from so101_demo.parallel_batch.pool_recovery import (
    INFRASTRUCTURE_FAILURE,
    RECOVERY_STEPS,
    BrokerPoolRecovery,
    PoolRecoveryError,
    RecoveryFacts,
)

BROKER_PID = 5001
BROKER_BIRTH = 9001
WORKERS = (("w1", 6001, 9101), ("w2", 6002, 9102))


class Ports:
    """Recording ports. Every port appends its name to one shared trace."""

    def __init__(self, *, motion_in_flight=True, absence=True, dropped=None,
                 reaped=None, broker_ready=True, worker_ready=True, requeue=True,
                 new_campaign="b-newcampaign", worker_ready_after=None):
        self.trace = []
        self.motion_in_flight = motion_in_flight
        self.absence = absence
        self.dropped = ["req-1"] if dropped is None else list(dropped)
        self.reaped = ([BROKER_PID] + [pid for _name, pid, _birth in WORKERS]
                       if reaped is None else list(reaped))
        self.broker_ready = broker_ready
        self.worker_ready = worker_ready
        #: When set, the Nth (1-based) worker spawn fails: a deterministic partial rebuild.
        self.worker_ready_after = worker_ready_after
        self.worker_spawn_calls = 0
        self.requeue = requeue
        self.new_campaign = new_campaign
        self.stopped = []
        self.infrastructure = []
        self.decision_payload = None
        self.spawned_workers = []

    # -- ports ---------------------------------------------------------------------------

    def remove_active_request(self, request_id):
        self.trace.append("remove_active_request")
        return tuple(self.dropped)

    def mark_infrastructure_failure(self, point_id, attempt, kind):
        self.trace.append("mark_infrastructure_failure")
        self.infrastructure.append((point_id, attempt, kind))

    def stop_worker(self, name):
        self.trace.append(f"stop_worker:{name}")
        self.stopped.append(name)
        return True

    def cancel_goals(self):
        self.trace.append("cancel_goals")
        return True

    def confirm_absence(self):
        self.trace.append("confirm_absence")
        return self.absence

    def reap_owned_processes(self):
        self.trace.append("reap_owned_processes")
        return tuple(self.reaped)

    def create_campaign_root(self):
        self.trace.append("create_campaign_root")
        return self.new_campaign

    def spawn_broker(self, campaign):
        self.trace.append(f"spawn_broker:{campaign}")
        return self.broker_ready

    def spawn_worker(self, name, campaign):
        self.trace.append(f"spawn_worker:{name}:{campaign}")
        self.worker_spawn_calls += 1
        self.spawned_workers.append((name, campaign))
        if self.worker_ready_after is not None and \
                self.worker_spawn_calls > self.worker_ready_after:
            return False
        return self.worker_ready

    def coordinator_decision(self, payload):
        self.trace.append("coordinator_decision")
        self.decision_payload = payload
        return self.requeue


def _recovery(ports, **facts_overrides):
    facts = {
        "campaign_id": "b-oldcampaign",
        "failed_request_id": "req-1",
        "point_id": "p1",
        "attempt": 2,
        "motion_in_flight": ports.motion_in_flight,
        "broker_pid": BROKER_PID,
        "broker_birth_identity": BROKER_BIRTH,
        "worker_processes": WORKERS,
    }
    facts.update(facts_overrides)
    return BrokerPoolRecovery(
        facts=RecoveryFacts(**facts),
        remove_active_request=ports.remove_active_request,
        mark_infrastructure_failure=ports.mark_infrastructure_failure,
        stop_worker=ports.stop_worker,
        cancel_goals=ports.cancel_goals,
        confirm_absence=ports.confirm_absence,
        reap_owned_processes=ports.reap_owned_processes,
        create_campaign_root=ports.create_campaign_root,
        spawn_broker=ports.spawn_broker,
        spawn_worker=ports.spawn_worker,
        coordinator_decision=ports.coordinator_decision,
    )


# --------------------------------------------------------------------------------------
# the declared order
# --------------------------------------------------------------------------------------


def test_recovery_steps_are_the_declared_closed_sequence():
    """The step list is the contract a caller can check against."""

    assert RECOVERY_STEPS == (
        "remove_active_request", "mark_infrastructure_failure", "stop_workers_safely",
        "cancel_controller_goals", "confirm_controller_absence", "reap_owned_processes",
        "create_new_campaign_path", "spawn_broker", "await_broker_ready", "spawn_workers",
        "await_workers_ready", "coordinator_decision",
    )
    assert INFRASTRUCTURE_FAILURE == "INFRASTRUCTURE_FAILURE"


def test_the_happy_path_follows_the_order_exactly():
    """Every port is called, in order, and the outcome is a proven recovery."""

    ports = Ports()
    outcome = _recovery(ports).recover()
    assert outcome.recovered is True
    assert outcome.requeue_allowed is True
    assert outcome.broker_ready is True
    assert outcome.workers_ready == ("w1", "w2")
    assert outcome.controller_absence_confirmed is True
    assert outcome.owned_processes_reaped == (BROKER_PID, 6001, 6002)
    assert ports.trace == [
        "remove_active_request",
        "mark_infrastructure_failure",
        "stop_worker:w1",
        "stop_worker:w2",
        "cancel_goals",
        "confirm_absence",
        "reap_owned_processes",
        "create_campaign_root",
        f"spawn_broker:{ports.new_campaign}",
        f"spawn_worker:w1:{ports.new_campaign}",
        f"spawn_worker:w2:{ports.new_campaign}",
        "coordinator_decision",
    ]
    # The outcome's trace is the declared step list, in order, and the serialized document
    # carries exactly that. The ports trace above is the same run with the per-worker and
    # per-broker calls spelled out; its order is what the equality above pinned down.
    assert outcome.trace == RECOVERY_STEPS, outcome.trace
    assert outcome.to_document()["trace"] == list(RECOVERY_STEPS)
    assert outcome.trace == RECOVERY_STEPS, outcome.trace


def test_without_motion_in_flight_the_controller_ports_are_not_called():
    """A stop during LEASED/INITIALIZING has no controller goal to cancel or confirm."""

    ports = Ports(motion_in_flight=False)
    outcome = _recovery(ports).recover()
    assert outcome.recovered is True
    assert "cancel_goals" not in ports.trace
    assert "confirm_absence" not in ports.trace
    assert outcome.controller_absence_confirmed is True


# --------------------------------------------------------------------------------------
# safety gates
# --------------------------------------------------------------------------------------


def test_the_request_is_removed_before_anything_else_happens():
    """If the local table will not give up the request, recovery does not even start."""

    ports = Ports(dropped=[])
    outcome = _recovery(ports).recover()
    assert outcome.recovered is False
    assert "RECOVERY_REQUEST_NOT_REMOVED" in outcome.detail
    assert ports.trace == ["remove_active_request"], ports.trace
    assert ports.infrastructure == []
    assert ports.stopped == []


def test_the_point_is_recorded_as_an_infrastructure_failure_not_a_business_one():
    """The disposition carries no business status and points at the failed attempt."""

    ports = Ports()
    outcome = _recovery(ports).recover()
    assert ports.infrastructure == [("p1", 2, INFRASTRUCTURE_FAILURE)]
    document = outcome.infrastructure_failure
    assert document["kind"] == INFRASTRUCTURE_FAILURE
    assert document["business_status"] is None
    assert document["point_id"] == "p1" and document["attempt"] == 2
    assert document["request_id"] == "req-1"
    assert document["new_campaign_id"] == ports.new_campaign


def test_unproven_controller_absence_stops_the_rebuild_before_any_spawn():
    """Cancelling is not enough: absence must be observed, or nothing new is spawned."""

    ports = Ports(absence=False)
    outcome = _recovery(ports).recover()
    assert outcome.recovered is False
    assert "RECOVERY_CONTROLLER_ABSENCE_UNPROVEN" in outcome.detail
    assert outcome.controller_absence_confirmed is False
    assert "reap_owned_processes" not in ports.trace
    assert "create_campaign_root" not in ports.trace
    assert ports.spawned_workers == []
    assert outcome.new_campaign_id is None


def test_an_unreaped_owned_process_stops_the_rebuild():
    """A process we cannot prove dead blocks the new pool: it could still hold the old socket."""

    ports = Ports(reaped=[BROKER_PID, 6001])
    outcome = _recovery(ports).recover()
    assert outcome.recovered is False
    assert "RECOVERY_PROCESSES_NOT_REAPED" in outcome.detail
    assert "6002" in outcome.detail
    assert "create_campaign_root" not in ports.trace
    assert outcome.owned_processes_reaped == (BROKER_PID, 6001)


def test_reusing_the_old_campaign_path_is_refused():
    """A restart must create a new random path; the old one is never rebound."""

    ports = Ports(new_campaign="b-oldcampaign")
    outcome = _recovery(ports).recover()
    assert outcome.recovered is False
    assert "RECOVERY_PATH_REUSED" in outcome.detail
    assert f"spawn_broker:{ports.new_campaign}" not in ports.trace


def test_a_broker_that_never_becomes_ready_stops_before_any_worker_spawns():
    """Workers are only started once the new Broker is warm."""

    ports = Ports(broker_ready=False)
    outcome = _recovery(ports).recover()
    assert outcome.recovered is False
    assert "RECOVERY_BROKER_NOT_READY" in outcome.detail
    assert ports.spawned_workers == []
    assert outcome.broker_ready is False


def test_the_second_worker_failing_leaves_no_half_ready_claim():
    """A partially rebuilt pool is not a recovery."""

    ports = Ports(worker_ready_after=1)
    outcome = _recovery(ports).recover()
    assert outcome.recovered is False
    assert "RECOVERY_WORKER_NOT_READY" in outcome.detail
    # No partial pool is ever reported as ready, whatever prefix succeeded.
    assert len(outcome.workers_ready) < 2
    assert outcome.requeue_allowed is False
    assert "coordinator_decision" not in ports.trace


def test_the_coordinator_can_decline_the_requeue_after_a_successful_rebuild():
    """Rebuilding the pool and requeueing the point are separate decisions."""

    ports = Ports(requeue=False)
    outcome = _recovery(ports).recover()
    assert outcome.recovered is False
    assert outcome.broker_ready is True
    assert outcome.workers_ready == ("w1", "w2")
    assert outcome.requeue_allowed is False
    assert "declined to requeue" in outcome.detail
    assert ports.decision_payload["new_campaign_id"] == ports.new_campaign
    assert ports.decision_payload["kind"] == INFRASTRUCTURE_FAILURE


def test_workers_are_always_pointed_at_the_new_path_and_never_the_old_one():
    """No surviving Worker ever receives the old endpoint."""

    ports = Ports()
    _recovery(ports).recover()
    assert {campaign for _name, campaign in ports.spawned_workers} == {ports.new_campaign}
    assert all("b-oldcampaign" not in entry for entry in ports.trace if entry.startswith("spawn_"))


def test_the_recovery_facts_are_a_closed_model():
    """The facts the recovery needs are explicit, so a caller cannot omit the identity."""

    with pytest.raises(TypeError):
        RecoveryFacts(campaign_id="b", failed_request_id="r", point_id="p", attempt=1,
                      motion_in_flight=False, broker_pid=BROKER_PID)
    facts = RecoveryFacts(campaign_id="b", failed_request_id="r", point_id="p", attempt=1,
                          motion_in_flight=False, broker_pid=BROKER_PID,
                          broker_birth_identity=BROKER_BIRTH)
    assert facts.worker_processes == ()
