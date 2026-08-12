from __future__ import annotations

from dataclasses import replace

import pytest

from so101_mujoco_demo_py.contact_policy import (
    ApprovalRecord,
    ApprovedContactPolicy,
    ContactEvaluationPolicy,
    ContactPolicyFingerprint,
    ContactThresholds,
)
from so101_mujoco_demo_py.grasp_outcome import evaluate_grasp
from so101_mujoco_demo_py.simulation.types import (
    ContactEvidence,
    ObjectState,
    ReceivedSimulationEvidence,
    SimulationEvidence,
)


def approved_policy() -> ApprovedContactPolicy:
    return ApprovedContactPolicy(
        policy_id="light_cup_wall_pick-contact",
        thresholds=ContactThresholds(
            minimum_bilateral_force_n=0.50,
            maximum_compression_distance_m=0.0015,
            maximum_safe_force_n=5.0,
            maximum_hold_linear_speed_m_s=0.01,
            minimum_stable_hold_duration_s=0.30,
        ),
        evaluation=ContactEvaluationPolicy(0.10, 5),
        allowed_other_contact_bodies=frozenset({"table"}),
        fingerprint=ContactPolicyFingerprint(
            dependency_commit="2" * 40,
            model_sha256="a" * 64,
            scene_sha256="b" * 64,
            motion_policy_sha256="c" * 64,
            source_evidence_sha256="d" * 64,
        ),
        approval=ApprovalRecord("e" * 64, "user", "2026-08-12T12:00:00+08:00"),
    )


def contact(
    side: str,
    force_n: float,
    *,
    signed_distance_m: float = -0.0004,
    body2: str | None = None,
    geom2: str | None = None,
) -> ContactEvidence:
    return ContactEvidence(
        body1_id=1,
        geom1_id=2,
        body1="cup",
        geom1="cup_collision",
        body2_id=3,
        geom2_id=4,
        body2=body2 or ("fixed_finger" if side == "left" else "moving_jaw"),
        geom2=geom2 or f"{side}_fingertip_pad",
        position_world=(0.20, 0.0, 0.04),
        normal_world=(1.0, 0.0, 0.0),
        signed_distance_m=signed_distance_m,
        normal_force_n=force_n,
    )


def sample(
    index: int,
    *,
    session: str = "session-a",
    epoch: int = 3,
    sequence: int | None = None,
    time_step_s: float = 0.10,
    received_step_s: float = 0.01,
    left_force_n: float | None = 0.61,
    right_force_n: float | None = 0.62,
    maximum_force_n: float | None = None,
    signed_distance_m: float = -0.0004,
    speed_m_s: float = 0.001,
    truncated: bool = False,
    other: tuple[ContactEvidence, ...] = (),
) -> ReceivedSimulationEvidence:
    left = (
        (contact("left", left_force_n, signed_distance_m=signed_distance_m),)
        if left_force_n is not None
        else ()
    )
    right = (
        (contact("right", right_force_n, signed_distance_m=signed_distance_m),)
        if right_force_n is not None
        else ()
    )
    contacts = (*left, *right, *other)
    maximum = max((item.normal_force_n for item in contacts), default=0.0)
    if maximum_force_n is not None:
        maximum = maximum_force_n
        if contacts:
            strongest = max(contacts, key=lambda item: item.normal_force_n)
            replacement = replace(strongest, normal_force_n=maximum_force_n)
            contacts = tuple(replacement if item is strongest else item for item in contacts)
            left = tuple(item for item in contacts if item.geom2 == "left_fingertip_pad")
            right = tuple(item for item in contacts if item.geom2 == "right_fingertip_pad")
            other = tuple(
                item
                for item in contacts
                if item.geom2 not in {"left_fingertip_pad", "right_fingertip_pad"}
            )
    minimum = min((item.signed_distance_m for item in contacts), default=0.0)
    evidence = SimulationEvidence(
        simulation_time_s=10.0 + index * time_step_s,
        frame_id="world",
        publisher_sequence=100 + index if sequence is None else sequence,
        simulation_step=1000 + index,
        reset_epoch=epoch,
        simulation_session_id=session,
        paused=False,
        object_state=ObjectState(
            body_id=1,
            body="cup",
            position_world=(0.20, 0.0, 0.04),
            orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
            linear_velocity_world=(speed_m_s, 0.0, 0.0),
            angular_velocity_world=(0.0, 0.0, 0.0),
        ),
        has_contact=bool(contacts),
        minimum_signed_distance_m=minimum,
        maximum_normal_force_n=maximum,
        truncated=truncated,
        left_fingertip_contacts=left,
        right_fingertip_contacts=right,
        other_object_contacts=other,
    )
    return ReceivedSimulationEvidence(evidence, 20.0 + index * received_step_s)


def five_bilateral_samples(**changes) -> tuple[ReceivedSimulationEvidence, ...]:
    return tuple(sample(index, **changes) for index in range(5))


def evaluate(samples: tuple[ReceivedSimulationEvidence, ...]):
    return evaluate_grasp(
        samples=samples,
        policy=approved_policy(),
        expected_session_id="session-a",
        expected_reset_epoch=3,
        action_boundary_sequence=99,
        now_monotonic_s=20.05,
    )


def test_accepts_fresh_bilateral_window_inside_approved_bounds() -> None:
    result = evaluate(
        five_bilateral_samples(
            other=(contact("other", 0.1, body2="table", geom2="table_collision"),)
        )
    )

    assert result.success
    assert result.failure_code is None
    assert result.sample_count == 5
    assert result.duration_s == pytest.approx(0.40)
    assert result.metrics["minimum_left_force_n"] == pytest.approx(0.61)
    assert result.metrics["minimum_right_force_n"] == pytest.approx(0.62)
    assert len(result.telemetry) == 5


def test_allowed_table_penetration_does_not_define_fingertip_compression() -> None:
    result = evaluate(
        five_bilateral_samples(
            signed_distance_m=-0.0004,
            other=(
                contact(
                    "other",
                    0.1,
                    signed_distance_m=-0.004,
                    body2="table",
                    geom2="table_collision",
                ),
            ),
        )
    )

    assert result.success
    assert result.failure_code is None
    assert result.metrics["maximum_compression_distance_m"] == pytest.approx(0.0004)


@pytest.mark.parametrize(
    ("samples", "code"),
    (
        (five_bilateral_samples(sequence=99), "GRASP_STALE_EVIDENCE"),
        (five_bilateral_samples(session="session-b"), "GRASP_PROVENANCE_MISMATCH"),
        (five_bilateral_samples(epoch=4), "GRASP_PROVENANCE_MISMATCH"),
        (five_bilateral_samples(truncated=True), "GRASP_TRUNCATED_CONTACTS"),
        (
            five_bilateral_samples(
                other=(contact("other", 0.1, body2="wall", geom2="wall_collision"),)
            ),
            "GRASP_FORBIDDEN_CONTACT",
        ),
        (five_bilateral_samples(left_force_n=None), "GRASP_LEFT_CONTACT_MISSING"),
        (five_bilateral_samples(right_force_n=None), "GRASP_RIGHT_CONTACT_MISSING"),
        (five_bilateral_samples(left_force_n=0.49), "GRASP_FORCE_TOO_LOW"),
        (five_bilateral_samples(maximum_force_n=5.01), "GRASP_FORCE_TOO_HIGH"),
        (
            five_bilateral_samples(signed_distance_m=-0.0016),
            "GRASP_OVER_COMPRESSED",
        ),
        (five_bilateral_samples(speed_m_s=0.011), "GRASP_SLIPPING"),
        (five_bilateral_samples(time_step_s=0.05), "GRASP_DWELL_TOO_SHORT"),
    ),
)
def test_rejects_each_distinct_physical_failure(
    samples: tuple[ReceivedSimulationEvidence, ...], code: str
) -> None:
    assert evaluate(samples).failure_code == code


def test_failure_precedence_is_independent_of_fixture_order() -> None:
    result = evaluate(five_bilateral_samples(left_force_n=None, maximum_force_n=5.01))

    assert result.failure_code == "GRASP_LEFT_CONTACT_MISSING"


@pytest.mark.parametrize(
    ("fault_injection", "expected_code"),
    (
        ({"right_force_n": None}, "GRASP_RIGHT_CONTACT_MISSING"),
        ({"left_force_n": None}, "GRASP_LEFT_CONTACT_MISSING"),
    ),
)
def test_unilateral_fault_injection_can_never_prove_stable_grasp(
    fault_injection: dict[str, float | None], expected_code: str
) -> None:
    result = evaluate(five_bilateral_samples(**fault_injection))

    assert result.success is False
    assert result.failure_code == expected_code


def test_rejects_latest_receipt_older_than_policy_age() -> None:
    result = evaluate_grasp(
        samples=five_bilateral_samples(),
        policy=approved_policy(),
        expected_session_id="session-a",
        expected_reset_epoch=3,
        action_boundary_sequence=99,
        now_monotonic_s=20.20,
    )

    assert result.failure_code == "GRASP_STALE_EVIDENCE"
