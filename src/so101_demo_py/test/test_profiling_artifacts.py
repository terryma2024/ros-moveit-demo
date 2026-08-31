import json
from pathlib import Path

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
        "p50_ns": 150,
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
