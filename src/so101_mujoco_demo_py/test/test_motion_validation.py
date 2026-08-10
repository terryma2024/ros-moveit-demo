from so101_mujoco_demo_py.domain import State
from so101_mujoco_demo_py.motion.evidence import RobotStateEvidence
from so101_mujoco_demo_py.motion.planner import (
    Trajectory,
    TrajectoryPoint,
    ValidationRules,
    validate_trajectory,
)


def evidence():
    return RobotStateEvidence(("1", "2"), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0, 0.0))


def point(joints, time_s, tcp=(0.0, 0.0, 0.0), contacts=()):
    return TrajectoryPoint(tuple(joints), time_s, tcp, frozenset(contacts))


RULES = ValidationRules(endpoint_tolerance=0.01, max_jump=1.0, min_duration=0.5)


def validate(trajectory, target=(0.1, 0.2), rules=RULES, waypoints=()):
    return validate_trajectory(
        State.DESCEND,
        trajectory,
        evidence(),
        target,
        rules=rules,
        required_waypoints=waypoints,
    )


def test_rejects_structural_start_endpoint_jump_and_duration_failures() -> None:
    assert validate(Trajectory((), ())).code == "EMPTY_TRAJECTORY"
    assert (
        validate(Trajectory(("1",), (point((0.0,), 0), point((0.1,), 1)))).code
        == "TRAJECTORY_JOINTS_MISMATCH"
    )
    assert (
        validate(Trajectory(("1", "2"), (point((0.1, 0), 0), point((0.1, 0.2), 1)))).code
        == "TRAJECTORY_START_MISMATCH"
    )
    assert (
        validate(Trajectory(("1", "2"), (point((0, 0), 0), point((0.1, 0.3), 1)))).code
        == "TRAJECTORY_ENDPOINT_MISMATCH"
    )
    jump = Trajectory(("1", "2"), (point((0, 0), 0), point((0.1, 0.2), 1)))
    assert validate(jump, rules=ValidationRules(0.01, 0.15, 0.5)).code == ("TRAJECTORY_JOINT_JUMP")
    short = Trajectory(("1", "2"), (point((0, 0), 0), point((0.1, 0.2), 0.1)))
    assert validate(short).code == "TRAJECTORY_DURATION_TOO_SHORT"


def test_waypoint_ladder_must_be_visited_in_order() -> None:
    trajectory = Trajectory(
        ("1", "2"),
        (point((0, 0), 0), point((0.05, 0.1), 0.5), point((0.1, 0.2), 1)),
    )
    assert validate(trajectory, waypoints=((0.05, 0.1),)) is None
    assert validate(trajectory, waypoints=((0.08, 0.02),)).code == ("TRAJECTORY_WAYPOINT_MISSING")


def test_axial_monotonicity_lateral_deviation_and_contacts() -> None:
    axial_rules = ValidationRules(
        0.01,
        1,
        0.5,
        path_direction=(0, 0, -1),
        monotonic_tolerance=0.001,
        max_lateral_deviation=0.01,
    )
    reverse = Trajectory(
        ("1", "2"),
        (
            point((0, 0), 0, (0, 0, 0)),
            point((0.05, 0.1), 0.5, (0, 0, -0.1)),
            point((0.1, 0.2), 1, (0, 0, -0.05)),
        ),
    )
    assert validate(reverse, rules=axial_rules).code == "TRAJECTORY_AXIAL_NONMONOTONIC"
    lateral = Trajectory(
        ("1", "2"),
        (
            point((0, 0), 0, (0, 0, 0)),
            point((0.05, 0.1), 0.5, (0.02, 0, -0.05)),
            point((0.1, 0.2), 1, (0, 0, -0.1)),
        ),
    )
    assert validate(lateral, rules=axial_rules).code == "TRAJECTORY_LATERAL_DEVIATION"

    allowed = frozenset({"plastic_cup:table"})
    contact_rules = ValidationRules(0.01, 1, 0.5, allowed_contacts=allowed)
    good = Trajectory(
        ("1", "2"),
        (point((0, 0), 0, contacts=allowed), point((0.1, 0.2), 1)),
    )
    assert validate(good, rules=contact_rules) is None
    bad = Trajectory(
        ("1", "2"),
        (point((0, 0), 0, contacts={"robot:table"}), point((0.1, 0.2), 1)),
    )
    assert validate(bad, rules=contact_rules).code == "TRAJECTORY_FORBIDDEN_CONTACT"
