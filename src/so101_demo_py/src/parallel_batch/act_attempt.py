"""Collection attempt classification before physical Teacher motion."""

from dataclasses import dataclass, fields

from so101_demo.parallel_batch.act_inference import ActInferenceRequest
from so101_demo.parallel_batch.contracts.common import AttemptStatus
from so101_demo.runtime.inference.contract import OUTCOMES
from so101_demo.runtime.parallel_ros_ports.observations import PerceptionTerminal
from so101_demo.runtime.parallel_worker_parts.receipts import RuntimeDecision


_STOP_FIELDS = frozenset({"fenced", "motion_stopped", "controllers_stopped", "recorder_stopped"})


def _terminal_status(terminal):
    if terminal.disposition == "CANCELLED":
        if terminal.reason != "PERCEPTION_CANCELLED":
            raise ValueError("ACT_PERCEPTION_CLASSIFICATION_MISMATCH")
        return AttemptStatus.INVALID
    expected = ("INVALID" if terminal.wire_outcome in {
        "INPUT_INVALID", "QUEUE_FULL", "QUEUE_TIMEOUT", "INFERENCE_TIMEOUT", "INFRA_ERROR"} else "FAILED")
    reason = ({"QUEUE_TIMEOUT": "PERCEPTION_QUEUE_TIMEOUT", "INFERENCE_TIMEOUT": "PERCEPTION_INFERENCE_TIMEOUT"}
              .get(terminal.wire_outcome, "PERCEPTION_INFRA_ERROR") if expected == "INVALID" else
              "PERCEPTION_MODEL_ERROR" if terminal.wire_outcome == "MODEL_ERROR" else "PERCEPTION_NO_POSE")
    if (terminal.disposition != expected or terminal.reason != reason
            or (terminal.wire_outcome == "DETECTED" and not terminal.rejection_reason)):
        raise ValueError("ACT_PERCEPTION_CLASSIFICATION_MISMATCH")
    return AttemptStatus(expected)


@dataclass(frozen=True, slots=True, kw_only=True)
class ActPerceptionTerminal(PerceptionTerminal):
    request: ActInferenceRequest
    wire_outcome: str
    audit_relative_path: str
    rejection_reason: str | None = None

    def __post_init__(self):
        if (type(self.request) is not ActInferenceRequest
                or self.wire_outcome not in OUTCOMES
                or self.disposition not in {"FAILED", "INVALID", "CANCELLED"}
                or self.audit_relative_path != f"perception/inference/{self.request.request_id}.json"
                or (self.rejection_reason is not None and type(self.rejection_reason) is not str)):
            raise ValueError("ACT_PERCEPTION_TERMINAL_INVALID")
        if (type(self.reason) is not str or not self.reason
                or any(value is not None and (type(value) is not str or not value)
                       for value in (self.failure_type, self.failure_message))):
            raise ValueError("ACT_PERCEPTION_TERMINAL_INVALID")
        _terminal_status(self)


@dataclass(frozen=True, slots=True, kw_only=True)
class ActPerceptionDecision(RuntimeDecision):
    perception: ActPerceptionTerminal
    stop_facts: dict

    def __post_init__(self):
        if (type(self.perception) is not ActPerceptionTerminal or type(self.stop_facts) is not dict
                or set(self.stop_facts) != _STOP_FIELDS
                or any(type(value) is not bool for value in self.stop_facts.values())):
            raise ValueError("ACT_PERCEPTION_DECISION_INVALID")
        stopped = all(self.stop_facts.values())
        expected = _terminal_status(self.perception) if stopped else AttemptStatus.INDETERMINATE
        if (self.status is not expected or self.physical_action_proven_absent is not True
                or self.reason != (self.perception.reason if stopped else "ACT_PERCEPTION_STOP_UNCONFIRMED")
                or self.teacher_execution_status is not None or self.teacher_task_result is not None):
            raise ValueError("ACT_PERCEPTION_DECISION_INVALID")

    @classmethod
    def from_terminal(cls, terminal, *, stop_facts):
        if (type(terminal) is not ActPerceptionTerminal or type(stop_facts) is not dict
                or set(stop_facts) != _STOP_FIELDS
                or any(type(value) is not bool for value in stop_facts.values())):
            raise ValueError("ACT_PERCEPTION_DECISION_INVALID")
        stopped = all(stop_facts.values())
        status = _terminal_status(terminal)
        return cls(status=status if stopped else AttemptStatus.INDETERMINATE,
            reason=terminal.reason if stopped else "ACT_PERCEPTION_STOP_UNCONFIRMED",
            physical_action_proven_absent=True, perception=terminal, stop_facts=stop_facts.copy())


def read_act_perception_terminal(workspace):
    """Read the current typed terminal and recheck its original inference audit and scope."""
    import hashlib
    import json
    from pathlib import Path

    from so101_demo.act.result_store import _read_regular
    from so101_demo.parallel_batch.act_inference import ActInferenceResult
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    from so101_demo.runtime.parallel_ipc.frames import _pairs

    def read(path):
        payload = _read_regular(path)
        document = json.loads(payload, object_pairs_hook=_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("nonfinite")))
        if type(document) is not dict:
            raise ValueError("object required")
        return document, payload

    try:
        root = Path(workspace)
        document, _payload = read(root / "perception/terminal.json")
        if (set(document) != {"schema_version", "kind", "terminal", "inference_audit_sha256"}
                or type(document["schema_version"]) is not int or document["schema_version"] != 1
                or document["kind"] != "ACT_PERCEPTION_TERMINAL"):
            raise ValueError("terminal schema")
        value = document["terminal"]
        if type(value) is not dict or set(value) != {field.name for field in fields(ActPerceptionTerminal)}:
            raise ValueError("terminal fields")
        identity = value["request"]
        if type(identity) is not dict or set(identity) != {field.name for field in fields(ActInferenceRequest)}:
            raise ValueError("request fields")
        request_values = identity.copy()
        if type(request_values["image_shape"]) is not list:
            raise ValueError("request shape")
        request_values["image_shape"] = tuple(request_values["image_shape"])
        request_values["execution_kind"] = ExecutionKind(request_values["execution_kind"])
        request = ActInferenceRequest(**request_values)
        terminal = ActPerceptionTerminal(**{**value, "request": request})
        audit, audit_bytes = read(root / terminal.audit_relative_path)
        if (set(audit) != {"schema_version", "kind", "request", "broker_generation", "response",
                          "started_monotonic_ns", "completed_monotonic_ns", "cancelled"}
                or type(audit["schema_version"]) is not int or audit["schema_version"] != 1
                or audit["kind"] != "ACT_LOCAL_INFERENCE_AUDIT"
                or hashlib.sha256(audit_bytes).hexdigest() != document["inference_audit_sha256"]
                or audit["request"] != identity):
            raise ValueError("audit binding")
        result = ActInferenceResult(request, audit["broker_generation"], audit["response"],
            audit["started_monotonic_ns"], audit["completed_monotonic_ns"], audit["cancelled"])
        if (result.response["outcome"] != terminal.wire_outcome
                or (result.cancelled and terminal.disposition != "CANCELLED")):
            raise ValueError("wire outcome")
        if terminal.disposition == "CANCELLED" or terminal.wire_outcome == "DETECTED":
            diagnostic = (None, None)
        else:
            diagnostic = (f"ActInferenceResponse.{terminal.wire_outcome}",
                          result.reason or terminal.wire_outcome)
        if (terminal.failure_type, terminal.failure_message) != diagnostic:
            raise ValueError("original diagnostic")
        metadata, _payload = read(root / "workspace_identity.json")
        if type(metadata.get("source_stamp")) is not dict or type(metadata.get("identity")) is not dict:
            raise ValueError("workspace schema")
        expected_kind = "execute" if request.execution_kind is ExecutionKind.ATTEMPT else "plan_only"
        names = ("batch_id", "coordinator_epoch", "worker_id", "worker_generation", "point_id", "lease_generation")
        if (metadata.get("run_mode") != expected_kind
                or metadata.get("reset_epoch") != request.reset_epoch
                or metadata.get("source_stamp", {}).get("simulation_session_id") != request.simulation_session_id
                or any(metadata.get("identity", {}).get(name) != getattr(request, name) for name in names)
                or metadata.get("identity", {}).get("attempt_id" if expected_kind == "execute" else "validation_id")
                != (request.attempt_id if expected_kind == "execute" else request.validation_id)):
            raise ValueError("workspace binding")
        return terminal
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise ValueError("ACT_PERCEPTION_TERMINAL_READBACK_INVALID") from error
