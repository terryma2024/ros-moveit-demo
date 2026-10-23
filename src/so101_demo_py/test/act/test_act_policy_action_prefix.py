"""The runner's prediction becomes the exact action prefix the execution adapter validates."""

import pytest

from so101_demo.act.contracts import validate_action_prefix
from so101_demo.act.policy import ActPolicyRunner, observation_spec, to_action_prefix


def _bundle(prefix=1, normalization=None):
    return {"schema_version": 1, "kind": "act_bundle",
            "action": {"chunk_size": 10, "execution_prefix": prefix,
                       "temporal_ensembling": False, "tail_padding_mask": True},
            "normalization": normalization if normalization is not None
            else {"state_mean": [0.0] * 8}}


class _Model:
    def __init__(self):
        self.seen = []

    def reset(self):
        pass

    def infer(self, observation):
        self.seen.append(observation)
        return tuple((0.01 * (row + 1),) * 6 for row in range(10))


def _prediction(prefix=2, observed=5.0):
    runner = ActPolicyRunner(_bundle(prefix), _Model())
    runner.reset("session-1", "attempt-1")
    return runner.predict({"sim_time_s": observed, "head": "h", "wrist": "w", "state": [0.0] * 8}, 7)


def test_prefix_satisfies_the_adapter_contract_and_keeps_the_identity():
    prefix = to_action_prefix(_prediction())
    checked = validate_action_prefix(prefix)
    assert (checked["session_id"], checked["attempt_id"], checked["sequence"]) == ("session-1", "attempt-1", 7)
    assert checked["observation_time_s"] == 5.0
    assert checked["target_times_s"] == pytest.approx((5.1, 5.2))
    assert checked["positions"] == ((0.01,) * 6, (0.02,) * 6)


def test_prefix_is_a_plain_closed_document():
    assert set(to_action_prefix(_prediction())) == {
        "session_id", "attempt_id", "sequence", "observation_time_s", "target_times_s", "positions"}


@pytest.mark.parametrize("damage", [
    lambda p: p.pop("actions"), lambda p: p.update(actions=()),
    lambda p: p.update(target_times_s=(5.1,)), lambda p: p.update(observed_s=float("nan")),
    lambda p: p.update(session_id="")])
def test_a_damaged_prediction_is_refused(damage):
    prediction = dict(_prediction())
    damage(prediction)
    with pytest.raises(ValueError, match="POLICY_PREDICTION_INVALID"):
        to_action_prefix(prediction)


def test_runner_accepts_the_cameras_and_state_dim_of_its_bundle():
    spec = {"cameras": ("side", "wrist"), "state_dim": 6}
    model = _Model()
    runner = ActPolicyRunner(_bundle(1), model, observation=spec)
    runner.reset("s", "a")
    result = runner.predict({"sim_time_s": 1.0, "side": "x", "wrist": "y", "state": [0.0] * 6}, 0)
    assert result["actions"][0] == (0.01,) * 6
    with pytest.raises(ValueError, match="POLICY_OBSERVATION_INVALID"):
        runner.predict({"sim_time_s": 2.0, "head": "x", "wrist": "y", "state": [0.0] * 6}, 1)
    with pytest.raises(ValueError, match="POLICY_OBSERVATION_INVALID"):
        runner.predict({"sim_time_s": 2.0, "side": "x", "wrist": "y", "state": [0.0] * 8}, 1)


def test_observation_spec_reads_the_bundle_then_the_declared_legacy_default():
    declared = _bundle(normalization={"state_mean": [0.0] * 6,
                                      "observation": {"cameras": ["side", "wrist"], "state_dim": 6}})
    assert observation_spec(declared) == {"cameras": ("side", "wrist"), "state_dim": 6}
    legacy = _bundle(normalization={"state_mean": [0.0] * 8})
    assert observation_spec(legacy, legacy_cameras=("head", "wrist")) == {
        "cameras": ("head", "wrist"), "state_dim": 8}
    with pytest.raises(ValueError, match="BUNDLE_OBSERVATION_UNDECLARED"):
        observation_spec(legacy)
    mismatch = _bundle(normalization={"state_mean": [0.0] * 8,
                                      "observation": {"cameras": ["head", "wrist"], "state_dim": 6}})
    with pytest.raises(ValueError, match="BUNDLE_OBSERVATION_INVALID"):
        observation_spec(mismatch)
    duplicate = _bundle(normalization={"state_mean": [0.0] * 8,
                                       "observation": {"cameras": ["head", "head"], "state_dim": 8}})
    with pytest.raises(ValueError, match="BUNDLE_OBSERVATION_INVALID"):
        observation_spec(duplicate)
