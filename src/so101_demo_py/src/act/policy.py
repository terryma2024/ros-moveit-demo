"""The runner-facing ACT policy contract.

Two things are easy to get wrong here and expensive to notice later. The action chunk must stay anchored
to the observation's own time origin — a chunk that quietly re-bases its timestamps desynchronises every
downstream comparison — and the runner must apply exactly the execution prefix the frozen config names,
in physical radians, without touching any ROS API.
"""

from __future__ import annotations

import math

DT_S = 0.1
_JOINTS = 6
#: The default observation of the shipped bundles. A bundle that declares its own cameras and state width, or a caller that
#: passes `observation=`, replaces both; nothing below assumes these names.
_DEFAULT_CAMERAS = ("head", "wrist")
_DEFAULT_STATE_DIM = 8


def observation_spec(bundle: dict, *, legacy_cameras=None) -> dict:
    """The cameras and the state width a bundle's policy takes, read from the bundle.

    A bundle declares them as ``normalization.observation = {"cameras": [...], "state_dim": N}``. A bundle written before that
    declaration existed has only its normalisation statistics: the state width is then the length of ``state_mean`` and the
    cameras are ``legacy_cameras`` (the caller's configured default for such bundles), or the bundle is refused.
    """

    normalization = bundle.get("normalization") if isinstance(bundle, dict) else None
    if not isinstance(normalization, dict):
        raise ValueError("BUNDLE_OBSERVATION_INVALID")
    mean = normalization.get("state_mean")
    declared = normalization.get("observation")
    if declared is None:
        if legacy_cameras is None:
            raise ValueError("BUNDLE_OBSERVATION_UNDECLARED")
        cameras, state_dim = legacy_cameras, len(mean) if isinstance(mean, list) else None
    else:
        if not isinstance(declared, dict) or set(declared) != {"cameras", "state_dim"}:
            raise ValueError("BUNDLE_OBSERVATION_INVALID")
        cameras, state_dim = declared["cameras"], declared["state_dim"]
    if (not isinstance(cameras, (list, tuple)) or not cameras or len(set(cameras)) != len(cameras)
            or any(not isinstance(name, str) or not name or name in {"sim_time_s", "state"} for name in cameras)
            or type(state_dim) is not int or state_dim < 1
            or (isinstance(mean, list) and len(mean) != state_dim)):
        raise ValueError("BUNDLE_OBSERVATION_INVALID")
    return {"cameras": tuple(cameras), "state_dim": state_dim}


def to_action_prefix(prediction: dict) -> dict:
    """The execution adapter's action prefix for a runner prediction (the document `validate_action_prefix` accepts).

    The identity, the sequence and the observation time come from the prediction unchanged; the target times are the prediction's
    own, anchored to the observation. Nothing is re-based or padded here.
    """

    from .contracts import ContractError, validate_action_prefix

    keys = {"sequence", "session_id", "attempt_id", "observed_s", "execution_prefix", "target_times_s", "actions"}
    if not isinstance(prediction, dict) or set(prediction) != keys:
        raise ValueError("POLICY_PREDICTION_INVALID")
    try:
        prefix = {"session_id": prediction["session_id"], "attempt_id": prediction["attempt_id"],
                  "sequence": prediction["sequence"], "observation_time_s": prediction["observed_s"],
                  "target_times_s": tuple(prediction["target_times_s"]),
                  "positions": tuple(tuple(row) for row in prediction["actions"])}
        validate_action_prefix(prefix)
    except (ContractError, TypeError) as error:
        raise ValueError("POLICY_PREDICTION_INVALID") from error
    if len(prefix["positions"]) != prediction["execution_prefix"]:
        raise ValueError("POLICY_PREDICTION_INVALID")
    return prefix


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

    def __init__(self, bundle: dict, infer, *, observation: dict | None = None) -> None:
        if not isinstance(bundle, dict) or not isinstance(bundle.get("action"), dict):
            raise ValueError("POLICY_BUNDLE_INVALID")
        action = bundle["action"]
        prefix = action.get("execution_prefix")
        if type(prefix) is not int or prefix < 1:
            raise ValueError("POLICY_BUNDLE_INVALID")
        if not callable(getattr(infer, "infer", None)) or not callable(getattr(infer, "reset", None)):
            raise ValueError("POLICY_INTERFACE_INVALID")
        spec = ({"cameras": _DEFAULT_CAMERAS, "state_dim": _DEFAULT_STATE_DIM}
                if observation is None else observation)
        if (not isinstance(spec, dict) or set(spec) != {"cameras", "state_dim"} or not spec["cameras"]
                or type(spec["state_dim"]) is not int or spec["state_dim"] < 1):
            raise ValueError("POLICY_BUNDLE_INVALID")
        self.observation_keys = frozenset({"sim_time_s", "state", *spec["cameras"]})
        self.state_dim = spec["state_dim"]
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
        return self._prediction(observation, sequence, None)

    def predict_from_chunk(self, observation: dict, sequence: int, chunk) -> dict:
        """The prediction for a chunk that was computed elsewhere (a worker thread or process) for exactly this observation.

        The same checks as `predict` apply; the model is not called. The caller owns the claim that `chunk` answers
        `observation` (the inference boundary matches replies to requests by sequence).
        """

        return self._prediction(observation, sequence, chunk)

    def _prediction(self, observation: dict, sequence: int, chunk) -> dict:
        if self.session_id is None or self.attempt_id is None:
            # a chunk produced from a stale model state is not evidence for this attempt
            raise ValueError("POLICY_NOT_RESET")
        if not isinstance(observation, dict) or set(observation) != self.observation_keys:
            raise ValueError("POLICY_OBSERVATION_INVALID")
        if not isinstance(observation["state"], (list, tuple)) \
                or len(observation["state"]) != self.state_dim:
            raise ValueError("POLICY_OBSERVATION_INVALID")
        observed_s = observation["sim_time_s"]
        if isinstance(observed_s, bool) or not isinstance(observed_s, (int, float)) \
                or not math.isfinite(observed_s):
            raise ValueError("POLICY_OBSERVATION_INVALID")
        if type(sequence) is not int or sequence < 0:
            raise ValueError("POLICY_SEQUENCE_INVALID")
        if chunk is None:
            chunk = self.infer.infer(observation)
        actions = _actions(chunk, self.execution_prefix)
        return {"sequence": sequence, "session_id": self.session_id, "attempt_id": self.attempt_id,
                "observed_s": float(observed_s), "execution_prefix": self.execution_prefix,
                "target_times_s": target_times(float(observed_s), self.execution_prefix),
                "actions": actions}
