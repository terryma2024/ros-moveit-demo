from pathlib import Path
import math
import pytest
from types import SimpleNamespace

from so101_gazebo_demo_py.live_execute import (
    carry_with_shadow_gates, compose_pose, relative_pose, shadow_divergence_healthy,
)
from so101_gazebo_demo_py.policy_config import PlanningShadowConfig
from so101_gazebo_demo_py.test_support.ros_gazebo_backend import (
    parse_model_pose, parse_tf_pose, select_stamped_transform,
)


PACKAGE = Path(__file__).parents[1]
LIVE_EXECUTE = PACKAGE / "so101_gazebo_demo_py/live_execute.py"


def test_live_forward_path_never_commands_gazebo_attachment() -> None:
    source = LIVE_EXECUTE.read_text()
    assert ".set_attached(" not in source
    assert '"ATTACH_GAZEBO"' not in source
    assert '"DETACH_GAZEBO"' not in source


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
