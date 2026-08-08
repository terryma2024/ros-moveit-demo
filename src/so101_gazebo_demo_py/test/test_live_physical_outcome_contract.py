from pathlib import Path
import math
import pytest
from types import SimpleNamespace

from so101_gazebo_demo_py.live_execute import (
    _stable_bilateral, carry_with_shadow_gates, compose_pose,
    plan_waypoint_sequence, relative_pose, rotated_grasp_pose,
    run_bounded_physical_grasp_attempts, shadow_divergence_healthy,
    translated_grasp_pose,
)
from so101_gazebo_demo_py.gazebo.observer import ContactPair
from so101_gazebo_demo_py.policy_config import PlanningShadowConfig
from so101_gazebo_demo_py.test_support.ros_gazebo_backend import (
    close_gazebo_subscription, closest_pose_pair, parse_model_pose, parse_tf_pose,
    pose_pair_ready, select_gazebo_pose, select_stamped_transform,
)


PACKAGE = Path(__file__).parents[1]
LIVE_EXECUTE = PACKAGE / "so101_gazebo_demo_py/live_execute.py"
LIVE_CLI = PACKAGE / "so101_gazebo_demo_py/cli/pick_place_state_machine.py"


def test_live_forward_path_never_commands_gazebo_attachment() -> None:
    source = LIVE_EXECUTE.read_text()
    assert ".set_attached(" not in source
    assert '"ATTACH_GAZEBO"' not in source
    assert '"DETACH_GAZEBO"' not in source
    assert '"physical-failure.json"' in source


def test_grasp_tcp_translation_occurs_before_physical_close() -> None:
    source = LIVE_EXECUTE.read_text()
    assert "_moveit_plan_grasp_translation" in source
    assert 'state.value == "DESCEND"' in source
    assert source.index("grasp_tcp_translation_offset_m") < source.index(
        "backend.move_gripper(close_target)"
    )


def test_grasp_tcp_translation_preserves_orientation() -> None:
    baseline = (0.02, -0.262, 0.201, 0.1, 0.2, 0.3, 0.9)
    assert translated_grasp_pose(baseline, (-0.0005, 0.0, 0.0)) == (
        0.0195, -0.262, 0.201, 0.1, 0.2, 0.3, 0.9,
    )


def test_grasp_world_x_rotation_changes_only_orientation() -> None:
    baseline = (0.02, -0.262, 0.201, 0.0, 0.0, 0.0, 1.0)
    rotated = rotated_grasp_pose(baseline, -0.017453292519943295)
    assert rotated[:3] == baseline[:3]
    half = -0.017453292519943295 / 2.0
    assert rotated[3:] == pytest.approx((math.sin(half), 0.0, 0.0, math.cos(half)))
    assert rotated_grasp_pose(baseline, 0.0) == baseline


def test_live_cli_forwards_selected_motion_policy() -> None:
    source = LIVE_CLI.read_text()
    assert "motion_policy=options.motion_policy" in source


def test_live_release_order_and_physical_outcome_states_are_explicit() -> None:
    source = LIVE_EXECUTE.read_text()
    assert source.index('"DETACH_MOVEIT"') < source.index('"OPEN_GRIPPER"')
    assert '"WAIT_RELEASE_SETTLE"' in source
    assert '"VALIDATE_FINAL_PLACEMENT"' in source
    assert "time.sleep(2.)" not in source


def test_moveit_shadow_attach_requires_authoritative_gazebo_pose() -> None:
    source = LIVE_EXECUTE.read_text()
    assert 'operation == "attach"' in source
    assert "object_pose is None" in source
    assert "object_pose[:3]" in source


def test_shadow_divergence_gate_fails_closed_on_each_bound_and_age() -> None:
    policy = PlanningShadowConfig(0.005, 0.070, 0.10)
    gazebo = (0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0)
    assert shadow_divergence_healthy(gazebo, gazebo, 0.01, policy)
    assert not shadow_divergence_healthy(
        gazebo, (0.006, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0), 0.01, policy,
    )
    tilted = (0.0, 0.0, 0.2, math.sin(0.08 / 2), 0.0, 0.0, math.cos(0.08 / 2))
    assert not shadow_divergence_healthy(gazebo, tilted, 0.01, policy)
    assert not shadow_divergence_healthy(gazebo, gazebo, 0.11, policy)


def test_gazebo_model_pose_preserves_authoritative_orientation() -> None:
    pose = parse_model_pose(
        "position [1.0 -2.0 0.3]\norientation [0.0 0.0 1.5707963267948966]"
    )
    assert pose[:3] == (1.0, -2.0, 0.3)
    assert pose[3:] == pytest.approx((0.0, 0.0, math.sqrt(0.5), math.sqrt(0.5)))


def test_relative_shadow_pose_round_trips_through_latest_tcp_pose() -> None:
    tcp = (0.1, -0.2, 0.3, 0.0, 0.0, math.sqrt(0.5), math.sqrt(0.5))
    cup = (0.12, -0.19, 0.28, 0.0, 0.0, 0.0, 1.0)
    assert compose_pose(tcp, relative_pose(tcp, cup)) == pytest.approx(cup)


def test_every_carry_motion_is_preceded_by_shadow_gate() -> None:
    calls = []
    policies = {
        name: SimpleNamespace(waypoints=index, velocity_scaling=0.1)
        for index, name in enumerate(("LIFT", "MOVE_ABOVE_PLACE", "DESCEND_TO_PLACE"))
    }

    class Backend:
        def move_arm(self, waypoints, velocity=None):
            calls.append(("move", waypoints, velocity))

    carry_with_shadow_gates(Backend(), policies, lambda name: calls.append(("gate", name)))
    assert calls[::2] == [("gate", name) for name in policies]


def test_tcp_pose_parser_requires_translation_and_quaternion() -> None:
    output = "Translation: [0.1, -0.2, 0.3]\nRotation: in Quaternion [0.0, 0.0, 0.0, 1.0]"
    assert parse_tf_pose(output) == (0.1, -0.2, 0.3, 0.0, 0.0, 0.0, 1.0)
    with pytest.raises(ValueError):
        parse_tf_pose("Translation: [0.1, -0.2, 0.3]")


def test_stamped_transform_selector_preserves_source_timestamp() -> None:
    transform = SimpleNamespace(
        child_frame_id="plastic_cup",
        header=SimpleNamespace(stamp=SimpleNamespace(sec=12, nanosec=500_000_000)),
        transform=SimpleNamespace(
            translation=SimpleNamespace(x=1.0, y=2.0, z=3.0),
            rotation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
        ),
    )
    assert select_stamped_transform([transform], "plastic_cup") == (
        (1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0), 12.5,
    )
    assert select_stamped_transform([transform], "so101_tcp") is None


def test_gazebo_pose_selector_uses_entity_name_and_source_timestamp() -> None:
    pose = SimpleNamespace(
        name="plastic_cup",
        position=SimpleNamespace(x=1.0, y=2.0, z=3.0),
        orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
    )
    message = SimpleNamespace(
        pose=[pose],
        header=SimpleNamespace(stamp=SimpleNamespace(sec=20, nsec=250_000_000)),
    )
    assert select_gazebo_pose(message, "plastic_cup") == (
        (1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0), 20.25,
    )
    assert select_gazebo_pose(message, "other") is None

    pose.position.x = float("nan")
    assert select_gazebo_pose(message, "plastic_cup") is None


def test_gazebo_pose_subscription_is_explicitly_closed() -> None:
    calls = []
    node = SimpleNamespace(unsubscribe=lambda topic: calls.append(topic))

    close_gazebo_subscription(node, "/world/example/pose/info")

    assert calls == ["/world/example/pose/info"]


def test_pose_pair_waits_for_configured_source_timestamp_freshness() -> None:
    observed = {
        "object": ((0.0,) * 7, 10.0),
        "tcp": ((0.0,) * 7, 10.11),
    }
    assert not pose_pair_ready(observed, 0.10)

    observed["object"] = ((0.0,) * 7, 10.02)
    assert pose_pair_ready(observed, 0.10)


def test_closest_pose_pair_retains_cross_source_history() -> None:
    object_samples = [((1.0,) * 7, 10.0), ((2.0,) * 7, 10.2)]
    tcp_samples = [((3.0,) * 7, 9.89), ((4.0,) * 7, 10.09)]

    pair = closest_pose_pair(object_samples, tcp_samples)

    assert pair == {
        "object": ((1.0,) * 7, 10.0),
        "tcp": ((4.0,) * 7, 10.09),
    }


def test_plan_only_validates_every_waypoint_as_a_contiguous_sequence() -> None:
    requests = []
    class Planner:
        def plan_joint_path(self, request, timeout):
            requests.append((request, timeout))
            return SimpleNamespace(
                failure=None,
                trajectory=SimpleNamespace(
                    joint_trajectory=SimpleNamespace(points=[object(), object()]),
                ),
            )
    points = plan_waypoint_sequence(
        Planner(), ("1", "2"), (0.0, 0.0), ((0.1, 0.2), (0.3, 0.4)),
    )
    assert points == 4
    assert requests[0][0].current_positions == (0.0, 0.0)
    assert requests[0][0].target_positions == requests[1][0].current_positions == (0.1, 0.2)
    assert requests[1][0].target_positions == (0.3, 0.4)


def test_calibration_candidate_stops_after_first_valid_physical_failure(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "so101_gazebo_demo_py.live_execute._stable_bilateral",
        lambda backend, ceiling=None: calls.append("stable") or (_ for _ in ()).throw(RuntimeError("missing")),
    )
    with pytest.raises(RuntimeError, match="missing"):
        run_bounded_physical_grasp_attempts(
            SimpleNamespace(move_gripper=lambda value: calls.append(value)),
            -0.053, 0.465, -0.0596, max_attempts=1,
        )
    assert calls == ["stable"]


def test_stable_bilateral_fails_immediately_on_moving_pad_hard_ceiling() -> None:
    contacts = (
        ContactPair("plastic_cup::body::wall_near", "fixed_fingertip_pad_collision_001", (0.0004,)),
        ContactPair("plastic_cup::body::wall_near", "moving_fingertip_pad_collision_001", (0.001250001,)),
    )
    backend = SimpleNamespace(contacts=lambda: contacts)

    with pytest.raises(RuntimeError, match="moving-pad penetration ceiling exceeded"):
        _stable_bilateral(backend)


def test_stable_bilateral_honors_diagnostic_ceiling_override() -> None:
    contacts = (
        ContactPair("plastic_cup::body::wall_near", "fixed_fingertip_pad_collision_001", (0.0004,)),
        ContactPair("plastic_cup::body::wall_near", "moving_fingertip_pad_collision_001", (0.00128,)),
    )
    backend = SimpleNamespace(contacts=lambda: contacts)

    with pytest.raises(RuntimeError, match="moving-pad penetration ceiling exceeded"):
        _stable_bilateral(backend)
    evidence = _stable_bilateral(backend, ceiling=0.0013)
    assert evidence.bilateral
    assert evidence.max_moving_pad_penetration_m == 0.00128


def test_attachment_safe_contact_honors_diagnostic_ceiling_override() -> None:
    from so101_gazebo_demo_py.gazebo.observer import BilateralContactEvidence
    from so101_gazebo_demo_py.live_execute import attachment_safe_contact

    evidence = BilateralContactEvidence(True, True, 0.0004, 0.00128, True)
    assert not attachment_safe_contact(evidence)
    assert attachment_safe_contact(evidence, ceiling=0.0013)
