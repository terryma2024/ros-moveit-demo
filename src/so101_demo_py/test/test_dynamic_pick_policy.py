from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]


def test_loads_the_gazebo_plan_only_variant() -> None:
    from so101_demo.core.dynamic_pick_policy import load_dynamic_policy_variant

    loaded = load_dynamic_policy_variant(PACKAGE)

    assert loaded.template.policy_id == "dynamic_cup_pick"
    assert loaded.template.object_id == "plastic_cup"
    assert loaded.qualification_status == "CALIBRATION_REQUIRED"
    assert loaded.execution_allowed is False
    assert len(loaded.sha256) == 64


def test_loads_the_mujoco_execute_candidate_without_fixed_policy_fallback() -> None:
    from so101_demo.core.dynamic_pick_policy import load_dynamic_policy_variant

    loaded = load_dynamic_policy_variant(PACKAGE, backend="mujoco")

    assert loaded.template.policy_id == "dynamic_cup_pick"
    assert loaded.execution_allowed is True
    assert loaded.qualification_status == "LOCAL_E2E_CANDIDATE"
    assert "light_cup_wall_pick" not in str(loaded.path)


def test_mujoco_candidate_resolves_four_mm_physical_micro_lift_margin() -> None:
    from so101_demo.core.domain import State
    from so101_demo.core.dynamic_pick import CupPoseSample, resolve_motion_targets
    from so101_demo.core.dynamic_pick_policy import load_dynamic_policy_variant
    from so101_demo.core.task_geometry import Pose7

    loaded = load_dynamic_policy_variant(PACKAGE, backend="mujoco")
    sample = CupPoseSample(
        frame_id="world",
        source_stamp_ns=1_000_000_000,
        received_monotonic_s=3.0,
        pose_world=Pose7((0.02, -0.33, 0.165, 0.0, 0.0, 0.0, 1.0)),
    )

    targets = resolve_motion_targets(sample, loaded.template)
    physical_margin_target = (
        targets.for_state(State.MICRO_LIFT).position_m[2]
        - targets.for_state(State.DESCEND).position_m[2]
    )

    assert physical_margin_target == pytest.approx(0.004)


def test_mujoco_source_age_budget_covers_synchronized_rgbd_artifacts() -> None:
    from so101_demo.core.dynamic_pick_policy import load_dynamic_policy_variant

    loaded = load_dynamic_policy_variant(PACKAGE, backend="mujoco")

    assert loaded.template.maximum_source_age_s == pytest.approx(2.0)


def test_rejects_an_unknown_backend_without_fallback() -> None:
    from so101_demo.core.dynamic_pick_policy import DynamicPolicyError, load_dynamic_policy_variant

    with pytest.raises(DynamicPolicyError, match="DYNAMIC_BACKEND_UNSUPPORTED"):
        load_dynamic_policy_variant(PACKAGE, backend="real_stub")
