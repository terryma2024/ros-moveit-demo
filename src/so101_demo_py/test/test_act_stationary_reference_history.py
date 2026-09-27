"""A controller publication window remains separate from goal authority."""

from copy import deepcopy

import pytest

from so101_demo.adapters.act.stationary_reference_history import (
    verify_stationary_reference_history,
)


NAMES = {
    "arm": ("1", "2", "3", "4", "5"),
    "gripper": ("6",),
    "neck": ("neck_yaw_joint",),
}


def frames():
    rows = {}
    for kind, names in NAMES.items():
        rows[kind] = tuple({
            "sim_stamp_ns": 1_100_000_000 + index * 2_000_000,
            "received_monotonic_ns": 10_000_000_000 + index * 2_000_000,
            "joint_names": names,
            "positions": (0.0,) * len(names),
            "velocities": (0.0,) * len(names),
        } for index in range(51))
    return rows


def verify(rows, *, now_ns=10_110_000_000):
    return verify_stationary_reference_history(
        selected_sim_time_ns=1_200_000_000,
        reference_frames=rows,
        expected_positions={kind: (0.0,) * len(names)
                            for kind, names in NAMES.items()},
        max_wall_age_s=0.2,
        stop_velocity_rad_s=0.002,
        monotonic_ns=lambda: now_ns,
    )


def test_exact_three_controller_window_remains_non_authoritative():
    result = verify(frames())
    assert result["bridge_sim_time_ns"] == 1_100_000_000
    assert result["selected_sim_time_ns"] == 1_200_000_000
    assert result["sample_count_by_controller"] == {
        "arm": 51, "gripper": 51, "neck": 51}
    assert result["owner_goal_interval_proof_required"] is True
    assert result["command_authority"] is False
    assert result["eligible_for_collection"] is False


@pytest.mark.parametrize("change", ["gap", "name", "velocity", "position", "receipt"])
def test_any_missing_or_changed_reference_refuses(change):
    rows = frames()
    changed = deepcopy(rows)
    arm = list(changed["arm"])
    if change == "gap":
        arm.pop(25)
    else:
        frame = dict(arm[25])
        if change == "name":
            frame["joint_names"] = tuple(reversed(frame["joint_names"]))
        elif change == "velocity":
            frame["velocities"] = (0.01,) + frame["velocities"][1:]
        elif change == "position":
            frame["positions"] = (0.001,) + frame["positions"][1:]
        elif change == "receipt":
            frame["received_monotonic_ns"] = 9_000_000_000
        arm[25] = frame
    changed["arm"] = tuple(arm)
    with pytest.raises(ValueError):
        verify(changed)


def test_stale_history_refuses():
    with pytest.raises(ValueError):
        verify(frames(), now_ns=10_400_000_000)
