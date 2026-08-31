"""Final profiling artifact assembly."""

from __future__ import annotations

import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from so101_demo.runtime.task_artifacts import atomic_json

from .model import ProfilingMode, validate_attributes


@dataclass(frozen=True, slots=True)
class FinalizationResult:
    """Summary of one profiling finalization pass."""

    complete: bool
    session_id: str | None
    span_count: int


@dataclass(frozen=True, slots=True)
class _Stream:
    path: Path
    events: tuple["_Event", ...]
    malformed: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class _Event:
    line: int
    value: dict[str, Any]


class EventSchemaError(ValueError):
    """A parsed JSON object does not satisfy the event schema."""


def finalize_profiling(
    profiling_root: Path,
    *,
    mode: ProfilingMode,
    backend: dict[str, object] | None = None,
    expected_session_id: str | None = None,
) -> FinalizationResult:
    """Merge process streams into atomic summary, trace, and manifest files."""

    streams = [_load_stream(path) for path in sorted((profiling_root / "processes").glob("*.jsonl"))]
    session_id = expected_session_id or _select_session_id(streams)
    included: list[_Stream] = []
    mismatched: list[str] = []
    for stream in streams:
        session_ids = {
            record.value["session_id"]
            for record in stream.events
        }
        if session_id is not None and session_ids and session_ids != {session_id}:
            mismatched.append(stream.path.name)
            continue
        included.append(stream)

    spans, incomplete_processes, lifecycle_errors = _complete_spans(included)
    malformed = [entry for stream in streams for entry in stream.malformed]
    malformed.extend(lifecycle_errors)
    complete = bool(included) and session_id is not None
    complete = complete and not incomplete_processes and not malformed and not mismatched
    backend_document = backend or {"status": "disabled", "name": None}
    summary = _summary_document(
        session_id=session_id,
        mode=mode,
        complete=complete,
        streams=included,
        spans=spans,
        backend=backend_document,
    )
    atomic_json(profiling_root / "summary.json", summary)

    artifacts: dict[str, object] = {"summary": "summary.json"}
    if mode is ProfilingMode.TRACE:
        atomic_json(profiling_root / "trace.json", _trace_document(spans))
        artifacts["trace"] = "trace.json"

    manifest: dict[str, object] = {
        "schema_version": 1,
        "session_id": session_id,
        "mode": mode.value,
        "complete": complete,
        "artifacts": artifacts,
        "incomplete_processes": incomplete_processes,
        "mismatched_sessions": mismatched,
        "malformed_events": malformed,
        "backend": backend_document,
    }
    atomic_json(profiling_root / "manifest.json", manifest)
    return FinalizationResult(complete, session_id, len(spans))


def _load_stream(path: Path) -> _Stream:
    events: list[_Event] = []
    malformed: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise EventSchemaError("profiling event must be an object")
                _validate_event(event)
            except (json.JSONDecodeError, EventSchemaError, TypeError, ValueError) as error:
                malformed.append(
                    {
                        "file": path.name,
                        "line": line_number,
                        "error": type(error).__name__,
                    }
                )
                continue
            events.append(_Event(line_number, event))
    return _Stream(path, tuple(events), tuple(malformed))


def _validate_event(event: dict[str, Any]) -> None:
    event_type = event.get("event_type")
    if event.get("schema_version") != 1:
        raise EventSchemaError("schema_version must be 1")
    if event_type not in {
        "process_anchor",
        "span_start",
        "span_complete",
        "instant",
        "process_close",
    }:
        raise EventSchemaError("unsupported event_type")
    _require_nonempty_string(event, "session_id")
    _require_nonempty_string(event, "process_role")
    request_id = event.get("request_id")
    if request_id is not None and not isinstance(request_id, str):
        raise EventSchemaError("request_id must be a string or null")
    for field in ("pid", "thread_id", "sequence", "monotonic_ns", "wall_time_ns"):
        _require_nonnegative_integer(event, field)
    if event_type == "process_anchor":
        for field in ("source_commit", "installed_prefix"):
            value = event.get(field)
            if value is not None and not isinstance(value, str):
                raise EventSchemaError(f"{field} must be a string or null")
        return
    if event_type in {"span_start", "span_complete"}:
        _require_nonempty_string(event, "span_id")
        _require_nonempty_string(event, "name")
        attributes = event.get("attributes")
        if not isinstance(attributes, dict):
            raise EventSchemaError("attributes must be an object")
        try:
            validate_attributes(attributes)
        except (TypeError, ValueError) as error:
            raise EventSchemaError(str(error)) from error
    if event_type == "span_complete":
        _require_nonnegative_integer(event, "duration_ns")
        _require_nonempty_string(event, "outcome")
    elif event_type == "instant":
        _require_nonempty_string(event, "name")
        attributes = event.get("attributes")
        if not isinstance(attributes, dict):
            raise EventSchemaError("attributes must be an object")
        try:
            validate_attributes(attributes)
        except (TypeError, ValueError) as error:
            raise EventSchemaError(str(error)) from error


def _require_nonempty_string(event: dict[str, Any], field: str) -> None:
    value = event.get(field)
    if not isinstance(value, str) or not value:
        raise EventSchemaError(f"{field} must be a non-empty string")


def _require_nonnegative_integer(event: dict[str, Any], field: str) -> None:
    value = event.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EventSchemaError(f"{field} must be a non-negative integer")


def _select_session_id(streams: list[_Stream]) -> str | None:
    for stream in streams:
        for record in stream.events:
            event = record.value
            session_id = event.get("session_id")
            if event.get("event_type") == "process_anchor" and isinstance(session_id, str):
                return session_id
    return None


def _complete_spans(
    streams: list[_Stream],
) -> tuple[list[dict[str, object]], list[str], list[dict[str, object]]]:
    spans: list[dict[str, object]] = []
    incomplete: list[str] = []
    malformed: list[dict[str, object]] = []
    for stream in streams:
        starts: dict[str, _Event] = {}
        completed: set[str] = set()
        anchored = False
        closed = False
        role = stream.path.name.removesuffix(".events.jsonl")
        for record in stream.events:
            event = record.value
            event_type = event.get("event_type")
            span_id = event.get("span_id")
            if event_type == "process_anchor":
                role = event["process_role"]
                if anchored or closed:
                    malformed.append(_lifecycle_error(stream, record))
                    continue
                anchored = True
            elif not anchored or closed:
                malformed.append(_lifecycle_error(stream, record))
            elif event_type == "span_start":
                assert isinstance(span_id, str)
                if span_id in starts:
                    malformed.append(_lifecycle_error(stream, record))
                    continue
                starts[span_id] = record
            elif event_type == "span_complete":
                assert isinstance(span_id, str)
                start_record = starts.get(span_id)
                if start_record is None or span_id in completed:
                    if not _has_prior_schema_error(stream, record.line):
                        malformed.append(_lifecycle_error(stream, record))
                    continue
                start = start_record.value
                if start["name"] != event["name"]:
                    malformed.append(_lifecycle_error(stream, record))
                    continue
                completed.add(span_id)
                attributes = dict(start["attributes"])
                attributes.update(event["attributes"])
                spans.append(
                    {
                        "name": start.get("name"),
                        "outcome": event.get("outcome"),
                        "session_id": start.get("session_id"),
                        "request_id": start.get("request_id"),
                        "process_role": start.get("process_role"),
                        "pid": start.get("pid"),
                        "thread_id": start.get("thread_id"),
                        "sequence": start.get("sequence"),
                        "wall_start_ns": start.get("wall_time_ns"),
                        "duration_ns": event.get("duration_ns"),
                        "attributes": attributes,
                    }
                )
            elif event_type == "process_close":
                closed = True
        if not anchored or not closed or set(starts) != completed:
            incomplete.append(role)
    spans.sort(
        key=lambda span: (
            int(span.get("wall_start_ns") or 0),
            str(span.get("process_role") or ""),
            int(span.get("sequence") or 0),
        )
    )
    return spans, sorted(set(incomplete)), malformed


def _lifecycle_error(stream: _Stream, record: _Event) -> dict[str, object]:
    return {
        "file": stream.path.name,
        "line": record.line,
        "error": "EventLifecycleError",
    }


def _has_prior_schema_error(stream: _Stream, line: int) -> bool:
    return any(
        isinstance(entry.get("line"), int) and entry["line"] < line
        for entry in stream.malformed
    )


def _summary_document(
    *,
    session_id: str | None,
    mode: ProfilingMode,
    complete: bool,
    streams: list[_Stream],
    spans: list[dict[str, object]],
    backend: dict[str, object],
) -> dict[str, object]:
    anchors = [
        event
        for stream in streams
        for record in stream.events
        for event in (record.value,)
        if event.get("event_type") == "process_anchor"
    ]
    starts = [int(span["wall_start_ns"]) for span in spans]
    ends = [
        int(span["wall_start_ns"]) + int(span["duration_ns"])
        for span in spans
    ]
    return {
        "schema_version": 1,
        "session_id": session_id,
        "platform": sys.platform,
        "mode": mode.value,
        "complete": complete,
        "backend": backend,
        "total_duration_ns": max(ends) - min(starts) if starts else 0,
        "provenance": [
            {
                "process_role": anchor.get("process_role"),
                "pid": anchor.get("pid"),
                "source_commit": anchor.get("source_commit"),
                "installed_prefix": anchor.get("installed_prefix"),
            }
            for anchor in anchors
        ],
        "spans": spans,
        "aggregates": _aggregates(spans),
    }


def _aggregates(spans: list[dict[str, object]]) -> dict[str, dict[str, int | float]]:
    grouped: dict[str, list[int]] = {}
    for span in spans:
        name = span.get("name")
        duration = span.get("duration_ns")
        if isinstance(name, str) and isinstance(duration, int):
            grouped.setdefault(name, []).append(duration)
    aggregates: dict[str, dict[str, int | float]] = {}
    for name, values in sorted(grouped.items()):
        ordered = sorted(values)
        document: dict[str, int | float] = {
            "count": len(ordered),
            "total_ns": sum(ordered),
            "min_ns": ordered[0],
            "max_ns": ordered[-1],
            "mean_ns": statistics.mean(ordered),
            "p50_ns": _nearest_rank(ordered, 0.50),
        }
        if len(ordered) >= 20:
            document["p95_ns"] = _nearest_rank(ordered, 0.95)
        aggregates[name] = document
    return aggregates


def _nearest_rank(ordered: list[int], percentile: float) -> int:
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _trace_document(spans: list[dict[str, object]]) -> dict[str, object]:
    trace_events: list[dict[str, object]] = []
    process_names: set[tuple[int, str]] = set()
    thread_names: set[tuple[int, int, str]] = set()
    for span in spans:
        pid = int(span.get("pid") or 0)
        thread_id = int(span.get("thread_id") or 0)
        role = str(span.get("process_role") or "unknown")
        process_names.add((pid, role))
        thread_names.add((pid, thread_id, role))
    for pid, role in sorted(process_names):
        trace_events.append(
            {
                "name": "process_name",
                "ph": "M",
                "pid": pid,
                "tid": 0,
                "args": {"name": role},
            }
        )
    for pid, thread_id, role in sorted(thread_names):
        trace_events.append(
            {
                "name": "thread_name",
                "ph": "M",
                "pid": pid,
                "tid": thread_id,
                "args": {"name": role},
            }
        )
    for span in spans:
        attributes = dict(span.get("attributes") or {})
        attributes["outcome"] = span.get("outcome")
        trace_events.append(
            {
                "name": span.get("name"),
                "cat": "so101.semantic",
                "ph": "X",
                "ts": int(span.get("wall_start_ns") or 0) / 1_000,
                "dur": int(span.get("duration_ns") or 0) / 1_000,
                "pid": span.get("pid"),
                "tid": span.get("thread_id"),
                "args": attributes,
            }
        )
    return {"traceEvents": trace_events, "displayTimeUnit": "ns"}
