"""Whole-pool rebuild after a Broker failure.

Task 9 of the macOS MPS / private IPC plan. The v4 design (section 6.3) refuses to let a surviving
Worker discover or validate a new endpoint, so a Broker failure is recovered by rebuilding the
entire W2 pool in a fixed order:

1. remove the affected request from the Coordinator's local active table, so its result can no
   longer be admitted;
2. mark the in-flight point as an **infrastructure** failure, never a business failure;
3. stop both Workers safely, and for a Worker already in motion cancel the controller goals and
   confirm absence;
4. terminate and reap the two Workers and the owned Broker by exact PID, birth identity and
   process group;
5. create a **new random campaign IPC path** and spawn plus warm up a new Broker;
6. spawn both Workers against that new path;
7. only after both Workers are ready, let the Coordinator decide whether to requeue.

The steps are recorded as an ordered trace. That trace is the evidence: a caller cannot skip the
controller-absence confirmation and still produce a "recovered" outcome, and a surviving Worker is
never handed a different endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

#: The ordered steps. The tuple is the contract: recovery is exactly this sequence.
RECOVERY_STEPS: tuple[str, ...] = (
    "remove_active_request",
    "mark_infrastructure_failure",
    "stop_workers_safely",
    "cancel_controller_goals",
    "confirm_controller_absence",
    "reap_owned_processes",
    "create_new_campaign_path",
    "spawn_broker",
    "await_broker_ready",
    "spawn_workers",
    "await_workers_ready",
    "coordinator_decision",
)

#: The point/attempt disposition for an interrupted inference. Deliberately not a business status.
INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


class PoolRecoveryError(RuntimeError):
    """The pool cannot be proven recovered. The caller must not continue the campaign."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class RecoveryFacts:
    """What the recovery needs to know and what it must prove, as plain data."""

    campaign_id: str
    failed_request_id: str
    point_id: str
    attempt: int
    #: True when at least one Worker had already begun executing motion for this point.
    motion_in_flight: bool
    broker_pid: int
    broker_birth_identity: int
    worker_processes: tuple[tuple[str, int, int], ...] = ()


@dataclass(frozen=True)
class RecoveryOutcome:
    """The result of one rebuild attempt, with the ordered trace that produced it."""

    recovered: bool
    trace: tuple[str, ...]
    infrastructure_failure: Mapping[str, object]
    new_campaign_id: str | None
    broker_ready: bool
    workers_ready: tuple[str, ...]
    requeue_allowed: bool
    controller_absence_confirmed: bool
    owned_processes_reaped: tuple[int, ...]
    detail: str = ""

    def to_document(self) -> dict:
        return {
            "recovered": self.recovered,
            "trace": list(self.trace),
            "infrastructure_failure": dict(self.infrastructure_failure),
            "new_campaign_id": self.new_campaign_id,
            "broker_ready": self.broker_ready,
            "workers_ready": list(self.workers_ready),
            "requeue_allowed": self.requeue_allowed,
            "controller_absence_confirmed": self.controller_absence_confirmed,
            "owned_processes_reaped": list(self.owned_processes_reaped),
            "detail": self.detail,
        }


@dataclass
class BrokerPoolRecovery:
    """The seven-step rebuild, expressed as injected ports so each step is independently provable.

    ``cancel_goals`` and ``confirm_absence`` are deliberately two separate ports. A single
    "cancel" call that also reports success would let a caller satisfy the design's
    controller-absence requirement without ever observing the controller, which is the exact
    failure mode this module exists to prevent.
    """

    facts: RecoveryFacts
    #: Remove the request from the Coordinator's local table and return the removed ids.
    remove_active_request: Callable[[str], Sequence[str]]
    #: Record the infrastructure disposition for the in-flight point.
    mark_infrastructure_failure: Callable[[str, int, str], None]
    #: Stop one Worker safely, by name.
    stop_worker: Callable[[str], bool]
    #: Ask the controllers to cancel. Returns whether the request was accepted.
    cancel_goals: Callable[[], bool]
    #: Independently observe controller goal absence.
    confirm_absence: Callable[[], bool]
    #: Terminate and reap the owned processes; returns the reaped PIDs.
    reap_owned_processes: Callable[[], Sequence[int]]
    #: Create a new random campaign IPC root; returns its path as a string.
    create_campaign_root: Callable[[], str]
    #: Spawn and warm up a new Broker against the new path; returns readiness.
    spawn_broker: Callable[[str], bool]
    #: Spawn one Worker against the new path.
    spawn_worker: Callable[[str, str], bool]
    #: Ask the Coordinator whether the point may be requeued.
    coordinator_decision: Callable[[Mapping[str, object]], bool]
    #: The Workers this campaign owns, by name.
    worker_names: tuple[str, ...] = ("w1", "w2")
    _trace: list[str] = field(default_factory=list)

    # -- internal helpers ----------------------------------------------------------------

    def _step(self, name: str) -> None:
        self._trace.append(name)

    def _fail(self, reason: str, detail: str, outcome: Mapping[str, object],
              absence: bool, reaped: Sequence[int]) -> RecoveryOutcome:
        return RecoveryOutcome(
            recovered=False, trace=tuple(self._trace),
            infrastructure_failure=dict(outcome), new_campaign_id=None, broker_ready=False,
            workers_ready=(), requeue_allowed=False, controller_absence_confirmed=absence,
            owned_processes_reaped=tuple(reaped), detail=f"{reason}: {detail}",
        )

    # -- the sequence --------------------------------------------------------------------

    def recover(self) -> RecoveryOutcome:
        """Run the rebuild in order, stopping at the first unprovable step."""

        facts = self.facts
        failure = {
            "kind": INFRASTRUCTURE_FAILURE,
            "campaign_id": facts.campaign_id,
            "request_id": facts.failed_request_id,
            "point_id": facts.point_id,
            "attempt": facts.attempt,
            "business_status": None,
            "broker_pid": facts.broker_pid,
            "broker_birth_identity": facts.broker_birth_identity,
        }

        # 1. The result must be inadmissible before anything else happens.
        removed = tuple(self.remove_active_request(facts.failed_request_id))
        self._step("remove_active_request")
        if facts.failed_request_id not in removed:
            return self._fail(
                "RECOVERY_REQUEST_NOT_REMOVED",
                f"local table still holds {facts.failed_request_id}",
                failure, absence=False, reaped=(),
            )

        # 2. Infrastructure, never a business failure.
        self.mark_infrastructure_failure(facts.point_id, facts.attempt, INFRASTRUCTURE_FAILURE)
        self._step("mark_infrastructure_failure")

        # 3. Stop both Workers safely.
        for name in self.worker_names:
            if not self.stop_worker(name):
                return self._fail("RECOVERY_WORKER_STOP_FAILED", name, failure,
                                  absence=False, reaped=())
        self._step("stop_workers_safely")

        # 4. Controller safety, but only when motion was actually in flight.
        absence_confirmed = True
        if facts.motion_in_flight:
            self.cancel_goals()
            self._step("cancel_controller_goals")
            absence_confirmed = bool(self.confirm_absence())
            self._step("confirm_controller_absence")
            if not absence_confirmed:
                return self._fail(
                    "RECOVERY_CONTROLLER_ABSENCE_UNPROVEN",
                    "controller goals could not be observed absent", failure,
                    absence=False, reaped=(),
                )

        # 5. Owned processes, by exact identity.
        reaped = tuple(self.reap_owned_processes())
        self._step("reap_owned_processes")
        expected = {facts.broker_pid} | {pid for _name, pid, _birth in facts.worker_processes}
        missing = sorted(expected - set(reaped))
        if missing:
            return self._fail(
                "RECOVERY_PROCESSES_NOT_REAPED", f"still owned: {missing}", failure,
                absence=absence_confirmed, reaped=reaped,
            )

        # 6. A brand-new campaign path. A surviving Worker is never re-pointed at it.
        new_campaign = str(self.create_campaign_root())
        self._step("create_new_campaign_path")
        if not new_campaign or new_campaign == facts.campaign_id:
            return self._fail("RECOVERY_PATH_REUSED", new_campaign, failure,
                              absence=absence_confirmed, reaped=reaped)

        # 7. Broker first, then both Workers, and only then the Coordinator's decision.
        if not self.spawn_broker(new_campaign):
            self._step("spawn_broker")
            return self._fail("RECOVERY_BROKER_NOT_READY", new_campaign, failure,
                              absence=absence_confirmed, reaped=reaped)
        self._step("spawn_broker")
        self._step("await_broker_ready")

        ready: list[str] = []
        for name in self.worker_names:
            if not self.spawn_worker(name, new_campaign):
                self._step("spawn_workers")
                return self._fail("RECOVERY_WORKER_NOT_READY", name, failure,
                                  absence=absence_confirmed, reaped=reaped)
            ready.append(name)
        self._step("spawn_workers")
        self._step("await_workers_ready")

        failure["new_campaign_id"] = new_campaign
        requeue = bool(self.coordinator_decision(dict(failure)))
        self._step("coordinator_decision")

        recovered = requeue and len(ready) == len(self.worker_names)
        return RecoveryOutcome(
            recovered=recovered, trace=tuple(self._trace), infrastructure_failure=failure,
            new_campaign_id=new_campaign, broker_ready=True, workers_ready=tuple(ready),
            requeue_allowed=requeue, controller_absence_confirmed=absence_confirmed,
            owned_processes_reaped=reaped,
            detail="" if recovered else "the Coordinator declined to requeue",
        )
