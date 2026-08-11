from moveit_msgs.msg import AllowedCollisionEntry, AllowedCollisionMatrix

from so101_mujoco_demo_py.planning_scene_acm import (
    collision_is_allowed,
    set_collision_allowed,
)


def test_empty_matrix_adds_a_symmetric_scoped_permission() -> None:
    matrix = AllowedCollisionMatrix()

    set_collision_allowed(matrix, "plastic_cup", "gripper", True)

    assert matrix.entry_names == ["plastic_cup", "gripper"]
    assert collision_is_allowed(matrix, "plastic_cup", "gripper")
    assert collision_is_allowed(matrix, "gripper", "plastic_cup")
    assert not collision_is_allowed(matrix, "plastic_cup", "plastic_cup")


def test_setting_pair_preserves_unrelated_entries() -> None:
    matrix = AllowedCollisionMatrix(
        entry_names=["table", "pedestal"],
        entry_values=[
            AllowedCollisionEntry(enabled=[False, True]),
            AllowedCollisionEntry(enabled=[True, False]),
        ],
        default_entry_names=["always_allowed"],
        default_entry_values=[True],
    )

    set_collision_allowed(matrix, "plastic_cup", "gripper", True)

    assert collision_is_allowed(matrix, "table", "pedestal")
    assert matrix.default_entry_names == ["always_allowed"]
    assert matrix.default_entry_values == [True]
    assert collision_is_allowed(matrix, "plastic_cup", "gripper")


def test_permission_can_be_explicitly_disabled_symmetrically() -> None:
    matrix = AllowedCollisionMatrix()
    set_collision_allowed(matrix, "plastic_cup", "gripper", True)

    set_collision_allowed(matrix, "plastic_cup", "gripper", False)

    assert not collision_is_allowed(matrix, "plastic_cup", "gripper")
    assert not collision_is_allowed(matrix, "gripper", "plastic_cup")


def test_query_for_missing_pair_is_fail_closed() -> None:
    matrix = AllowedCollisionMatrix()

    assert not collision_is_allowed(matrix, "plastic_cup", "gripper")
