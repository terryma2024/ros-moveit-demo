from pathlib import Path

import pytest


PACKAGE = Path("src/so101_demo_py")


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


def test_rejects_an_unknown_backend_without_fallback() -> None:
    from so101_demo.core.dynamic_pick_policy import DynamicPolicyError, load_dynamic_policy_variant

    with pytest.raises(DynamicPolicyError, match="DYNAMIC_BACKEND_UNSUPPORTED"):
        load_dynamic_policy_variant(PACKAGE, backend="real_stub")
