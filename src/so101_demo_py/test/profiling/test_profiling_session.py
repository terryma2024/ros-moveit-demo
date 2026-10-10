from pathlib import Path
import json
import math
import threading

import pytest

from so101_demo.profiling.model import (
    ProfilingConfig,
    ProfilingMode,
    validate_attributes,
)
from so101_demo.profiling.session import build_profiler


def test_parse_mode_accepts_only_public_values() -> None:
    assert ProfilingMode.parse("off") is ProfilingMode.OFF
    assert ProfilingMode.parse("summary") is ProfilingMode.SUMMARY
    assert ProfilingMode.parse("trace") is ProfilingMode.TRACE

    with pytest.raises(ValueError, match="profiling"):
        ProfilingMode.parse("yes")


def test_disabled_factory_does_not_read_clocks_or_create_files(
    tmp_path: Path,
) -> None:
    def forbidden_clock() -> int:
        raise AssertionError("disabled profiling read a clock")

    config = ProfilingConfig.disabled(
        session_id="session-1",
        process_role="text-agent",
    )
    profiler = build_profiler(
        config,
        monotonic_ns=forbidden_clock,
        wall_time_ns=forbidden_clock,
    )

    assert profiler is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("value", [{"nested": 1}, [1], object()])
def test_event_attributes_reject_non_scalar_values(value: object) -> None:
    with pytest.raises(TypeError, match="scalar JSON"):
        validate_attributes({"bad": value})


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_event_attributes_reject_non_finite_floats(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        validate_attributes({"bad": value})


def test_enabled_profiler_writes_exact_span_and_instant_timing(tmp_path: Path) -> None:
    monotonic_values = iter([100, 110, 150, 175, 190])
    profiling_root = tmp_path / "profiling"
    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.TRACE,
            output_root=profiling_root,
            session_id="session-1",
            process_role="text-agent",
            request_id="request-1",
        ),
        monotonic_ns=lambda: next(monotonic_values),
        wall_time_ns=lambda: 1_000,
        pid=lambda: 42,
        thread_id=lambda: 7,
    )
    assert profiler is not None

    token = profiler.start_span("agent.plan", {"provider": "ollama"})
    profiler.finish_span(token, outcome="ok", attributes={"fallback": False})
    profiler.instant("agent.review", {"status": "approved"})
    profiler.close()
    profiler.close()

    lines = [
        json.loads(line)
        for line in (
            profiling_root / "processes" / "text-agent.events.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    assert [line["event_type"] for line in lines] == [
        "process_anchor",
        "span_start",
        "span_complete",
        "instant",
        "process_close",
    ]
    assert lines[1] | {"span_id": "ignored"} == {
        "schema_version": 1,
        "event_type": "span_start",
        "session_id": "session-1",
        "request_id": "request-1",
        "process_role": "text-agent",
        "pid": 42,
        "thread_id": 7,
        "sequence": 1,
        "span_id": "ignored",
        "name": "agent.plan",
        "monotonic_ns": 110,
        "wall_time_ns": 1_010,
        "attributes": {"provider": "ollama"},
    }
    assert lines[2]["duration_ns"] == 40
    assert lines[2]["outcome"] == "ok"
    assert lines[2]["attributes"] == {"fallback": False}
    assert lines[3]["wall_time_ns"] == 1_075
    assert lines[4]["wall_time_ns"] == 1_090


def test_sink_failure_disables_profiling_without_raising(tmp_path: Path) -> None:
    class BrokenSink:
        def write(self, value: str) -> int:
            raise OSError("disk full")

        def flush(self) -> None:
            raise AssertionError("flush follows a failed write")

        def close(self) -> None:
            pass

    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.SUMMARY,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="perception",
        ),
        monotonic_ns=lambda: 10,
        wall_time_ns=lambda: 20,
        pid=lambda: 42,
        thread_id=lambda: 7,
        sink_factory=lambda _: BrokenSink(),
    )
    assert profiler is not None

    token = profiler.start_span("perception.total")
    profiler.finish_span(token, outcome="error")
    profiler.close()

    assert profiler.disabled_by_error is True
    assert profiler.warnings == ("OSError: disk full",)


def test_non_os_sink_failure_disables_profiling_without_raising(tmp_path: Path) -> None:
    class BrokenAfterAnchorSink:
        def __init__(self) -> None:
            self.write_count = 0

        def write(self, value: str) -> int:
            self.write_count += 1
            if self.write_count > 1:
                raise ValueError("closed stream")
            return len(value)

        def flush(self) -> None:
            pass

        def close(self) -> None:
            pass

    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.SUMMARY,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="perception",
        ),
        monotonic_ns=lambda: 10,
        wall_time_ns=lambda: 20,
        pid=lambda: 42,
        thread_id=lambda: 7,
        sink_factory=lambda _: BrokenAfterAnchorSink(),
    )
    assert profiler is not None

    profiler.instant("perception.ready")

    assert profiler.disabled_by_error is True
    assert profiler.warnings == ("ValueError: closed stream",)


def test_close_waits_for_an_inflight_write_without_leaking_errors(tmp_path: Path) -> None:
    class BlockingSink:
        def __init__(self) -> None:
            self.instant_entered = threading.Event()
            self.release_instant = threading.Event()
            self.closed = threading.Event()

        def write(self, value: str) -> int:
            if '"event_type":"instant"' in value:
                self.instant_entered.set()
                assert self.release_instant.wait(timeout=2.0)
            if self.closed.is_set():
                raise ValueError("write after close")
            return len(value)

        def flush(self) -> None:
            if self.closed.is_set():
                raise ValueError("flush after close")

        def close(self) -> None:
            self.closed.set()

    sink = BlockingSink()
    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.SUMMARY,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="perception",
        ),
        monotonic_ns=lambda: 10,
        wall_time_ns=lambda: 20,
        pid=lambda: 42,
        thread_id=threading.get_ident,
        sink_factory=lambda _: sink,
    )
    assert profiler is not None
    errors: list[BaseException] = []

    def record(operation) -> None:
        try:
            operation()
        except BaseException as error:
            errors.append(error)

    writer = threading.Thread(
        target=record,
        args=(lambda: profiler.instant("perception.ready"),),
    )
    writer.start()
    assert sink.instant_entered.wait(timeout=2.0)
    closer = threading.Thread(target=record, args=(profiler.close,))
    closer.start()
    sink.closed.wait(timeout=0.1)
    sink.release_instant.set()
    writer.join(timeout=2.0)
    closer.join(timeout=2.0)

    assert not writer.is_alive()
    assert not closer.is_alive()
    assert errors == []
    assert profiler.disabled_by_error is False


def test_each_profiler_instance_owns_a_unique_stream_file(tmp_path: Path) -> None:
    config = ProfilingConfig(
        mode=ProfilingMode.SUMMARY,
        output_root=tmp_path / "profiling",
        session_id="session-1",
        process_role="perception",
    )
    first = build_profiler(config, pid=lambda: 42)
    second = build_profiler(config, pid=lambda: 42)
    assert first is not None
    assert second is not None

    first.close()
    second.close()

    streams = sorted((tmp_path / "profiling/processes").glob("*.events.jsonl"))
    assert len(streams) == 2
    assert streams[0] != streams[1]
