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
    evaluate_transport,
)

SEGMENTS = ("LIFT", "MOVE_ABOVE_PLACE", "DESCEND_TO_PLACE")


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
        MicroLiftPolicy(0.0015, 0.0035, 0.0015, 0.001, 0.001, 0.30),
        TransportPolicy(0.005, 0.070, 0.001),
        0.10,
        (-0.21, -0.46, 0.12, 0.21, 0.06, 0.30),
    )


def samples() -> tuple[CarrySample, ...]:
    result = []
    for index in range(6):
        segment = SEGMENTS[index // 2]
        x = 0.02 - index * 0.015
        z = 0.18 + (0.01 if segment != "DESCEND_TO_PLACE" else 0.0)
        result.append(
            CarrySample(
                segment=segment,
                simulation_session_id="session-a",
                reset_epoch=3,
                publisher_sequence=100 + index,
                simulation_time_s=10.0 + index * 0.10,
                received_monotonic_s=20.0 + index * 0.01,
                cup_pose_xyz_xyzw=(x, -0.28, z, 0.0, 0.0, 0.0, 1.0),
                tcp_pose_xyz_xyzw=(x, -0.28, z + 0.08, 0.0, 0.0, 0.0, 1.0),
                table_contact=False,
                table_clearance_m=0.01,
                left_force_n=0.61,
                right_force_n=0.62,
                maximum_force_n=0.62,
                forbidden_contact=False,
            )
        )
    return tuple(result)


def evaluate(values: tuple[CarrySample, ...]):
    return evaluate_transport(
        values,
        contact_policy(),
        carry_policy(),
        "session-a",
        3,
        99,
        20.06,
    )


def changed(values: tuple[CarrySample, ...], index: int, **changes) -> tuple[CarrySample, ...]:
    result = list(values)
    result[index] = replace(result[index], **changes)
    return tuple(result)


def test_accepts_stable_relative_pose_across_all_transport_segments() -> None:
    result = evaluate(samples())

    assert result.success
    assert result.failure_code is None
    assert result.sample_count == 6
    assert result.metrics["maximum_relative_position_drift_m"] == pytest.approx(0.0)
    assert result.metrics["maximum_relative_orientation_drift_rad"] == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("mutate", "code"),
    (
        (
            lambda values: tuple(item for item in values if item.segment != "MOVE_ABOVE_PLACE"),
            "TRANSPORT_MISSING_SEGMENT",
        ),
        (
            lambda values: changed(
                changed(values, 2, segment="DESCEND_TO_PLACE"),
                4,
                segment="MOVE_ABOVE_PLACE",
            ),
            "TRANSPORT_MISSING_SEGMENT",
        ),
        (
            lambda values: changed(values, 2, publisher_sequence=100),
            "CARRY_STALE_EVIDENCE",
        ),
        (
            lambda values: changed(values, 3, table_contact=True),
            "TRANSPORT_TABLE_RECONTACT",
        ),
        (
            lambda values: changed(values, 3, table_clearance_m=0.0005),
            "TRANSPORT_CLEARANCE",
        ),
        (
            lambda values: changed(
                values,
                3,
                tcp_pose_xyz_xyzw=(-0.025, -0.28, 0.275, 0.0, 0.0, 0.0, 1.0),
            ),
            "TRANSPORT_POSITION_DRIFT",
        ),
        (
            lambda values: changed(
                values,
                3,
                cup_pose_xyz_xyzw=(-0.025, -0.28, 0.19, 0.05, 0.0, 0.0, 0.9987492178),
            ),
            "TRANSPORT_ORIENTATION_DRIFT",
        ),
        (lambda values: changed(values, 3, right_force_n=0.0), "CARRY_RIGHT_CONTACT_MISSING"),
        (lambda values: changed(values, 3, forbidden_contact=True), "CARRY_FORBIDDEN_CONTACT"),
        (lambda values: changed(values, 3, reset_epoch=4), "CARRY_PROVENANCE_MISMATCH"),
        (
            lambda values: changed(
                values,
                3,
                cup_pose_xyz_xyzw=(0.30, -0.28, 0.19, 0.0, 0.0, 0.0, 1.0),
            ),
            "CARRY_WORKSPACE_EXIT",
        ),
    ),
)
def test_rejects_segment_or_physical_transport_failure(mutate, code: str) -> None:
    assert evaluate(mutate(samples())).failure_code == code
