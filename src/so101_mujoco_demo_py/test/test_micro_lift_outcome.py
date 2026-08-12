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
from so101_mujoco_demo_py.grasp_outcome import (
    CarryPolicy,
    CarrySample,
    MicroLiftPolicy,
    TransportPolicy,
    evaluate_micro_lift,
)


def contact_policy() -> ApprovedContactPolicy:
    return ApprovedContactPolicy(
        "contact",
        ContactThresholds(0.50, 0.0015, 5.0, 0.01, 0.30),
        ContactEvaluationPolicy(0.10, 5),
        frozenset({"table"}),
        ContactPolicyFingerprint("2" * 40, "a" * 64, "b" * 64, "c" * 64, "d" * 64),
        ApprovalRecord("e" * 64, "user", "2026-08-12T12:00:00+08:00"),
    )


def carry_policy() -> CarryPolicy:
    return CarryPolicy(
        micro_lift=MicroLiftPolicy(0.0015, 0.0035, 0.0015, 0.001, 0.001, 0.30),
        transport=TransportPolicy(0.005, 0.070, 0.001),
        max_observation_age_s=0.10,
        catastrophic_workspace_bounds_m=(-0.21, -0.46, 0.12, 0.21, 0.06, 0.30),
    )


def samples(*, time_step_s: float = 0.10) -> tuple[CarrySample, ...]:
    values = []
    for index in range(5):
        lift = 0.0005 * index
        values.append(
            CarrySample(
                segment="MICRO_LIFT",
                simulation_session_id="session-a",
                reset_epoch=3,
                publisher_sequence=100 + index,
                simulation_time_s=10.0 + index * time_step_s,
                received_monotonic_s=20.0 + index * 0.01,
                cup_pose_xyz_xyzw=(0.02, -0.28, 0.165 + lift, 0.0, 0.0, 0.0, 1.0),
                tcp_pose_xyz_xyzw=(0.02, -0.28, 0.245 + lift, 0.0, 0.0, 0.0, 1.0),
                table_contact=index == 0,
                table_clearance_m=0.0 if index == 0 else lift,
                left_force_n=0.61,
                right_force_n=0.62,
                maximum_force_n=0.62,
                forbidden_contact=False,
            )
        )
    return tuple(values)


def evaluate(values: tuple[CarrySample, ...], *, now: float = 20.05):
    return evaluate_micro_lift(
        values,
        contact_policy(),
        carry_policy(),
        "session-a",
        3,
        99,
        now,
    )


def changed(values: tuple[CarrySample, ...], index: int, **changes) -> tuple[CarrySample, ...]:
    result = list(values)
    result[index] = replace(result[index], **changes)
    return tuple(result)


def test_accepts_correlated_cup_and_tcp_micro_lift() -> None:
    result = evaluate(samples())

    assert result.success
    assert result.failure_code is None
    assert result.metrics["cup_lift_m"] == pytest.approx(0.002)
    assert result.metrics["tcp_lift_m"] == pytest.approx(0.002)
    assert result.metrics["maximum_relative_position_drift_m"] == pytest.approx(0.0)
    assert result.sample_count == 5


@pytest.mark.parametrize(
    ("mutate", "code"),
    (
        (
            lambda values: changed(
                values,
                -1,
                cup_pose_xyz_xyzw=(0.02, -0.28, 0.169, 0.0, 0.0, 0.0, 1.0),
            ),
            "MICRO_LIFT_CUP_TELEPORT",
        ),
        (
            lambda values: tuple(
                replace(item, cup_pose_xyz_xyzw=(0.02, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0))
                for item in values
            ),
            "MICRO_LIFT_CUP_NOT_LIFTED",
        ),
        (
            lambda values: tuple(
                replace(item, tcp_pose_xyz_xyzw=(0.02, -0.28, 0.245, 0.0, 0.0, 0.0, 1.0))
                for item in values
            ),
            "MICRO_LIFT_TCP_NOT_LIFTED",
        ),
        (lambda values: changed(values, -1, table_contact=True), "MICRO_LIFT_TABLE_SUPPORTED"),
        (
            lambda values: changed(
                values,
                -1,
                cup_pose_xyz_xyzw=(0.022, -0.28, 0.167, 0.0, 0.0, 0.0, 1.0),
            ),
            "MICRO_LIFT_LATERAL_DRIFT",
        ),
        (
            lambda values: changed(
                values,
                -1,
                tcp_pose_xyz_xyzw=(0.02, -0.28, 0.249, 0.0, 0.0, 0.0, 1.0),
            ),
            "MICRO_LIFT_RELATIVE_DRIFT",
        ),
        (lambda values: changed(values, 2, left_force_n=0.0), "CARRY_LEFT_CONTACT_MISSING"),
        (lambda values: changed(values, 2, maximum_force_n=5.1), "CARRY_FORCE_TOO_HIGH"),
        (lambda values: changed(values, 2, forbidden_contact=True), "CARRY_FORBIDDEN_CONTACT"),
        (
            lambda values: changed(values, 2, simulation_session_id="session-b"),
            "CARRY_PROVENANCE_MISMATCH",
        ),
        (
            lambda values: changed(values, 2, reset_epoch=4),
            "CARRY_PROVENANCE_MISMATCH",
        ),
        (
            lambda values: changed(
                values,
                2,
                cup_pose_xyz_xyzw=(0.30, -0.28, 0.166, 0.0, 0.0, 0.0, 1.0),
            ),
            "CARRY_WORKSPACE_EXIT",
        ),
        (
            lambda values: changed(values, -1, table_clearance_m=0.0005),
            "MICRO_LIFT_TABLE_CLEARANCE",
        ),
    ),
)
def test_rejects_noncausal_or_unsafe_micro_lift(mutate, code: str) -> None:
    assert evaluate(mutate(samples())).failure_code == code


def test_rejects_stale_receipt_and_short_dwell() -> None:
    assert evaluate(samples(), now=20.20).failure_code == "CARRY_STALE_EVIDENCE"
    assert evaluate(samples(time_step_s=0.05)).failure_code == "MICRO_LIFT_DWELL_TOO_SHORT"


def test_rejects_intermediate_cup_teleport_even_when_final_pose_recovers() -> None:
    values = changed(
        samples(),
        2,
        cup_pose_xyz_xyzw=(0.02, -0.28, 0.170, 0.0, 0.0, 0.0, 1.0),
        tcp_pose_xyz_xyzw=(0.02, -0.28, 0.250, 0.0, 0.0, 0.0, 1.0),
        table_clearance_m=0.005,
    )

    assert evaluate(values).failure_code == "MICRO_LIFT_CUP_TELEPORT"


def test_rejects_table_recontact_before_final_clearance() -> None:
    assert evaluate(changed(samples(), 3, table_contact=True)).failure_code == (
        "MICRO_LIFT_TABLE_SUPPORTED"
    )


@pytest.mark.parametrize(
    "changes",
    (
        {"publisher_sequence": -1},
        {"table_clearance_m": -0.001},
        {"left_force_n": float("nan")},
        {"maximum_force_n": 0.1},
        {"cup_pose_xyz_xyzw": (0.02, -0.28, float("nan"), 0.0, 0.0, 0.0, 1.0)},
    ),
)
def test_carry_sample_rejects_invalid_atomic_measurements(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(samples()[0], **changes)
