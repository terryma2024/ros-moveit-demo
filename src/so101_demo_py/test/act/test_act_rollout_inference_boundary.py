"""What the rollout adds to the inference boundary and the runner: abandon a refused request, and take a chunk computed elsewhere."""

import pytest

from so101_demo.act.policy import ActPolicyRunner
from so101_demo.act.runtime_config import load_runtime_config
from so101_demo.adapters.act.inference_process import ActInferenceProcess
from paths import PACKAGE_ROOT


class _Transport:
    def __init__(self, reply):
        self.sent, self.replies = [], [reply]

    def send(self, request):
        self.sent.append(request)

    def receive(self):
        return self.replies.pop(0) if self.replies else None

    def close(self):
        return True


def test_an_abandoned_request_frees_the_boundary_without_applying_its_reply():
    transport = _Transport({"sequence": 0, "actions": ((0.0,) * 6,), "age_s": 9.0})
    boundary = ActInferenceProcess(config=load_runtime_config(PACKAGE_ROOT / "config/act/runtime.yaml"),
                                   transport=transport, clock=lambda: 100.0)
    boundary.submit({"sim_time_s": 1.0, "state": [0.0] * 8}, sequence=0)
    with pytest.raises(ValueError, match="INFERENCE_REPLY_STALE"):
        boundary.poll()
    assert boundary.pending is not None                         # a refusal alone leaves the request in flight
    boundary.abandon()
    assert boundary.pending is None
    boundary.submit({"sim_time_s": 1.1, "state": [0.0] * 8}, sequence=1)
    assert [item["sequence"] for item in transport.sent] == [0, 1]
    boundary.close()
    with pytest.raises(ValueError, match="INFERENCE_PROCESS_CLOSED"):
        boundary.abandon()


def _bundle(prefix):
    return {"action": {"chunk_size": 10, "execution_prefix": prefix, "temporal_ensembling": False,
                       "tail_padding_mask": True}}


class _Forbidden:
    def reset(self):
        pass

    def infer(self, observation):
        raise AssertionError("the model must not run")


def test_a_chunk_computed_elsewhere_gets_the_same_checks_and_never_calls_the_model():
    runner = ActPolicyRunner(_bundle(2), _Forbidden())
    observation = {"sim_time_s": 3.0, "head": "h", "wrist": "w", "state": [0.0] * 8}
    with pytest.raises(ValueError, match="POLICY_NOT_RESET"):
        runner.predict_from_chunk(observation, 0, ((0.0,) * 6,) * 10)
    runner.reset("s", "a")
    chunk = tuple((0.1 * (row + 1),) * 6 for row in range(10))
    result = runner.predict_from_chunk(observation, 4, chunk)
    assert result["actions"] == chunk[:2] and result["sequence"] == 4
    with pytest.raises(ValueError, match="POLICY_ACTION_INVALID"):
        runner.predict_from_chunk(observation, 5, ((0.0,) * 5,) * 10)
    with pytest.raises(ValueError, match="POLICY_OBSERVATION_INVALID"):
        runner.predict_from_chunk({"sim_time_s": 3.0, "state": [0.0] * 8}, 5, chunk)
