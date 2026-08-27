"""PID-bound macOS MuJoCo viewer screenshot capture."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


class WindowBackend(Protocol):
    def list_windows(self, owner_pid: int) -> list[dict[str, object]]: ...


@dataclass(frozen=True, slots=True)
class ViewerCaptureResult:
    path: Path
    window_id: int
    window_title: str
    owner_pid: int
    captured_at: float


class SwiftWindowBackend:
    def __init__(self, helper: Path) -> None:
        self._helper = helper

    def list_windows(self, owner_pid: int) -> list[dict[str, object]]:
        completed = subprocess.run(
            ["/usr/bin/swift", str(self._helper), str(owner_pid)],
            check=True,
            capture_output=True,
            text=True,
        )
        document = json.loads(completed.stdout)
        if not isinstance(document, list):
            raise RuntimeError("window helper returned a non-list document")
        return document


def _screencapture(window_id: int, output: Path) -> None:
    subprocess.run(
        ["/usr/sbin/screencapture", "-x", "-l", str(window_id), str(output)],
        check=True,
    )


class MacViewerCapture:
    def __init__(
        self,
        owner_pid: int,
        windows: WindowBackend,
        screencapture: Callable[[int, Path], None] = _screencapture,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if owner_pid <= 0:
            raise ValueError("MuJoCo owner PID must be positive")
        self._owner_pid = owner_pid
        self._windows = windows
        self._screencapture = screencapture
        self._clock = clock

    @classmethod
    def from_package(cls, owner_pid: int, package_share: Path):
        return cls(
            owner_pid,
            SwiftWindowBackend(package_share / "assets/macos/list_windows.swift"),
        )

    def capture(
        self,
        output: Path,
        *,
        terminal_timestamp: float | None = None,
    ) -> ViewerCaptureResult:
        if not output.is_absolute():
            raise ValueError("viewer screenshot path must be absolute")
        candidates = [
            window
            for window in self._windows.list_windows(self._owner_pid)
            if int(window.get("owner_pid", self._owner_pid)) == self._owner_pid
            and bool(window.get("onscreen", True))
            and "mujoco" in str(window.get("title", "")).lower()
        ]
        if len(candidates) != 1:
            raise RuntimeError("expected exactly one on-screen MuJoCo window for owner PID")
        window = candidates[0]
        window_id = int(window["window_id"])
        output.parent.mkdir(parents=True, exist_ok=True)
        self._screencapture(window_id, output)
        if not output.is_file() or not output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("MuJoCo window capture did not produce a PNG")
        captured_at = output.stat().st_mtime
        if terminal_timestamp is not None and captured_at < terminal_timestamp:
            raise RuntimeError("MuJoCo screenshot predates point terminal event")
        return ViewerCaptureResult(
            output,
            window_id,
            str(window.get("title", "")),
            self._owner_pid,
            max(captured_at, self._clock()),
        )
