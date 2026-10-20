"""The rollout loop clamps a prefix that exceeds a joint limit by at most the configured tolerance, and refuses it otherwise."""

import dataclasses

from so101_demo.act.joints import ACT_JOINT_LIMITS

from test_act_rollout_episode import SETTINGS, Ports, Sink, _run

TOLERANCE = 0.01
WRIST_FLEX_HIGH = ACT_JOINT_LIMITS["4"][1]
ELBOW_HIGH = ACT_JOINT_LIMITS["3"][1]
GRIPPER_HIGH = ACT_JOINT_LIMITS["6"][1]
CLAMPING = dataclasses.replace(SETTINGS, joint_limit_clamp_tolerance_rad=TOLERANCE)


def _state(**joints):
    state = [0.0, 0.1, -0.2, 0.3, 0.0, 0.5, 0.0, 1.0]
    for index, value in joints.items():
        state[int(index.lstrip("j"))] = value
    return tuple(state)


def _ports(step_rad, **state):
    ports = Ports(session_kwargs={"state0": _state(**state), "enforce_limits": True, "moves": False})
    ports.inference.step_rad = step_rad
    return ports


def test_the_default_settings_carry_no_clamp_tolerance():
    assert SETTINGS.joint_limit_clamp_tolerance_rad is None


def test_an_overshoot_within_the_tolerance_is_clamped_applied_and_recorded_per_step():
    ports, sink = _ports(0.002, j3=WRIST_FLEX_HIGH), Sink()
    result = _run(ports, sink, settings=CLAMPING)
    assert result["counts"]["limit_refused"] == 0 and result["counts"]["applied"] > 5
    assert result["counts"]["clamped_steps"] == result["counts"]["applied"]
    assert ports.session.prefixes and all(p["positions"][0][3] == WRIST_FLEX_HIGH for p in ports.session.prefixes)
    clamped = [row for row in sink.steps if row.get("clamped")]
    assert len(clamped) == result["counts"]["clamped_steps"]
    row = clamped[0]
    assert row["applied"] is True and len(row["clamps"]) == 1
    clamp = row["clamps"][0]
    assert (clamp["joint_index"], clamp["joint"], clamp["clamped"]) == (3, "4", WRIST_FLEX_HIGH)
    assert abs(clamp["original"] - (WRIST_FLEX_HIGH + 0.002)) < 1e-9 and clamp["position_index"] == 0
    # the recorded prefix of the row is what was sent, the original is only in `clamps`
    assert row["prefix"]["positions"][0][3] == WRIST_FLEX_HIGH
    assert all("clamped" not in step or step["clamped"] is True for step in sink.steps)


def test_a_multi_joint_prefix_is_clamped_on_every_joint_that_overshoots():
    ports, sink = _ports(0.002, j2=ELBOW_HIGH, j3=WRIST_FLEX_HIGH, j5=GRIPPER_HIGH), Sink()
    result = _run(ports, sink, settings=CLAMPING)
    assert result["counts"]["limit_refused"] == 0 and result["counts"]["clamped_steps"] > 0
    first = next(row for row in sink.steps if row.get("clamped"))
    assert sorted(c["joint_index"] for c in first["clamps"]) == [2, 3, 5]
    sent = ports.session.prefixes[0]["positions"][0]
    assert (sent[2], sent[3], sent[5]) == (ELBOW_HIGH, WRIST_FLEX_HIGH, GRIPPER_HIGH)


def test_an_overshoot_above_the_tolerance_is_refused_as_before_and_nothing_is_clamped():
    ports, sink = _ports(0.02, j3=WRIST_FLEX_HIGH), Sink()
    result = _run(ports, sink, settings=CLAMPING)
    assert result["counts"]["limit_refused"] > 0 and result["counts"]["applied"] == 0
    assert result["counts"]["clamped_steps"] == 0 and not ports.session.prefixes
    assert not any(row.get("clamped") for row in sink.steps)
    assert any(row.get("reason") == "JOINT_LIMIT_INVALID" for row in sink.steps)


def test_one_joint_above_the_tolerance_refuses_the_prefix_even_when_another_is_within_it():
    settings = dataclasses.replace(SETTINGS, joint_limit_clamp_tolerance_rad=0.004)
    # step 0.005: the wrist flex overshoots by 0.005 (above 0.004), the gripper by 0.0037 (within)
    ports = _ports(0.005, j3=WRIST_FLEX_HIGH, j5=GRIPPER_HIGH - 0.0013)
    result = _run(ports, settings=settings)
    assert result["counts"]["limit_refused"] > 0 and result["counts"]["applied"] == 0
    assert result["counts"]["clamped_steps"] == 0


def test_without_the_tolerance_the_overshoot_is_refused_exactly_as_before():
    ports, sink = _ports(0.002, j3=WRIST_FLEX_HIGH), Sink()
    result = _run(ports, sink)                                   # SETTINGS: key absent
    assert result["counts"]["limit_refused"] > 0 and result["counts"]["applied"] == 0
    assert result["counts"]["clamped_steps"] == 0 and not any("clamped" in row or "clamps" in row for row in sink.steps)


def test_a_prefix_inside_the_limits_is_untouched_and_has_no_clamp_fields():
    ports, sink = Ports(session_kwargs={"moves": False, "enforce_limits": True}), Sink()
    ports.inference.step_rad = 0.001                         # stays far inside every limit from the default state
    result = _run(ports, sink, settings=CLAMPING)
    assert result["counts"]["applied"] > 5 and result["counts"]["clamped_steps"] == 0
    assert not any("clamped" in row or "clamps" in row for row in sink.steps)


def test_clamping_also_applies_to_the_temporal_ensembling_mode():
    from so101_demo.act.rollout_execution import resolve_execution

    # an ensemble also draws on the later rows of older chunks, so the step is small enough that every row stays within 0.01
    ports, sink = _ports(0.0005, j3=WRIST_FLEX_HIGH), Sink()
    execution = resolve_execution({"chunk_size": 10, "execution_prefix": 1, "temporal_ensembling": False,
                                   "tail_padding_mask": True}, prefix=None, ensembling=0.01)
    from so101_demo.act.rollout_episode import run_episode
    from test_act_rollout_episode import SCENE, SNAPSHOT_TARGETS, _endpoint_policy

    result = run_episode(scene=SCENE, attempt_id="attempt-1", ports=ports, settings=CLAMPING, snapshot_targets=SNAPSHOT_TARGETS,
                         endpoint_policy=_endpoint_policy(), sink=sink, execution=execution)
    assert result["counts"]["limit_refused"] == 0 and result["counts"]["clamped_steps"] > 0
