"""Controls for the teacher_endpoint rule and the Teacher execution policy (pure, standalone)."""

from __future__ import annotations

import copy
import math

import pytest
import yaml

from so101_demo.act.teacher_endpoint import (
    evaluate_teacher_endpoint,
    load_teacher_endpoint_policy,
    load_teacher_execution_policy,
    validate_task_targets,
)
from paths import PACKAGE_ROOT

CONFIG = PACKAGE_ROOT / "config/act"
ENDPOINT_YAML = CONFIG / "teacher_endpoint.yaml"
EXECUTION_YAML = CONFIG / "teacher_execution_policy_v1.yaml"


def _quat_z(angle):
    return {"x": 0.0, "y": 0.0, "z": math.sin(angle / 2), "w": math.cos(angle / 2)}


def _quat_x(angle):
    return {"x": math.sin(angle / 2), "y": 0.0, "z": 0.0, "w": math.cos(angle / 2)}


def _pose(x, y, z, orientation=None):
    return {"position": [x, y, z], "orientation": orientation or _quat_z(0.0)}


START_TARGET = _pose(0.02, -0.28, 0.165)
END_TARGET = _pose(-0.07, -0.23, 0.165)


def _obs(target, *, dx=0.0, dy=0.0, dz=0.0, orientation=None, t=1.0, session="s1", epoch=3,
         object_id="cup", frame="world"):
    x, y, z = target["position"]
    return {
        "object_id": object_id, "frame_id": frame, "session_id": session, "reset_epoch": epoch,
        "simulation_time_s": t, "position": [x + dx, y + dy, z + dz],
        "orientation": orientation or target["orientation"],
    }


@pytest.fixture()
def policy():
    return load_teacher_endpoint_policy(ENDPOINT_YAML)


def _run(policy, start=None, end=None, **kw):
    return evaluate_teacher_endpoint(
        policy, start_target=START_TARGET, end_target=END_TARGET,
        start_observation=start if start is not None else _obs(START_TARGET, t=1.0),
        end_observation=end if end is not None else _obs(END_TARGET, t=9.0),
        **kw,
    )


def test_endpoint_config_loads_with_expected_values(policy):
    assert policy["rule_version"] == "teacher_endpoint"
    assert policy["tolerances"] == {
        "initial_position_m": 0.010, "initial_axis_rad": 0.15, "final_xy_m": 0.020,
        "final_z_m": 0.010, "final_axis_rad": 0.15, "settle_s": 0.5,
    }
    assert len(policy["policy_sha256"]) == 64
    assert load_teacher_endpoint_policy(ENDPOINT_YAML.read_bytes())["policy_sha256"] == policy["policy_sha256"]


def test_endpoint_config_hash_changes_with_value():
    doc = yaml.safe_load(ENDPOINT_YAML.read_text())
    doc["tolerances"]["settle_s"] = 0.0
    other = load_teacher_endpoint_policy(yaml.safe_dump(doc).encode())
    assert other["policy_sha256"] != load_teacher_endpoint_policy(ENDPOINT_YAML)["policy_sha256"]
    assert other["tolerances"]["settle_s"] == 0.0


def _mutated(mutator):
    doc = yaml.safe_load(ENDPOINT_YAML.read_text())
    mutator(doc)
    return yaml.safe_dump(doc).encode()


@pytest.mark.parametrize("mutator", [
    lambda d: d.update(extra=1),
    lambda d: d.pop("rule_version"),
    lambda d: d.update(kind="OTHER"),
    lambda d: d.update(schema_version=2),
    lambda d: d.update(rule_version="endpoint_pose_v1"),
    lambda d: d["tolerances"].update(extra=1),
    lambda d: d["tolerances"].pop("final_z_m"),
    lambda d: d["tolerances"].update(final_xy_m=0.0),
    lambda d: d["tolerances"].update(final_xy_m=-1.0),
    lambda d: d["tolerances"].update(final_z_m=float("nan")),
    lambda d: d["tolerances"].update(initial_axis_rad=float("inf")),
    lambda d: d["tolerances"].update(settle_s=-0.1),
    lambda d: d["tolerances"].update(settle_s=float("nan")),
    lambda d: d["tolerances"].update(settle_s=True),
    lambda d: d["tolerances"].update(final_xy_m="0.02"),
])
def test_endpoint_config_rejects_bad_documents(mutator):
    with pytest.raises(ValueError, match="TEACHER_ENDPOINT_POLICY_INVALID"):
        load_teacher_endpoint_policy(_mutated(mutator))


def test_endpoint_config_rejects_non_mapping_and_garbage():
    with pytest.raises(ValueError, match="TEACHER_ENDPOINT_POLICY_INVALID"):
        load_teacher_endpoint_policy(b"- 1\n- 2\n")
    with pytest.raises(ValueError, match="TEACHER_ENDPOINT_POLICY_INVALID"):
        load_teacher_endpoint_policy(b"a: [unclosed")


def test_execution_policy_loads_and_is_closed():
    policy = load_teacher_execution_policy(EXECUTION_YAML)
    assert policy["state_max_age_s"] == 0.5
    assert policy["state_unavailable_stop_s"] == 1.0
    assert policy["execution_deadline_s"] == 180.0
    assert len(policy["policy_sha256"]) == 64
    doc = yaml.safe_load(EXECUTION_YAML.read_text())
    for mutate in (lambda d: d.update(extra=1), lambda d: d.pop("state_max_age_s"),
                   lambda d: d.update(state_max_age_s=0), lambda d: d.update(execution_deadline_s=float("inf")),
                   lambda d: d.update(kind="X"), lambda d: d.update(schema_version=2),
                   lambda d: d.update(state_unavailable_stop_s=True)):
        bad = copy.deepcopy(doc)
        mutate(bad)
        with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
            load_teacher_execution_policy(yaml.safe_dump(bad).encode())


def test_validate_targets_accepts_the_recipe(policy):
    validate_task_targets(policy, START_TARGET, END_TARGET)


def test_upright_end_target_required(policy):
    tipped = _pose(-0.07, -0.23, 0.165, _quat_x(0.5))
    with pytest.raises(ValueError, match="TEACHER_ENDPOINT_TARGET_NOT_UPRIGHT"):
        validate_task_targets(policy, START_TARGET, tipped)


def test_non_unit_target_quaternion_refused(policy):
    bad = _pose(-0.07, -0.23, 0.165, {"x": 0.0, "y": 0.0, "z": 0.0, "w": 2.0})
    with pytest.raises(ValueError, match="TEACHER_ENDPOINT_TARGET_INVALID"):
        validate_task_targets(policy, START_TARGET, bad)
    nan = _pose(-0.07, -0.23, 0.165, {"x": 0.0, "y": 0.0, "z": 0.0, "w": float("nan")})
    with pytest.raises(ValueError, match="TEACHER_ENDPOINT_TARGET_INVALID"):
        validate_task_targets(policy, START_TARGET, nan)


def test_coincident_targets_refused(policy):
    far_enough = _pose(0.02 + 0.04, -0.28, 0.165)  # 0.04 m apart, above 0.010 + 0.020
    validate_task_targets(policy, START_TARGET, far_enough)
    too_near = _pose(0.02 + 0.025, -0.28, 0.165)  # 0.025 m apart, below the 0.030 m sum
    with pytest.raises(ValueError, match="TEACHER_ENDPOINT_TARGETS_COINCIDENT"):
        validate_task_targets(policy, START_TARGET, too_near)
    with pytest.raises(ValueError, match="TEACHER_ENDPOINT_TARGETS_COINCIDENT"):
        validate_task_targets(policy, START_TARGET, START_TARGET)


def test_pass_case(policy):
    result = _run(policy)
    assert result["result"] == "PASS"
    assert result["reasons"] == []
    assert result["rule_version"] == "teacher_endpoint"
    assert result["policy_sha256"] == policy["policy_sha256"]
    m = result["measured"]
    assert m["initial_position_error_m"] == pytest.approx(0.0, abs=1e-12)
    assert m["final_xy_error_m"] == pytest.approx(0.0, abs=1e-12)
    assert m["final_axis_tilt_rad"] == pytest.approx(0.0, abs=1e-6)
    assert result["start_target"] == START_TARGET
    assert result["end_observation"]["session_id"] == "s1"


def test_final_xy_offset_fails(policy):
    result = _run(policy, end=_obs(END_TARGET, dx=0.03, t=9.0))
    assert result["result"] == "FAIL"
    assert any("FINAL_XY" in r for r in result["reasons"])
    assert result["measured"]["final_xy_error_m"] == pytest.approx(0.03)


def test_final_z_fails(policy):
    result = _run(policy, end=_obs(END_TARGET, dz=-0.02, t=9.0))
    assert result["result"] == "FAIL"
    assert any("FINAL_Z" in r for r in result["reasons"])
    assert result["measured"]["final_z_error_m"] == pytest.approx(0.02)


def test_tipped_cup_fails(policy):
    result = _run(policy, end=_obs(END_TARGET, orientation=_quat_x(0.4), t=9.0))
    assert result["result"] == "FAIL"
    assert any("FINAL_AXIS" in r for r in result["reasons"])
    assert result["measured"]["final_axis_tilt_rad"] == pytest.approx(0.4)


def test_yaw_rotated_end_still_passes(policy):
    result = _run(policy, end=_obs(END_TARGET, orientation=_quat_z(math.pi / 2), t=9.0))
    assert result["result"] == "PASS"
    assert result["measured"]["final_axis_tilt_rad"] == pytest.approx(0.0, abs=1e-6)


def test_start_offset_beyond_tolerance_fails(policy):
    result = _run(policy, start=_obs(START_TARGET, dx=0.02, t=1.0))
    assert result["result"] == "FAIL"
    assert any("INITIAL_POSITION" in r for r in result["reasons"])


def test_start_axis_beyond_tolerance_fails(policy):
    result = _run(policy, start=_obs(START_TARGET, orientation=_quat_x(0.3), t=1.0))
    assert result["result"] == "FAIL"
    assert any("INITIAL_AXIS" in r for r in result["reasons"])


def test_missing_end_is_unconfirmed(policy):
    result = evaluate_teacher_endpoint(
        policy, start_target=START_TARGET, end_target=END_TARGET,
        start_observation=_obs(START_TARGET, t=1.0), end_observation=None)
    assert result["result"] == "UNCONFIRMED"
    assert result["reasons"]
    assert result["end_observation"] is None


def test_missing_start_is_unconfirmed(policy):
    result = evaluate_teacher_endpoint(
        policy, start_target=START_TARGET, end_target=END_TARGET,
        start_observation=None, end_observation=_obs(END_TARGET, t=9.0))
    assert result["result"] == "UNCONFIRMED"


def test_wrong_session_is_unconfirmed(policy):
    result = _run(policy, end=_obs(END_TARGET, t=9.0, session="other"))
    assert result["result"] == "UNCONFIRMED"


def test_wrong_epoch_or_object_is_unconfirmed(policy):
    assert _run(policy, end=_obs(END_TARGET, t=9.0, epoch=4))["result"] == "UNCONFIRMED"
    assert _run(policy, end=_obs(END_TARGET, t=9.0, object_id="ball"))["result"] == "UNCONFIRMED"


def test_wrong_frame_is_unconfirmed(policy):
    assert _run(policy, end=_obs(END_TARGET, t=9.0, frame="base_link"))["result"] == "UNCONFIRMED"


def test_end_time_not_after_start_is_unconfirmed(policy):
    assert _run(policy, end=_obs(END_TARGET, t=1.0))["result"] == "UNCONFIRMED"
    assert _run(policy, end=_obs(END_TARGET, t=0.5))["result"] == "UNCONFIRMED"


def test_invalid_quaternion_is_unconfirmed(policy):
    bad = _obs(END_TARGET, t=9.0, orientation={"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.0})
    assert _run(policy, end=bad)["result"] == "UNCONFIRMED"
    nan = _obs(END_TARGET, t=9.0, orientation={"x": 0.0, "y": 0.0, "z": 0.0, "w": float("nan")})
    assert _run(policy, end=nan)["result"] == "UNCONFIRMED"
    inf_pos = _obs(END_TARGET, t=9.0)
    inf_pos["position"] = [float("inf"), 0.0, 0.0]
    assert _run(policy, end=inf_pos)["result"] == "UNCONFIRMED"


def test_unconfirmed_beats_fail(policy):
    result = evaluate_teacher_endpoint(
        policy, start_target=START_TARGET, end_target=END_TARGET,
        start_observation=_obs(START_TARGET, dx=0.5, t=1.0), end_observation=None)
    assert result["result"] == "UNCONFIRMED"


def test_bad_targets_raise_from_evaluate(policy):
    with pytest.raises(ValueError, match="TEACHER_ENDPOINT_TARGETS_COINCIDENT"):
        evaluate_teacher_endpoint(
            policy, start_target=START_TARGET, end_target=START_TARGET,
            start_observation=_obs(START_TARGET), end_observation=_obs(START_TARGET, t=9.0))


# ---- C3(b): the gripper close target is a frozen Teacher execution policy parameter -----------------------------

def test_c3_the_execution_policy_freezes_the_calibration_close_target():
    policy = load_teacher_execution_policy(EXECUTION_YAML)
    assert policy["gripper_close_target_rad"] == pytest.approx(-0.0476086, abs=1e-7)
    assert "contact_calibration" in EXECUTION_YAML.read_text() or "model-parity" in EXECUTION_YAML.read_text()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), True, "x", None, 0.5, -0.5])
def test_c3_the_policy_refuses_a_missing_or_non_finite_close_target(bad):
    doc = yaml.safe_load(EXECUTION_YAML.read_text())
    doc["gripper_close_target_rad"] = bad
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        load_teacher_execution_policy(yaml.safe_dump(doc).encode())
    doc.pop("gripper_close_target_rad")
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        load_teacher_execution_policy(yaml.safe_dump(doc).encode())


# ---- C6: frozen carry scaling -----------------------------------------------------------------------------------

def test_c6_the_execution_policy_freezes_the_carry_scaling():
    policy = load_teacher_execution_policy(EXECUTION_YAML)
    assert policy["carry_max_velocity_scaling"] == 0.03
    assert policy["carry_max_acceleration_scaling"] == 0.0075
    text = EXECUTION_YAML.read_text()
    assert "CP-3382" in text and "C5" in text


@pytest.mark.parametrize("key", ["carry_max_velocity_scaling", "carry_max_acceleration_scaling"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), True, "x", None, 0, 0.0, -0.01, 1.01])
def test_c6_the_policy_refuses_a_missing_or_invalid_carry_scaling(key, bad):
    doc = yaml.safe_load(EXECUTION_YAML.read_text())
    doc[key] = bad
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        load_teacher_execution_policy(yaml.safe_dump(doc).encode())
    doc.pop(key)
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        load_teacher_execution_policy(yaml.safe_dump(doc).encode())


# ---- R11: ACT-only place descent offset ----------------------------------------------------------------------------

def test_r11_the_policy_freezes_the_place_descend_offset_with_its_rationale():
    policy = load_teacher_execution_policy(EXECUTION_YAML)
    assert policy["place_descend_offset_m"] == -0.01325
    text = EXECUTION_YAML.read_text()
    assert "support-before-open" in text and "r11-exp" in text


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), True, "x", None, 0.06, -0.06])
def test_r11_the_policy_refuses_an_invalid_or_missing_place_descend_offset(bad):
    doc = yaml.safe_load(EXECUTION_YAML.read_text())
    doc["place_descend_offset_m"] = bad
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        load_teacher_execution_policy(yaml.safe_dump(doc).encode())
    doc.pop("place_descend_offset_m")
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        load_teacher_execution_policy(yaml.safe_dump(doc).encode())
