"""Strict workflow event encoding, decoding, and phase validation."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Callable


EVENT_PREFIX = b"SO101_EVENT "
EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "workflow_id",
        "sequence",
        "component",
        "event",
        "status",
        "timestamp_ns",
        "failure_code",
        "payload",
    }
)
MAX_EVENT_AGE_NS = 5_000_000_000
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_EVENT_COMPONENT = {
    "STACK_READY": "supervisor",
    "DISPATCH_PREVIEW": "text_agent",
    "PLANNER_FAILED": "text_agent",
    "COMMAND_INVALID": "text_agent",
    "DISPATCH_REJECTED": "text_agent",
    "RUNTIME_STARTED": "dynamic_runtime",
    "RUNTIME_READY": "dynamic_runtime",
    "RUNTIME_COMPLETED": "dynamic_runtime",
    "RUNTIME_FAILED": "dynamic_runtime",
    "PERCEPTION_READY": "perception",
    "TARGET_SELECTED": "perception",
    "CUP_POSE_PUBLISHED": "perception",
    "PERCEPTION_FAILED": "perception",
    "E2E_ACCEPTED": "e2e_validator",
    "E2E_REJECTED": "e2e_validator",
}
_FAILURE_CODES_BY_EVENT = {
    "PLANNER_FAILED": frozenset(
        {"PLANNER_CHAIN_FAILED", "PLANNER_INTERNAL_ERROR"}
    ),
    "COMMAND_INVALID": frozenset(
        {"COMMAND_INVALID", "INPUT_INVALID", "COMMAND_INTERNAL_ERROR"}
    ),
    "DISPATCH_REJECTED": frozenset(
        {
            "REQUEST_ID_INVALID",
            "PLANNER_OUTCOME_UNSUPPORTED",
            "PLANNER_OUTCOME_AMBIGUOUS",
            "CAPABILITY_UNSUPPORTED",
            "CONSTRAINT_UNCONSUMED",
            "EXPLICIT_EXECUTE_REQUIRED",
            "BACKEND_NOT_QUALIFIED",
            "CONFIRMATION_DIGEST_REQUIRED",
            "CONFIRMATION_DIGEST_INVALID",
            "CONFIRMATION_DIGEST_MISMATCH",
            "CONFIRMATION_BYPASS_REQUIRES_EXECUTE",
            "CONFIRMATION_MODE_CONFLICT",
            "DUPLICATE_REQUEST_ID",
            "DISPATCH_INTERNAL_ERROR",
        }
    ),
    "RUNTIME_FAILED": frozenset(
        {
            "RUNTIME_FAILED",
            "DYNAMIC_RUNTIME_CONTEXT_INVALID",
            "DYNAMIC_RUNTIME_EXCEPTION",
            "DYNAMIC_RUNTIME_RESULT_INVALID",
            "EXECUTOR_RESULT_INVALID",
            "DYNAMIC_EXECUTION_NOT_QUALIFIED",
            "DYNAMIC_LIVE_RUNTIME_CONFIG_REQUIRED",
            "DYNAMIC_EXECUTION_FAILED",
            "DYNAMIC_EXECUTION_FINISH_FAILED",
            "DYNAMIC_EXECUTION_CLEANUP_FAILED",
            "DYNAMIC_TARGET_UNREACHABLE",
            "DYNAMIC_TARGET_REACHABILITY_UNKNOWN",
            "DYNAMIC_PLAN_FAILED",
            "CUP_POSE_PLAN_FAILED",
            "CUP_POSE_TIMEOUT",
            "CUP_POSE_INVALID",
            "CUP_POSE_TF_UNAVAILABLE",
            "CUP_POSE_SCENE_IDENTITY_MISSING",
            "CUP_POSE_SCENE_SESSION_MISMATCH",
            "CUP_POSE_SCENE_RESET_EPOCH_MISMATCH",
            "CUP_POSE_SCENE_PAUSED",
            "CUP_POSE_SCENE_DIVERGENCE",
            "DYNAMIC_SESSION_MISMATCH",
            "DYNAMIC_RESET_EPOCH_MISMATCH",
            "DYNAMIC_EVIDENCE_TIMEOUT",
            "DYNAMIC_STABLE_STATE_TIMEOUT",
            "DYNAMIC_FORCE_LIMIT_EXCEEDED",
            "DYNAMIC_EARLY_TABLE_CONTACT",
            "DYNAMIC_PRECLOSE_CUP_MOVED",
            "DYNAMIC_ACM_APPLY_FAILED",
            "DYNAMIC_ATTACH_FAILED",
            "DYNAMIC_ATTACH_READBACK_MISMATCH",
            "DYNAMIC_DETACH_SYNC_FAILED",
            "DYNAMIC_DETACH_SYNC_READBACK_MISMATCH",
            "DYNAMIC_FINAL_PLACEMENT_NOT_PROVED",
            "DYNAMIC_PHYSICAL_GRASP_NOT_PROVED",
            "DYNAMIC_MICRO_LIFT_NOT_PROVED",
            "JOINT_STATE_TIMEOUT",
            "MOVEIT_EXECUTION_FAILED",
            "GRIPPER_COMMAND_FAILED",
            "RCLPY_INIT_FAILED",
            "NODE_CREATE_FAILED",
            "DYNAMIC_RUNTIME_INTERNAL_ERROR",
        }
    ),
    "PERCEPTION_FAILED": frozenset(
        {
            "TARGET_NOT_FOUND",
            "TARGET_AMBIGUOUS",
            "DEPTH_INVALID",
            "TF_UNAVAILABLE",
            "RGBD_INVALID",
            "GEOMETRY_REJECTED",
            "MODEL_UNAVAILABLE",
            "MODEL_LOAD_FAILED",
            "MODEL_BUNDLE_INVALID",
            "MODEL_HASH_MISMATCH",
            "WEIGHTS_HASH_MISMATCH",
            "DEVICE_UNAVAILABLE",
            "INFERENCE_FAILED",
            "EVIDENCE_WRITE_FAILED",
            "OUTPUT_SUBSCRIBER_UNAVAILABLE",
            "RGBD_TIMEOUT",
            "SIM_CLOCK_UNAVAILABLE",
            "CLEANUP_FAILED",
            "RGBD_CUP_POSE_PREFLIGHT_FAILED",
            "RGBD_CUP_POSE_FRAME_INVALID",
            "RGBD_CUP_POSE_STALE_FRAME",
            "RGBD_CUP_POSE_TF_UNAVAILABLE",
            "RGBD_CUP_POSE_TIMEOUT",
            "RGBD_CUP_POSE_FATAL",
            "RGBD_CUP_POSE_CLEANUP_FAILED",
            "PERCEPTION_INTERNAL_ERROR",
        }
    ),
    "E2E_REJECTED": frozenset(
        {
            "E2E_EVIDENCE_REJECTED",
            "E2E_IDENTITY_MISMATCH",
            "E2E_DYNAMIC_EVIDENCE_INVALID",
            "E2E_MUJOCO_FINAL_INVALID",
            "E2E_PLANNING_SCENE_INVALID",
            "E2E_VALIDATION_INTERNAL_ERROR",
        }
    ),
}
_SUCCESS_EVENTS = frozenset(_EVENT_COMPONENT).difference(_FAILURE_CODES_BY_EVENT)
_PAYLOAD_FIELDS = {
    "DISPATCH_PREVIEW": frozenset({"request_id", "provider", "model", "fallback"}),
    "RUNTIME_STARTED": frozenset({"request_id", "session_id", "reset_epoch"}),
    "RUNTIME_READY": frozenset({"request_id", "session_id", "reset_epoch"}),
    "TARGET_SELECTED": frozenset({"target_id", "class_name"}),
    "CUP_POSE_PUBLISHED": frozenset({"source_stamp_ns", "frame_id"}),
    "RUNTIME_COMPLETED": frozenset({"manifest_path", "runtime_exit_code"}),
    "E2E_ACCEPTED": frozenset({"result_path"}),
    "E2E_REJECTED": frozenset({"result_path"}),
}
_REQUIRED_PAYLOAD_FIELDS = {
    "RUNTIME_COMPLETED": frozenset({"manifest_path", "runtime_exit_code"}),
    "E2E_ACCEPTED": frozenset({"result_path"}),
    "E2E_REJECTED": frozenset({"result_path"}),
}
_INTERNAL_FAILURE_CODE = {
    "PLANNER_FAILED": "PLANNER_INTERNAL_ERROR",
    "COMMAND_INVALID": "COMMAND_INTERNAL_ERROR",
    "DISPATCH_REJECTED": "DISPATCH_INTERNAL_ERROR",
    "RUNTIME_FAILED": "DYNAMIC_RUNTIME_INTERNAL_ERROR",
    "PERCEPTION_FAILED": "PERCEPTION_INTERNAL_ERROR",
    "E2E_REJECTED": "E2E_VALIDATION_INTERNAL_ERROR",
}
_STRING_PAYLOAD_FIELDS = frozenset(
    {
        "request_id",
        "provider",
        "model",
        "session_id",
        "target_id",
        "class_name",
        "frame_id",
        "manifest_path",
        "result_path",
    }
)
_INTEGER_PAYLOAD_FIELDS = frozenset(
    {"reset_epoch", "source_stamp_ns", "runtime_exit_code"}
)


class WorkflowProtocolError(ValueError):
    """Report a fail-closed workflow protocol violation."""

    def __init__(self, detail: str = "") -> None:
        super().__init__("EVENT_PROTOCOL_INVALID")
        self.code = "EVENT_PROTOCOL_INVALID"
        self.detail = detail


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    schema_version: int
    workflow_id: str
    sequence: int
    component: str
    event: str
    status: str
    timestamp_ns: int
    failure_code: str | None
    payload: dict[str, object]


def _invalid(detail: str) -> WorkflowProtocolError:
    return WorkflowProtocolError(detail)


def _reject_json_constant(value: str) -> object:
    raise _invalid(f"non-standard JSON constant: {value}")


def _validate_payload(event: str, payload: object) -> dict[str, object]:
    if type(payload) is not dict:
        raise _invalid("payload must be an object")
    allowed = _PAYLOAD_FIELDS.get(event, frozenset())
    keys = frozenset(payload)
    if keys.difference(allowed):
        raise _invalid("payload contains unknown fields")
    if not _REQUIRED_PAYLOAD_FIELDS.get(event, frozenset()).issubset(keys):
        raise _invalid("payload is missing required fields")
    for name, value in payload.items():
        if type(name) is not str:
            raise _invalid("payload field names must be strings")
        if name in _STRING_PAYLOAD_FIELDS and (
            type(value) is not str or not value.strip()
        ):
            raise _invalid(f"payload {name} must be a non-empty string")
        if name in _INTEGER_PAYLOAD_FIELDS and (
            type(value) is not int or value < 0
        ):
            raise _invalid(f"payload {name} must be a non-negative integer")
        if name == "fallback" and type(value) is not bool:
            raise _invalid("payload fallback must be a boolean")
    if event == "RUNTIME_COMPLETED" and payload["runtime_exit_code"] != 0:
        raise _invalid("RUNTIME_COMPLETED requires runtime_exit_code zero")
    return dict(payload)


def normalize_failure_code(event: str, candidate: object) -> str:
    """Return a registered code or the event's fixed internal failure code."""

    if event not in _FAILURE_CODES_BY_EVENT:
        raise ValueError("event does not accept a failure code")
    if type(candidate) is str and candidate in _FAILURE_CODES_BY_EVENT[event]:
        return candidate
    return _INTERNAL_FAILURE_CODE[event]


def _validate_document(
    document: object,
    *,
    workflow_id: str,
    allowed_components: frozenset[str],
    now_ns: int,
) -> WorkflowEvent:
    if type(document) is not dict or frozenset(document) != EVENT_FIELDS:
        raise _invalid("event must contain the exact schema fields")
    if type(now_ns) is not int or now_ns < 0:
        raise _invalid("arrival timestamp must be a non-negative integer")
    schema_version = document["schema_version"]
    sequence = document["sequence"]
    timestamp_ns = document["timestamp_ns"]
    if type(schema_version) is not int or schema_version != 1:
        raise _invalid("unsupported schema version")
    if type(sequence) is not int or sequence <= 0:
        raise _invalid("sequence must be a positive integer")
    if type(timestamp_ns) is not int or timestamp_ns < 0:
        raise _invalid("timestamp_ns must be a non-negative integer")
    age_ns = now_ns - timestamp_ns
    if age_ns < 0 or age_ns > MAX_EVENT_AGE_NS:
        raise _invalid("event timestamp is outside the acceptance window")

    record_workflow_id = document["workflow_id"]
    component = document["component"]
    event = document["event"]
    status = document["status"]
    failure_code = document["failure_code"]
    if type(record_workflow_id) is not str or record_workflow_id != workflow_id:
        raise _invalid("workflow binding mismatch")
    if type(component) is not str or component not in allowed_components:
        raise _invalid("component binding mismatch")
    if type(event) is not str or _EVENT_COMPONENT.get(event) != component:
        raise _invalid("event is not owned by the component")
    if event in _SUCCESS_EVENTS:
        if status != "OK" or failure_code is not None:
            raise _invalid("success event status is invalid")
    else:
        if (
            status != "ERROR"
            or type(failure_code) is not str
            or failure_code not in _FAILURE_CODES_BY_EVENT[event]
        ):
            raise _invalid("failure event status or code is invalid")
    payload = _validate_payload(event, document["payload"])
    return WorkflowEvent(
        schema_version=schema_version,
        workflow_id=record_workflow_id,
        sequence=sequence,
        component=component,
        event=event,
        status=status,
        timestamp_ns=timestamp_ns,
        failure_code=failure_code,
        payload=payload,
    )


class EventEmitter:
    """Create one component's strictly sequenced, immediately flushed events."""

    def __init__(
        self,
        workflow_id: str,
        component: str,
        write: Callable[[str], None],
        clock_ns: Callable[[], int],
    ) -> None:
        if (
            type(workflow_id) is not str
            or _IDENTIFIER_PATTERN.fullmatch(workflow_id) is None
            or component not in frozenset(_EVENT_COMPONENT.values())
            or not callable(write)
            or not callable(clock_ns)
        ):
            raise ValueError("invalid event emitter configuration")
        self._workflow_id = workflow_id
        self._component = component
        self._write = write
        self._clock_ns = clock_ns
        owner = getattr(write, "__self__", None)
        flush = getattr(owner, "flush", None)
        if flush is None:
            flush = getattr(write, "flush", None)
        self._flush = flush if callable(flush) else None
        self._sequence = 0
        self._last_event: WorkflowEvent | None = None

    @property
    def workflow_id(self) -> str:
        return self._workflow_id

    @property
    def component(self) -> str:
        return self._component

    @property
    def last_event(self) -> WorkflowEvent | None:
        return self._last_event

    def emit(
        self,
        event: str,
        *,
        payload: dict[str, object],
        failure_code: str | None = None,
    ) -> WorkflowEvent:
        """Validate and write the next event for this component."""

        timestamp_ns = self._clock_ns()
        document = {
            "schema_version": 1,
            "workflow_id": self._workflow_id,
            "sequence": self._sequence + 1,
            "component": self._component,
            "event": event,
            "status": "ERROR" if failure_code is not None else "OK",
            "timestamp_ns": timestamp_ns,
            "failure_code": failure_code,
            "payload": payload,
        }
        workflow_event = _validate_document(
            document,
            workflow_id=self._workflow_id,
            allowed_components=frozenset({self._component}),
            now_ns=timestamp_ns,
        )
        encoded = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        self._sequence = workflow_event.sequence
        self._write(f"SO101_EVENT {encoded}\n")
        if self._flush is not None:
            self._flush()
        self._last_event = workflow_event
        return workflow_event


class WorkflowState:
    """Validate the global cross-component workflow phase order."""

    def __init__(self, backend: str) -> None:
        if backend not in {"color_geometry", "yolo_seg", "grounded_sam"}:
            raise ValueError("unsupported perception backend")
        self._backend = backend
        self._phase = "INITIAL"
        self._terminal = False
        self._identity: dict[str, object] = {}

    def _accept_identity(self, payload: dict[str, object]) -> None:
        correlated = {
            name: payload[name]
            for name in ("request_id", "session_id", "reset_epoch")
            if name in payload
        }
        for name, value in correlated.items():
            if name in self._identity and self._identity[name] != value:
                raise WorkflowProtocolError("workflow identity mismatch")
        self._identity.update(correlated)

    def accept(self, event: WorkflowEvent) -> str | None:
        """Accept one event and return its fixed orchestration effect."""

        if self._terminal or _EVENT_COMPONENT.get(event.event) != event.component:
            raise WorkflowProtocolError("event is invalid for workflow state")
        failure_phases = {
            "PLANNER_FAILED": frozenset({"STACK_READY"}),
            "COMMAND_INVALID": frozenset({"STACK_READY"}),
            "DISPATCH_REJECTED": frozenset({"STACK_READY"}),
            "RUNTIME_FAILED": frozenset(
                {
                    "RUNTIME_STARTED",
                    "RUNTIME_READY",
                    "PERCEPTION_READY",
                    "TARGET_SELECTED",
                    "CUP_POSE_PUBLISHED",
                }
            ),
            "PERCEPTION_FAILED": frozenset(
                {"RUNTIME_READY", "PERCEPTION_READY", "TARGET_SELECTED"}
            ),
            "E2E_REJECTED": frozenset({"RUNTIME_COMPLETED"}),
        }
        if event.event in failure_phases:
            if (
                self._phase not in failure_phases[event.event]
                or event.status != "ERROR"
                or event.failure_code not in _FAILURE_CODES_BY_EVENT[event.event]
            ):
                raise WorkflowProtocolError("failure event is out of phase")
            self._phase = event.event
            self._terminal = True
            return "FAIL"
        expected = {
            "INITIAL": "STACK_READY",
            "STACK_READY": "DISPATCH_PREVIEW",
            "DISPATCH_PREVIEW": "RUNTIME_STARTED",
            "RUNTIME_STARTED": "RUNTIME_READY",
            "RUNTIME_READY": "PERCEPTION_READY",
            "PERCEPTION_READY": (
                "CUP_POSE_PUBLISHED"
                if self._backend == "color_geometry"
                else "TARGET_SELECTED"
            ),
            "TARGET_SELECTED": "CUP_POSE_PUBLISHED",
            "CUP_POSE_PUBLISHED": "RUNTIME_COMPLETED",
            "RUNTIME_COMPLETED": "E2E_ACCEPTED",
        }.get(self._phase)
        if event.event != expected or event.status != "OK" or event.failure_code is not None:
            raise WorkflowProtocolError("workflow event is out of order")
        self._accept_identity(event.payload)
        self._phase = event.event
        if event.event == "RUNTIME_READY":
            return "START_PERCEPTION"
        if event.event == "RUNTIME_COMPLETED":
            return "START_ACCEPTANCE"
        if event.event == "E2E_ACCEPTED":
            self._terminal = True
            return "ACCEPT"
        return None


class EventDecoder:
    """Decode newline-delimited workflow events from one child process."""

    def __init__(self, workflow_id: str, allowed_components: frozenset[str]) -> None:
        if (
            type(workflow_id) is not str
            or _IDENTIFIER_PATTERN.fullmatch(workflow_id) is None
            or type(allowed_components) is not frozenset
            or not allowed_components
            or not allowed_components.issubset(frozenset(_EVENT_COMPONENT.values()))
        ):
            raise ValueError("invalid event decoder binding")
        self._workflow_id = workflow_id
        self._allowed_components = allowed_components
        self._buffer = bytearray()
        self._sequences = {component: 0 for component in allowed_components}

    def _decode_and_validate(self, raw: bytes, *, now_ns: int) -> WorkflowEvent:
        try:
            document = json.loads(raw, parse_constant=_reject_json_constant)
            event = _validate_document(
                document,
                workflow_id=self._workflow_id,
                allowed_components=self._allowed_components,
                now_ns=now_ns,
            )
        except WorkflowProtocolError:
            raise
        except (TypeError, ValueError) as error:
            raise WorkflowProtocolError("invalid event record") from error
        expected_sequence = self._sequences[event.component] + 1
        if event.sequence != expected_sequence:
            raise WorkflowProtocolError("component sequence mismatch")
        self._sequences[event.component] = event.sequence
        return event

    def feed(self, chunk: bytes, *, now_ns: int) -> list[WorkflowEvent]:
        self._buffer.extend(chunk)
        events: list[WorkflowEvent] = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                return events
            line = bytes(self._buffer[:newline])
            del self._buffer[: newline + 1]
            if line.startswith(b"SO101_EVENT") and not line.startswith(EVENT_PREFIX):
                raise WorkflowProtocolError("invalid event prefix")
            if not line.startswith(EVENT_PREFIX):
                continue
            events.append(
                self._decode_and_validate(line[len(EVENT_PREFIX) :], now_ns=now_ns)
            )

    def finish(self, *, now_ns: int) -> list[WorkflowEvent]:
        """Finish one child stream, rejecting a truncated event record."""

        del now_ns
        tail = bytes(self._buffer)
        self._buffer.clear()
        if tail.startswith(b"SO101_EVENT"):
            raise WorkflowProtocolError("truncated event record")
        return []
