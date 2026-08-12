import hashlib
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from so101_mujoco_demo_py.task_policy import load_task_policy

MOTION_POLICY = (
    Path(__file__).parents[1] / "config" / "motion_policies" / "light_cup_wall_pick.yaml"
)

EXPECTED_STATES = {
    "MOVE_ABOVE_OBJECT",
    "DESCEND",
    "LIFT",
    "MOVE_ABOVE_PLACE",
    "DESCEND_TO_PLACE",
    "RETREAT",
    "RECOVER_LIFT_TO_SAFE_HEIGHT",
    "RECOVER_MOVE_ABOVE_PICK",
    "RECOVER_DESCEND_TO_PICK",
    "RECOVER_RETREAT",
}


def write_candidate(tmp_path: Path, change) -> Path:
    document = yaml.safe_load(MOTION_POLICY.read_text(encoding="utf-8"))
    change(document)
    candidate = tmp_path / "candidate.yaml"
    candidate.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return candidate


def test_loads_single_source_motion_and_final_outcome_policy() -> None:
    policy = load_task_policy(MOTION_POLICY)

    assert policy.policy_id == "light_cup_wall_pick"
    assert policy.object_id == "plastic_cup"
    assert policy.gripper.grasp_close_q6 == -0.047608632840292
    assert policy.states["MOVE_ABOVE_PLACE"].velocity_scaling == 0.10
    assert policy.physical_outcome.final_target_min_xy_m == (-0.090, -0.260)
    assert policy.physical_outcome.final_target_max_xy_m == (-0.070, -0.240)
    assert policy.maximum_diagnostic_force_n == 11.60
    assert set(policy.states) == EXPECTED_STATES
    assert (
        policy.fingerprint.motion_policy_sha256
        == hashlib.sha256(MOTION_POLICY.read_bytes()).hexdigest()
    )
    assert policy.fingerprint.contact_policy_sha256 is None


def test_returns_immutable_policy_values() -> None:
    policy = load_task_policy(MOTION_POLICY)

    with pytest.raises(TypeError):
        policy.states["UNREVIEWED"] = policy.states["LIFT"]  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        policy.gripper.release_q6 = 0.0  # type: ignore[misc]
    assert isinstance(policy.states["LIFT"].waypoints, tuple)
    assert isinstance(policy.states["LIFT"].waypoints[0], tuple)


def test_rejects_unknown_root_key(tmp_path: Path) -> None:
    candidate = write_candidate(tmp_path, lambda document: document.update(unreviewed=True))

    with pytest.raises(ValueError, match="unknown task policy keys: unreviewed"):
        load_task_policy(candidate)


def test_rejects_non_five_joint_motion_vector(tmp_path: Path) -> None:
    def change(document: dict[str, object]) -> None:
        document["states"]["LIFT"]["waypoints"][0] = [0.0] * 4  # type: ignore[index]

    candidate = write_candidate(tmp_path, change)

    with pytest.raises(ValueError, match=r"LIFT.waypoints\[0\].*five arm joints"):
        load_task_policy(candidate)


def test_rejects_nonfinite_scaling(tmp_path: Path) -> None:
    def change(document: dict[str, object]) -> None:
        document["states"]["LIFT"]["velocity_scaling"] = float("nan")  # type: ignore[index]

    candidate = write_candidate(tmp_path, change)

    with pytest.raises(ValueError, match="LIFT.velocity_scaling.*finite"):
        load_task_policy(candidate)


@pytest.mark.parametrize(
    ("keys", "value", "message"),
    (
        (("states", "RETREAT", "acceleration_scaling"), 1.01, "must not exceed 1.0"),
        (("physical_outcome", "consecutive_samples"), 0, "positive integer"),
        (("physical_outcome", "settle_timeout_s"), 0.0, "must be positive"),
    ),
)
def test_rejects_nonpositive_counts_durations_and_excess_scaling(
    tmp_path: Path,
    keys: tuple[str, ...],
    value: object,
    message: str,
) -> None:
    def change(document: dict[str, object]) -> None:
        target = document
        for key in keys[:-1]:
            target = target[key]  # type: ignore[assignment]
        target[keys[-1]] = value

    candidate = write_candidate(tmp_path, change)

    with pytest.raises(ValueError, match=message):
        load_task_policy(candidate)


def test_rejects_reversed_final_target_bounds(tmp_path: Path) -> None:
    def change(document: dict[str, object]) -> None:
        document["physical_outcome"]["final_target_region"]["min_xy_m"] = [  # type: ignore[index]
            -0.060,
            -0.260,
        ]

    candidate = write_candidate(tmp_path, change)

    with pytest.raises(ValueError, match="final_target_region.*ordered"):
        load_task_policy(candidate)


def test_rejects_unknown_planning_shadow_key(tmp_path: Path) -> None:
    def change(document: dict[str, object]) -> None:
        document["physical_outcome"]["planning_shadow"]["unreviewed"] = 1  # type: ignore[index]

    candidate = write_candidate(tmp_path, change)

    with pytest.raises(ValueError, match="unknown planning_shadow keys: unreviewed"):
        load_task_policy(candidate)
