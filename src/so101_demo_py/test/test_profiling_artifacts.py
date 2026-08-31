import json
from pathlib import Path

import pytest

from so101_demo.profiling.artifacts import finalize_profiling
from so101_demo.profiling.model import ProfilingMode


def _write_stream(path: Path, events: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )


def _events(
    *,
    role: str,
    pid: int,
    span_id: str,
    start_wall_ns: int,
    duration_ns: int,
) -> list[dict[str, object]]:
    common = {
        "schema_version": 1,
        "session_id": "session-1",
        "request_id": "request-1",
        "process_role": role,
        "pid": pid,
        "thread_id": 7,
    }
    return [
        common
        | {
            "event_type": "process_anchor",
            "sequence": 0,
            "monotonic_ns": 100,
            "wall_time_ns": start_wall_ns - 10,
            "source_commit": "abc123",
            "installed_prefix": "/candidate/install",
        },
        common
        | {
            "event_type": "span_start",
            "sequence": 1,
            "span_id": span_id,
            "name": "runtime.state.PLAN",
            "monotonic_ns": 110,
            "wall_time_ns": start_wall_ns,
            "attributes": {"state": "PLAN"},
        },
        common
        | {
            "event_type": "span_complete",
            "sequence": 2,
            "span_id": span_id,
            "name": "runtime.state.PLAN",
            "monotonic_ns": 110 + duration_ns,
            "wall_time_ns": start_wall_ns + duration_ns,
            "duration_ns": duration_ns,
            "outcome": "ok",
            "attributes": {"status": "SUCCEEDED"},
        },
        common
        | {
            "event_type": "process_close",
            "sequence": 3,
            "monotonic_ns": 120 + duration_ns,
            "wall_time_ns": start_wall_ns + duration_ns + 10,
        },
    ]


def test_finalizer_merges_processes_into_summary_manifest_and_trace(
    tmp_path: Path,
) -> None:
    profiling_root = tmp_path / "profiling"
    _write_stream(
        profiling_root / "processes" / "text-agent.events.jsonl",
        _events(
            role="text-agent",
            pid=41,
            span_id="span-a",
            start_wall_ns=1_000,
            duration_ns=100,
        ),
    )
    _write_stream(
        profiling_root / "processes" / "dynamic-runtime.events.jsonl",
        _events(
            role="dynamic-runtime",
            pid=41,
            span_id="span-b",
            start_wall_ns=2_000,
            duration_ns=200,
        ),
    )

    result = finalize_profiling(profiling_root, mode=ProfilingMode.TRACE)
    summary = json.loads((profiling_root / "summary.json").read_text())
    trace = json.loads((profiling_root / "trace.json").read_text())
    manifest = json.loads((profiling_root / "manifest.json").read_text())

    assert result.complete is True
    assert summary["schema_version"] == 1
    assert summary["session_id"] == "session-1"
    assert [span["process_role"] for span in summary["spans"]] == [
        "text-agent",
        "dynamic-runtime",
    ]
    assert summary["aggregates"]["runtime.state.PLAN"] == {
        "count": 2,
        "total_ns": 300,
        "min_ns": 100,
        "max_ns": 200,
        "mean_ns": 150,
        "p50_ns": 100,
    }
    assert [event["ph"] for event in trace["traceEvents"]].count("X") == 2
    assert manifest["artifacts"] == {
        "summary": "summary.json",
        "trace": "trace.json",
    }
    assert manifest["malformed_events"] == []


def test_finalizer_reports_malformed_mismatched_and_interrupted_streams(
    tmp_path: Path,
) -> None:
    profiling_root = tmp_path / "profiling"
    events = _events(
        role="launch",
        pid=40,
        span_id="span-a",
        start_wall_ns=1_000,
        duration_ns=100,
    )
    events.pop()
    _write_stream(profiling_root / "processes" / "launch.events.jsonl", events)
    other_session = _events(
        role="perception",
        pid=42,
        span_id="span-b",
        start_wall_ns=2_000,
        duration_ns=200,
    )
    for event in other_session:
        event["session_id"] = "session-2"
    _write_stream(
        profiling_root / "processes" / "perception.events.jsonl",
        other_session,
    )
    with (profiling_root / "processes" / "launch.events.jsonl").open("a") as stream:
        stream.write("{broken json\n")

    result = finalize_profiling(profiling_root, mode=ProfilingMode.SUMMARY)
    manifest = json.loads((profiling_root / "manifest.json").read_text())
    summary = json.loads((profiling_root / "summary.json").read_text())

    assert result.complete is False
    assert manifest["incomplete_processes"] == ["launch"]
    assert manifest["mismatched_sessions"] == ["perception.events.jsonl"]
    assert manifest["malformed_events"] == [
        {"file": "launch.events.jsonl", "line": 4, "error": "JSONDecodeError"}
    ]
    assert len(summary["spans"]) == 1
    assert not (profiling_root / "trace.json").exists()


def test_finalizer_lists_structurally_malformed_events_without_raising(
    tmp_path: Path,
) -> None:
    profiling_root = tmp_path / "profiling"
    events = _events(
        role="launch",
        pid=40,
        span_id="span-a",
        start_wall_ns=1_000,
        duration_ns=100,
    )
    events[1]["attributes"] = 42
    _write_stream(profiling_root / "processes/launch.events.jsonl", events)

    result = finalize_profiling(profiling_root, mode=ProfilingMode.SUMMARY)
    manifest = json.loads((profiling_root / "manifest.json").read_text())

    assert result.complete is False
    assert manifest["malformed_events"] == [
        {
            "file": "launch.events.jsonl",
            "line": 2,
            "error": "EventSchemaError",
        }
    ]


@pytest.mark.parametrize(
    "events",
    [
        [],
        [
            {
                "schema_version": 1,
                "event_type": "process_close",
                "session_id": "session-1",
                "request_id": None,
                "process_role": "launch",
                "pid": 40,
                "thread_id": 7,
                "sequence": 0,
                "monotonic_ns": 100,
                "wall_time_ns": 1_000,
            }
        ],
        _events(
            role="launch",
            pid=40,
            span_id="span-a",
            start_wall_ns=1_000,
            duration_ns=100,
        )[1:],
        [
            _events(
                role="launch",
                pid=40,
                span_id="span-a",
                start_wall_ns=1_000,
                duration_ns=100,
            )[0],
            _events(
                role="launch",
                pid=40,
                span_id="span-a",
                start_wall_ns=1_000,
                duration_ns=100,
            )[2],
            _events(
                role="launch",
                pid=40,
                span_id="span-a",
                start_wall_ns=1_000,
                duration_ns=100,
            )[3],
        ],
        [
            _events(
                role="launch",
                pid=40,
                span_id="span-a",
                start_wall_ns=1_000,
                duration_ns=100,
            )[0],
            _events(
                role="launch",
                pid=40,
                span_id="span-a",
                start_wall_ns=1_000,
                duration_ns=100,
            )[0],
            _events(
                role="launch",
                pid=40,
                span_id="span-a",
                start_wall_ns=1_000,
                duration_ns=100,
            )[3],
        ],
    ],
    ids=["empty-stream", "close-only", "missing-anchor", "orphan-complete", "duplicate-anchor"],
)
def test_finalizer_marks_invalid_process_lifecycles_incomplete(
    tmp_path: Path,
    events: list[dict[str, object]],
) -> None:
    profiling_root = tmp_path / "profiling"
    _write_stream(profiling_root / "processes/launch.events.jsonl", events)

    result = finalize_profiling(profiling_root, mode=ProfilingMode.SUMMARY)

    assert result.complete is False


def test_finalizer_marks_a_session_without_streams_incomplete(tmp_path: Path) -> None:
    result = finalize_profiling(
        tmp_path / "profiling",
        mode=ProfilingMode.SUMMARY,
        expected_session_id="session-1",
    )

    assert result.complete is False
    assert result.session_id == "session-1"


def test_finalizer_uses_expected_session_for_cross_process_correlation(
    tmp_path: Path,
) -> None:
    profiling_root = tmp_path / "profiling"
    _write_stream(
        profiling_root / "processes/a-stale.events.jsonl",
        _events(
            role="stale",
            pid=41,
            span_id="span-stale",
            start_wall_ns=1_000,
            duration_ns=100,
        ),
    )
    stale_path = profiling_root / "processes/a-stale.events.jsonl"
    stale_events = [json.loads(line) for line in stale_path.read_text().splitlines()]
    for event in stale_events:
        event["session_id"] = "session-stale"
    _write_stream(stale_path, stale_events)
    _write_stream(
        profiling_root / "processes/z-current.events.jsonl",
        _events(
            role="current",
            pid=42,
            span_id="span-current",
            start_wall_ns=2_000,
            duration_ns=200,
        ),
    )

    result = finalize_profiling(
        profiling_root,
        mode=ProfilingMode.SUMMARY,
        expected_session_id="session-1",
    )
    summary = json.loads((profiling_root / "summary.json").read_text())
    manifest = json.loads((profiling_root / "manifest.json").read_text())

    assert result.session_id == "session-1"
    assert [span["process_role"] for span in summary["spans"]] == ["current"]
    assert manifest["mismatched_sessions"] == ["a-stale.events.jsonl"]


def test_finalizer_includes_backend_status_in_summary(tmp_path: Path) -> None:
    profiling_root = tmp_path / "profiling"
    _write_stream(
        profiling_root / "processes/launch.events.jsonl",
        _events(
            role="launch",
            pid=40,
            span_id="span-a",
            start_wall_ns=1_000,
            duration_ns=100,
        ),
    )
    backend = {"status": "ready", "name": "ros2_tracing"}

    finalize_profiling(
        profiling_root,
        mode=ProfilingMode.TRACE,
        backend=backend,
    )
    summary = json.loads((profiling_root / "summary.json").read_text())

    assert summary["backend"] == backend
