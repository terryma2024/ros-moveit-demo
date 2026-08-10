"""Durable, five-attempt physical grasp retry coordinator."""

from dataclasses import replace
from typing import Any, Callable

from ..domain import ActionResult, ActionStatus, Failure
from .evidence_store import PhysicalGraspEvidence, RetryPhase


CONTACT_MISSING = frozenset({
    "PHYSICAL_GRASP_FIXED_CONTACT_MISSING", "PHYSICAL_GRASP_MOVING_CONTACT_MISSING",
    "PHYSICAL_GRASP_REQUIRED_WALL_MISSING",
})
RETRYABLE = CONTACT_MISSING | frozenset({"PHYSICAL_GRASP_OBJECT_DRIFT", "PHYSICAL_GRASP_MICRO_LIFT", "PHYSICAL_GRASP_Q6_MOVING"})
PHASES = (RetryPhase.OPEN_PENDING, RetryPhase.DESCEND_PENDING, RetryPhase.CLOSE_PENDING, RetryPhase.LIFT_PENDING, RetryPhase.VERIFY_PENDING)


class PhysicalGraspRetryCoordinator:
    def __init__(self, store: Any, side_effect: Callable[[RetryPhase, float], ActionResult]) -> None:
        self._store, self._side_effect = store, side_effect

    def retry(self, failure: Failure, evidence: PhysicalGraspEvidence) -> ActionResult:
        if failure.code not in RETRYABLE: return ActionResult(ActionStatus.FAILED, failure)
        if evidence.attempt_index >= 5:
            exhausted = replace(failure, metrics={**failure.metrics, "attempt_count": 5.0})
            return ActionResult(ActionStatus.FAILED, exhausted)
        missing_count = evidence.contact_missing_count + int(failure.code in CONTACT_MISSING)
        tightening = min(.004, missing_count * .001)
        target = evidence.current_reclose_target_q6
        if failure.code in CONTACT_MISSING:
            target = max(evidence.current_reclose_target_q6 - .001, evidence.current_reclose_target_q6 - (.004-tightening+.001))
        current = replace(evidence, attempt_index=evidence.attempt_index+1,
                          contact_missing_count=missing_count, current_reclose_target_q6=target,
                          micro_lift_preload_target_q6=target-.006)
        for phase in PHASES:
            current = replace(current, phase=phase)
            store_failure = self._store.commit(current)
            if store_failure: return ActionResult(ActionStatus.FAILED, store_failure)
            result = self._side_effect(phase, current.micro_lift_preload_target_q6 if phase is RetryPhase.LIFT_PENDING else target)
            if result.status is not ActionStatus.SUCCEEDED: return result
        current = replace(current, phase=RetryPhase.COMPLETE)
        store_failure = self._store.commit(current)
        if store_failure: return ActionResult(ActionStatus.FAILED, store_failure)
        clear_failure = self._store.reset_for_fresh_run()
        if clear_failure: return ActionResult(ActionStatus.FAILED, clear_failure)
        return ActionResult(ActionStatus.SUCCEEDED)
