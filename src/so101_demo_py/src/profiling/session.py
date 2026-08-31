"""Process-local semantic profiling session."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .model import ProfilingConfig, ProfilingMode, validate_attributes


@dataclass(frozen=True, slots=True)
class SpanToken:
    """Opaque handle returned when a semantic span starts."""

    span_id: str
    name: str
    start_monotonic_ns: int
    active: bool = True


class SemanticProfiler:
    """Append-only semantic event writer owned by one process role."""

    def __init__(
        self,
        config: ProfilingConfig,
        *,
        monotonic_ns: Callable[[], int],
        wall_time_ns: Callable[[], int],
        pid: Callable[[], int],
        thread_id: Callable[[], int],
        sink_factory: Callable[[Path], TextIO],
    ) -> None:
        if config.mode is ProfilingMode.OFF:
            raise ValueError("SemanticProfiler requires enabled profiling")
        if config.output_root is None:
            raise ValueError("enabled profiling requires an output root")

        self._config = config
        self._monotonic_ns = monotonic_ns
        self._thread_id = thread_id
        self._pid = pid()
        self._anchor_monotonic_ns = monotonic_ns()
        self._anchor_wall_time_ns = wall_time_ns()
        self._sequence = 0
        self._closed = False
        self._disabled_by_error = False
        self._warnings: list[str] = []
        self._lock = threading.RLock()

        process_dir = config.output_root / "processes"
        process_dir.mkdir(parents=True, exist_ok=True)
        stream_path = process_dir / f"{config.process_role}.events.jsonl"
        try:
            self._sink: TextIO | None = sink_factory(stream_path)
        except FileExistsError:
            stream_path = process_dir / (
                f"{config.process_role}.{self._pid}.{uuid.uuid4().hex}.events.jsonl"
            )
            self._sink = sink_factory(stream_path)
        self._emit(
            {
                "schema_version": 1,
                "event_type": "process_anchor",
                "session_id": config.session_id,
                "request_id": config.request_id,
                "process_role": config.process_role,
                "pid": self._pid,
                "thread_id": thread_id(),
                "sequence": self._next_sequence(),
                "monotonic_ns": self._anchor_monotonic_ns,
                "wall_time_ns": self._anchor_wall_time_ns,
                "source_commit": config.source_commit,
                "installed_prefix": config.installed_prefix,
            }
        )

    @property
    def disabled_by_error(self) -> bool:
        return self._disabled_by_error

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings)

    @property
    def config(self) -> ProfilingConfig:
        return self._config

    def start_span(
        self,
        name: str,
        attributes: Mapping[str, object] | None = None,
    ) -> SpanToken:
        with self._lock:
            if not self._available:
                return SpanToken("", name, 0, active=False)
            now = self._monotonic_ns()
            token = SpanToken(uuid.uuid4().hex, name, now)
            self._emit(
                self._event_base("span_start", now)
                | {
                    "span_id": token.span_id,
                    "name": name,
                    "attributes": validate_attributes(attributes or {}),
                }
            )
            return token

    def finish_span(
        self,
        token: SpanToken,
        *,
        outcome: str,
        attributes: Mapping[str, object] | None = None,
    ) -> None:
        with self._lock:
            if not token.active or not self._available:
                return
            now = self._monotonic_ns()
            self._emit(
                self._event_base("span_complete", now)
                | {
                    "span_id": token.span_id,
                    "name": token.name,
                    "duration_ns": max(0, now - token.start_monotonic_ns),
                    "outcome": outcome,
                    "attributes": validate_attributes(attributes or {}),
                }
            )

    def instant(
        self,
        name: str,
        attributes: Mapping[str, object] | None = None,
    ) -> None:
        with self._lock:
            if not self._available:
                return
            now = self._monotonic_ns()
            self._emit(
                self._event_base("instant", now)
                | {
                    "name": name,
                    "attributes": validate_attributes(attributes or {}),
                }
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._available:
                now = self._monotonic_ns()
                self._emit(self._event_base("process_close", now))
            self._closed = True
            sink, self._sink = self._sink, None
            if sink is None:
                return
            try:
                sink.close()
            except Exception as error:
                self._disabled_by_error = True
                self._remember_error(error)

    @property
    def _available(self) -> bool:
        return not self._closed and not self._disabled_by_error and self._sink is not None

    def _event_base(self, event_type: str, monotonic_ns: int) -> dict[str, object]:
        return {
            "schema_version": 1,
            "event_type": event_type,
            "session_id": self._config.session_id,
            "request_id": self._config.request_id,
            "process_role": self._config.process_role,
            "pid": self._pid,
            "thread_id": self._thread_id(),
            "sequence": self._next_sequence(),
            "monotonic_ns": monotonic_ns,
            "wall_time_ns": self._anchor_wall_time_ns
            + monotonic_ns
            - self._anchor_monotonic_ns,
        }

    def _next_sequence(self) -> int:
        sequence = self._sequence
        self._sequence += 1
        return sequence

    def _emit(self, event: Mapping[str, object]) -> None:
        with self._lock:
            if not self._available:
                return
            assert self._sink is not None
            try:
                self._sink.write(
                    json.dumps(
                        event,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                    + "\n"
                )
                self._sink.flush()
            except Exception as error:
                sink, self._sink = self._sink, None
                self._disabled_by_error = True
                self._remember_error(error)
                if sink is not None:
                    try:
                        sink.close()
                    except Exception as close_error:
                        self._remember_error(close_error)

    def _remember_error(self, error: Exception) -> None:
        self._warnings.append(f"{type(error).__name__}: {error}")


def _open_text(path: Path) -> TextIO:
    return path.open("x", encoding="utf-8")


def build_profiler(
    config: ProfilingConfig,
    *,
    monotonic_ns: Callable[[], int] = time.perf_counter_ns,
    wall_time_ns: Callable[[], int] = time.time_ns,
    pid: Callable[[], int] = os.getpid,
    thread_id: Callable[[], int] = threading.get_ident,
    sink_factory: Callable[[Path], TextIO] = _open_text,
) -> SemanticProfiler | None:
    """Build an enabled profiler without touching clocks on the off path."""

    if config.mode is ProfilingMode.OFF:
        return None
    return SemanticProfiler(
        config,
        monotonic_ns=monotonic_ns,
        wall_time_ns=wall_time_ns,
        pid=pid,
        thread_id=thread_id,
        sink_factory=sink_factory,
    )
