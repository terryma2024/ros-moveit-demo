"""Task 13: the runner-facing ACT policy contract.

Two things are easy to get wrong here and expensive to notice later. The action chunk must stay anchored
to the observation's own time origin — a chunk that quietly re-bases its timestamps desynchronises every
downstream comparison — and the runner must apply exactly the execution prefix the frozen config names,
in physical radians, without touching any ROS API.
"""

from __future__ import annotations

import math

DT_S = 0.1
_JOINTS = 6
_OBSERVATION_KEYS = frozenset({"sim_time_s", "head", "wrist", "state"})
_STATE_DIM = 8


def target_times(observed_s: float, count: int) -> tuple:
    """The 10 Hz target times of an action chunk, anchored to the observation time."""

    if isinstance(observed_s, bool) or not isinstance(observed_s, (int, float)) \
            or not math.isfinite(observed_s):
        raise ValueError("OBSERVATION_TIME_INVALID")
    if type(count) is not int or count < 1:
        raise ValueError("CHUNK_COUNT_INVALID")
    return tuple(round(observed_s + DT_S * step, 6) for step in range(1, count + 1))


def _actions(values, count: int) -> tuple:
    if not isinstance(values, (list, tuple)) or len(values) < count:
        raise ValueError("POLICY_ACTION_INVALID")
    selected = []
    for row in values[:count]:
        if not isinstance(row, (list, tuple)) or len(row) != _JOINTS:
            raise ValueError("POLICY_ACTION_INVALID")
        joints = []
        for value in row:
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(value):
                raise ValueError("POLICY_ACTION_INVALID")
            joints.append(float(value))
        selected.append(tuple(joints))
    return tuple(selected)


class ActPolicyRunner:
    """Applies a bundle's frozen prefix to a model's chunk and reports the action prefix."""

    def __init__(self, bundle: dict, infer) -> None:
        if not isinstance(bundle, dict) or not isinstance(bundle.get("action"), dict):
            raise ValueError("POLICY_BUNDLE_INVALID")
        action = bundle["action"]
        prefix = action.get("execution_prefix")
        if type(prefix) is not int or prefix < 1:
            raise ValueError("POLICY_BUNDLE_INVALID")
        if not callable(getattr(infer, "infer", None)) or not callable(getattr(infer, "reset", None)):
            raise ValueError("POLICY_INTERFACE_INVALID")
        self.bundle = bundle
        self.infer = infer
        self.execution_prefix = prefix
        self.session_id = None
        self.attempt_id = None

    def reset(self, session_id: str, attempt_id: str) -> None:
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("POLICY_SESSION_INVALID")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise ValueError("POLICY_SESSION_INVALID")
        self.infer.reset()
        self.session_id, self.attempt_id = session_id, attempt_id

    def predict(self, observation: dict, sequence: int) -> dict:
        if self.session_id is None or self.attempt_id is None:
            # a chunk produced from a stale model state is not evidence for this attempt
            raise ValueError("POLICY_NOT_RESET")
        if not isinstance(observation, dict) or set(observation) != _OBSERVATION_KEYS:
            raise ValueError("POLICY_OBSERVATION_INVALID")
        if not isinstance(observation["state"], (list, tuple)) \
                or len(observation["state"]) != _STATE_DIM:
            raise ValueError("POLICY_OBSERVATION_INVALID")
        observed_s = observation["sim_time_s"]
        if isinstance(observed_s, bool) or not isinstance(observed_s, (int, float)) \
                or not math.isfinite(observed_s):
            raise ValueError("POLICY_OBSERVATION_INVALID")
        if type(sequence) is not int or sequence < 0:
            raise ValueError("POLICY_SEQUENCE_INVALID")
        chunk = self.infer.infer(observation)
        actions = _actions(chunk, self.execution_prefix)
        return {"sequence": sequence, "session_id": self.session_id, "attempt_id": self.attempt_id,
                "observed_s": float(observed_s), "execution_prefix": self.execution_prefix,
                "target_times_s": target_times(float(observed_s), self.execution_prefix),
                "actions": actions}
