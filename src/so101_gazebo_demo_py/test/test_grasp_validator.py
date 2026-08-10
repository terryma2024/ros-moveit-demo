from dataclasses import replace

from so101_gazebo_demo.domain import ActionStatus
from so101_gazebo_demo.grasp.stabilizer import GraspSample, StabilizedGraspEvidence
from so101_gazebo_demo.grasp.validator import PhysicalGraspValidator, PhysicalGraspValidationPolicy


def evidence(z=.2, **changes):
    session = changes.pop("simulation_session_id", "s")
    fingerprint = changes.pop("policy_bundle_sha256", "f")
    sample = GraspSample(session, fingerprint, 1., True, True, "wall_near", frozenset(), .0007, -.04, 0., .03, (0., 0., z))
    sample = replace(sample, **changes)
    return StabilizedGraspEvidence(session, fingerprint, 3, sample, None)


POLICY = PhysicalGraspValidationPolicy(
    required_wall="wall_near", forbidden_collisions=frozenset({"rim", "bottom", "wall_opposite"}),
    max_penetration_m=.0013, q6_target=-.04, q6_position_tolerance=.001,
    q6_velocity_tolerance=.01, min_contact_height_m=.02, max_contact_height_m=.05,
    max_object_drift_m=.001, micro_lift_m=.002, lift_tolerance_m=.0005,
)


def code(before=None, after=None):
    return PhysicalGraspValidator(POLICY).validate(before or evidence(), after or evidence(.202)).failure.code


def test_requires_bilateral_required_wall_clean_contact_and_stopped_q6() -> None:
    assert code(before=evidence(fixed_contact=False)) == "PHYSICAL_GRASP_FIXED_CONTACT_MISSING"
    assert code(before=evidence(moving_contact=False)) == "PHYSICAL_GRASP_MOVING_CONTACT_MISSING"
    assert code(before=evidence(required_wall="wall_opposite")) == "PHYSICAL_GRASP_REQUIRED_WALL_MISSING"
    assert code(before=evidence(forbidden_contacts=frozenset({"rim"}))) == "PHYSICAL_GRASP_FORBIDDEN_CONTACT"
    assert code(before=evidence(penetration_m=.00131)) == "PHYSICAL_GRASP_PENETRATION_EXCEEDED"
    assert code(before=evidence(q6_position=-.038)) == "PHYSICAL_GRASP_Q6_POSITION"
    assert code(before=evidence(q6_velocity=.02)) == "PHYSICAL_GRASP_Q6_MOVING"
    assert code(before=evidence(contact_height_m=.01)) == "PHYSICAL_GRASP_CONTACT_HEIGHT"


def test_requires_two_mm_world_z_lift_without_lateral_drift() -> None:
    assert PhysicalGraspValidator(POLICY).validate(evidence(), evidence(.202)).status is ActionStatus.SUCCEEDED
    assert code(after=evidence(.201)) == "PHYSICAL_GRASP_MICRO_LIFT"
    assert code(after=evidence(.202, object_position=(.002, 0., .202))) == "PHYSICAL_GRASP_OBJECT_DRIFT"
    assert code(after=evidence(.202, simulation_session_id="other")) == "PHYSICAL_GRASP_EVIDENCE_SESSION_MISMATCH"
