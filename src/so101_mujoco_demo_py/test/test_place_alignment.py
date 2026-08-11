import math
from pathlib import Path

import pytest

from so101_mujoco_demo_py.place_alignment import (
    PlaceAlignmentPolicy,
    align_cup_for_release,
    load_place_alignment_policy,
    measured_settling_compensation,
    release_alignment_target,
)

CONFIG = (
    Path(__file__).resolve().parents[1] / "config" / "motion_policies" / "light_cup_wall_pick.yaml"
)


def test_mujoco_policy_uses_measured_settling_compensation() -> None:
    policy = load_place_alignment_policy(CONFIG)

    assert policy.settling_compensation_m == pytest.approx((0.0012, 0.0025, 0.0185), abs=1e-12)
    assert policy.xy_tolerance_m == 0.003
    assert policy.z_tolerance_m == 0.003
    assert policy.max_attempts == 3


def test_exp111_measurement_derives_mujoco_pre_release_compensation() -> None:
    pre_release = (-0.07653212406397943, -0.2611527991773442, 0.18441365797552164)
    settled = (-0.0777226275456006, -0.26367182817826534, 0.1659472856188451)

    compensation = measured_settling_compensation(pre_release, settled)

    assert compensation == pytest.approx(
        (0.00119050348162117, 0.00251902900092114, 0.01846637235667655),
        abs=1e-12,
    )


def test_exp127_full_release_retreat_measurement_includes_retreat_interaction() -> None:
    pre_release = (-0.078190536404924, -0.24611131054611562, 0.1826726608372338)
    settled = (-0.0790507188907473, -0.26109349992666697, 0.1654421668216515)

    compensation = measured_settling_compensation(pre_release, settled)

    assert compensation == pytest.approx(
        (0.0008601824858233041, 0.014982189380551347, 0.0172304940155823),
        abs=1e-12,
    )


def test_release_target_is_backend_specific_and_does_not_relax_final_region() -> None:
    policy = PlaceAlignmentPolicy(
        settling_compensation_m=(0.0012, 0.0025, 0.0185),
        xy_tolerance_m=0.003,
        z_tolerance_m=0.003,
        max_attempts=3,
        max_axis_correction_m=0.03,
    )

    assert release_alignment_target((-0.08, -0.25, 0.165), policy) == pytest.approx(
        (-0.0788, -0.2475, 0.1835), abs=1e-12
    )


def test_closed_loop_correction_rejects_old_six_millimetre_error_and_converges() -> None:
    policy = PlaceAlignmentPolicy(
        settling_compensation_m=(0.0012, 0.0025, 0.0185),
        xy_tolerance_m=0.003,
        z_tolerance_m=0.003,
        max_attempts=3,
        max_axis_correction_m=0.03,
    )
    target = release_alignment_target((-0.08, -0.25, 0.165), policy)
    current = [[-0.0765321241, -0.2611527992, 0.1844136580]]
    commands: list[tuple[float, float, float]] = []

    def observe() -> tuple[float, float, float]:
        return tuple(current[0])

    def execute(delta: tuple[float, float, float]) -> None:
        commands.append(delta)
        current[0] = [value + change for value, change in zip(current[0], delta)]

    result = align_cup_for_release(observe, target, execute, policy)

    assert len(commands) == 1
    assert math.hypot(commands[0][0], commands[0][1]) > policy.xy_tolerance_m
    assert result.position_m == pytest.approx(target, abs=1e-12)
    assert result.attempt_count == 1
    assert len(result.telemetry) == 1


def test_alignment_is_bounded_and_fails_without_progress() -> None:
    policy = PlaceAlignmentPolicy(
        settling_compensation_m=(0.0, 0.0, 0.0),
        xy_tolerance_m=0.001,
        z_tolerance_m=0.001,
        max_attempts=2,
        max_axis_correction_m=0.03,
    )
    commands: list[tuple[float, float, float]] = []

    with pytest.raises(RuntimeError, match="did not converge"):
        align_cup_for_release(
            lambda: (0.01, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            commands.append,
            policy,
        )

    assert len(commands) == 2


def test_alignment_rejects_unbounded_or_nonfinite_inputs() -> None:
    policy = PlaceAlignmentPolicy(
        settling_compensation_m=(0.0, 0.0, 0.0),
        xy_tolerance_m=0.001,
        z_tolerance_m=0.001,
        max_attempts=1,
        max_axis_correction_m=0.03,
    )
    with pytest.raises(RuntimeError, match="exceeds bound"):
        align_cup_for_release(
            lambda: (0.04, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            lambda _delta: None,
            policy,
        )
    with pytest.raises(ValueError, match="finite"):
        align_cup_for_release(
            lambda: (math.nan, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            lambda _delta: None,
            policy,
        )
