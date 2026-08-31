"""Final profiling artifact assembly."""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from so101_demo.runtime.task_artifacts import atomic_json

from .model import ProfilingMode


@dataclass(frozen=True, slots=True)
class FinalizationResult:
    """Summary of one profiling finalization pass."""

    complete: bool
    session_id: str | None
    span_count: int


@dataclass(frozen=True, slots=True)
class _Stream:
    path: Path
    events: tuple[dict[str, Any], ...]
    malformed: tuple[dict[str, object], ...]


def finalize_profiling(
    profiling_root: Path,
    *,
    mode: ProfilingMode,
    backend: dict[str, object] | None = None,
) -> FinalizationResult:
    """Merge process streams into atomic summary, trace, and manifest files."""

    streams = [_load_stream(path) for path in sorted((profiling_root / "processes").glob("*.jsonl"))]
    session_id = _select_session_id(streams)
    included: list[_Stream] = []
    mismatched: list[str] = []
    for stream in streams:
        session_ids = {
            event.get("session_id")
            for event in stream.events
            if isinstance(event.get("session_id"), str)
        }
        if session_id is not None and session_ids and session_ids != {session_id}:
            mismatched.append(stream.path.name)
            continue
        included.append(stream)

    spans, incomplete_processes = _complete_spans(included)
    malformed = [entry for stream in streams for entry in stream.malformed]
    complete = not incomplete_processes and not malformed and not mismatched
    summary = _summary_document(
        session_id=session_id,
        mode=mode,
        complete=complete,
        streams=included,
        spans=spans,
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
        "backend": backend or {"status": "disabled", "name": None},
    }
    atomic_json(profiling_root / "manifest.json", manifest)
    return FinalizationResult(complete, session_id, len(spans))


def _load_stream(path: Path) -> _Stream:
    events: list[dict[str, Any]] = []
    malformed: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise TypeError("profiling event must be an object")
            except (json.JSONDecodeError, TypeError) as error:
                malformed.append(
                    {
                        "file": path.name,
                        "line": line_number,
                        "error": type(error).__name__,
                    }
                )
                continue
            events.append(event)
    return _Stream(path, tuple(events), tuple(malformed))


def _select_session_id(streams: list[_Stream]) -> str | None:
    for stream in streams:
        for event in stream.events:
            session_id = event.get("session_id")
            if event.get("event_type") == "process_anchor" and isinstance(session_id, str):
                return session_id
    return None


def _complete_spans(
    streams: list[_Stream],
) -> tuple[list[dict[str, object]], list[str]]:
    spans: list[dict[str, object]] = []
    incomplete: list[str] = []
    for stream in streams:
        starts: dict[str, dict[str, Any]] = {}
        completed: set[str] = set()
        closed = False
        role = stream.path.name.removesuffix(".events.jsonl")
        for event in stream.events:
            event_type = event.get("event_type")
            span_id = event.get("span_id")
            if event_type == "process_anchor" and isinstance(event.get("process_role"), str):
                role = event["process_role"]
            elif event_type == "span_start" and isinstance(span_id, str):
                starts[span_id] = event
            elif event_type == "span_complete" and isinstance(span_id, str):
                start = starts.get(span_id)
                if start is None:
                    continue
                completed.add(span_id)
                attributes = dict(start.get("attributes") or {})
                attributes.update(event.get("attributes") or {})
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
        if not closed or set(starts) != completed:
            incomplete.append(role)
    spans.sort(
        key=lambda span: (
            int(span.get("wall_start_ns") or 0),
            str(span.get("process_role") or ""),
            int(span.get("sequence") or 0),
        )
    )
    return spans, sorted(set(incomplete))


def _summary_document(
    *,
    session_id: str | None,
    mode: ProfilingMode,
    complete: bool,
    streams: list[_Stream],
    spans: list[dict[str, object]],
) -> dict[str, object]:
    anchors = [
        event
        for stream in streams
        for event in stream.events
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
            "p50_ns": statistics.median(ordered),
        }
        if len(ordered) >= 20:
            document["p95_ns"] = ordered[max(0, int(0.95 * len(ordered) + 0.9999) - 1)]
        aggregates[name] = document
    return aggregates


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
