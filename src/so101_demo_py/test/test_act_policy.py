"""Task 13: time alignment, the frozen execution prefix, and the runner's reset contract."""

import pytest

from so101_demo.act.policy import ActPolicyRunner, target_times


def _bundle(prefix=1):
    return {"schema_version": 1, "kind": "act_bundle", "action": {"chunk_size": 10,
                                                                 "execution_prefix": prefix,
                                                                 "temporal_ensembling": False,
                                                                 "tail_padding_mask": True}}


class _Model:
    def __init__(self, chunk=None):
        self.resets = 0
        self.calls = []
        self._chunk = chunk if chunk is not None else tuple((0.5,) * 6 for _ in range(10))

    def reset(self):
        self.resets += 1

    def infer(self, observation):
        self.calls.append(observation)
        return self._chunk


def _observation(sim_time_s=5.0):
    return {"sim_time_s": sim_time_s, "head": "frame-h", "wrist": "frame-w", "state": [0.0] * 8}


def test_chunk_keeps_observation_time_origin():
    assert target_times(5., 3) == pytest.approx((5.1, 5.2, 5.3))


def test_time_alignment_and_prefix_are_closed():
    for bad_time in (float("nan"), float("inf"), True, "5.0"):
        with pytest.raises(ValueError, match="OBSERVATION_TIME_INVALID"):
            target_times(bad_time, 3)
    for bad_count in (0, -1, 2.0, True):
        with pytest.raises(ValueError, match="CHUNK_COUNT_INVALID"):
            target_times(5.0, bad_count)


def test_the_runner_applies_exactly_the_frozen_prefix_and_requires_a_reset():
    model = _Model()
    runner = ActPolicyRunner(_bundle(prefix=2), model)
    with pytest.raises(ValueError, match="POLICY_NOT_RESET"):
        runner.predict(_observation(), 0)              # nothing may run before the model is reset
    runner.reset("session-1", "attempt-1")
    assert model.resets == 1
    prefix = runner.predict(_observation(sim_time_s=7.4), 3)
    assert prefix["actions"] == ((0.5,) * 6, (0.5,) * 6)         # prefix 2, not the whole chunk
    assert prefix["target_times_s"] == pytest.approx((7.5, 7.6))
    assert prefix["sequence"] == 3 and prefix["session_id"] == "session-1"
    assert prefix["observed_s"] == 7.4
    for bad in ({}, {"sim_time_s": 1.0}, {**_observation(), "extra": 1},
                {**_observation(), "state": [0.0] * 7}):
        with pytest.raises(ValueError, match="POLICY_OBSERVATION_INVALID"):
            runner.predict(bad, 0)
    with pytest.raises(ValueError, match="POLICY_SEQUENCE_INVALID"):
        runner.predict(_observation(), -1)


def test_a_malformed_chunk_or_bundle_is_refused():
    runner = ActPolicyRunner(_bundle(prefix=1), _Model(chunk=((1.0,) * 5,)))
    runner.reset("s", "a")
    with pytest.raises(ValueError, match="POLICY_ACTION_INVALID"):
        runner.predict(_observation(), 0)
    short = ActPolicyRunner(_bundle(prefix=4), _Model(chunk=((1.0,) * 6,)))
    short.reset("s", "a")
    with pytest.raises(ValueError, match="POLICY_ACTION_INVALID"):
        short.predict(_observation(), 0)
    for bad_bundle in ({}, {"action": {}}, {"action": {"execution_prefix": 0}}):
        with pytest.raises(ValueError, match="POLICY_BUNDLE_INVALID"):
            ActPolicyRunner(bad_bundle, _Model())
    with pytest.raises(ValueError, match="POLICY_INTERFACE_INVALID"):
        ActPolicyRunner(_bundle(), object())
    with pytest.raises(ValueError, match="POLICY_SESSION_INVALID"):
        ActPolicyRunner(_bundle(), _Model()).reset("", "a")


def test_the_policy_module_touches_no_ros_api():
    import so101_demo.act.policy as policy

    source = open(policy.__file__).read()
    assert "rclpy" not in source and "import ros" not in source
