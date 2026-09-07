from __future__ import annotations

import json

import pytest

from so101_demo.runtime.workflow_events import (
    EventDecoder,
    EventEmitter,
    WorkflowEvent,
    WorkflowProtocolError,
    WorkflowState,
    normalize_failure_code,
)


def _record(**overrides: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_id": "w1",
        "sequence": 1,
        "component": "text_agent",
        "event": "DISPATCH_PREVIEW",
        "status": "OK",
        "timestamp_ns": 100,
        "failure_code": None,
        "payload": {},
        **overrides,
    }


def _line(**overrides: object) -> bytes:
    return (
        "SO101_EVENT "
        + json.dumps(_record(**overrides), ensure_ascii=False)
        + "\n"
    ).encode()


def _document_line(document: dict[str, object]) -> bytes:
    return (
        "SO101_EVENT "
        + json.dumps(document, ensure_ascii=False, allow_nan=True)
        + "\n"
    ).encode()


def test_event_can_be_split_at_every_byte() -> None:
    line = _line(payload={"model": "杯子模型"})

    for cut in range(len(line)):
        decoder = EventDecoder("w1", frozenset({"text_agent", "dynamic_runtime"}))
        events = decoder.feed(line[:cut], now_ns=100)
        events += decoder.feed(line[cut:], now_ns=100)
        assert len(events) == 1
        assert events[0].event == "DISPATCH_PREVIEW"


def test_decoder_handles_multiple_lines_and_ignores_ordinary_logs() -> None:
    decoder = EventDecoder("w1", frozenset({"text_agent"}))
    stream = b"planner warming up\n" + _line() + _line(sequence=2)

    events = decoder.feed(stream, now_ns=100)

    assert [event.sequence for event in events] == [1, 2]


def test_finish_rejects_prefixed_partial_line_but_ignores_ordinary_tail() -> None:
    decoder = EventDecoder("w1", frozenset({"text_agent"}))
    assert decoder.feed(b"ordinary tail", now_ns=100) == []
    assert decoder.finish(now_ns=100) == []

    decoder = EventDecoder("w1", frozenset({"text_agent"}))
    assert decoder.feed(_line()[:-1], now_ns=100) == []
    with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
        decoder.finish(now_ns=100)


@pytest.mark.parametrize(
    ("overrides", "now_ns"),
    [
        ({"schema_version": 2}, 100),
        ({"schema_version": True}, 100),
        ({"workflow_id": "other"}, 100),
        ({"sequence": True}, 100),
        ({"sequence": 2}, 100),
        ({"component": "unknown"}, 100),
        ({"event": "RUNTIME_READY"}, 100),
        ({"status": "ERROR"}, 100),
        ({"failure_code": "COMMAND_INVALID"}, 100),
        ({"timestamp_ns": True}, 100),
        ({"timestamp_ns": 101}, 100),
        ({"timestamp_ns": 0}, 5_000_000_001),
        ({"timestamp_ns": float("nan")}, 100),
        ({"payload": []}, 100),
        ({"payload": {"unknown": "value"}}, 100),
        ({"payload": {"fallback": "false"}}, 100),
    ],
)
def test_decoder_rejects_invalid_schema_binding_and_payload(
    overrides: dict[str, object], now_ns: int
) -> None:
    decoder = EventDecoder("w1", frozenset({"text_agent"}))

    with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
        decoder.feed(_line(**overrides), now_ns=now_ns)


@pytest.mark.parametrize(
    ("component", "event", "status", "failure_code", "payload"),
    [
        (
            "text_agent",
            "DISPATCH_PREVIEW",
            "OK",
            None,
            {
                "request_id": "r1",
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "fallback": False,
            },
        ),
        (
            "dynamic_runtime",
            "RUNTIME_STARTED",
            "OK",
            None,
            {"request_id": "r1", "session_id": "s1", "reset_epoch": 0},
        ),
        (
            "dynamic_runtime",
            "RUNTIME_READY",
            "OK",
            None,
            {"request_id": "r1", "session_id": "s1", "reset_epoch": 0},
        ),
        (
            "perception",
            "TARGET_SELECTED",
            "OK",
            None,
            {"target_id": "cup-1", "class_name": "plastic_cup"},
        ),
        (
            "perception",
            "CUP_POSE_PUBLISHED",
            "OK",
            None,
            {"source_stamp_ns": 99, "frame_id": "world"},
        ),
        (
            "dynamic_runtime",
            "RUNTIME_COMPLETED",
            "OK",
            None,
            {"manifest_path": "/evidence/manifest.json", "runtime_exit_code": 0},
        ),
        (
            "e2e_validator",
            "E2E_ACCEPTED",
            "OK",
            None,
            {"result_path": "/evidence/result.json"},
        ),
        (
            "e2e_validator",
            "E2E_REJECTED",
            "ERROR",
            "E2E_EVIDENCE_REJECTED",
            {"result_path": "/evidence/result.json"},
        ),
    ],
)
def test_decoder_accepts_each_defined_correlated_payload(
    component: str,
    event: str,
    status: str,
    failure_code: str | None,
    payload: dict[str, object],
) -> None:
    decoder = EventDecoder("w1", frozenset({component}))
    events = decoder.feed(
        _line(
            component=component,
            event=event,
            status=status,
            failure_code=failure_code,
            payload=payload,
        ),
        now_ns=100,
    )
    assert events[0].payload == payload


@pytest.mark.parametrize(
    ("component", "event", "payload"),
    [
        ("dynamic_runtime", "RUNTIME_COMPLETED", {}),
        (
            "dynamic_runtime",
            "RUNTIME_COMPLETED",
            {"manifest_path": "/manifest.json", "runtime_exit_code": 1},
        ),
        (
            "dynamic_runtime",
            "RUNTIME_READY",
            {"session_id": "s1", "reset_epoch": True},
        ),
        (
            "perception",
            "CUP_POSE_PUBLISHED",
            {"source_stamp_ns": -1, "frame_id": "world"},
        ),
        (
            "perception",
            "CUP_POSE_PUBLISHED",
            {"source_stamp_ns": 99, "frame_id": "task_camera_frame"},
        ),
        ("perception", "CUP_POSE_PUBLISHED", {}),
        ("e2e_validator", "E2E_ACCEPTED", {}),
        (
            "e2e_validator",
            "E2E_ACCEPTED",
            {"result_path": ""},
        ),
    ],
)
def test_decoder_rejects_missing_or_invalid_correlated_payload(
    component: str, event: str, payload: dict[str, object]
) -> None:
    decoder = EventDecoder("w1", frozenset({component}))
    with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
        decoder.feed(
            _line(component=component, event=event, payload=payload), now_ns=100
        )


def test_decoder_rejects_unknown_failure_code_and_plain_status_logs() -> None:
    decoder = EventDecoder("w1", frozenset({"perception"}))
    assert decoder.feed(b"status=DONE failure=None\n", now_ns=100) == []
    with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
        decoder.feed(
            _line(
                component="perception",
                event="PERCEPTION_FAILED",
                status="ERROR",
                failure_code="MODEL_OUTPUT_SAID_THIS",
            ),
            now_ns=100,
        )


@pytest.mark.parametrize("remove", ["payload", "failure_code", "timestamp_ns"])
def test_decoder_requires_the_exact_top_level_field_set(remove: str) -> None:
    document = _record()
    del document[remove]
    decoder = EventDecoder("w1", frozenset({"text_agent"}))
    with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
        decoder.feed(_document_line(document), now_ns=100)

    document = _record(extra="forbidden")
    with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
        EventDecoder("w1", frozenset({"text_agent"})).feed(
            _document_line(document), now_ns=100
        )


def test_sequence_is_strict_per_component() -> None:
    decoder = EventDecoder(
        "w1", frozenset({"text_agent", "dynamic_runtime"})
    )
    assert decoder.feed(_line(), now_ns=100)[0].sequence == 1
    assert (
        decoder.feed(
            _line(
                component="dynamic_runtime",
                event="RUNTIME_STARTED",
                payload={"session_id": "s1", "reset_epoch": 0},
            ),
            now_ns=100,
        )[0].sequence
        == 1
    )
    with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
        decoder.feed(_line(), now_ns=100)


def test_malformed_event_prefix_and_json_fail_closed() -> None:
    decoder = EventDecoder("w1", frozenset({"text_agent"}))
    with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
        decoder.feed(b"SO101_EVENT{}\n", now_ns=100)
    with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
        EventDecoder("w1", frozenset({"text_agent"})).feed(
            b"SO101_EVENT {bad json}\n", now_ns=100
        )


class _Writer:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.flush_count = 0

    def write(self, value: str) -> None:
        self.lines.append(value)

    def flush(self) -> None:
        self.flush_count += 1


def test_emitter_assigns_sequence_status_and_flushes_each_record() -> None:
    writer = _Writer()
    timestamps = iter((100, 101))
    emitter = EventEmitter("w1", "text_agent", writer.write, lambda: next(timestamps))

    first = emitter.emit(
        "DISPATCH_PREVIEW",
        payload={"request_id": "r1", "provider": "deepseek", "fallback": False},
    )
    second = emitter.emit(
        "DISPATCH_REJECTED",
        payload={},
        failure_code="CONFIRMATION_DIGEST_MISMATCH",
    )

    assert (first.sequence, first.status, first.failure_code) == (1, "OK", None)
    assert (second.sequence, second.status, second.failure_code) == (
        2,
        "ERROR",
        "CONFIRMATION_DIGEST_MISMATCH",
    )
    assert writer.flush_count == 2
    decoder = EventDecoder("w1", frozenset({"text_agent"}))
    decoded = decoder.feed("".join(writer.lines).encode(), now_ns=101)
    assert decoded == [first, second]


@pytest.mark.parametrize(
    ("event", "failure_code", "payload"),
    [
        ("UNKNOWN", None, {}),
        ("RUNTIME_READY", None, {}),
        ("DISPATCH_PREVIEW", "COMMAND_INVALID", {}),
        ("COMMAND_INVALID", None, {}),
        ("COMMAND_INVALID", "ARBITRARY_MODEL_TEXT", {}),
        ("DISPATCH_PREVIEW", None, {"secret": "must-not-pass"}),
    ],
)
def test_emitter_rejects_unowned_events_and_unfixed_failure_codes(
    event: str, failure_code: str | None, payload: dict[str, object]
) -> None:
    emitter = EventEmitter("w1", "text_agent", lambda _line: None, lambda: 100)
    with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
        emitter.emit(event, payload=payload, failure_code=failure_code)


def test_unknown_component_error_maps_to_one_fixed_internal_code() -> None:
    assert (
        normalize_failure_code("RUNTIME_FAILED", "MODEL_OUTPUT_SAID_THIS")
        == "DYNAMIC_RUNTIME_INTERNAL_ERROR"
    )
    assert (
        normalize_failure_code("RUNTIME_FAILED", "DYNAMIC_TARGET_UNREACHABLE")
        == "DYNAMIC_TARGET_UNREACHABLE"
    )


_COMPONENT_BY_EVENT = {
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


def _workflow_event(
    event: str,
    *,
    failure_code: str | None = None,
    payload: dict[str, object] | None = None,
) -> WorkflowEvent:
    return WorkflowEvent(
        schema_version=1,
        workflow_id="w1",
        sequence=1,
        component=_COMPONENT_BY_EVENT[event],
        event=event,
        status="ERROR" if failure_code else "OK",
        timestamp_ns=100,
        failure_code=failure_code,
        payload=payload or {},
    )


@pytest.mark.parametrize("backend", ["yolo_seg", "grounded_sam"])
def test_model_backend_success_path_has_strict_effects(backend: str) -> None:
    state = WorkflowState(backend)
    path = (
        "STACK_READY",
        "DISPATCH_PREVIEW",
        "RUNTIME_STARTED",
        "RUNTIME_READY",
        "PERCEPTION_READY",
        "TARGET_SELECTED",
        "CUP_POSE_PUBLISHED",
        "RUNTIME_COMPLETED",
        "E2E_ACCEPTED",
    )

    assert [state.accept(_workflow_event(event)) for event in path] == [
        None,
        None,
        None,
        "START_PERCEPTION",
        None,
        None,
        None,
        "START_ACCEPTANCE",
        "ACCEPT",
    ]


def test_color_backend_success_path_skips_target_selection() -> None:
    state = WorkflowState("color_geometry")
    path = (
        "STACK_READY",
        "DISPATCH_PREVIEW",
        "RUNTIME_STARTED",
        "RUNTIME_READY",
        "PERCEPTION_READY",
        "CUP_POSE_PUBLISHED",
        "RUNTIME_COMPLETED",
        "E2E_ACCEPTED",
    )
    effects = [state.accept(_workflow_event(event)) for event in path]

    assert effects[3] == "START_PERCEPTION"
    assert effects[-2:] == ["START_ACCEPTANCE", "ACCEPT"]


def _advance(state: WorkflowState, *events: str) -> None:
    for event in events:
        state.accept(_workflow_event(event))


@pytest.mark.parametrize(
    ("backend", "prefix", "invalid_event"),
    [
        ("yolo_seg", (), "DISPATCH_PREVIEW"),
        ("yolo_seg", ("STACK_READY",), "STACK_READY"),
        (
            "yolo_seg",
            (
                "STACK_READY",
                "DISPATCH_PREVIEW",
                "RUNTIME_STARTED",
                "RUNTIME_READY",
                "PERCEPTION_READY",
            ),
            "CUP_POSE_PUBLISHED",
        ),
        (
            "color_geometry",
            (
                "STACK_READY",
                "DISPATCH_PREVIEW",
                "RUNTIME_STARTED",
                "RUNTIME_READY",
                "PERCEPTION_READY",
            ),
            "TARGET_SELECTED",
        ),
    ],
)
def test_state_rejects_missing_duplicate_and_backend_mismatched_stages(
    backend: str, prefix: tuple[str, ...], invalid_event: str
) -> None:
    state = WorkflowState(backend)
    _advance(state, *prefix)
    with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
        state.accept(_workflow_event(invalid_event))


@pytest.mark.parametrize(
    ("prefix", "event", "failure_code"),
    [
        (("STACK_READY",), "PLANNER_FAILED", "PLANNER_CHAIN_FAILED"),
        (("STACK_READY",), "COMMAND_INVALID", "COMMAND_INVALID"),
        (("STACK_READY",), "DISPATCH_REJECTED", "BACKEND_NOT_QUALIFIED"),
        (
            ("STACK_READY", "DISPATCH_PREVIEW", "RUNTIME_STARTED"),
            "RUNTIME_FAILED",
            "DYNAMIC_TARGET_UNREACHABLE",
        ),
        (
            (
                "STACK_READY",
                "DISPATCH_PREVIEW",
                "RUNTIME_STARTED",
                "RUNTIME_READY",
            ),
            "PERCEPTION_FAILED",
            "TARGET_AMBIGUOUS",
        ),
        (
            (
                "STACK_READY",
                "DISPATCH_PREVIEW",
                "RUNTIME_STARTED",
                "RUNTIME_READY",
                "PERCEPTION_READY",
                "TARGET_SELECTED",
                "CUP_POSE_PUBLISHED",
                "RUNTIME_COMPLETED",
            ),
            "E2E_REJECTED",
            "E2E_MUJOCO_FINAL_INVALID",
        ),
    ],
)
def test_failure_events_only_terminate_their_active_stage(
    prefix: tuple[str, ...], event: str, failure_code: str
) -> None:
    state = WorkflowState("yolo_seg")
    _advance(state, *prefix)

    assert state.accept(_workflow_event(event, failure_code=failure_code)) == "FAIL"
    with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
        state.accept(_workflow_event(event, failure_code=failure_code))


@pytest.mark.parametrize(
    ("prefix", "event", "failure_code"),
    [
        (("STACK_READY",), "RUNTIME_FAILED", "RUNTIME_FAILED"),
        (("STACK_READY",), "PERCEPTION_FAILED", "TARGET_NOT_FOUND"),
        (("STACK_READY",), "E2E_REJECTED", "E2E_EVIDENCE_REJECTED"),
        (
            ("STACK_READY", "DISPATCH_PREVIEW", "RUNTIME_STARTED"),
            "PLANNER_FAILED",
            "PLANNER_CHAIN_FAILED",
        ),
    ],
)
def test_failure_event_from_the_wrong_stage_is_rejected(
    prefix: tuple[str, ...], event: str, failure_code: str
) -> None:
    state = WorkflowState("yolo_seg")
    _advance(state, *prefix)
    with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
        state.accept(_workflow_event(event, failure_code=failure_code))


@pytest.mark.parametrize(
    ("started_payload", "ready_payload"),
    [
        (
            {"request_id": "other", "session_id": "s1", "reset_epoch": 0},
            None,
        ),
        (
            {"request_id": "r1", "session_id": "s1", "reset_epoch": 0},
            {"request_id": "r1", "session_id": "s2", "reset_epoch": 0},
        ),
        (
            {"request_id": "r1", "session_id": "s1", "reset_epoch": 0},
            {"request_id": "r1", "session_id": "s1", "reset_epoch": 1},
        ),
    ],
)
def test_state_rejects_cross_stage_identity_mismatch(
    started_payload: dict[str, object], ready_payload: dict[str, object] | None
) -> None:
    state = WorkflowState("yolo_seg")
    state.accept(_workflow_event("STACK_READY"))
    state.accept(_workflow_event("DISPATCH_PREVIEW", payload={"request_id": "r1"}))

    if ready_payload is None:
        with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
            state.accept(_workflow_event("RUNTIME_STARTED", payload=started_payload))
        return

    state.accept(_workflow_event("RUNTIME_STARTED", payload=started_payload))
    with pytest.raises(WorkflowProtocolError, match="EVENT_PROTOCOL_INVALID"):
        state.accept(_workflow_event("RUNTIME_READY", payload=ready_payload))
