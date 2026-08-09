"""Exact pre-attachment physical grasp gate."""

from dataclasses import dataclass
import math

from ..domain import ActionResult, ActionStatus, Failure, FailureCategory
from .stabilizer import StabilizedGraspEvidence


@dataclass(frozen=True, slots=True)
class PhysicalGraspValidationPolicy:
    required_wall: str
    forbidden_collisions: frozenset[str]
    max_penetration_m: float
    q6_target: float
    q6_position_tolerance: float
    q6_velocity_tolerance: float
    min_contact_height_m: float
    max_contact_height_m: float
    max_object_drift_m: float
    micro_lift_m: float = .002
    lift_tolerance_m: float = .0005


class PhysicalGraspValidator:
    def __init__(self, policy: PhysicalGraspValidationPolicy) -> None: self.policy = policy

    def validate(self, before: StabilizedGraspEvidence, after: StabilizedGraspEvidence) -> ActionResult:
        def fail(code: str, message: str | None = None) -> ActionResult:
            return ActionResult(
                ActionStatus.FAILED,
                Failure(FailureCategory.POSTCONDITION, code, message or code),
            )
        if before.failure: return ActionResult(ActionStatus.FAILED, before.failure)
        if after.failure: return ActionResult(ActionStatus.FAILED, after.failure)
        if before.simulation_session_id != after.simulation_session_id: return fail("PHYSICAL_GRASP_EVIDENCE_SESSION_MISMATCH")
        if before.policy_bundle_sha256 != after.policy_bundle_sha256: return fail("PHYSICAL_GRASP_EVIDENCE_FINGERPRINT_MISMATCH")
        first, second = before.representative, after.representative
        for sample in (first, second):
            if not sample.fixed_contact: return fail("PHYSICAL_GRASP_FIXED_CONTACT_MISSING")
            if not sample.moving_contact: return fail("PHYSICAL_GRASP_MOVING_CONTACT_MISSING")
            if sample.required_wall != self.policy.required_wall: return fail("PHYSICAL_GRASP_REQUIRED_WALL_MISSING")
            if sample.forbidden_contacts & self.policy.forbidden_collisions: return fail("PHYSICAL_GRASP_FORBIDDEN_CONTACT")
            if sample.penetration_m > self.policy.max_penetration_m: return fail("PHYSICAL_GRASP_PENETRATION_EXCEEDED")
            if abs(sample.q6_position-self.policy.q6_target)>self.policy.q6_position_tolerance: return fail("PHYSICAL_GRASP_Q6_POSITION")
            if abs(sample.q6_velocity)>self.policy.q6_velocity_tolerance: return fail("PHYSICAL_GRASP_Q6_MOVING")
            if not self.policy.min_contact_height_m <= sample.contact_height_m <= self.policy.max_contact_height_m: return fail("PHYSICAL_GRASP_CONTACT_HEIGHT")
        dx=second.object_position[0]-first.object_position[0]; dy=second.object_position[1]-first.object_position[1]
        if math.hypot(dx,dy)>self.policy.max_object_drift_m: return fail("PHYSICAL_GRASP_OBJECT_DRIFT")
        lift=second.object_position[2]-first.object_position[2]
        if abs(lift-self.policy.micro_lift_m)>self.policy.lift_tolerance_m: return fail("PHYSICAL_GRASP_MICRO_LIFT")
        return ActionResult(ActionStatus.SUCCEEDED)
