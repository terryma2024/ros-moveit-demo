import math

from so101_gazebo_demo_py.gazebo.observer import (
    ContactPair,
    SourceEvidence,
    WorldObservation,
    evaluate_support_contact,
)


def test_accepts_featherstone_compound_owner_support_with_bounded_negative_noise() -> None:
    evidence = evaluate_support_contact(
        (
            ContactPair(
                "plastic_cup::body::wall_near",
                "table::table_top::collision",
                (-0.00000009, -0.00000011, 0.00002),
            ),
        ),
        intended_support_collision="table::table_top::collision",
        minimum_depth_m=-0.0000001,
    )
    assert evidence.supported
    assert evidence.compound_owner_collision == "plastic_cup::body::wall_near"
    assert evidence.accepted_depth_count == 2
    assert evidence.rejected_depth_count == 1
    assert evidence.minimum_depth_m == -0.00000011
    assert evidence.maximum_depth_m == 0.00002


def test_support_contact_rejects_missing_nonfinite_wrong_table_and_excessive_negative_depth() -> None:
    contacts = (
        ContactPair("plastic_cup::body::wall_near", "other::table", (0.001,)),
        ContactPair(
            "plastic_cup::body::wall_near",
            "table::table_top::collision",
            (math.nan, math.inf, -0.00000011),
        ),
    )
    evidence = evaluate_support_contact(
        contacts,
        intended_support_collision="table::table_top::collision",
        minimum_depth_m=-0.0000001,
    )
    assert not evidence.supported
    assert evidence.accepted_depth_count == 0
    assert evidence.rejected_depth_count == 3


def test_world_observation_keeps_independent_source_sequences_and_timestamps() -> None:
    pose = SourceEvidence(source_timestamp_s=10.0, receipt_sequence=40)
    support = SourceEvidence(source_timestamp_s=10.1, receipt_sequence=42)
    observation = WorldObservation(
        captured_monotonic_s=10.2,
        object_pose_world=(0.0, -0.25, 0.165, 0.0, 0.0, 0.0, 1.0),
        attached=False,
        fixed_finger_contact=False,
        moving_jaw_contact=False,
        pose_source=pose,
        support_source=support,
    )
    assert observation.pose_source.receipt_sequence == 40
    assert observation.support_source.receipt_sequence == 42
    assert observation.pose_source.source_timestamp_s != observation.support_source.source_timestamp_s
