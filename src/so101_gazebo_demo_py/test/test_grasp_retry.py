from so101_gazebo_demo_py.domain import ActionResult, ActionStatus, Failure, FailureCategory
from so101_gazebo_demo_py.grasp.evidence_store import PhysicalGraspEvidence, RetryPhase
from so101_gazebo_demo_py.grasp.retry import PhysicalGraspRetryCoordinator


class Store:
    def __init__(self): self.values=[]; self.cleared=False
    def commit(self, value): self.values.append(value); return None
    def reset_for_fresh_run(self): self.cleared=True; return None


def evidence(attempt=1, missing=0, target=-.04):
    return PhysicalGraspEvidence("s", "f", attempt, missing, target, target-.006, RetryPhase.IDLE, {}, {})


def failure(code): return Failure(FailureCategory.POSTCONDITION, code, code)


def test_retry_persists_every_phase_and_keeps_fixed_seating_preload() -> None:
    store=Store(); calls=[]
    coordinator=PhysicalGraspRetryCoordinator(store, lambda phase, q6: calls.append((phase, q6)) or ActionResult(ActionStatus.SUCCEEDED))
    result=coordinator.retry(failure("PHYSICAL_GRASP_FIXED_CONTACT_MISSING"), evidence())
    assert result.status is ActionStatus.SUCCEEDED
    assert [item.phase for item in store.values] == [RetryPhase.OPEN_PENDING, RetryPhase.DESCEND_PENDING, RetryPhase.CLOSE_PENDING, RetryPhase.LIFT_PENDING, RetryPhase.VERIFY_PENDING, RetryPhase.COMPLETE]
    assert store.values[-1].current_reclose_target_q6 == -.041
    assert store.values[-1].micro_lift_preload_target_q6 == -.047
    assert store.cleared


def test_contact_present_keeps_target_and_nonretryable_or_fifth_failure_stops() -> None:
    store=Store(); coordinator=PhysicalGraspRetryCoordinator(store, lambda phase,q6: ActionResult(ActionStatus.SUCCEEDED))
    present=coordinator.retry(failure("PHYSICAL_GRASP_OBJECT_DRIFT"), evidence())
    assert present.status is ActionStatus.SUCCEEDED
    assert store.values[-1].current_reclose_target_q6 == -.04
    assert coordinator.retry(failure("PHYSICAL_GRASP_PENETRATION_EXCEEDED"), evidence()).status is ActionStatus.FAILED
    exhausted=coordinator.retry(failure("PHYSICAL_GRASP_FIXED_CONTACT_MISSING"), evidence(5,4,-.044))
    assert exhausted.failure.code == "PHYSICAL_GRASP_FIXED_CONTACT_MISSING"
    assert exhausted.failure.metrics["attempt_count"] == 5.0
